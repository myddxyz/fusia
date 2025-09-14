from flask import Flask, render_template, request, jsonify
import requests
import json
from mistralai import Mistral
import wikipedia
import os
import re
import random
import time
from datetime import datetime
import difflib
import hashlib

app = Flask(__name__)

class WikipediaMistralSummarizer:
    def __init__(self):
        """
        Initialise le résumeur avec rotation automatique des clés API
        """
        # Clés API Mistral avec rotation automatique
        self.api_keys = [
            "FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX",
            "9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF",
            "cvkQHVcomFFEW47G044x2p4DTyk5BIc7"
        ]
        self.current_key_index = 0
        
        # Cache des résumés (en mémoire)
        self.cache = {}
        
        # Statistiques
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'wikipedia_success': 0,
            'mistral_only': 0
        }
        
        # Configuration Wikipedia
        wikipedia.set_lang("fr")
        wikipedia.set_rate_limiting(True)
    
    def get_mistral_client(self):
        """Obtient un client Mistral avec rotation des clés"""
        key = self.api_keys[self.current_key_index % len(self.api_keys)]
        self.current_key_index += 1
        return Mistral(api_key=key)
    
    def retry_with_different_keys(self, func, *args, **kwargs):
        """Retry une fonction avec toutes les clés API disponibles"""
        last_exception = None
        
        for attempt in range(len(self.api_keys)):
            try:
                print(f"Tentative {attempt + 1} avec clé API")
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                print(f"Erreur avec clé {attempt + 1}: {str(e)}")
                last_exception = e
                # Passer à la clé suivante
                self.current_key_index += 1
                continue
        
        # Si toutes les clés ont échoué
        raise Exception(f"Toutes les clés API ont échoué. Dernière erreur: {str(last_exception)}")
    
    def get_cache_key(self, theme, length_mode):
        """Génère une clé de cache unique"""
        return hashlib.md5(f"{theme.lower().strip()}_{length_mode}".encode()).hexdigest()
    
    def smart_wikipedia_search(self, theme):
        """
        Recherche intelligente sur Wikipedia avec plusieurs stratégies
        """
        print(f"🔍 Recherche Wikipedia pour: '{theme}'")
        
        # Nettoyer le thème
        theme_clean = theme.strip()
        
        # Stratégie 1: Recherche directe
        try:
            print("Tentative de recherche directe...")
            page = wikipedia.page(theme_clean, auto_suggest=False)
            print(f"✅ Trouvé directement: {page.title}")
            return {
                'title': page.title,
                'content': page.content[:10000],  # Limiter pour éviter les timeouts
                'url': page.url,
                'method': 'direct'
            }
        except wikipedia.exceptions.DisambiguationError as e:
            print(f"Désambiguïsation nécessaire, options: {e.options[:3]}")
            try:
                # Prendre la première option de désambiguïsation
                page = wikipedia.page(e.options[0])
                print(f"✅ Trouvé via désambiguïsation: {page.title}")
                return {
                    'title': page.title,
                    'content': page.content[:10000],
                    'url': page.url,
                    'method': 'disambiguation'
                }
            except Exception as nested_e:
                print(f"Erreur dans la désambiguïsation: {nested_e}")
        except wikipedia.exceptions.PageError:
            print("Page non trouvée directement, essai avec suggestions...")
        except Exception as e:
            print(f"Erreur recherche directe: {e}")
        
        # Stratégie 2: Recherche par suggestions
        try:
            print("Recherche avec suggestions...")
            suggestions = wikipedia.search(theme_clean, results=5)
            print(f"Suggestions trouvées: {suggestions}")
            
            if suggestions:
                for suggestion in suggestions[:3]:  # Essayer les 3 premières
                    try:
                        print(f"Test suggestion: {suggestion}")
                        page = wikipedia.page(suggestion)
                        print(f"✅ Trouvé via suggestion: {page.title}")
                        return {
                            'title': page.title,
                            'content': page.content[:10000],
                            'url': page.url,
                            'method': f'suggestion ({suggestion})'
                        }
                    except Exception as e:
                        print(f"Erreur avec suggestion '{suggestion}': {e}")
                        continue
        except Exception as e:
            print(f"Erreur recherche suggestions: {e}")
        
        print(f"❌ Aucune page Wikipedia trouvée pour: '{theme}'")
        return None
    
    def markdown_to_html(self, text):
        """Convertit le Markdown simple en HTML"""
        if not text:
            return ""
        
        text = text.strip()
        
        # Remplacer **texte** par <strong>texte</strong>
        text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
        
        # Remplacer *texte* par <em>texte</em>
        text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
        
        # Convertir les paragraphes
        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<'):
                # Gérer les listes à puces
                if para.startswith('- ') or para.startswith('• '):
                    para = f'<p>{para}</p>'
                else:
                    para = f'<p>{para}</p>'
            if para:
                formatted_paragraphs.append(para)
        
        return '\n'.join(formatted_paragraphs)
    
    def get_word_count_for_length(self, length_mode):
        """Retourne le nombre de mots selon la longueur"""
        configs = {
            'court': '150-200 mots',
            'moyen': '250-350 mots', 
            'long': '400-500 mots'
        }
        return configs.get(length_mode, configs['moyen'])
    
    def summarize_with_mistral(self, title, content, length_mode='moyen'):
        """Utilise Mistral AI pour résumer le contenu Wikipedia"""
        def _summarize():
            client = self.get_mistral_client()
            
            # Limiter le contenu si trop long
            max_chars = 8000
            if len(content) > max_chars:
                content_truncated = content[:max_chars] + "..."
            else:
                content_truncated = content
            
            word_count = self.get_word_count_for_length(length_mode)
            
            prompt = f"""Tu es un expert en résumé. Voici le contenu d'une page Wikipedia sur "{title}".

Contenu Wikipedia:
{content_truncated}

Consigne: Crée un résumé clair, informatif et bien structuré de cette page Wikipedia en français.
- Le résumé doit faire environ {word_count}
- Utilise un langage accessible et précis
- Structure le texte en paragraphes cohérents
- Concentre-toi sur les informations les plus importantes
- Écris en texte brut, sans formatage markdown

Résumé:"""
            
            messages = [{"role": "user", "content": prompt}]
            
            response = client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.2,
                max_tokens=800
            )
            
            return response.choices[0].message.content.strip()
        
        return self.retry_with_different_keys(_summarize)
    
    def answer_with_mistral_only(self, theme, length_mode='moyen'):
        """Utilise Mistral AI pour répondre directement sur un thème sans Wikipedia"""
        def _answer():
            client = self.get_mistral_client()
            
            word_count = self.get_word_count_for_length(length_mode)
            
            prompt = f"""Tu es un assistant expert qui doit fournir des informations complètes sur un sujet.

Sujet demandé: "{theme}"

Consigne: Fournis une explication complète et informative sur ce sujet en français.
- Explique ce que c'est, son contexte, son importance
- Donne des détails utiles et intéressants
- Le texte doit faire environ {word_count}
- Utilise un langage clair et accessible
- Structure en paragraphes cohérents
- Écris en texte brut, sans formatage markdown

Réponse:"""
            
            messages = [{"role": "user", "content": prompt}]
            
            response = client.chat.complete(
                model="mistral-large-latest", 
                messages=messages,
                temperature=0.3,
                max_tokens=800
            )
            
            return response.choices[0].message.content.strip()
        
        return self.retry_with_different_keys(_answer)

    def process_theme(self, theme, length_mode='moyen'):
        """Traite un thème complet"""
        print(f"\n🚀 DÉBUT DU TRAITEMENT: '{theme}' (longueur: {length_mode})")
        self.stats['requests'] += 1
        start_time = time.time()
        
        # Validation
        if not theme or len(theme.strip()) < 2:
            return {
                'success': False,
                'error': 'Le thème doit contenir au moins 2 caractères'
            }
        
        theme = theme.strip()
        
        # Vérifier le cache
        cache_key = self.get_cache_key(theme, length_mode)
        if cache_key in self.cache:
            print("💾 Résultat trouvé en cache")
            self.stats['cache_hits'] += 1
            return self.cache[cache_key]
        
        try:
            # Recherche Wikipedia
            print("🔍 Début recherche Wikipedia...")
            wiki_data = self.smart_wikipedia_search(theme)
            
            if not wiki_data:
                # Réponse Mistral seul
                print(f"🤖 Génération directe avec Mistral pour: {theme}")
                mistral_response = self.answer_with_mistral_only(theme, length_mode)
                
                if not mistral_response:
                    return {'success': False, 'error': 'Erreur lors de la génération de la réponse'}
                
                formatted_response = self.markdown_to_html(mistral_response)
                
                result = {
                    'success': True,
                    'title': f"Informations sur: {theme}",
                    'summary': formatted_response,
                    'url': None,
                    'source': 'mistral_only',
                    'method': 'direct_ai',
                    'processing_time': round(time.time() - start_time, 2),
                    'length_mode': length_mode
                }
                
                self.stats['mistral_only'] += 1
                
            else:
                # Résumé Wikipedia + Mistral
                print(f"📖 Résumé Wikipedia pour: {wiki_data['title']}")
                summary = self.summarize_with_mistral(wiki_data['title'], wiki_data['content'], length_mode)
                
                if not summary:
                    return {'success': False, 'error': 'Erreur lors de la génération du résumé'}
                
                formatted_summary = self.markdown_to_html(summary)
                
                result = {
                    'success': True,
                    'title': wiki_data['title'],
                    'summary': formatted_summary,
                    'url': wiki_data['url'],
                    'source': 'wikipedia',
                    'method': wiki_data['method'],
                    'processing_time': round(time.time() - start_time, 2),
                    'length_mode': length_mode
                }
                
                self.stats['wikipedia_success'] += 1
            
            # Sauvegarder en cache
            self.cache[cache_key] = result
            print(f"✅ TRAITEMENT TERMINÉ en {result['processing_time']}s")
            return result
            
        except Exception as e:
            print(f"❌ ERREUR GÉNÉRALE: {str(e)}")
            return {
                'success': False,
                'error': f'Erreur lors du traitement: {str(e)}'
            }

# Instance globale du résumeur
summarizer = WikipediaMistralSummarizer()

@app.route('/')
def index():
    """Page d'accueil avec l'interface"""
    return """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wikipedia Summarizer Pro</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --bg-primary: #e6e7ee;
            --bg-secondary: #d1d2d9;
            --bg-tertiary: #fbfcff;
            --text-primary: #5a5c69;
            --text-secondary: #8b8d97;
            --accent: #667eea;
            --accent-secondary: #764ba2;
            --shadow-light: #bebfc5;
            --shadow-dark: #ffffff;
        }

        [data-theme="dark"] {
            --bg-primary: #2d3748;
            --bg-secondary: #1a202c;
            --bg-tertiary: #4a5568;
            --text-primary: #f7fafc;
            --text-secondary: #e2e8f0;
            --shadow-light: #1a202c;
            --shadow-dark: #4a5568;
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
        }

        .container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
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
            padding: 12px;
            cursor: pointer;
            font-size: 1.2rem;
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

        .input::placeholder {
            color: var(--text-secondary);
        }

        .length-selector {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }

        .length-btn {
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
            flex: 1;
            min-width: 150px;
        }

        .length-btn:hover {
            transform: translateY(-2px);
        }

        .length-btn.active {
            background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
            color: white;
            box-shadow: 
                inset 4px 4px 8px rgba(0,0,0,0.2);
        }

        .suggestions {
            margin-top: 15px;
        }

        .suggestion-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
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
            box-shadow: 
                3px 3px 6px var(--shadow-light),
                -3px -3px 6px var(--shadow-dark);
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
        }

        .btn:hover:not(:disabled) {
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

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
            color: white;
            box-shadow: 
                8px 8px 16px rgba(102, 126, 234, 0.3),
                -8px -8px 16px rgba(255, 255, 255, 0.8);
        }

        .btn-primary:hover:not(:disabled) {
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

        .status-text {
            color: var(--text-primary);
            font-weight: 500;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
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

        .result-title {
            color: var(--text-primary);
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 2px solid var(--bg-secondary);
        }

        .result-meta {
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 20px;
        }

        .result-content {
            color: var(--text-secondary);
            line-height: 1.7;
            font-size: 1rem;
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

        @media (max-width: 768px) {
            .container {
                padding: 25px 20px;
                margin: 10px;
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

            .length-selector {
                flex-direction: column;
                gap: 10px;
            }

            .length-btn {
                min-width: auto;
            }

            .controls {
                flex-direction: column;
                gap: 10px;
            }

            .btn {
                width: 100%;
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
            <form id="summarizerForm" onsubmit="handleFormSubmit(event)">
                <div class="form-group">
                    <label class="label" for="theme">🔍 Thème à rechercher</label>
                    <input 
                        type="text" 
                        id="theme" 
                        class="input" 
                        placeholder="Intelligence artificielle, Paris, Einstein..."
                        required
                    >
                    
                    <div class="suggestions">
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">💡 Suggestions populaires:</span>
                        <div class="suggestion-chips" id="suggestionChips">
                        </div>
                    </div>
                </div>

                <div class="form-group">
                    <label class="label">📏 Longueur du résumé</label>
                    <div class="length-selector">
                        <button type="button" class="length-btn" onclick="selectLength('court', this)">
                            📝 Court<br><small>150-200 mots</small>
                        </button>
                        <button type="button" class="length-btn active" onclick="selectLength('moyen', this)">
                            📄 Moyen<br><small>250-350 mots</small>
                        </button>
                        <button type="button" class="length-btn" onclick="selectLength('long', this)">
                            📚 Long<br><small>400-500 mots</small>
                        </button>
                    </div>
                </div>

                <div class="controls">
                    <button type="submit" class="btn btn-primary" id="generateBtn">
                        ✨ Générer le résumé
                    </button>
                    <button type="button" class="btn" onclick="clearAll()">
                        🗑️ Effacer
                    </button>
                </div>
            </form>
        </div>

        <div id="status" class="status">
            <div class="status-text">
                <span class="loading"></span>
                <span id="statusText">Traitement en cours...</span>
            </div>
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
        </div>

        <div id="result" class="result">
            <div class="result-title" id="resultTitle">📖 Résumé généré</div>
            <div class="result-meta" id="resultMeta">Source: Wikipedia • 2.3s • Moyen</div>
            <div class="result-content" id="resultContent"></div>
            <div id="resultUrl" class="result-url" style="display: none;">
                <strong>🔗 Source Wikipedia:</strong><br>
                <a href="#" target="_blank" id="wikiLink"></a>
            </div>
        </div>
    </div>

    <script>
        // Variables globales
        let isProcessing = false;
        let currentLength = 'moyen';
        
        const popularThemes = [
            "Intelligence artificielle", "Réchauffement climatique", "Einstein",
            "Révolution française", "Marie Curie", "Paris",
            "Photosynthèse", "Bitcoin", "Système solaire"
        ];

        // Initialisation au chargement
        document.addEventListener('DOMContentLoaded', function() {
            console.log('🚀 Page chargée, initialisation...');
            initializeSuggestions();
            initializeTheme();
            loadStats();
            
            // Focus sur l'input
            const themeInput = document.getElementById('theme');
            if (themeInput) {
                themeInput.focus();
            }
            
            console.log('✅ Initialisation terminée');
        });

        // Gestion des événements
        function handleFormSubmit(event) {
            event.preventDefault();
            console.log('📝 Formulaire soumis');
            
            if (isProcessing) {
                console.log('⏳ Traitement déjà en cours, ignorer');
                showNotification('Un traitement est déjà en cours...', 'info');
                return false;
            }

            const themeInput = document.getElementById('theme');
            const theme = themeInput ? themeInput.value.trim() : '';
            
            if (!theme) {
                console.log('❌ Thème vide');
                showNotification('Veuillez entrer un thème de recherche', 'error');
                if (themeInput) themeInput.focus();
                return false;
            }

            if (theme.length < 2) {
                console.log('❌ Thème trop court');
                showNotification('Le thème doit contenir au moins 2 caractères', 'error');
                if (themeInput) themeInput.focus();
                return false;
            }

            console.log(`🚀 Démarrage du traitement pour: "${theme}" (longueur: ${currentLength})`);
            processTheme(theme, currentLength);
            return false;
        }

        function selectLength(length, element) {
            console.log(`📏 Sélection longueur: ${length}`);
            
            // Retirer la classe active de tous les boutons
            document.querySelectorAll('.length-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Ajouter la classe active au bouton cliqué
            element.classList.add('active');
            currentLength = length;
            console.log(`✅ Longueur mise à jour: ${currentLength}`);
        }

        function initializeSuggestions() {
            console.log('💡 Initialisation des suggestions');
            const container = document.getElementById('suggestionChips');
            if (!container) {
                console.log('❌ Container suggestions non trouvé');
                return;
            }
            
            // Mélanger et prendre 6 suggestions
            const shuffled = [...popularThemes].sort(() => 0.5 - Math.random()).slice(0, 6);
            console.log('Suggestions sélectionnées:', shuffled);
            
            shuffled.forEach(theme => {
                const chip = document.createElement('button');
                chip.className = 'chip';
                chip.textContent = theme;
                chip.type = 'button';
                chip.onclick = function() {
                    console.log(`💡 Suggestion cliquée: ${theme}`);
                    const themeInput = document.getElementById('theme');
                    if (themeInput) {
                        themeInput.value = theme;
                        themeInput.focus();
                    }
                };
                container.appendChild(chip);
            });
            
            console.log('✅ Suggestions initialisées');
        }

        function initializeTheme() {
            console.log('🎨 Initialisation du thème');
            const savedTheme = localStorage.getItem('theme') || 'light';
            console.log(`Thème sauvegardé: ${savedTheme}`);
            
            if (savedTheme === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
                const themeIcon = document.getElementById('themeIcon');
                if (themeIcon) {
                    themeIcon.textContent = '☀️';
                }
            }
            console.log('✅ Thème initialisé');
        }

        function toggleTheme() {
            console.log('🎨 Basculement du thème');
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            const themeIcon = document.getElementById('themeIcon');
            if (themeIcon) {
                themeIcon.textContent = newTheme === 'dark' ? '☀️' : '🌙';
            }
            localStorage.setItem('theme', newTheme);
            console.log(`✅ Thème changé vers: ${newTheme}`);
        }

        async function loadStats() {
            console.log('📊 Chargement des statistiques');
            try {
                const response = await fetch('/api/stats', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                if (response.ok) {
                    const stats = await response.json();
                    console.log('📊 Stats reçues:', stats);
                    updateStatsDisplay(stats);
                } else {
                    console.log('⚠️ Erreur HTTP stats:', response.status);
                }
            } catch (error) {
                console.log('❌ Erreur chargement stats:', error);
            }
        }

        function updateStatsDisplay(stats) {
            console.log('📊 Mise à jour affichage stats');
            const elements = {
                totalRequests: document.getElementById('totalRequests'),
                cacheHits: document.getElementById('cacheHits'),
                wikiSuccess: document.getElementById('wikiSuccess'),
                aiOnly: document.getElementById('aiOnly')
            };

            if (elements.totalRequests) elements.totalRequests.textContent = stats.requests || 0;
            if (elements.cacheHits) elements.cacheHits.textContent = stats.cache_hits || 0;
            if (elements.wikiSuccess) elements.wikiSuccess.textContent = stats.wikipedia_success || 0;
            if (elements.aiOnly) elements.aiOnly.textContent = stats.mistral_only || 0;
            
            console.log('✅ Stats mises à jour dans l\'interface');
        }

        async function processTheme(theme, lengthMode) {
            console.log(`🚀 DÉBUT processTheme: "${theme}" (${lengthMode})`);
            
            if (isProcessing) {
                console.log('⏳ Déjà en traitement, abandon');
                return;
            }
            
            isProcessing = true;
            const generateBtn = document.getElementById('generateBtn');
            
            if (generateBtn) {
                generateBtn.disabled = true;
                generateBtn.textContent = '⏳ Traitement...';
                console.log('🔄 Bouton désactivé');
            }
            
            showStatus('🔍 Recherche en cours...');
            hideResult();

            try {
                console.log('📡 Préparation de la requête API');
                
                const requestData = {
                    theme: theme,
                    length_mode: lengthMode
                };
                
                console.log('📡 Données à envoyer:', requestData);
                
                updateProgress(10);
                updateStatus('🔍 Recherche Wikipedia...');
                await sleep(200);
                
                updateProgress(30);
                
                console.log('📡 Envoi de la requête vers /api/summarize');
                
                const response = await fetch('/api/summarize', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });

                console.log(`📡 Réponse reçue - Status: ${response.status}`);

                updateProgress(60);
                updateStatus('🤖 Génération du résumé...');
                await sleep(300);

                if (!response.ok) {
                    const errorText = await response.text();
                    console.log('❌ Erreur HTTP:', response.status, errorText);
                    
                    let errorMessage = 'Erreur lors du traitement';
                    try {
                        const errorData = JSON.parse(errorText);
                        errorMessage = errorData.error || errorMessage;
                    } catch (e) {
                        errorMessage = `Erreur HTTP ${response.status}`;
                    }
                    
                    throw new Error(errorMessage);
                }

                const data = await response.json();
                console.log('✅ Données reçues:', data);

                updateProgress(90);
                updateStatus('✅ Finalisation...');
                await sleep(300);

                if (!data.success) {
                    throw new Error(data.error || 'Erreur inconnue');
                }

                updateProgress(100);
                updateStatus('🎉 Résumé terminé!');
                await sleep(500);

                showResult(data);
                hideStatus();
                
                // Recharger les stats après succès
                setTimeout(loadStats, 500);
                
                showNotification('Résumé généré avec succès!', 'success');
                console.log('🎉 TRAITEMENT TERMINÉ AVEC SUCCÈS');

            } catch (error) {
                console.error('❌ ERREUR COMPLÈTE:', error);
                showNotification(error.message || 'Erreur lors du traitement', 'error');
                hideStatus();
                console.log('💥 TRAITEMENT ÉCHOUÉ');
            } finally {
                isProcessing = false;
                if (generateBtn) {
                    generateBtn.disabled = false;
                    generateBtn.textContent = '✨ Générer le résumé';
                    console.log('🔄 Bouton réactivé');
                }
            }
        }

        function updateProgress(percent) {
            const progressFill = document.getElementById('progressFill');
            if (progressFill) {
                progressFill.style.width = percent + '%';
                console.log(`📈 Progression: ${percent}%`);
            }
        }

        function updateStatus(message) {
            const statusText = document.getElementById('statusText');
            if (statusText) {
                statusText.textContent = message;
                console.log(`📢 Status: ${message}`);
            }
        }

        function showStatus(message) {
            console.log(`👁️ Affichage status: ${message}`);
            updateStatus(message);
            const statusDiv = document.getElementById('status');
            if (statusDiv) {
                statusDiv.classList.add('active');
            }
            updateProgress(0);
        }

        function hideStatus() {
            console.log('👁️ Masquage du status');
            const statusDiv = document.getElementById('status');
            if (statusDiv) {
                statusDiv.classList.remove('active');
            }
            setTimeout(() => {
                updateProgress(0);
            }, 300);
        }

        function showResult(data) {
            console.log('👁️ Affichage du résultat:', data.title);
            
            const elements = {
                title: document.getElementById('resultTitle'),
                content: document.getElementById('resultContent'),
                meta: document.getElementById('resultMeta'),
                url: document.getElementById('resultUrl'),
                link: document.getElementById('wikiLink'),
                result: document.getElementById('result')
            };
            
            if (elements.title) elements.title.textContent = data.title;
            if (elements.content) elements.content.innerHTML = data.summary;
            
            const sourceIcon = data.source === 'wikipedia' ? '📖' : '🤖';
            const sourceText = data.source === 'wikipedia' ? 'Wikipedia' : 'IA seule';
            let metaText = `${sourceIcon} ${sourceText} • ${data.processing_time}s • ${data.length_mode}`;
            
            if (data.method) {
                metaText += ` • ${data.method}`;
            }
            
            if (elements.meta) elements.meta.textContent = metaText;
            
            if (data.url && elements.url && elements.link) {
                elements.link.href = data.url;
                elements.link.textContent = data.url;
                elements.url.style.display = 'block';
                console.log('🔗 URL Wikipedia affichée');
            } else if (elements.url) {
                elements.url.style.display = 'none';
                console.log('🔗 Pas d\'URL Wikipedia');
            }

            if (elements.result) {
                elements.result.classList.add('active');
                console.log('✅ Résultat affiché');
            }
        }

        function hideResult() {
            console.log('👁️ Masquage du résultat');
            const resultDiv = document.getElementById('result');
            if (resultDiv) {
                resultDiv.classList.remove('active');
            }
        }

        function clearAll() {
            console.log('🗑️ Effacement de tout');
            const themeInput = document.getElementById('theme');
            if (themeInput) {
                themeInput.value = '';
                themeInput.focus();
            }
            hideStatus();
            hideResult();
            isProcessing = false;
            const generateBtn = document.getElementById('generateBtn');
            if (generateBtn) {
                generateBtn.disabled = false;
                generateBtn.textContent = '✨ Générer le résumé';
            }
            console.log('✅ Tout effacé');
        }

        function showNotification(message, type = 'info') {
            console.log(`🔔 Notification: ${message} (${type})`);
            
            // Supprimer les notifications existantes
            document.querySelectorAll('.notification').forEach(n => n.remove());
            
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.textContent = message;
            
            document.body.appendChild(notification);
            
            // Animation d'apparition
            setTimeout(() => notification.classList.add('show'), 100);
            
            // Disparition automatique
            setTimeout(() => {
                notification.classList.remove('show');
                setTimeout(() => notification.remove(), 300);
            }, 4000);
        }

        function sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

        // Raccourcis clavier
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'Enter':
                        e.preventDefault();
                        if (!isProcessing) {
                            const themeInput = document.getElementById('theme');
                            if (themeInput && themeInput.value.trim()) {
                                console.log('⌨️ Raccourci Ctrl+Enter détecté');
                                handleFormSubmit(e);
                            }
                        }
                        break;
                    case 'k':
                        e.preventDefault();
                        const themeInput = document.getElementById('theme');
                        if (themeInput) {
                            themeInput.focus();
                            themeInput.select();
                            console.log('⌨️ Raccourci Ctrl+K détecté - Focus sur input');
                        }
                        break;
                    case 'd':
                        e.preventDefault();
                        toggleTheme();
                        console.log('⌨️ Raccourci Ctrl+D détecté - Toggle thème');
                        break;
                }
            }
            
            if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
                const target = e.target;
                if (target && target.id === 'theme') {
                    e.preventDefault();
                    if (!isProcessing && target.value.trim()) {
                        console.log('⌨️ Enter dans input détecté');
                        handleFormSubmit(e);
                    }
                }
            }
        });

        // Test de connexion API au chargement
        window.addEventListener('load', function() {
            console.log('🧪 Test de connexion API...');
            fetch('/api/stats')
                .then(response => {
                    if (response.ok) {
                        console.log('✅ API accessible');
                    } else {
                        console.log('⚠️ API répond mais avec erreur:', response.status);
                    }
                })
                .catch(error => {
                    console.log('❌ API non accessible:', error);
                    showNotification('Problème de connexion au serveur', 'error');
                });
        });
    </script>
</body>
</html>"""

@app.route('/api/summarize', methods=['POST'])
def summarize():
    """API endpoint pour traiter les résumés"""
    try:
        print("\n" + "="*50)
        print("🚀 REQUÊTE REÇUE sur /api/summarize")
        print("="*50)
        
        # Vérifier si on reçoit du JSON
        if not request.is_json:
            print("❌ ERREUR: Pas de JSON reçu")
            return jsonify({'success': False, 'error': 'Content-Type doit être application/json'}), 400
        
        data = request.get_json()
        print(f"📨 Données reçues: {data}")
        
        if not data:
            print("❌ ERREUR: Données JSON vides")
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        theme = data.get('theme')
        length_mode = data.get('length_mode', 'moyen')
        
        print(f"🎯 Thème: '{theme}'")
        print(f"📏 Longueur: '{length_mode}'")
        
        if not theme:
            print("❌ ERREUR: Thème manquant")
            return jsonify({'success': False, 'error': 'Thème requis'}), 400
        
        if not theme.strip():
            print("❌ ERREUR: Thème vide")
            return jsonify({'success': False, 'error': 'Thème ne peut pas être vide'}), 400
        
        print(f"🚀 DÉBUT TRAITEMENT: '{theme}' en mode '{length_mode}'")
        
        # Appeler le processeur
        result = summarizer.process_theme(theme, length_mode)
        
        print(f"📤 Résultat du traitement: success={result.get('success')}")
        
        if not result.get('success'):
            error_msg = result.get('error', 'Erreur inconnue')
            print(f"❌ ÉCHEC: {error_msg}")
            return jsonify({
                'success': False, 
                'error': error_msg
            }), 500
        
        print(f"✅ SUCCÈS: {result.get('title', 'Sans titre')}")
        print(f"📊 Temps: {result.get('processing_time', 0)}s")
        print(f"📖 Source: {result.get('source', 'inconnue')}")
        
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"💥 ERREUR GÉNÉRALE dans l'endpoint: {error_msg}")
        print(f"Type d'erreur: {type(e).__name__}")
        
        return jsonify({
            'success': False,
            'error': f'Erreur serveur: {error_msg}'
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API endpoint pour récupérer les statistiques"""
    try:
        print("📊 Requête stats reçue")
        stats = summarizer.stats.copy()
        print(f"📊 Stats envoyées: {stats}")
        return jsonify(stats), 200
    except Exception as e:
        print(f"❌ Erreur stats: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 80)
    print("🌟 WIKIPEDIA SUMMARIZER PRO - VERSION CORRIGÉE 🌟")
    print("=" * 80)
    print("🌐 Interface: http://localhost:4000")
    print("🚀 API Résumé: http://localhost:4000/api/summarize")
    print("📊 API Stats: http://localhost:4000/api/stats")
    print("-" * 80)
    print("✨ Fonctionnalités:")
    print("   🤖 3 clés API Mistral avec rotation automatique")
    print("   📚 Recherche Wikipedia intelligente multi-stratégies")
    print("   💾 Cache des résumés en mémoire")
    print("   📏 3 longueurs: court/moyen/long")
    print("   🎨 Mode sombre/clair")
    print("   📊 Statistiques temps réel")
    print("   ⌨️  Raccourcis: Ctrl+Enter, Ctrl+K, Ctrl+D")
    print("   📱 Interface responsive")
    print("-" * 80)
    print("🔧 Corrections apportées:")
    print("   ✅ Gestion d'erreurs JavaScript renforcée")
    print("   ✅ Rotation des clés API optimisée")
    print("   ✅ Logs détaillés front & backend")
    print("   ✅ Validation des données améliorée")
    print("   ✅ Gestion des timeouts Wikipedia")
    print("   ✅ États d'interface cohérents")
    print("=" * 80)
    
    try:
        # Test des imports
        from mistralai import Mistral
        import wikipedia
        print("✅ Toutes les dépendances sont installées")
        
        # Test des clés API
        test_client = Mistral(api_key=summarizer.api_keys[0])
        print("✅ Clés API Mistral configurées")
        
        # Test Wikipedia
        wikipedia.set_lang("fr")
        print("✅ Wikipedia configuré en français")
        
    except ImportError as e:
        print(f"❌ Module manquant: {e}")
        print("🔧 Installez avec: pip install flask mistralai wikipedia")
        exit(1)
    except Exception as e:
        print(f"⚠️  Avertissement configuration: {e}")
    
    print("\n🚀 DÉMARRAGE DU SERVEUR...")
    print("=" * 80)
    
    app.run(debug=True, host='0.0.0.0', port=4000)
