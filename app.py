from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
import requests
import json
from mistralai import Mistral
import wikipedia
import os
import re
import random
import time
from datetime import datetime, timedelta
import difflib
from functools import wraps
import hashlib
import threading

app = Flask(__name__)

class WikipediaMistralSummarizer:
    def __init__(self):
        """
        Initialise le résumeur avec rotation automatique des clés API
        """
        # 🔑 Clés API Mistral avec rotation automatique
        self.api_keys = [
            "FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX",
            "9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF",
            "cvkQHVcomFFEW47G044x2p4DTyk5BIc7"
        ]
        self.current_key_index = 0
        self.mistral_client = None
        self.init_client()
        
        # 💾 Cache des résumés (en mémoire)
        self.cache = {}
        self.cache_max_size = 100
        
        # 📊 Statistiques
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'wikipedia_success': 0,
            'mistral_only': 0
        }
        
        # 🌍 Configuration Wikipedia
        wikipedia.set_lang("fr")
        wikipedia.set_rate_limiting(True)
    
    def init_client(self):
        """Initialise le client Mistral avec une clé aléatoire"""
        try:
            key = random.choice(self.api_keys)
            self.mistral_client = Mistral(api_key=key)
            self.current_key = key
            print(f"✅ Client Mistral initialisé avec la clé: ...{key[-8:]}")
        except Exception as e:
            print(f"❌ Erreur initialisation client: {e}")
    
    def retry_with_different_key(self, func, *args, **kwargs):
        """Retry une fonction avec différentes clés API en cas d'échec"""
        for attempt in range(len(self.api_keys)):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"⚠️ Tentative {attempt + 1} échouée: {e}")
                if attempt < len(self.api_keys) - 1:
                    # Changer de clé pour le prochain essai
                    self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
                    self.mistral_client = Mistral(api_key=self.api_keys[self.current_key_index])
                    self.current_key = self.api_keys[self.current_key_index]
                    print(f"🔄 Changement vers la clé: ...{self.current_key[-8:]}")
                    time.sleep(1)  # Petit délai avant retry
                else:
                    raise e
    
    def get_cache_key(self, theme, length_mode):
        """Génère une clé de cache unique"""
        return hashlib.md5(f"{theme.lower().strip()}_{length_mode}".encode()).hexdigest()
    
    def get_from_cache(self, theme, length_mode):
        """Récupère un résumé du cache s'il existe"""
        cache_key = self.get_cache_key(theme, length_mode)
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            # Vérifier que le cache n'est pas trop vieux (24h)
            if datetime.now() - cached_data['timestamp'] < timedelta(hours=24):
                self.stats['cache_hits'] += 1
                print(f"💾 Cache hit pour: {theme}")
                return cached_data['data']
            else:
                # Supprimer l'entrée expirée
                del self.cache[cache_key]
        return None
    
    def save_to_cache(self, theme, length_mode, data):
        """Sauvegarde un résumé dans le cache"""
        cache_key = self.get_cache_key(theme, length_mode)
        
        # Gérer la taille max du cache
        if len(self.cache) >= self.cache_max_size:
            # Supprimer l'entrée la plus ancienne
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        self.cache[cache_key] = {
            'data': data,
            'timestamp': datetime.now()
        }
        print(f"💾 Résumé mis en cache pour: {theme}")
    
    def smart_wikipedia_search(self, theme):
        """
        Recherche intelligente sur Wikipedia avec plusieurs stratégies
        """
        print(f"🔍 Recherche intelligente pour: '{theme}'")
        
        # Stratégie 1: Recherche directe
        try:
            page = wikipedia.page(theme)
            print(f"✅ Trouvé directement: {page.title}")
            return {
                'title': page.title,
                'content': page.content,
                'url': page.url,
                'method': 'direct'
            }
        except wikipedia.exceptions.DisambiguationError as e:
            # Prendre la première option si ambiguïté
            try:
                page = wikipedia.page(e.options[0])
                print(f"✅ Trouvé via désambiguïsation: {page.title}")
                return {
                    'title': page.title,
                    'content': page.content,
                    'url': page.url,
                    'method': 'disambiguation'
                }
            except:
                pass
        except wikipedia.exceptions.PageError:
            pass
        except Exception as e:
            print(f"⚠️ Erreur recherche directe: {e}")
        
        # Stratégie 2: Recherche par suggestions
        try:
            suggestions = wikipedia.search(theme, results=10)
            print(f"📋 Suggestions trouvées: {suggestions[:3]}...")
            
            if suggestions:
                # Essayer les suggestions par ordre de pertinence
                for suggestion in suggestions[:3]:
                    try:
                        # Calculer similarité avec le thème original
                        similarity = difflib.SequenceMatcher(None, 
                                                           theme.lower(), 
                                                           suggestion.lower()).ratio()
                        
                        if similarity > 0.3:  # Seuil de similarité
                            page = wikipedia.page(suggestion)
                            print(f"✅ Trouvé via suggestion '{suggestion}' (similarité: {similarity:.2f})")
                            return {
                                'title': page.title,
                                'content': page.content,
                                'url': page.url,
                                'method': f'suggestion ({similarity:.2f})'
                            }
                    except:
                        continue
        except Exception as e:
            print(f"⚠️ Erreur recherche par suggestions: {e}")
        
        # Stratégie 3: Recherche par mots-clés
        try:
            # Extraire les mots principaux (sans mots vides)
            stop_words = ['le', 'la', 'les', 'de', 'du', 'des', 'et', 'ou', 'un', 'une']
            keywords = [word for word in theme.lower().split() 
                       if word not in stop_words and len(word) > 2]
            
            if keywords:
                for keyword in keywords:
                    try:
                        suggestions = wikipedia.search(keyword, results=5)
                        if suggestions:
                            page = wikipedia.page(suggestions[0])
                            print(f"✅ Trouvé via mot-clé '{keyword}': {page.title}")
                            return {
                                'title': page.title,
                                'content': page.content,
                                'url': page.url,
                                'method': f'keyword ({keyword})'
                            }
                    except:
                        continue
        except Exception as e:
            print(f"⚠️ Erreur recherche par mots-clés: {e}")
        
        print(f"❌ Aucune page Wikipedia trouvée pour: '{theme}'")
        return None
    
    def markdown_to_html(self, text):
        """
        Convertit le Markdown simple en HTML de manière plus robuste
        """
        if not text:
            return ""
        
        text = text.strip()
        
        # Remplacer **texte** par <strong>texte</strong> (gras)
        text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
        
        # Remplacer *texte* par <em>texte</em> (italique)
        text = re.sub(r'\*([^*]+?)\*', r'<em>\1</em>', text)
        
        # Gérer les titres avec #
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        
        # Remplacer les listes à puces
        text = re.sub(r'^[-*] (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        
        # Encapsuler les listes dans <ul></ul>
        if '<li>' in text:
            lines = text.split('\n')
            result_lines = []
            in_list = False
            
            for line in lines:
                if '<li>' in line:
                    if not in_list:
                        result_lines.append('<ul>')
                        in_list = True
                    result_lines.append(line)
                else:
                    if in_list:
                        result_lines.append('</ul>')
                        in_list = False
                    result_lines.append(line)
            
            if in_list:
                result_lines.append('</ul>')
                
            text = '\n'.join(result_lines)
        
        # Convertir les paragraphes
        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<') and not para.endswith('>'):
                para = f'<p>{para}</p>'
            if para:
                formatted_paragraphs.append(para)
        
        result = '\n'.join(formatted_paragraphs)
        result = re.sub(r'<p>\s*</p>', '', result)
        
        return result
    
    def get_length_config(self, length_mode):
        """Retourne la configuration selon la longueur demandée"""
        configs = {
            'court': {
                'words': '150-200',
                'description': 'résumé concis'
            },
            'moyen': {
                'words': '250-350',
                'description': 'résumé détaillé'
            },
            'long': {
                'words': '400-500',
                'description': 'analyse complète'
            }
        }
        return configs.get(length_mode, configs['moyen'])
    
    def summarize_with_mistral(self, title, content, length_mode='moyen'):
        """
        Utilise Mistral AI pour résumer le contenu Wikipedia
        """
        def _summarize():
            try:
                # Limiter le contenu si trop long
                max_chars = 10000
                if len(content) > max_chars:
                    content_limited = content[:max_chars] + "..."
                else:
                    content_limited = content
                
                length_config = self.get_length_config(length_mode)
                
                prompt = f"""
                Voici le contenu d'une page Wikipedia sur le sujet "{title}".
                
                Contenu:
                {content_limited}
                
                Consigne: Fais un {length_config['description']} de cette page Wikipedia en français. 
                Le résumé doit faire environ {length_config['words']} mots.
                Il doit être informatif, bien structuré et captivant.
                Mets en avant les points les plus importants et les plus intéressants.
                
                IMPORTANT: Écris en texte brut simple et lisible, sans formatage Markdown.
                Structure ton texte en paragraphes clairs.
                """
                
                messages = [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
                
                response = self.mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=800 if length_mode == 'long' else 600
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                print(f"❌ Erreur lors du résumé avec Mistral: {e}")
                raise e
        
        # Utiliser le système de retry avec différentes clés
        return self.retry_with_different_key(_summarize)
    
    def answer_with_mistral_only(self, theme, length_mode='moyen'):
        """
        Utilise Mistral AI pour répondre directement sur un thème sans Wikipedia
        """
        def _answer():
            try:
                length_config = self.get_length_config(length_mode)
                
                prompt = f"""
                L'utilisateur me demande des informations sur le thème: "{theme}"
                
                Aucune page Wikipedia n'a été trouvée pour ce sujet.
                
                Consigne: Fournis une réponse complète et informative sur ce thème en français.
                Explique ce que c'est, donne des détails importants, du contexte historique si pertinent,
                et tout ce qui pourrait être utile à connaître sur ce sujet.
                
                Le texte doit faire environ {length_config['words']} mots et être un {length_config['description']}.
                
                IMPORTANT: Écris en texte brut simple et lisible, sans formatage Markdown.
                Structure ton texte en paragraphes clairs et engageants.
                """
                
                messages = [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
                
                response = self.mistral_client.chat.complete(
                    model="mistral-large-latest",
                    messages=messages,
                    temperature=0.4,
                    max_tokens=800 if length_mode == 'long' else 600
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                print(f"❌ Erreur lors de la réponse avec Mistral: {e}")
                raise e
        
        # Utiliser le système de retry avec différentes clés
        return self.retry_with_different_key(_answer)

    def process_theme(self, theme, length_mode='moyen'):
        """
        Traite un thème complet avec toutes les améliorations
        """
        self.stats['requests'] += 1
        start_time = time.time()
        
        # Validation du thème
        if not theme or len(theme.strip()) < 2:
            return {
                'success': False,
                'error': 'Le thème doit contenir au moins 2 caractères'
            }
        
        theme = theme.strip()
        
        # Vérifier le cache d'abord
        cached_result = self.get_from_cache(theme, length_mode)
        if cached_result:
            return cached_result
        
        # Recherche Wikipedia intelligente
        wiki_data = self.smart_wikipedia_search(theme)
        
        if not wiki_data:
            # Mistral répond sans Wikipedia
            print(f"📝 Génération directe avec Mistral pour: {theme}")
            mistral_response = self.answer_with_mistral_only(theme, length_mode)
            
            if not mistral_response:
                return {
                    'success': False,
                    'error': 'Erreur lors de la génération de la réponse'
                }
            
            formatted_response = self.markdown_to_html(mistral_response)
            
            result = {
                'success': True,
                'title': f"Informations sur: {theme}",
                'summary': formatted_response,
                'url': None,
                'source': 'mistral_only',
                'method': 'direct_ai',
                'processing_time': round(time.time() - start_time, 2),
                'length_mode': length_mode,
                'cached': False
            }
            
            self.stats['mistral_only'] += 1
            
        else:
            # Résumer avec Mistral
            print(f"📖 Résumé Wikipedia + Mistral pour: {wiki_data['title']}")
            summary = self.summarize_with_mistral(wiki_data['title'], wiki_data['content'], length_mode)
            
            if not summary:
                return {
                    'success': False,
                    'error': 'Erreur lors de la génération du résumé'
                }
            
            formatted_summary = self.markdown_to_html(summary)
            
            result = {
                'success': True,
                'title': wiki_data['title'],
                'summary': formatted_summary,
                'url': wiki_data['url'],
                'source': 'wikipedia',
                'method': wiki_data['method'],
                'processing_time': round(time.time() - start_time, 2),
                'length_mode': length_mode,
                'cached': False
            }
            
            self.stats['wikipedia_success'] += 1
        
        # Sauvegarder en cache
        self.save_to_cache(theme, length_mode, result)
        
        return result

# Instance globale du résumeur
summarizer = WikipediaMistralSummarizer()

# Historique des recherches (en mémoire par session)
search_history = []
MAX_HISTORY = 50

# Thèmes populaires suggérés
POPULAR_THEMES = [
    "Intelligence artificielle", "Réchauffement climatique", "Napoléon Bonaparte",
    "Révolution française", "Albert Einstein", "Marie Curie", "Paris",
    "Photosynthèse", "ADN", "Guerre mondiale", "Renaissance", "Bitcoin",
    "Quantum computing", "Biodiversité", "Système solaire", "Pyramides d'Égypte"
]

@app.route('/')
def index():
    """Page d'accueil avec l'interface améliorée"""
    return '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wikipedia Summarizer Pro - Mistral AI</title>
    <style>
        :root {
            /* Mode clair */
            --bg-primary: #e6e7ee;
            --bg-secondary: #d1d2d9;
            --bg-tertiary: #fbfcff;
            --text-primary: #5a5c69;
            --text-secondary: #8b8d97;
            --accent: #667eea;
            --accent-secondary: #764ba2;
            --shadow-light: #bebfc5;
            --shadow-dark: #ffffff;
            --border-color: #d1d2d9;
        }

        [data-theme="dark"] {
            /* Mode sombre */
            --bg-primary: #2d3748;
            --bg-secondary: #1a202c;
            --bg-tertiary: #4a5568;
            --text-primary: #f7fafc;
            --text-secondary: #e2e8f0;
            --accent: #667eea;
            --accent-secondary: #764ba2;
            --shadow-light: #1a202c;
            --shadow-dark: #4a5568;
            --border-color: #4a5568;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }

        .container {
            background: var(--bg-primary);
            border-radius: 30px;
            padding: 40px;
            width: 100%;
            max-width: 900px;
            box-shadow: 
                20px 20px 60px var(--shadow-light),
                -20px -20px 60px var(--shadow-dark);
            position: relative;
            overflow: hidden;
        }

        .container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--accent), var(--accent-secondary), #f093fb);
            border-radius: 30px 30px 0 0;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            position: relative;
        }

        .theme-toggle {
            position: absolute;
            top: 0;
            right: 0;
            background: var(--bg-primary);
            border: none;
            border-radius: 15px;
            padding: 10px;
            cursor: pointer;
            box-shadow: 
                6px 6px 12px var(--shadow-light),
                -6px -6px 12px var(--shadow-dark);
            transition: all 0.2s ease;
        }

        .theme-toggle:hover {
            transform: translateY(-2px);
        }

        .title {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 1.1rem;
            font-weight: 400;
        }

        .stats {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }

        .stat-item {
            background: var(--bg-primary);
            padding: 10px 20px;
            border-radius: 15px;
            box-shadow: 
                inset 4px 4px 8px var(--shadow-light),
                inset -4px -4px 8px var(--shadow-dark);
            font-size: 0.9rem;
            color: var(--text-secondary);
        }

        .form-section {
            background: var(--bg-primary);
            border-radius: 25px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 
                inset 8px 8px 16px var(--shadow-light),
                inset -8px -8px 16px var(--shadow-dark);
        }

        .form-group {
            margin-bottom: 25px;
        }

        .label {
            display: block;
            color: var(--text-primary);
            font-weight: 600;
            margin-bottom: 12px;
            font-size: 1rem;
        }

        .input {
            width: 100%;
            padding: 18px 24px;
            background: var(--bg-primary);
            border: none;
            border-radius: 20px;
            font-size: 1rem;
            color: var(--text-primary);
            box-shadow: 
                inset 8px 8px 16px var(--shadow-light),
                inset -8px -8px 16px var(--shadow-dark);
            transition: all 0.3s ease;
            outline: none;
        }

        .input:focus {
            box-shadow: 
                inset 12px 12px 20px var(--shadow-light),
                inset -12px -12px 20px var(--shadow-dark);
        }

        .length-selector {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .length-option {
            background: var(--bg-primary);
            border: none;
            border-radius: 15px;
            padding: 12px 20px;
            font-size: 0.9rem;
            color: var(--text-secondary);
            cursor: pointer;
            box-shadow: 
                6px 6px 12px var(--shadow-light),
                -6px -6px 12px var(--shadow-dark);
            transition: all 0.2s ease;
        }

        .length-option.active {
            background: var(--accent);
            color: white;
            box-shadow: 
                inset 4px 4px 8px rgba(0,0,0,0.3);
        }

        .suggestions {
            margin-top: 15px;
        }

        .suggestion-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .chip {
            background: var(--bg-tertiary);
            border: none;
            border-radius: 20px;
            padding: 8px 16px;
            font-size: 0.8rem;
            color: var(--text-primary);
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .chip:hover {
            background: var(--accent);
            color: white;
            transform: translateY(-2px);
        }

        .btn {
            background: var(--bg-primary);
            border: none;
            border-radius: 20px;
            padding: 18px 36px;
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
            cursor: pointer;
            box-shadow: 
                8px 8px 16px var(--shadow-light),
                -8px -8px 16px var(--shadow-dark);
            transition: all 0.2s ease;
            position: relative;
            overflow: hidden;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 
                12px 12px 20px var(--shadow-light),
                -12px -12px 20px var(--shadow-dark);
        }

        .btn:active {
            transform: translateY(0);
            box-shadow: 
                inset 4px 4px 8px var(--shadow-light),
                inset -4px -4px 8px var(--shadow-dark);
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
            color: white;
            box-shadow: 
                8px 8px 16px rgba(102, 126, 234, 0.3),
                -8px -8px 16px rgba(255, 255, 255, 0.8);
        }

        .btn-primary:hover {
            box-shadow: 
                12px 12px 20px rgba(102, 126, 234, 0.4),
                -12px -12px 20px rgba(255, 255, 255, 0.9);
        }

        .controls {
            display: flex;
            justify-content: center;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }

        .status {
            margin: 30px 0;
            padding: 25px;
            background: var(--bg-primary);
            border-radius: 20px;
            box-shadow: 
                inset 6px 6px 12px var(--shadow-light),
                inset -6px -6px 12px var(--shadow-dark);
            display: none;
        }

        .status.active {
            display: block;
            animation: slideDown 0.3s ease;
        }

        .status-steps {
            display: flex;
            justify-content: space-between;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 10px;
        }

        .step {
            flex: 1;
            min-width: 120px;
            text-align: center;
            padding: 10px;
            background: var(--bg-secondary);
            border-radius: 10px;
            font-size: 0.8rem;
            color: var(--text-secondary);
            transition: all 0.3s ease;
        }

        .step.active {
            background: var(--accent);
            color: white;
        }

        .step.completed {
            background: #2ecc71;
            color: white;
        }

        .progress-bar {
            width: 100%;
            height: 8px;
            background: var(--bg-secondary);
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 
                inset 3px 3px 6px var(--shadow-light),
                inset -3px -3px 6px var(--shadow-dark);
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
            border-radius: 10px;
            width: 0%;
            transition: width 0.3s ease;
        }

        .result {
            margin-top: 30px;
            padding: 30px;
            background: var(--bg-primary);
            border-radius: 25px;
            box-shadow: 
                inset 8px 8px 16px var(--shadow-light),
                inset -8px -8px 16px var(--shadow-dark);
            display: none;
        }

        .result.active {
            display: block;
            animation: slideUp 0.5s ease;
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 10px;
        }

        .result-title {
            color: var(--text-primary);
            font-size: 1.3rem;
            font-weight: 600;
            flex: 1;
        }

        .result-meta {
            display: flex;
            gap: 15px;
            font-size: 0.8rem;
            color: var(--text-secondary);
            align-items: center;
        }

        .result-actions {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }

        .btn-small {
            padding: 8px 16px;
            font-size: 0.8rem;
            border-radius: 15px;
        }

        .result-content {
            color: var(--text-secondary);
            line-height: 1.7;
            font-size: 1rem;
            margin-bottom: 20px;
        }

        .result-content p {
            margin-bottom: 15px;
        }

        .result-content strong {
            color: var(--text-primary);
            font-weight: 600;
        }

        .result-content em {
            font-style: italic;
            color: var(--accent);
        }

        .result-content ul {
            margin: 15px 0;
            padding-left: 25px;
        }

        .result-content li {
            margin-bottom: 8px;
            list-style-type: disc;
        }

        .result-url {
            margin-top: 20px;
            padding: 15px;
            background: rgba(102, 126, 234, 0.1);
            border-radius: 15px;
            border-left: 4px solid var(--accent);
        }

        .result-url a {
            color: var(--accent);
            text-decoration: none;
            font-weight: 500;
            word-break: break-all;
        }

        .result-url a:hover {
            text-decoration: underline;
        }

        .history-section {
            margin-top: 30px;
            padding: 25px;
            background: var(--bg-primary);
            border-radius: 20px;
            box-shadow: 
                inset 6px 6px 12px var(--shadow-light),
                inset -6px -6px 12px var(--shadow-dark);
        }

        .history-title {
            color: var(--text-primary);
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .history-list {
            max-height: 200px;
            overflow-y: auto;
        }

        .history-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            margin-bottom: 8px;
            background: var(--bg-tertiary);
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .history-item:hover {
            background: var(--accent);
            color: white;
            transform: translateX(5px);
        }

        .history-item-title {
            font-weight: 500;
            flex: 1;
        }

        .history-item-meta {
            font-size: 0.7rem;
            opacity: 0.7;
        }

        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid var(--bg-secondary);
            border-radius: 50%;
            border-top-color: var(--accent);
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 15px;
            color: white;
            font-weight: 500;
            z-index: 1000;
            transform: translateX(400px);
            transition: all 0.3s ease;
        }

        .notification.show {
            transform: translateX(0);
        }

        .notification.error {
            background: #e74c3c;
        }

        .notification.success {
            background: #2ecc71;
        }

        .notification.info {
            background: var(--accent);
        }

        .modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 2000;
        }

        .modal.active {
            display: flex;
            animation: fadeIn 0.3s ease;
        }

        .modal-content {
            background: var(--bg-primary);
            border-radius: 20px;
            padding: 30px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: var(--text-secondary);
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        @media (max-width: 768px) {
            .container {
                padding: 25px 20px;
                margin: 10px;
                border-radius: 25px;
            }

            .title {
                font-size: 2rem;
            }

            .stats {
                gap: 10px;
            }

            .stat-item {
                padding: 8px 15px;
                font-size: 0.8rem;
            }

            .controls {
                flex-direction: column;
                gap: 10px;
            }

            .suggestion-chips {
                gap: 6px;
            }

            .chip {
                font-size: 0.7rem;
                padding: 6px 12px;
            }

            .result-header {
                flex-direction: column;
                gap: 15px;
            }

            .result-actions {
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <button class="theme-toggle" onclick="toggleTheme()" title="Changer de thème">
                <span id="themeIcon">🌙</span>
            </button>
            <h1 class="title">🌟 Wikipedia Summarizer Pro</h1>
            <p class="subtitle">Résumés intelligents avec Mistral AI</p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-item">📊 <span id="totalRequests">0</span> requêtes</div>
            <div class="stat-item">💾 <span id="cacheHits">0</span> en cache</div>
            <div class="stat-item">📖 <span id="wikiSuccess">0</span> Wikipedia</div>
            <div class="stat-item">🤖 <span id="aiOnly">0</span> IA seule</div>
        </div>

        <div class="form-section">
            <form id="summarizerForm">
                <div class="form-group">
                    <label class="label" for="theme">🔍 Thème à rechercher</label>
                    <input 
                        type="text" 
                        id="theme" 
                        class="input" 
                        placeholder="Intelligence artificielle, Paris, Einstein..."
                        autocomplete="off"
                        required
                    >
                    
                    <div class="suggestions">
                        <div style="margin-bottom: 10px;">
                            <span style="color: var(--text-secondary); font-size: 0.9rem;">💡 Suggestions populaires:</span>
                        </div>
                        <div class="suggestion-chips" id="suggestionChips">
                            <!-- Les suggestions seront ajoutées dynamiquement -->
                        </div>
                    </div>
                </div>

                <div class="form-group">
                    <label class="label">📏 Longueur du résumé</label>
                    <div class="length-selector">
                        <button type="button" class="length-option" data-length="court">📝 Court (150-200 mots)</button>
                        <button type="button" class="length-option active" data-length="moyen">📄 Moyen (250-350 mots)</button>
                        <button type="button" class="length-option" data-length="long">📚 Long (400-500 mots)</button>
                    </div>
                </div>

                <div class="controls">
                    <button type="submit" class="btn btn-primary">
                        ✨ Générer le résumé
                    </button>
                    <button type="button" class="btn" onclick="clearAll()">
                        🗑️ Effacer
                    </button>
                    <button type="button" class="btn" onclick="showHistory()">
                        📚 Historique
                    </button>
                </div>
            </form>
        </div>

        <div id="status" class="status">
            <div class="status-steps">
                <div class="step" id="step1">🔍 Recherche</div>
                <div class="step" id="step2">📖 Analyse</div>
                <div class="step" id="step3">🤖 Résumé</div>
                <div class="step" id="step4">✅ Terminé</div>
            </div>
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
        </div>

        <div id="result" class="result">
            <div class="result-header">
                <div>
                    <div class="result-title" id="resultTitle">📖 Résumé généré</div>
                    <div class="result-meta">
                        <span id="resultMeta">Source: Wikipedia</span>
                        <span>•</span>
                        <span id="resultTime">2.3s</span>
                        <span>•</span>
                        <span id="resultLength">Moyen</span>
                    </div>
                </div>
                <div class="result-actions">
                    <button class="btn btn-small" onclick="exportSummary()">📤 Exporter</button>
                    <button class="btn btn-small" onclick="regenerateSummary()">🔄 Régénérer</button>
                </div>
            </div>
            <div class="result-content" id="resultContent"></div>
            <div id="resultUrl" class="result-url" style="display: none;">
                <strong>🔗 Source Wikipedia:</strong><br>
                <a href="#" target="_blank" id="wikiLink"></a>
            </div>
        </div>
    </div>

    <!-- Modal pour l'historique -->
    <div id="historyModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>📚 Historique des recherches</h3>
                <button class="modal-close" onclick="closeHistory()">&times;</button>
            </div>
            <div id="historyList" class="history-list">
                <p style="text-align: center; color: var(--text-secondary); padding: 20px;">
                    Aucune recherche dans l'historique
                </p>
            </div>
            <div style="margin-top: 20px; text-align: center;">
                <button class="btn btn-small" onclick="clearHistory()">🗑️ Vider l'historique</button>
            </div>
        </div>
    </div>

    <script>
        // Variables globales
        let isProcessing = false;
        let currentTheme = '';
        let currentLength = 'moyen';
        let searchHistory = JSON.parse(localStorage.getItem('searchHistory') || '[]');
        let stats = JSON.parse(localStorage.getItem('stats') || '{"requests": 0, "cache_hits": 0, "wikipedia_success": 0, "mistral_only": 0}');

        // Suggestions populaires
        const popularThemes = [
            "Intelligence artificielle", "Réchauffement climatique", "Napoléon Bonaparte",
            "Révolution française", "Albert Einstein", "Marie Curie", "Paris",
            "Photosynthèse", "ADN", "Bitcoin", "Système solaire", "Renaissance"
        ];

        // Elements DOM
        const form = document.getElementById('summarizerForm');
        const themeInput = document.getElementById('theme');
        const statusDiv = document.getElementById('status');
        const resultDiv = document.getElementById('result');
        const progressFill = document.getElementById('progressFill');

        // Initialisation
        document.addEventListener('DOMContentLoaded', function() {
            initializeSuggestions();
            initializeLengthSelector();
            initializeTheme();
            updateStats();
            
            // Charger les stats depuis le serveur
            loadServerStats();
        });

        // Initialiser les suggestions
        function initializeSuggestions() {
            const container = document.getElementById('suggestionChips');
            const shuffled = popularThemes.sort(() => 0.5 - Math.random()).slice(0, 8);
            
            shuffled.forEach(theme => {
                const chip = document.createElement('button');
                chip.className = 'chip';
                chip.textContent = theme;
                chip.onclick = () => {
                    themeInput.value = theme;
                    themeInput.focus();
                };
                container.appendChild(chip);
            });
        }

        // Initialiser le sélecteur de longueur
        function initializeLengthSelector() {
            const options = document.querySelectorAll('.length-option');
            options.forEach(option => {
                option.addEventListener('click', function() {
                    options.forEach(opt => opt.classList.remove('active'));
                    this.classList.add('active');
                    currentLength = this.dataset.length;
                });
            });
        }

        // Initialiser le thème
        function initializeTheme() {
            const savedTheme = localStorage.getItem('theme') || 'light';
            if (savedTheme === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
                document.getElementById('themeIcon').textContent = '☀️';
            }
        }

        // Basculer le thème
        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            document.getElementById('themeIcon').textContent = newTheme === 'dark' ? '☀️' : '🌙';
            localStorage.setItem('theme', newTheme);
        }

        // Charger les statistiques du serveur
        async function loadServerStats() {
            try {
                const response = await fetch('/api/stats');
                const serverStats = await response.json();
                updateStatsDisplay(serverStats);
            } catch (error) {
                console.log('Impossible de charger les stats du serveur');
            }
        }

        // Mettre à jour l'affichage des stats
        function updateStatsDisplay(serverStats) {
            document.getElementById('totalRequests').textContent = serverStats.requests || 0;
            document.getElementById('cacheHits').textContent = serverStats.cache_hits || 0;
            document.getElementById('wikiSuccess').textContent = serverStats.wikipedia_success || 0;
            document.getElementById('aiOnly').textContent = serverStats.mistral_only || 0;
        }

        // Gestionnaire de soumission du formulaire
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (isProcessing) return;

            const theme = themeInput.value.trim();
            if (!theme) {
                showNotification('⚠️ Veuillez entrer un thème de recherche', 'error');
                return;
            }

            currentTheme = theme;
            await processTheme(theme, currentLength);
        });

        // Traitement principal
        async function processTheme(theme, lengthMode) {
            isProcessing = true;
            showStatus();
            hideResult();

            try {
                // Étape 1: Recherche
                updateStep(1, 'active');
                updateProgress(25);
                await sleep(500);

                const response = await fetch('/api/summarize', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        theme: theme,
                        length_mode: lengthMode
                    })
                });

                // Étape 2: Analyse
                updateStep(1, 'completed');
                updateStep(2, 'active');
                updateProgress(50);
                await sleep(300);

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Erreur lors du traitement');
                }

                // Étape 3: Résumé
                updateStep(2, 'completed');
                updateStep(3, 'active');
                updateProgress(75);
                await sleep(300);

                const data = await response.json();

                // Étape 4: Terminé
                updateStep(3, 'completed');
                updateStep(4, 'active');
                updateProgress(100);
                await sleep(500);

                // Ajouter à l'historique
                addToHistory(theme, data);
                
                // Mettre à jour les stats
                await loadServerStats();

                // Afficher le résultat
                showResult(data);
                hideStatus();
                
                showNotification('✅ Résumé généré avec succès!', 'success');

            } catch (error) {
                console.error('Erreur:', error);
                showNotification('❌ ' + error.message, 'error');
                hideStatus();
            } finally {
                isProcessing = false;
                resetSteps();
            }
        }

        // Gestion des étapes de progression
        function updateStep(stepNumber, status) {
            const step = document.getElementById(`step${stepNumber}`);
            step.className = `step ${status}`;
        }

        function resetSteps() {
            for (let i = 1; i <= 4; i++) {
                const step = document.getElementById(`step${i}`);
                step.className = 'step';
            }
        }

        function updateProgress(percent) {
            progressFill.style.width = percent + '%';
        }

        // Affichage du statut
        function showStatus() {
            statusDiv.classList.add('active');
            updateProgress(0);
        }

        function hideStatus() {
            statusDiv.classList.remove('active');
            setTimeout(() => {
                updateProgress(0);
                resetSteps();
            }, 300);
        }

        // Affichage du résultat
        function showResult(data) {
            document.getElementById('resultTitle').textContent = `📖 ${data.title}`;
            document.getElementById('resultContent').innerHTML = data.summary;
            
            // Métadonnées
            const sourceIcon = data.source === 'wikipedia' ? '📖' : '🤖';
            const sourceText = data.source === 'wikipedia' ? 'Wikipedia' : 'IA seule';
            document.getElementById('resultMeta').innerHTML = 
                `${sourceIcon} ${sourceText} • ${data.method || 'direct'}${data.cached ? ' • 💾 Cache' : ''}`;
            
            document.getElementById('resultTime').textContent = `${data.processing_time}s`;
            document.getElementById('resultLength').textContent = data.length_mode;
            
            // URL Wikipedia si disponible
            if (data.url) {
                document.getElementById('wikiLink').href = data.url;
                document.getElementById('wikiLink').textContent = data.url;
                document.getElementById('resultUrl').style.display = 'block';
            } else {
                document.getElementById('resultUrl').style.display = 'none';
            }

            resultDiv.classList.add('active');
        }

        function hideResult() {
            resultDiv.classList.remove('active');
        }

        // Gestion de l'historique
        function addToHistory(theme, data) {
            const historyItem = {
                theme: theme,
                title: data.title,
                timestamp: new Date().toISOString(),
                source: data.source,
                length_mode: data.length_mode,
                processing_time: data.processing_time
            };
            
            // Éviter les doublons récents
            const isDuplicate = searchHistory.some(item => 
                item.theme.toLowerCase() === theme.toLowerCase() && 
                Date.now() - new Date(item.timestamp).getTime() < 5 * 60 * 1000 // 5 minutes
            );
            
            if (!isDuplicate) {
                searchHistory.unshift(historyItem);
                searchHistory = searchHistory.slice(0, 50); // Garder max 50 items
                localStorage.setItem('searchHistory', JSON.stringify(searchHistory));
            }
        }

        function showHistory() {
            const modal = document.getElementById('historyModal');
            const historyList = document.getElementById('historyList');
            
            if (searchHistory.length === 0) {
                historyList.innerHTML = `
                    <p style="text-align: center; color: var(--text-secondary); padding: 20px;">
                        Aucune recherche dans l'historique
                    </p>`;
            } else {
                historyList.innerHTML = searchHistory.map(item => `
                    <div class="history-item" onclick="replaySearch('${item.theme}', '${item.length_mode}')">
                        <div class="history-item-title">${item.title}</div>
                        <div class="history-item-meta">
                            ${new Date(item.timestamp).toLocaleDateString('fr-FR')} • 
                            ${item.source === 'wikipedia' ? '📖' : '🤖'} • 
                            ${item.length_mode}
                        </div>
                    </div>
                `).join('');
            }
            
            modal.classList.add('active');
        }

        function closeHistory() {
            document.getElementById('historyModal').classList.remove('active');
        }

        function clearHistory() {
            if (confirm('Êtes-vous sûr de vouloir vider l\'historique ?')) {
                searchHistory = [];
                localStorage.removeItem('searchHistory');
                closeHistory();
                showNotification('🗑️ Historique vidé', 'info');
            }
        }

        function replaySearch(theme, lengthMode) {
            themeInput.value = theme;
            
            // Mettre à jour la longueur sélectionnée
            document.querySelectorAll('.length-option').forEach(opt => opt.classList.remove('active'));
            document.querySelector(`[data-length="${lengthMode}"]`).classList.add('active');
            currentLength = lengthMode;
            
            closeHistory();
            processTheme(theme, lengthMode);
        }

        // Fonctions utilitaires
        function exportSummary() {
            const title = document.getElementById('resultTitle').textContent;
            const content = document.getElementById('resultContent').textContent;
            const url = document.getElementById('wikiLink').href;
            
            let markdown = `# ${title}\n\n${content}\n\n`;
            if (url) {
                markdown += `**Source:** ${url}\n`;
            }
            markdown += `**Généré le:** ${new Date().toLocaleDateString('fr-FR')}\n`;
            
            const blob = new Blob([markdown], { type: 'text/markdown' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `resume-${currentTheme.replace(/\s+/g, '-').toLowerCase()}.md`;
            a.click();
            
            showNotification('📤 Résumé exporté!', 'success');
        }

        function regenerateSummary() {
            if (currentTheme) {
                processTheme(currentTheme, currentLength);
            }
        }

        function clearAll() {
            themeInput.value = '';
            hideStatus();
            hideResult();
            isProcessing = false;
            currentTheme = '';
        }

        function showNotification(message, type = 'info') {
            // Supprimer les notifications existantes
            document.querySelectorAll('.notification').forEach(n => n.remove());
            
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.textContent = message;
            
            document.body.appendChild(notification);
            
            setTimeout(() => notification.classList.add('show'), 100);
            setTimeout(() => {
                notification.classList.remove('show');
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        }

        function sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

        function updateStats() {
            updateStatsDisplay(stats);
        }

        // Fermer les modals en cliquant à l'extérieur
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('modal')) {
                e.target.classList.remove('active');
            }
        });

        // Raccourcis clavier
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'Enter':
                        e.preventDefault();
                        if (!isProcessing && themeInput.value.trim()) {
                            form.dispatchEvent(new Event('submit'));
                        }
                        break;
                    case 'k':
                        e.preventDefault();
                        themeInput.focus();
                        themeInput.select();
                        break;
                    case 'h':
                        e.preventDefault();
                        showHistory();
                        break;
                    case 'd':
                        e.preventDefault();
                        toggleTheme();
                        break;
                }
            }
            
            if (e.key === 'Escape') {
                closeHistory();
            }
        });
    </script>
</body>
</html>
    '''

@app.route('/api/summarize', methods=['POST'])
def summarize():
    """API endpoint pour traiter les résumés"""
    try:
        data = request.get_json()
        theme = data.get('theme')
        length_mode = data.get('length_mode', 'moyen')
        
        if not theme:
            return jsonify({'error': 'Thème requis'}), 400
        
        # Traiter le thème
        result = summarizer.process_theme(theme, length_mode)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 500
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur dans l'endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """API endpoint pour récupérer les statistiques"""
    return jsonify(summarizer.stats)

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """API endpoint pour vider le cache"""
    summarizer.cache.clear()
    return jsonify({'success': True, 'message': 'Cache vidé'})

if __name__ == '__main__':
    print("=" * 60)
    print("🌟 Wikipedia Summarizer Pro - Enhanced Version")
    print("=" * 60)
    print("📱 Interface: http://localhost:4000")
    print("🔧 API: http://localhost:4000/api/summarize")
    print("📊 Stats: http://localhost:4000/api/stats")
    print("-" * 60)
    print("🚀 Nouvelles fonctionnalités:")
    print("   • 🔑 Clés API automatiques avec rotation")
    print("   • 🔍 Recherche Wikipedia intelligente")
    print("   • 💾 Cache des résumés")
    print("   • 📚 Historique des recherches")
    print("   • 🌙 Mode sombre/clair")
    print("   • 📏 Choix de longueur")
    print("   • 📤 Export markdown")
    print("   • 🔄 Retry automatique")
    print("   • ⌨️ Raccourcis clavier (Ctrl+K, Ctrl+H, Ctrl+D)")
    print("-" * 60)
    
    # Vérifier les dépendances
    try:
        from mistralai import Mistral
        import wikipedia
        print("✅ Toutes les dépendances sont installées")
        print("🔑 3 clés API Mistral configurées avec rotation automatique")
        print("🧠 Recherche intelligente avec fuzzy matching activée")
        print("⚡ Cache et retry automatique opérationnels")
    except ImportError as e:
        print(f"❌ Module manquant: {e}")
        print("💡 Installez les dépendances avec:")
        print("   pip install flask mistralai wikipedia requests")
        exit(1)
    
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=4000)
