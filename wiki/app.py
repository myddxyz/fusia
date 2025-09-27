from flask import Flask, request, jsonify
import requests
import json
from mistralai import Mistral
import wikipedia
import os
import re
import time
import hashlib

app = Flask(__name__)

class WikipediaMistralSummarizer:
    def __init__(self):
        """
        Initialise le résumeur avec clés API depuis variables d'environnement
        """
        # Clés API Mistral depuis variables d'environnement OU valeurs par défaut
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
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
        
        # Configuration Wikipedia par défaut
        self.current_language = 'en'
        self.setup_wikipedia_language('en')
    
    def setup_wikipedia_language(self, lang_code):
        """Configure Wikipedia pour une langue donnée"""
        try:
            wikipedia.set_lang(lang_code)
            wikipedia.set_rate_limiting(True)
            self.current_language = lang_code
            print(f"✅ Wikipedia configuré pour: {lang_code}")
        except Exception as e:
            print(f"⚠️ Erreur config Wikipedia ({lang_code}): {e}")
            # Fallback vers l'anglais
            try:
                wikipedia.set_lang('en')
                self.current_language = 'en'
            except:
                pass
    
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
                self.current_key_index += 1
                # Attendre entre les tentatives pour éviter rate limiting
                if attempt < len(self.api_keys) - 1:
                    time.sleep(2)
                continue
        
        # Si toutes les clés ont échoué, utiliser un modèle moins cher
        print("⚠️ Tentative avec modèle alternatif...")
        try:
            return self.retry_with_alternative_model(func, *args, **kwargs)
        except:
            raise Exception(f"Toutes les clés API ont échoué. Service temporairement indisponible. Dernière erreur: {str(last_exception)}")
    
    def retry_with_alternative_model(self, func, *args, **kwargs):
        """Retry avec un modèle Mistral moins cher"""
        for attempt in range(len(self.api_keys)):
            try:
                # Utiliser mistral-small au lieu de mistral-large
                if hasattr(self, '_use_small_model'):
                    result = func(*args, **kwargs)
                    return result
            except:
                self.current_key_index += 1
                continue
        raise Exception("Tous les modèles ont échoué")
    
    def get_cache_key(self, theme, length_mode, language, mode):
        """Génère une clé de cache unique incluant la langue et le mode"""
        return hashlib.md5(f"{theme.lower().strip()}_{length_mode}_{language}_{mode}".encode()).hexdigest()
    
    def smart_wikipedia_search(self, theme):
        """Recherche intelligente sur Wikipedia"""
        print(f"🔍 Recherche Wikipedia pour: '{theme}' (langue: {self.current_language})")
        
        theme_clean = theme.strip()
        
        try:
            print("Tentative de recherche directe...")
            page = wikipedia.page(theme_clean, auto_suggest=False)
            print(f"✅ Trouvé directement: {page.title}")
            return {
                'title': page.title,
                'content': page.content[:8000],  # Limiter pour Render
                'url': page.url,
                'method': 'direct'
            }
        except wikipedia.exceptions.DisambiguationError as e:
            try:
                page = wikipedia.page(e.options[0])
                print(f"✅ Trouvé via désambiguïsation: {page.title}")
                return {
                    'title': page.title,
                    'content': page.content[:8000],
                    'url': page.url,
                    'method': 'disambiguation'
                }
            except:
                pass
        except:
            pass
        
        try:
            print("Recherche avec suggestions...")
            suggestions = wikipedia.search(theme_clean, results=3)
            print(f"Suggestions trouvées: {suggestions}")
            
            if suggestions:
                for suggestion in suggestions:
                    try:
                        page = wikipedia.page(suggestion)
                        print(f"✅ Trouvé via suggestion: {page.title}")
                        return {
                            'title': page.title,
                            'content': page.content[:8000],
                            'url': page.url,
                            'method': f'suggestion ({suggestion})'
                        }
                    except:
                        continue
        except:
            pass
        
        print(f"❌ Aucune page Wikipedia trouvée pour: '{theme}'")
        return None
    
    def markdown_to_html(self, text):
        """Convertit le Markdown simple en HTML"""
        if not text:
            return ""
        
        text = text.strip()
        text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
        
        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<'):
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
    
    def get_language_instruction(self, language):
        """Retourne l'instruction de langue pour Mistral"""
        language_instructions = {
            'en': 'Write the summary in English.',
            'fr': 'Écris le résumé en français.',
            'es': 'Escribe el resumen en español.'
        }
        return language_instructions.get(language, language_instructions['en'])
    
    def get_mode_instruction(self, mode, language):
        """Retourne l'instruction spécifique selon le mode de résumé"""
        instructions = {
            'en': {
                'general': '',
                'historique': '- Focus on historical dates, events, periods, and key historical figures\n- Emphasize chronological order and historical context\n- Highlight the historical significance and impact',
                'scientifique': '- Focus on scientific definitions, theories, experiments, and discoveries\n- Emphasize technical concepts and scientific methodology\n- Include key scientific principles and breakthroughs',
                'biographique': '- Focus on the person\'s life journey, important dates, and achievements\n- Emphasize key life events, career milestones, and personal impact\n- Structure chronologically when relevant',
                'scolaire': '- Use simple, clear explanations suitable for students\n- Focus on educational aspects and learning points\n- Make complex concepts accessible and easy to understand',
                'culture': '- Focus on social, artistic, and cultural impact\n- Emphasize cultural significance and influence on society\n- Highlight artistic, literary, or cultural contributions',
                'faits': '- Present essential facts in a clear, concise format\n- Structure as key points suitable for revision notes\n- Focus on the most important and memorable information'
            },
            'fr': {
                'general': '',
                'historique': '- Concentre-toi sur les dates historiques, événements, périodes et personnages historiques clés\n- Mets l\'accent sur l\'ordre chronologique et le contexte historique\n- Souligne la significance et l\'impact historiques',
                'scientifique': '- Concentre-toi sur les définitions scientifiques, théories, expériences et découvertes\n- Mets l\'accent sur les concepts techniques et la méthodologie scientifique\n- Inclus les principes scientifiques et percées importantes',
                'biographique': '- Concentre-toi sur le parcours de vie, les dates importantes et les réalisations\n- Mets l\'accent sur les événements clés de la vie, les étapes de carrière et l\'impact personnel\n- Structure chronologiquement quand pertinent',
                'scolaire': '- Utilise des explications simples et claires adaptées aux étudiants\n- Concentre-toi sur les aspects éducatifs et les points d\'apprentissage\n- Rends les concepts complexes accessibles et faciles à comprendre',
                'culture': '- Concentre-toi sur l\'impact social, artistique et culturel\n- Mets l\'accent sur la significance culturelle et l\'influence sur la société\n- Souligne les contributions artistiques, littéraires ou culturelles',
                'faits': '- Présente les faits essentiels dans un format clair et concis\n- Structure comme des points clés adaptés aux notes de révision\n- Concentre-toi sur les informations les plus importantes et mémorables'
            },
            'es': {
                'general': '',
                'historique': '- Enfócate en fechas históricas, eventos, períodos y figuras históricas clave\n- Enfatiza el orden cronológico y el contexto histórico\n- Destaca la significación e impacto históricos',
                'scientifique': '- Enfócate en definiciones científicas, teorías, experimentos y descubrimientos\n- Enfatiza conceptos técnicos y metodología científica\n- Incluye principios científicos y avances importantes',
                'biographique': '- Enfócate en el recorrido de vida, fechas importantes y logros\n- Enfatiza eventos clave de la vida, hitos profesionales e impacto personal\n- Estructura cronológicamente cuando sea relevante',
                'scolaire': '- Usa explicaciones simples y claras adecuadas para estudiantes\n- Enfócate en aspectos educativos y puntos de aprendizaje\n- Haz conceptos complejos accesibles y fáciles de entender',
                'culture': '- Enfócate en el impacto social, artístico y cultural\n- Enfatiza la significación cultural y la influencia en la sociedad\n- Destaca contribuciones artísticas, literarias o culturales',
                'faits': '- Presenta hechos esenciales en un formato claro y conciso\n- Estructura como puntos clave adecuados para notas de revisión\n- Enfócate en la información más importante y memorable'
            }
        }
        
        lang_instructions = instructions.get(language, instructions['en'])
        return lang_instructions.get(mode, lang_instructions['general'])
    
    def summarize_with_mistral(self, title, content, length_mode='moyen', language='en', mode='general'):
        """Utilise Mistral AI pour résumer le contenu Wikipedia avec mode spécifique"""
        def _summarize():
            client = self.get_mistral_client()
            
            max_chars = 6000  # Réduit pour Render
            if len(content) > max_chars:
                content_truncated = content[:max_chars] + "..."
            else:
                content_truncated = content
            
            word_count = self.get_word_count_for_length(length_mode)
            language_instruction = self.get_language_instruction(language)
            mode_instruction = self.get_mode_instruction(mode, language)
            
            # Construction du prompt avec instructions spécifiques au mode
            base_prompt = f"""You are an expert summarizer. Here is the content of a Wikipedia page about "{title}".

Wikipedia Content:
{content_truncated}

Instructions: Create a clear, informative and well-structured summary of this Wikipedia page.
- The summary should be approximately {word_count}
- Use accessible and precise language
- Structure the text in coherent paragraphs
- Focus on the most important information
- Write in plain text, without markdown formatting
- {language_instruction}"""

            if mode_instruction:
                base_prompt += f"""

Special focus for this summary:
{mode_instruction}"""

            base_prompt += "\n\nSummary:"
            
            # Format correct pour Mistral AI v1.0.0
            messages = [{"role": "user", "content": base_prompt}]
            
            # Essayer d'abord avec le modèle standard, puis avec le modèle plus petit
            try:
                response = client.chat.complete(
                    model="mistral-large-latest",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=600
                )
            except Exception as e:
                if "429" in str(e) or "capacity exceeded" in str(e):
                    print("⚠️ Rate limit atteint, utilisation du modèle small...")
                    response = client.chat.complete(
                        model="mistral-small-latest",
                        messages=messages,
                        temperature=0.2,
                        max_tokens=600
                    )
                else:
                    raise e
            
            return response.choices[0].message.content.strip()
        
        return self.retry_with_different_keys(_summarize)
    
    def answer_with_mistral_only(self, theme, length_mode='moyen', language='en', mode='general'):
        """Utilise Mistral AI pour répondre directement sur un thème sans Wikipedia avec mode spécifique"""
        def _answer():
            client = self.get_mistral_client()
            
            word_count = self.get_word_count_for_length(length_mode)
            language_instruction = self.get_language_instruction(language)
            mode_instruction = self.get_mode_instruction(mode, language)
            
            base_prompt = f"""You are an expert assistant who must provide complete information on a subject.

Requested topic: "{theme}"

Instructions: Provide a complete and informative explanation of this topic.
- Explain what it is, its context, its importance
- Give useful and interesting details
- The text should be approximately {word_count}
- Use clear and accessible language
- Structure in coherent paragraphs
- Write in plain text, without markdown formatting
- {language_instruction}"""

            if mode_instruction:
                base_prompt += f"""

Special focus for this explanation:
{mode_instruction}"""

            base_prompt += "\n\nResponse:"
            
            messages = [{"role": "user", "content": base_prompt}]
            
            # Essayer d'abord avec le modèle standard, puis avec le modèle plus petit
            try:
                response = client.chat.complete(
                    model="mistral-large-latest", 
                    messages=messages,
                    temperature=0.3,
                    max_tokens=600
                )
            except Exception as e:
                if "429" in str(e) or "capacity exceeded" in str(e):
                    print("⚠️ Rate limit atteint, utilisation du modèle small...")
                    response = client.chat.complete(
                        model="mistral-small-latest",
                        messages=messages,
                        temperature=0.3,
                        max_tokens=600
                    )
                else:
                    raise e
            
            return response.choices[0].message.content.strip()
        
        return self.retry_with_different_keys(_answer)

    def process_theme(self, theme, length_mode='moyen', language='en', mode='general'):
        """Traite un thème complet avec support multilingue et mode spécifique"""
        print(f"\n🚀 DÉBUT DU TRAITEMENT: '{theme}' (longueur: {length_mode}, langue: {language}, mode: {mode})")
        self.stats['requests'] += 1
        start_time = time.time()
        
        if not theme or len(theme.strip()) < 2:
            return {
                'success': False,
                'error': 'Le thème doit contenir au moins 2 caractères'
            }
        
        theme = theme.strip()
        
        # Configurer Wikipedia pour la langue demandée
        lang_code = {'en': 'en', 'fr': 'fr', 'es': 'es'}.get(language, 'en')
        self.setup_wikipedia_language(lang_code)
        
        # Vérifier le cache
        cache_key = self.get_cache_key(theme, length_mode, language, mode)
        if cache_key in self.cache:
            print("💾 Résultat trouvé en cache")
            self.stats['cache_hits'] += 1
            return self.cache[cache_key]
        
        try:
            wiki_data = self.smart_wikipedia_search(theme)
            
            if not wiki_data:
                print(f"🤖 Génération directe avec Mistral pour: {theme}")
                mistral_response = self.answer_with_mistral_only(theme, length_mode, language, mode)
                
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
                    'length_mode': length_mode,
                    'language': language,
                    'mode': mode
                }
                
                self.stats['mistral_only'] += 1
                
            else:
                print(f"📖 Résumé Wikipedia pour: {wiki_data['title']}")
                summary = self.summarize_with_mistral(wiki_data['title'], wiki_data['content'], length_mode, language, mode)
                
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
                    'length_mode': length_mode,
                    'language': language,
                    'mode': mode
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
    """Page d'accueil avec l'interface en plein écran"""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wikipedia Summarizer Pro</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #f8fafc;
            --bg-secondary: #e2e8f0;
            --bg-tertiary: #ffffff;
            --text-primary: #1a202c;
            --text-secondary: #4a5568;
            --accent: #667eea;
            --accent-secondary: #764ba2;
            --border: #e2e8f0;
            --shadow: rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] {
            --bg-primary: #1a202c;
            --bg-secondary: #2d3748;
            --bg-tertiary: #4a5568;
            --text-primary: #f7fafc;
            --text-secondary: #e2e8f0;
            --border: #4a5568;
            --shadow: rgba(0, 0, 0, 0.3);
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            transition: all 0.3s ease;
        }
        
        [data-theme="light"] body {
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            color: white;
        }
        
        .top-header {
            position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.3);
            padding: 15px 30px;
            display: flex; justify-content: space-between; align-items: center;
        }
        
        [data-theme="dark"] .top-header {
            background: rgba(26, 32, 44, 0.9);
            border-bottom: 1px solid var(--border);
        }
        
        .back-button {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 15px; padding: 10px 20px; 
            color: var(--text-primary); text-decoration: none;
            display: flex; align-items: center; gap: 10px; 
            font-weight: 600; font-size: 0.9rem;
            transition: all 0.3s ease;
            box-shadow: 0 2px 10px var(--shadow);
        }
        
        [data-theme="light"] .back-button {
            background: rgba(255, 255, 255, 0.3);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }
        
        .back-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px var(--shadow);
        }
        
        .header-controls {
            display: flex; gap: 15px; align-items: center;
        }
        
        .language-selector {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 15px; padding: 10px 15px; 
            cursor: pointer; font-size: 0.9rem;
            color: var(--text-primary); 
            transition: all 0.2s ease;
            box-shadow: 0 2px 10px var(--shadow);
        }
        
        [data-theme="light"] .language-selector {
            background: rgba(255, 255, 255, 0.3);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }
        
        .language-selector:hover { 
            transform: translateY(-2px);
            box-shadow: 0 8px 20px var(--shadow);
        }
        
        .theme-toggle {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 15px; padding: 12px; 
            cursor: pointer; font-size: 1.2rem; 
            transition: all 0.2s ease;
            color: var(--text-primary);
            box-shadow: 0 2px 10px var(--shadow);
        }
        
        [data-theme="light"] .theme-toggle {
            background: rgba(255, 255, 255, 0.3);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }
        
        .theme-toggle:hover { 
            transform: translateY(-2px);
            box-shadow: 0 8px 20px var(--shadow);
        }
        
        .author-link {
            font-size: 0.85rem; 
            color: var(--text-primary); 
            text-decoration: none;
            font-weight: 500; 
            transition: all 0.2s ease;
            opacity: 0.8;
        }
        
        [data-theme="light"] .author-link {
            color: white;
        }
        
        .author-link:hover { 
            opacity: 1; 
            transform: translateY(-1px); 
        }
        
        .container {
            flex: 1; padding: 100px 30px 30px; max-width: 1200px; margin: 0 auto; width: 100%;
            display: flex; flex-direction: column; gap: 30px;
        }
        
        .title-section {
            text-align: center; margin-bottom: 20px;
        }
        
        .title {
            font-size: 2.5rem; font-weight: 700; margin-bottom: 10px; color: white;
            text-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        
        [data-theme="dark"] .title {
            color: var(--text-primary);
            text-shadow: none;
        }
        
        .subtitle { 
            color: rgba(255,255,255,0.9); 
            font-size: 1.1rem; 
        }
        
        [data-theme="dark"] .subtitle {
            color: var(--text-secondary);
        }
        
        .stats {
            display: flex; justify-content: center; gap: 20px; margin-bottom: 30px; flex-wrap: wrap;
        }
        
        .stat-item {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            padding: 10px 20px; border-radius: 15px;
            font-size: 0.9rem; color: rgba(255,255,255,0.95);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .stat-item {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .form-section {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 25px; padding: 30px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .form-section {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            backdrop-filter: none;
        }
        
        .form-group { margin-bottom: 25px; }
        
        .label {
            display: block; color: white; font-weight: 600; margin-bottom: 12px; font-size: 1rem;
        }
        
        [data-theme="dark"] .label {
            color: var(--text-primary);
        }
        
        .input {
            width: 100%; padding: 18px 24px; 
            background: rgba(255, 255, 255, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.4);
            border-radius: 20px; font-size: 1rem; color: white; outline: none; 
            transition: all 0.3s ease;
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .input {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .input:focus {
            background: rgba(255, 255, 255, 0.4);
            border-color: rgba(255, 255, 255, 0.6);
            box-shadow: 0 0 0 3px rgba(255,255,255,0.2);
        }
        
        [data-theme="dark"] .input:focus {
            background: var(--bg-secondary);
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
        }
        
        .input::placeholder { color: rgba(255,255,255,0.8); }
        
        [data-theme="dark"] .input::placeholder {
            color: var(--text-secondary);
        }
        
        .length-selector { display: flex; gap: 15px; flex-wrap: wrap; }
        
        .length-btn {
            background: rgba(255, 255, 255, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 15px; padding: 12px 20px; font-size: 0.9rem; 
            color: rgba(255,255,255,0.9);
            cursor: pointer; transition: all 0.2s ease; flex: 1; min-width: 150px;
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .length-btn {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .length-btn:hover { 
            transform: translateY(-2px); 
            background: rgba(255, 255, 255, 0.35);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .length-btn:hover {
            background: var(--bg-secondary);
            box-shadow: 0 8px 25px var(--shadow);
        }
        
        .length-btn.active {
            background: rgba(255, 255, 255, 0.5); 
            color: white; 
            border-color: rgba(255, 255, 255, 0.6);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
        }
        
        [data-theme="dark"] .length-btn.active {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }
        
        .mode-selector { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
        
        .mode-chip {
            background: rgba(255, 255, 255, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 12px; padding: 8px 14px; font-size: 0.8rem; 
            color: rgba(255,255,255,0.9);
            cursor: pointer; transition: all 0.2s ease;
            backdrop-filter: blur(20px);
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .mode-chip {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .mode-chip:hover { 
            transform: translateY(-1px); 
            background: rgba(255, 255, 255, 0.35);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .mode-chip:hover {
            background: var(--bg-secondary);
            box-shadow: 0 4px 15px var(--shadow);
        }
        
        .mode-chip.active {
            background: rgba(255, 255, 255, 0.5); 
            color: white; transform: translateY(-1px);
            border-color: rgba(255, 255, 255, 0.6);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
        }
        
        [data-theme="dark"] .mode-chip.active {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }
        
        .suggestions { margin-top: 15px; }
        .suggestion-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
        
        .chip {
            background: rgba(255, 255, 255, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 20px; padding: 8px 16px; font-size: 0.8rem; 
            color: rgba(255,255,255,0.95);
            cursor: pointer; transition: all 0.2s ease;
            backdrop-filter: blur(20px);
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .chip {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .chip:hover {
            background: rgba(255, 255, 255, 0.4); 
            color: white; transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .chip:hover {
            background: var(--bg-secondary);
            color: var(--text-primary);
            box-shadow: 0 6px 20px var(--shadow);
        }
        
        .btn {
            background: rgba(255, 255, 255, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 20px; padding: 18px 36px; font-size: 1.1rem; font-weight: 600;
            color: rgba(255,255,255,0.95); cursor: pointer; transition: all 0.2s ease;
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .btn {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .btn:hover:not(:disabled) {
            transform: translateY(-2px); 
            background: rgba(255, 255, 255, 0.35);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .btn:hover:not(:disabled) {
            background: var(--bg-secondary);
            box-shadow: 0 8px 25px var(--shadow);
        }
        
        .btn:active { transform: translateY(0); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        
        .btn-primary {
            background: rgba(255, 255, 255, 0.4); 
            color: white;
            border-color: rgba(255, 255, 255, 0.5);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .btn-primary {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }
        
        .btn-primary:hover:not(:disabled) {
            background: rgba(255, 255, 255, 0.5);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }
        
        [data-theme="dark"] .btn-primary:hover:not(:disabled) {
            background: #5a6fd8;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
        }
        
        .controls {
            display: flex; justify-content: center; align-items: center;
            flex-wrap: wrap; gap: 15px;
        }
        
        .status {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 20px;
            padding: 25px; display: none;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .status {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            backdrop-filter: none;
        }
        
        .status.active { display: block; animation: slideDown 0.3s ease; }
        
        .status-text {
            color: white; font-weight: 500; margin-bottom: 15px;
            display: flex; align-items: center;
        }
        
        [data-theme="dark"] .status-text {
            color: var(--text-primary);
        }
        
        .progress-bar {
            width: 100%; height: 8px; 
            background: rgba(255, 255, 255, 0.3); border-radius: 10px; overflow: hidden;
        }
        
        [data-theme="dark"] .progress-bar {
            background: var(--bg-primary);
        }
        
        .progress-fill {
            height: 100%; border-radius: 10px; width: 0%; transition: width 0.3s ease;
            background: linear-gradient(90deg, rgba(255,255,255,0.9), rgba(255,255,255,0.7));
        }
        
        [data-theme="dark"] .progress-fill {
            background: linear-gradient(90deg, var(--accent), #5a6fd8);
        }
        
        .result {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 25px;
            padding: 30px; display: none; position: relative;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .result {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            backdrop-filter: none;
        }
        
        .result.active { display: block; animation: slideUp 0.5s ease; }
        
        .result-header {
            display: flex; justify-content: space-between; align-items: flex-start;
            margin-bottom: 15px;
        }
        
        .result-title {
            color: white; font-size: 1.3rem; font-weight: 600;
            padding-bottom: 15px; border-bottom: 2px solid rgba(255, 255, 255, 0.3);
            flex: 1; margin-right: 20px;
        }
        
        [data-theme="dark"] .result-title {
            color: var(--text-primary);
            border-bottom: 2px solid var(--border);
        }
        
        .copy-btn {
            background: rgba(255, 255, 255, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 12px; padding: 10px; cursor: pointer; font-size: 1rem; 
            color: rgba(255,255,255,0.9); transition: all 0.2s ease;
            backdrop-filter: blur(20px);
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .copy-btn {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .copy-btn:hover {
            transform: translateY(-2px); color: white; 
            background: rgba(255, 255, 255, 0.35);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .copy-btn:hover {
            background: var(--bg-secondary);
            color: var(--text-primary);
            box-shadow: 0 6px 20px var(--shadow);
        }
        
        .copy-btn.success { color: #4ade80; }
        
        .result-meta { color: rgba(255,255,255,0.9); font-size: 0.9rem; margin-bottom: 20px; }
        
        [data-theme="dark"] .result-meta {
            color: var(--text-secondary);
        }
        
        .result-content { color: rgba(255,255,255,0.95); line-height: 1.7; font-size: 1rem; }
        
        [data-theme="dark"] .result-content {
            color: var(--text-primary);
        }
        
        .result-content p { margin-bottom: 15px; }
        .result-content strong { color: white; font-weight: 600; }
        
        [data-theme="dark"] .result-content strong {
            color: var(--text-primary);
        }
        
        .result-content em { font-style: italic; color: rgba(255,255,255,0.98); }
        
        [data-theme="dark"] .result-content em {
            color: var(--text-secondary);
        }
        
        .result-url {
            margin-top: 20px; padding: 15px; border-radius: 15px;
            background: rgba(255, 255, 255, 0.2); 
            border-left: 4px solid rgba(255,255,255,0.6);
        }
        
        [data-theme="dark"] .result-url {
            background: var(--bg-primary);
            border-left: 4px solid var(--accent);
        }
        
        .result-url a {
            color: rgba(255,255,255,0.95); text-decoration: none; font-weight: 500; word-break: break-all;
        }
        
        [data-theme="dark"] .result-url a {
            color: var(--text-primary);
        }
        
        .result-url a:hover { color: white; text-decoration: underline; }
        
        [data-theme="dark"] .result-url a:hover {
            color: var(--accent);
        }
        
        .loading {
            display: inline-block; width: 20px; height: 20px; margin-right: 10px;
            border: 3px solid rgba(255,255,255,0.4); border-radius: 50%;
            border-top-color: white; animation: spin 1s ease-in-out infinite;
        }
        
        [data-theme="dark"] .loading {
            border: 3px solid var(--text-secondary);
            border-top-color: var(--accent);
        }
        
        .modal {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); display: none; align-items: center; justify-content: center;
            z-index: 1000; backdrop-filter: blur(10px);
        }
        
        .modal.active { display: flex; animation: fadeIn 0.3s ease; }
        
        .modal-content {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(25px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 25px; padding: 40px;
            max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto;
            position: relative;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }
        
        [data-theme="dark"] .modal-content {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            backdrop-filter: none;
        }
        
        .modal-close {
            position: absolute; top: 20px; right: 20px; background: none;
            border: none; font-size: 1.5rem; cursor: pointer; 
            color: rgba(255,255,255,0.9);
            transition: color 0.2s ease;
        }
        
        [data-theme="dark"] .modal-close {
            color: var(--text-primary);
        }
        
        .modal-close:hover { color: white; }
        
        [data-theme="dark"] .modal-close:hover {
            color: var(--accent);
        }
        
        .modal h2 {
            color: white; font-size: 1.8rem; margin-bottom: 20px;
        }
        
        [data-theme="dark"] .modal h2 {
            color: var(--text-primary);
        }
        
        .modal p {
            color: rgba(255,255,255,0.95); line-height: 1.6; margin-bottom: 15px;
        }
        
        [data-theme="dark"] .modal p {
            color: var(--text-primary);
        }
        
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        
        .notification {
            position: fixed; top: 90px; right: 20px; padding: 15px 25px;
            border-radius: 15px; color: white; font-weight: 500; z-index: 1000;
            transform: translateX(400px); transition: all 0.3s ease;
            backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.3);
        }
        
        .notification.show { transform: translateX(0); }
        .notification.error { background: rgba(239, 68, 68, 0.9); }
        .notification.success { background: rgba(34, 197, 94, 0.9); }
        .notification.info { background: rgba(59, 130, 246, 0.9); }
        
        @media (max-width: 768px) {
            .top-header { padding: 15px 20px; flex-direction: column; gap: 15px; }
            .header-controls { width: 100%; justify-content: space-between; }
            .container { padding: 140px 20px 20px; }
            .title { font-size: 2rem; }
            .stats { gap: 10px; }
            .stat-item { padding: 8px 15px; font-size: 0.8rem; }
            .length-selector { flex-direction: column; gap: 10px; }
            .length-btn { min-width: auto; }
            .mode-selector { justify-content: center; }
            .controls { flex-direction: column; gap: 10px; }
            .btn { width: 100%; }
            .result-header { flex-direction: column; align-items: flex-start; }
            .result-title { margin-right: 0; margin-bottom: 15px; }
            .modal-content { padding: 25px 20px; }
        }
    </style>
</head>
<body>
    <!-- Header fixe avec bouton retour -->
    <div class="top-header">
        <a href="/" class="back-button">
            <span>←</span>
            <span data-text-key="back_to_hub">Retour au Hub</span>
        </a>
        
        <div class="header-controls">
            <select class="language-selector" id="languageSelector" onchange="changeLanguage()">
                <option value="en">🇺🇸 English</option>
                <option value="fr">🇫🇷 Français</option>
                <option value="es">🇪🇸 Español</option>
            </select>
            
            <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()">🌙</button>
            <a href="#" class="author-link" onclick="showAuthorModal()" data-text-key="by_mydd">by Mydd</a>
        </div>
    </div>

    <div class="container">
        <div class="title-section">
            <h1 class="title" data-text-key="title">Wikipedia Summarizer Pro</h1>
            <p class="subtitle" data-text-key="subtitle">Smart summaries with Mistral AI</p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-item">📊 <span id="totalRequests">0</span> <span data-text-key="requests">requests</span></div>
            <div class="stat-item">💾 <span id="cacheHits">0</span> <span data-text-key="cached">cached</span></div>
            <div class="stat-item">📖 <span id="wikiSuccess">0</span> <span data-text-key="wikipedia">Wikipedia</span></div>
            <div class="stat-item">🤖 <span id="aiOnly">0</span> <span data-text-key="ai_only">AI only</span></div>
        </div>

        <div class="form-section">
            <form id="summarizerForm" onsubmit="handleFormSubmit(event)">
                <div class="form-group">
                    <label class="label" for="theme">🔍 <span data-text-key="search_theme">Theme to search</span></label>
                    <input type="text" id="theme" class="input" 
                           data-placeholder-key="search_placeholder" required>
                    
                    <div class="suggestions">
                        <span style="color: rgba(255,255,255,0.9); font-size: 0.9rem;">💡 <span data-text-key="popular_suggestions">Popular suggestions:</span></span>
                        <div class="suggestion-chips" id="suggestionChips"></div>
                    </div>
                </div>

                <div class="form-group">
                    <label class="label">📏 <span data-text-key="summary_length">Summary length</span></label>
                    <div class="length-selector">
                        <button type="button" class="length-btn" onclick="selectLength('court', this)">
                            📝 <span data-text-key="short">Short</span><br><small><span data-text-key="short_desc">150-200 words</span></small>
                        </button>
                        <button type="button" class="length-btn active" onclick="selectLength('moyen', this)">
                            📄 <span data-text-key="medium">Medium</span><br><small><span data-text-key="medium_desc">250-350 words</span></small>
                        </button>
                        <button type="button" class="length-btn" onclick="selectLength('long', this)">
                            📚 <span data-text-key="long">Long</span><br><small><span data-text-key="long_desc">400-500 words</span></small>
                        </button>
                    </div>
                </div>

                <div class="form-group">
                    <label class="label">🎯 <span data-text-key="summary_mode">Summary mode</span> <small style="opacity: 0.8;">(<span data-text-key="optional">optional</span>)</small></label>
                    <div class="mode-selector">
                        <button type="button" class="mode-chip active" onclick="selectMode('general', this)">
                            📋 <span data-text-key="mode_general">General</span>
                        </button>
                        <button type="button" class="mode-chip" onclick="selectMode('historique', this)">
                            ⏳ <span data-text-key="mode_historical">Historical</span>
                        </button>
                        <button type="button" class="mode-chip" onclick="selectMode('scientifique', this)">
                            🔬 <span data-text-key="mode_scientific">Scientific</span>
                        </button>
                        <button type="button" class="mode-chip" onclick="selectMode('biographique', this)">
                            👤 <span data-text-key="mode_biographical">Biographical</span>
                        </button>
                        <button type="button" class="mode-chip" onclick="selectMode('scolaire', this)">
                            🎓 <span data-text-key="mode_educational">Educational</span>
                        </button>
                        <button type="button" class="mode-chip" onclick="selectMode('culture', this)">
                            🎭 <span data-text-key="mode_cultural">Cultural</span>
                        </button>
                        <button type="button" class="mode-chip" onclick="selectMode('faits', this)">
                            ⚡ <span data-text-key="mode_key_facts">Key Facts</span>
                        </button>
                    </div>
                </div>

                <div class="controls">
                    <button type="submit" class="btn btn-primary" id="generateBtn">
                        ✨ <span data-text-key="generate">Generate summary</span>
                    </button>
                    <button type="button" class="btn" onclick="clearAll()">
                        🗑️ <span data-text-key="clear">Clear</span>
                    </button>
                </div>
            </form>
        </div>

        <div id="status" class="status">
            <div class="status-text">
                <span class="loading"></span>
                <span id="statusText" data-text-key="processing">Processing...</span>
            </div>
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
        </div>

        <div id="result" class="result">
            <div class="result-header">
                <div class="result-title" id="resultTitle">📖 <span data-text-key="generated_summary">Generated summary</span></div>
                <button class="copy-btn" id="copyBtn" onclick="copyResult()" title="Copy to clipboard">
                    📋
                </button>
            </div>
            <div class="result-meta" id="resultMeta">Source: Wikipedia • 2.3s • Medium</div>
            <div class="result-content" id="resultContent"></div>
            <div id="resultUrl" class="result-url" style="display: none;">
                <strong>🔗 <span data-text-key="wikipedia_source">Wikipedia Source:</span></strong><br>
                <a href="#" target="_blank" id="wikiLink"></a>
            </div>
        </div>
    </div>

    <!-- Author Modal -->
    <div id="authorModal" class="modal">
        <div class="modal-content">
            <button class="modal-close" onclick="hideAuthorModal()">×</button>
            <h2 data-text-key="about_author">About the Author</h2>
            <p data-text-key="author_intro">Hi! I'm Mydd, and I'm 16 years old.</p>
            <p data-text-key="author_student">I'm still a student, passionate about technology and artificial intelligence.</p>
            <p data-text-key="author_motivation">I created this project because I believe it's important to have reliable sources and that ideas should be well explained, without errors.</p>
            <p data-text-key="author_mission">My goal is to make information more accessible to everyone through intelligent tools that combine the reliability of Wikipedia with the power of AI.</p>
            <p data-text-key="author_thanks">Thank you for using Wikipedia Summarizer Pro!</p>
        </div>
    </div>

    <script>
        let isProcessing = false;
        let currentLength = 'moyen';
        let currentLanguage = 'en';
        let currentTheme = 'light';
        let currentMode = 'general';
        
        // Translations object
        const translations = {
            en: {
                title: "Wikipedia Summarizer Pro",
                subtitle: "Smart summaries with Mistral AI",
                back_to_hub: "Back to Hub",
                search_theme: "Theme to search",
                search_placeholder: "Artificial intelligence, Paris, Einstein...",
                popular_suggestions: "Popular suggestions:",
                summary_length: "Summary length",
                summary_mode: "Summary mode",
                optional: "optional",
                short: "Short",
                medium: "Medium",
                long: "Long",
                short_desc: "150-200 words",
                medium_desc: "250-350 words", 
                long_desc: "400-500 words",
                mode_general: "General",
                mode_historical: "Historical",
                mode_scientific: "Scientific",
                mode_biographical: "Biographical",
                mode_educational: "Educational",
                mode_cultural: "Cultural",
                mode_key_facts: "Key Facts",
                generate: "Generate summary",
                clear: "Clear",
                processing: "Processing...",
                generated_summary: "Generated summary",
                wikipedia_source: "Wikipedia Source:",
                requests: "requests",
                cached: "cached",
                wikipedia: "Wikipedia",
                ai_only: "AI only",
                by_mydd: "by Mydd",
                about_author: "About the Author",
                author_intro: "Hi! I'm Mydd, and I'm 16 years old.",
                author_student: "I'm still a student, passionate about technology and artificial intelligence.",
                author_motivation: "I created this project because I believe it's important to have reliable sources and that ideas should be well explained, without errors.",
                author_mission: "My goal is to make information more accessible to everyone through intelligent tools that combine the reliability of Wikipedia with the power of AI.",
                author_thanks: "Thank you for using Wikipedia Summarizer Pro!",
                searching: "Searching...",
                generating: "Generating...",
                completed: "Completed!",
                copied: "Copied!",
                copy_error: "Copy failed",
                processing_theme: "Processing in progress...",
                already_processing: "A process is already running...",
                invalid_theme: "Please enter a valid theme (minimum 2 characters)",
                summary_generated: "Summary generated!",
                processing_error: "Processing error"
            },
            fr: {
                title: "Wikipedia Summarizer Pro",
                subtitle: "Résumés intelligents avec Mistral AI",
                back_to_hub: "Retour au Hub",
                search_theme: "Thème à rechercher",
                search_placeholder: "Intelligence artificielle, Paris, Einstein...",
                popular_suggestions: "Suggestions populaires:",
                summary_length: "Longueur du résumé",
                summary_mode: "Mode de résumé",
                optional: "optionnel",
                short: "Court",
                medium: "Moyen", 
                long: "Long",
                short_desc: "150-200 mots",
                medium_desc: "250-350 mots",
                long_desc: "400-500 mots",
                mode_general: "Général",
                mode_historical: "Historique",
                mode_scientific: "Scientifique",
                mode_biographical: "Biographique",
                mode_educational: "Scolaire",
                mode_cultural: "Culturel",
                mode_key_facts: "Faits Clés",
                generate: "Générer le résumé",
                clear: "Effacer",
                processing: "Traitement en cours...",
                generated_summary: "Résumé généré",
                wikipedia_source: "Source Wikipedia:",
                requests: "requêtes",
                cached: "en cache",
                wikipedia: "Wikipedia",
                ai_only: "IA seule",
                by_mydd: "by Mydd",
                about_author: "À propos de l'auteur",
                author_intro: "Salut ! Je suis Mydd, et j'ai 16 ans.",
                author_student: "Je suis encore étudiant, passionné par la technologie et l'intelligence artificielle.",
                author_motivation: "J'ai créé ce projet parce que je pense qu'il est important d'avoir des sources fiables et que les idées soient bien expliquées, sans erreurs.",
                author_mission: "Mon objectif est de rendre l'information plus accessible à tous grâce à des outils intelligents qui combinent la fiabilité de Wikipedia avec la puissance de l'IA.",
                author_thanks: "Merci d'utiliser Wikipedia Summarizer Pro !",
                searching: "Recherche en cours...",
                generating: "Génération...",
                completed: "Terminé !",
                copied: "Copié !",
                copy_error: "Échec de la copie",
                processing_theme: "Traitement en cours...",
                already_processing: "Un traitement est déjà en cours...",
                invalid_theme: "Veuillez entrer un thème valide (minimum 2 caractères)",
                summary_generated: "Résumé généré !",
                processing_error: "Erreur de traitement"
            },
            es: {
                title: "Wikipedia Summarizer Pro", 
                subtitle: "Resúmenes inteligentes con Mistral AI",
                back_to_hub: "Volver al Hub",
                search_theme: "Tema a buscar",
                search_placeholder: "Inteligencia artificial, París, Einstein...",
                popular_suggestions: "Sugerencias populares:",
                summary_length: "Longitud del resumen",
                summary_mode: "Modo de resumen",
                optional: "opcional",
                short: "Corto",
                medium: "Medio",
                long: "Largo", 
                short_desc: "150-200 palabras",
                medium_desc: "250-350 palabras",
                long_desc: "400-500 palabras",
                mode_general: "General",
                mode_historical: "Histórico",
                mode_scientific: "Científico",
                mode_biographical: "Biográfico",
                mode_educational: "Educativo",
                mode_cultural: "Cultural",
                mode_key_facts: "Datos Clave",
                generate: "Generar resumen",
                clear: "Limpiar",
                processing: "Procesando...",
                generated_summary: "Resumen generado",
                wikipedia_source: "Fuente Wikipedia:",
                requests: "solicitudes",
                cached: "en caché", 
                wikipedia: "Wikipedia",
                ai_only: "Solo IA",
                by_mydd: "by Mydd",
                about_author: "Acerca del Autor",
                author_intro: "¡Hola! Soy Mydd, y tengo 16 años.",
                author_student: "Todavía soy estudiante, apasionado por la tecnología y la inteligencia artificial.",
                author_motivation: "Creé este proyecto porque creo que es importante tener fuentes confiables y que las ideas estén bien explicadas, sin errores.",
                author_mission: "Mi objetivo es hacer la información más accesible para todos a través de herramientas inteligentes que combinan la confiabilidad de Wikipedia con el poder de la IA.",
                author_thanks: "¡Gracias por usar Wikipedia Summarizer Pro!",
                searching: "Buscando...",
                generating: "Generando...",
                completed: "¡Completado!",
                copied: "¡Copiado!",
                copy_error: "Error al copiar",
                processing_theme: "Procesamiento en curso...",
                already_processing: "Ya hay un proceso en ejecución...",
                invalid_theme: "Por favor ingrese un tema válido (mínimo 2 caracteres)",
                summary_generated: "¡Resumen generado!",
                processing_error: "Error de procesamiento"
            }
        };

        const popularThemes = {
            en: ["Artificial Intelligence", "Climate Change", "Einstein", "French Revolution", "Marie Curie", "Paris", "Photosynthesis", "Bitcoin", "Solar System"],
            fr: ["Intelligence artificielle", "Réchauffement climatique", "Einstein", "Révolution française", "Marie Curie", "Paris", "Photosynthèse", "Bitcoin", "Système solaire"],
            es: ["Inteligencia Artificial", "Cambio Climático", "Einstein", "Revolución Francesa", "Marie Curie", "París", "Fotosíntesis", "Bitcoin", "Sistema Solar"]
        };

        document.addEventListener('DOMContentLoaded', function() {
            initializeApp();
        });

        function initializeApp() {
            loadTheme();
            loadLanguage();
            initializeSuggestions();
            loadStats();
            updateTranslations();
            const themeInput = document.getElementById('theme');
            if (themeInput) themeInput.focus();
        }

        function loadTheme() {
            const savedTheme = localStorage.getItem('theme') || 'light';
            currentTheme = savedTheme;
            document.documentElement.setAttribute('data-theme', savedTheme);
            updateThemeToggle();
        }

        function loadLanguage() {
            const savedLanguage = localStorage.getItem('language') || 'en';
            currentLanguage = savedLanguage;
            document.getElementById('languageSelector').value = savedLanguage;
            updateTranslations();
        }

        function toggleTheme() {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', currentTheme);
            localStorage.setItem('theme', currentTheme);
            updateThemeToggle();
        }

        function updateThemeToggle() {
            const toggle = document.getElementById('themeToggle');
            if (toggle) {
                toggle.textContent = currentTheme === 'light' ? '🌙' : '☀️';
            }
        }

        function changeLanguage() {
            const selector = document.getElementById('languageSelector');
            currentLanguage = selector.value;
            localStorage.setItem('language', currentLanguage);
            updateTranslations();
            initializeSuggestions();
        }

        function updateTranslations() {
            const elements = document.querySelectorAll('[data-text-key]');
            elements.forEach(element => {
                const key = element.getAttribute('data-text-key');
                if (translations[currentLanguage] && translations[currentLanguage][key]) {
                    element.textContent = translations[currentLanguage][key];
                }
            });

            // Update placeholder
            const themeInput = document.getElementById('theme');
            if (themeInput && translations[currentLanguage].search_placeholder) {
                themeInput.placeholder = translations[currentLanguage].search_placeholder;
            }
        }

        function selectLength(length, element) {
            document.querySelectorAll('.length-btn').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            currentLength = length;
        }

        function selectMode(mode, element) {
            document.querySelectorAll('.mode-chip').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            currentMode = mode;
        }

        function showAuthorModal() {
            document.getElementById('authorModal').classList.add('active');
        }

        function hideAuthorModal() {
            document.getElementById('authorModal').classList.remove('active');
        }

        function copyResult() {
            const content = document.getElementById('resultContent');
            const copyBtn = document.getElementById('copyBtn');
            
            if (!content || !content.textContent) {
                showNotification(translations[currentLanguage].copy_error, 'error');
                return;
            }

            const textContent = content.textContent || content.innerText;
            
            navigator.clipboard.writeText(textContent).then(function() {
                copyBtn.textContent = '✅';
                copyBtn.classList.add('success');
                showNotification(translations[currentLanguage].copied, 'success');
                
                setTimeout(() => {
                    copyBtn.textContent = '📋';
                    copyBtn.classList.remove('success');
                }, 2000);
            }).catch(function() {
                showNotification(translations[currentLanguage].copy_error, 'error');
            });
        }

        function handleFormSubmit(event) {
            event.preventDefault();
            
            if (isProcessing) {
                showNotification(translations[currentLanguage].already_processing, 'info');
                return false;
            }

            const themeInput = document.getElementById('theme');
            const theme = themeInput ? themeInput.value.trim() : '';
            
            if (!theme || theme.length < 2) {
                showNotification(translations[currentLanguage].invalid_theme, 'error');
                if (themeInput) themeInput.focus();
                return false;
            }

            processTheme(theme, currentLength, currentLanguage, currentMode);
            return false;
        }

        function initializeSuggestions() {
            const container = document.getElementById('suggestionChips');
            if (!container) return;
            
            container.innerHTML = '';
            const themes = popularThemes[currentLanguage] || popularThemes.en;
            const shuffled = [...themes].sort(() => 0.5 - Math.random()).slice(0, 6);
            
            shuffled.forEach(theme => {
                const chip = document.createElement('button');
                chip.className = 'chip';
                chip.textContent = theme;
                chip.type = 'button';
                chip.onclick = function() {
                    const themeInput = document.getElementById('theme');
                    if (themeInput) {
                        themeInput.value = theme;
                        themeInput.focus();
                    }
                };
                container.appendChild(chip);
            });
        }

        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                if (response.ok) {
                    const stats = await response.json();
                    updateStatsDisplay(stats);
                }
            } catch (error) {
                console.log('Stats error:', error);
            }
        }

        function updateStatsDisplay(stats) {
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
        }

        async function processTheme(theme, lengthMode, language, mode) {
            isProcessing = true;
            const generateBtn = document.getElementById('generateBtn');
            const generateText = generateBtn.querySelector('[data-text-key="generate"]');
            
            if (generateBtn) {
                generateBtn.disabled = true;
                if (generateText) generateText.textContent = translations[currentLanguage].processing_theme;
            }
            
            showStatus(translations[currentLanguage].searching);
            hideResult();

            try {
                const requestData = {
                    theme: theme,
                    length_mode: lengthMode,
                    language: language,
                    mode: mode
                };
                
                updateProgress(20);
                updateStatus(translations[currentLanguage].searching);
                
                const response = await fetch('/api/summarize', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });

                updateProgress(60);
                updateStatus(translations[currentLanguage].generating);

                if (!response.ok) {
                    let errorMessage = `HTTP Error ${response.status}`;
                    try {
                        const errorData = await response.json();
                        errorMessage = errorData.error || errorMessage;
                    } catch (e) {
                        const errorText = await response.text();
                        errorMessage = errorText || errorMessage;
                    }
                    throw new Error(errorMessage);
                }

                const data = await response.json();

                if (!data.success) {
                    throw new Error(data.error || 'Unknown error');
                }

                updateProgress(100);
                updateStatus(translations[currentLanguage].completed);
                await sleep(500);

                showResult(data);
                hideStatus();
                
                setTimeout(loadStats, 500);
                showNotification(translations[currentLanguage].summary_generated, 'success');

            } catch (error) {
                console.error('Error:', error);
                showNotification(error.message || translations[currentLanguage].processing_error, 'error');
                hideStatus();
            } finally {
                isProcessing = false;
                if (generateBtn && generateText) {
                    generateBtn.disabled = false;
                    generateText.textContent = translations[currentLanguage].generate;
                }
            }
        }

        function updateProgress(percent) {
            const progressFill = document.getElementById('progressFill');
            if (progressFill) progressFill.style.width = percent + '%';
        }

        function updateStatus(message) {
            const statusText = document.getElementById('statusText');
            if (statusText) statusText.textContent = message;
        }

        function showStatus(message) {
            updateStatus(message);
            const statusDiv = document.getElementById('status');
            if (statusDiv) statusDiv.classList.add('active');
            updateProgress(0);
        }

        function hideStatus() {
            const statusDiv = document.getElementById('status');
            if (statusDiv) statusDiv.classList.remove('active');
            setTimeout(() => updateProgress(0), 300);
        }

        function showResult(data) {
            const elements = {
                title: document.getElementById('resultTitle'),
                content: document.getElementById('resultContent'),
                meta: document.getElementById('resultMeta'),
                url: document.getElementById('resultUrl'),
                link: document.getElementById('wikiLink'),
                result: document.getElementById('result')
            };
            
            const titleSpan = elements.title ? elements.title.querySelector('[data-text-key="generated_summary"]') : null;
            if (titleSpan) {
                elements.title.innerHTML = '📖 <span data-text-key="generated_summary">' + translations[currentLanguage].generated_summary + '</span>';
            }
            if (elements.content) elements.content.innerHTML = data.summary;
            
            const sourceIcon = data.source === 'wikipedia' ? '📖' : '🤖';
            const sourceText = data.source === 'wikipedia' ? translations[currentLanguage].wikipedia : translations[currentLanguage].ai_only;
            
            const modeText = currentMode !== 'general' ? ` • ${currentMode}` : '';
            let metaText = `${sourceIcon} ${sourceText} • ${data.processing_time}s • ${data.length_mode}${modeText}`;
            
            if (data.method) metaText += ` • ${data.method}`;
            if (elements.meta) elements.meta.textContent = metaText;
            
            if (data.url && elements.url && elements.link) {
                const sourceSpan = elements.url.querySelector('[data-text-key="wikipedia_source"]');
                if (sourceSpan) sourceSpan.textContent = translations[currentLanguage].wikipedia_source;
                elements.link.href = data.url;
                elements.link.textContent = data.url;
                elements.url.style.display = 'block';
            } else if (elements.url) {
                elements.url.style.display = 'none';
            }

            if (elements.result) elements.result.classList.add('active');
        }

        function hideResult() {
            const resultDiv = document.getElementById('result');
            if (resultDiv) resultDiv.classList.remove('active');
        }

        function clearAll() {
            const themeInput = document.getElementById('theme');
            if (themeInput) {
                themeInput.value = '';
                themeInput.focus();
            }
            hideStatus();
            hideResult();
            isProcessing = false;
            
            currentMode = 'general';
            document.querySelectorAll('.mode-chip').forEach(btn => btn.classList.remove('active'));
            document.querySelector('.mode-chip[onclick*="general"]').classList.add('active');
            
            const generateBtn = document.getElementById('generateBtn');
            const generateText = generateBtn ? generateBtn.querySelector('[data-text-key="generate"]') : null;
            if (generateBtn) {
                generateBtn.disabled = false;
                if (generateText) generateText.textContent = translations[currentLanguage].generate;
            }
        }

        function showNotification(message, type = 'info') {
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

        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
                const target = e.target;
                if (target && target.id === 'theme' && !isProcessing && target.value.trim()) {
                    e.preventDefault();
                    handleFormSubmit(e);
                }
            }
            
            if (e.key === 'Escape') {
                hideAuthorModal();
            }
        });

        document.getElementById('authorModal').addEventListener('click', function(e) {
            if (e.target === this) {
                hideAuthorModal();
            }
        });
    </script>
</body>
</html>'''

@app.route('/api/summarize', methods=['POST'])
def summarize():
    """API endpoint pour traiter les résumés avec support multilingue et modes thématiques"""
    try:
        print("🚀 REQUÊTE /api/summarize")
        
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type doit être application/json'}), 400
        
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        theme = data.get('theme')
        length_mode = data.get('length_mode', 'moyen')
        language = data.get('language', 'en')
        mode = data.get('mode', 'general')
        
        if not theme or not theme.strip():
            return jsonify({'success': False, 'error': 'Thème requis'}), 400
        
        print(f"🚀 TRAITEMENT: '{theme}' ({length_mode}, {language}, {mode})")
        
        result = summarizer.process_theme(theme, length_mode, language, mode)
        
        if not result.get('success'):
            error_msg = result.get('error', 'Erreur inconnue')
            print(f"❌ ÉCHEC: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500
        
        print(f"✅ SUCCÈS: {result.get('title', 'Sans titre')}")
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"💥 ERREUR ENDPOINT: {error_msg}")
        return jsonify({'success': False, 'error': f'Erreur serveur: {error_msg}'}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API endpoint pour les statistiques"""
    try:
        return jsonify(summarizer.stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint pour Render"""
    return jsonify({'status': 'OK', 'service': 'Wikipedia Summarizer Pro'}), 200

if __name__ == '__main__':
    print("🌐 WIKIPEDIA SUMMARIZER PRO - VERSION ENHANCED WITH THEMATIC MODES")
    print("="*70)
    
    try:
        from mistralai import Mistral
        import wikipedia
        print("✅ Dépendances OK")
        
        # Configuration pour Render
        port = int(os.environ.get('PORT', 4000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port: {port}")
        print(f"🔧 Debug: {debug_mode}")
        print(f"🔑 Clés API configurées: {len(summarizer.api_keys)}")
        
    except ImportError as e:
        print(f"❌ ERREUR: {e}")
        exit(1)
    except Exception as e:
        print(f"⚠️ Avertissement: {e}")
    
    print("🚀 DÉMARRAGE...")
    
    # Démarrage adapté pour Render
    app.run(
        host='0.0.0.0', 
        port=port, 
        debug=debug_mode
    )
