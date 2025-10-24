from flask import Flask, request, jsonify, render_template_string
import os
import json
import logging
import time
import hashlib
import re
from datetime import datetime, timedelta
from collections import defaultdict
import traceback

# Configuration du logging DÉTAILLÉ
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS Configuration RENFORCÉE
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

# Configuration
class Config:
    # 🔑 CLÉS API - À CONFIGURER !
    API_KEYS = os.environ.get('MISTRAL_API_KEY', '').split(',') if os.environ.get('MISTRAL_API_KEY') else []
    
    # Sécurité
    MAX_CONCEPT_LENGTH = 200
    MIN_CONCEPT_LENGTH = 2
    
    # Performance
    CACHE_MAX_SIZE = 100
    
    # Mistral
    MISTRAL_MODEL_PRIMARY = "mistral-large-latest"
    MISTRAL_MODEL_FALLBACK = "mistral-small-latest"
    MISTRAL_MAX_TOKENS = 1200
    MISTRAL_TEMPERATURE = 0.7

# Vérification des clés API
if not Config.API_KEYS or Config.API_KEYS == ['']:
    logger.warning("⚠️ AUCUNE CLÉ API MISTRAL CONFIGURÉE !")
    logger.warning("⚠️ Mode DÉMO activé - Les explications seront simulées")
    logger.warning("⚠️ Pour utiliser Mistral AI, définissez: export MISTRAL_API_KEY='votre_clé'")
    DEMO_MODE = True
else:
    logger.info(f"✅ {len(Config.API_KEYS)} clé(s) API Mistral configurée(s)")
    DEMO_MODE = False

# Cache LRU simple
class LRUCache:
    def __init__(self, max_size=100):
        self.cache = {}
        self.access_order = []
        self.max_size = max_size
    
    def get(self, key):
        if key in self.cache:
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def set(self, key, value):
        if key in self.cache:
            self.access_order.remove(key)
        elif len(self.cache) >= self.max_size:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
        
        self.cache[key] = value
        self.access_order.append(key)
    
    def size(self):
        return len(self.cache)

class MathiaExplorer:
    """Explorateur mathématique avec IA Mistral"""
    
    def __init__(self):
        self.api_keys = Config.API_KEYS
        self.current_key_index = 0
        self.cache = LRUCache(max_size=Config.CACHE_MAX_SIZE)
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'concepts_explored': 0,
            'errors': 0,
            'avg_processing_time': 0
        }
        self.processing_times = []
        
        logger.info("✅ Mathia Explorer initialisé")
    
    def generate_demo_explanation(self, concept, language, detail_level):
        """Génère une explication démo quand les clés API ne sont pas configurées"""
        
        translations = {
            'fr': {
                'title': 'Explication Démo',
                'intro': f"Ceci est une explication de démonstration pour le concept : **{concept}**",
                'warning': "⚠️ Mode Démonstration",
                'warning_text': "Pour obtenir des explications réelles générées par l'IA Mistral, configurez votre clé API.",
                'definition': "Définition",
                'definition_text': f"Le concept de '{concept}' est un élément fondamental en mathématiques.",
                'explanation': "Explication",
                'explanation_text': "En mode démo, cette section contiendrait une explication détaillée générée par Mistral AI.",
                'examples': "Exemples",
                'examples_text': "Des exemples concrets seraient fournis ici avec l'IA configurée.",
                'howto': "Comment configurer l'API",
                'step1': "1. Créez un compte sur console.mistral.ai",
                'step2': "2. Générez une clé API",
                'step3': "3. Définissez la variable d'environnement: export MISTRAL_API_KEY='votre_clé'",
                'step4': "4. Redémarrez l'application"
            },
            'en': {
                'title': 'Demo Explanation',
                'intro': f"This is a demo explanation for the concept: **{concept}**",
                'warning': "⚠️ Demo Mode",
                'warning_text': "To get real AI-generated explanations from Mistral, configure your API key.",
                'definition': "Definition",
                'definition_text': f"The concept of '{concept}' is a fundamental element in mathematics.",
                'explanation': "Explanation",
                'explanation_text': "In demo mode, this section would contain a detailed explanation generated by Mistral AI.",
                'examples': "Examples",
                'examples_text': "Concrete examples would be provided here with configured AI.",
                'howto': "How to configure the API",
                'step1': "1. Create an account on console.mistral.ai",
                'step2': "2. Generate an API key",
                'step3': "3. Set environment variable: export MISTRAL_API_KEY='your_key'",
                'step4': "4. Restart the application"
            },
            'es': {
                'title': 'Explicación Demo',
                'intro': f"Esta es una explicación de demostración del concepto: **{concept}**",
                'warning': "⚠️ Modo Demostración",
                'warning_text': "Para obtener explicaciones reales generadas por IA de Mistral, configure su clave API.",
                'definition': "Definición",
                'definition_text': f"El concepto de '{concept}' es un elemento fundamental en matemáticas.",
                'explanation': "Explicación",
                'explanation_text': "En modo demo, esta sección contendría una explicación detallada generada por Mistral AI.",
                'examples': "Ejemplos",
                'examples_text': "Se proporcionarían ejemplos concretos aquí con la IA configurada.",
                'howto': "Cómo configurar la API",
                'step1': "1. Cree una cuenta en console.mistral.ai",
                'step2': "2. Genere una clave API",
                'step3': "3. Defina la variable de entorno: export MISTRAL_API_KEY='su_clave'",
                'step4': "4. Reinicie la aplicación"
            }
        }
        
        t = translations.get(language, translations['fr'])
        
        return f"""
<div style="background: rgba(255, 193, 7, 0.1); border: 2px solid rgba(255, 193, 7, 0.5); border-radius: 10px; padding: 20px; margin-bottom: 20px;">
    <h3>⚠️ {t['warning']}</h3>
    <p>{t['warning_text']}</p>
</div>

<h2>{t['title']}</h2>
<p>{t['intro']}</p>

<h3>📖 {t['definition']}</h3>
<p>{t['definition_text']}</p>

<h3>💡 {t['explanation']}</h3>
<p>{t['explanation_text']}</p>

<h3>📝 {t['examples']}</h3>
<p>{t['examples_text']}</p>

<div style="background: rgba(33, 150, 243, 0.1); border: 2px solid rgba(33, 150, 243, 0.5); border-radius: 10px; padding: 20px; margin-top: 30px;">
    <h3>🔧 {t['howto']}</h3>
    <p><strong>{t['step1']}</strong></p>
    <p><strong>{t['step2']}</strong></p>
    <p><strong>{t['step3']}</strong></p>
    <p><strong>{t['step4']}</strong></p>
</div>
"""
    
    def call_mistral_with_retry(self, prompt, max_retries=None):
        """Appelle Mistral avec retry"""
        if DEMO_MODE:
            time.sleep(1)  # Simule le délai
            return None  # Retourne None pour déclencher le mode démo
        
        try:
            from mistralai import Mistral
        except ImportError:
            logger.error("❌ Module mistralai non installé: pip install mistralai")
            return None
        
        if max_retries is None:
            max_retries = len(self.api_keys)
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                api_key = self.api_keys[self.current_key_index % len(self.api_keys)]
                self.current_key_index += 1
                
                client = Mistral(api_key=api_key)
                
                logger.info(f"🔑 Tentative {attempt + 1}/{max_retries}")
                
                response = client.chat.complete(
                    model=Config.MISTRAL_MODEL_PRIMARY,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=Config.MISTRAL_TEMPERATURE,
                    max_tokens=Config.MISTRAL_MAX_TOKENS
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                error_msg = str(e).lower()
                
                if "429" in error_msg or "capacity" in error_msg:
                    logger.warning(f"⚠️ Rate limit - Tentative fallback")
                    try:
                        response = client.chat.complete(
                            model=Config.MISTRAL_MODEL_FALLBACK,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=Config.MISTRAL_TEMPERATURE,
                            max_tokens=Config.MISTRAL_MAX_TOKENS
                        )
                        return response.choices[0].message.content.strip()
                    except Exception as fallback_error:
                        logger.warning(f"❌ Fallback échoué: {fallback_error}")
                
                last_exception = e
                logger.warning(f"❌ Erreur tentative {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        
        logger.error(f"Toutes les tentatives ont échoué: {last_exception}")
        return None
    
    def get_cache_key(self, concept, language, detail_level):
        """Génère une clé de cache unique"""
        normalized = f"{concept.lower().strip()}_{language}_{detail_level}"
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def markdown_to_html(self, text):
        """Convertit le Markdown en HTML"""
        if not text:
            return ""
        
        try:
            import markdown
            html = markdown.markdown(text, extensions=['extra', 'nl2br'])
            return html
        except:
            text = text.strip()
            text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
            
            paragraphs = text.split('\n\n')
            formatted = []
            
            for para in paragraphs:
                para = para.strip()
                if para and not para.startswith('<'):
                    para = f'<p>{para}</p>'
                if para:
                    formatted.append(para)
            
            return '\n'.join(formatted)
    
    def get_language_instruction(self, language):
        """Retourne l'instruction de langue"""
        instructions = {
            'fr': 'Réponds EXCLUSIVEMENT en français.',
            'en': 'Respond EXCLUSIVELY in English.',
            'es': 'Responde EXCLUSIVAMENTE en español.'
        }
        return instructions.get(language, instructions['fr'])
    
    def build_prompt(self, concept, language, detail_level):
        """Construit le prompt pour Mistral"""
        lang_instruction = self.get_language_instruction(language)
        
        word_counts = {
            'court': '150-200 mots',
            'moyen': '300-400 mots',
            'long': '500-600 mots'
        }
        word_count = word_counts.get(detail_level, word_counts['moyen'])
        
        prompt = f"""Tu es Mathia, un expert en mathématiques passionné par la vulgarisation.

**Concept à explorer:** "{concept}"

{lang_instruction}

**Instructions:**
Fournis une explication complète en {word_count}, structurée ainsi:

1. **DÉFINITION** (2-3 phrases)
2. **EXPLICATION DÉTAILLÉE** (plusieurs paragraphes)
3. **EXEMPLES CONCRETS** (3-5 exemples avec calculs)
4. **CONCEPTS LIÉS** (4-6 concepts connexes)
5. **IMPORTANCE** (applications réelles)
6. **CONSEIL D'APPRENTISSAGE**

Utilise le markdown pour la mise en forme. Réponds maintenant:"""
        
        return prompt
    
    def validate_concept(self, concept):
        """Valide le concept d'entrée"""
        if not concept or not isinstance(concept, str):
            return False, "Le concept doit être une chaîne de caractères"
        
        concept = concept.strip()
        
        if len(concept) < Config.MIN_CONCEPT_LENGTH:
            return False, f"Le concept doit contenir au moins {Config.MIN_CONCEPT_LENGTH} caractères"
        
        if len(concept) > Config.MAX_CONCEPT_LENGTH:
            return False, f"Le concept ne doit pas dépasser {Config.MAX_CONCEPT_LENGTH} caractères"
        
        if re.search(r'[<>{}]', concept):
            return False, "Le concept contient des caractères non autorisés"
        
        return True, concept
    
    def process_concept(self, concept, language='fr', detail_level='moyen'):
        """Traite un concept mathématique"""
        logger.info(f"🔍 Requête: '{concept}' (langue={language}, détail={detail_level})")
        self.stats['requests'] += 1
        start_time = time.time()
        
        # Validation
        is_valid, result = self.validate_concept(concept)
        if not is_valid:
            self.stats['errors'] += 1
            logger.error(f"❌ Validation échouée: {result}")
            return {'success': False, 'error': result}
        
        concept = result
        
        # Vérifier le cache
        cache_key = self.get_cache_key(concept, language, detail_level)
        cached_result = self.cache.get(cache_key)
        
        if cached_result:
            logger.info("💾 Cache HIT")
            self.stats['cache_hits'] += 1
            cached_result['from_cache'] = True
            return cached_result
        
        logger.info("🔄 Cache MISS - Génération")
        
        try:
            # Construire le prompt
            prompt = self.build_prompt(concept, language, detail_level)
            
            # Appeler Mistral
            ai_response = self.call_mistral_with_retry(prompt)
            
            # Si pas de réponse (mode démo ou erreur), générer explication démo
            if not ai_response:
                logger.info("📝 Mode DÉMO - Génération d'une explication exemple")
                formatted_response = self.generate_demo_explanation(concept, language, detail_level)
            else:
                formatted_response = self.markdown_to_html(ai_response)
            
            # Temps de traitement
            processing_time = round(time.time() - start_time, 2)
            self.processing_times.append(processing_time)
            
            if self.processing_times:
                self.stats['avg_processing_time'] = round(
                    sum(self.processing_times) / len(self.processing_times), 2
                )
            
            result = {
                'success': True,
                'concept': concept.title(),
                'explanation': formatted_response,
                'processing_time': processing_time,
                'detail_level': detail_level,
                'language': language,
                'source': 'demo' if DEMO_MODE else 'mistral_ai',
                'from_cache': False,
                'cache_size': self.cache.size(),
                'demo_mode': DEMO_MODE
            }
            
            # Mettre en cache
            self.cache.set(cache_key, result)
            self.stats['concepts_explored'] += 1
            
            logger.info(f"✅ Succès en {processing_time}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur: {str(e)}")
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
            return {
                'success': False,
                'error': f'Erreur lors du traitement: {str(e)}'
            }

# Instance globale
mathia = MathiaExplorer()

# Routes
@app.route('/')
def index():
    """Interface principale"""
    return render_template_string(MATHIA_TEMPLATE)

@app.route('/api/explore', methods=['POST', 'OPTIONS'])
def explore():
    """API d'exploration de concepts"""
    
    logger.info(f"📨 Requête {request.method} depuis {request.remote_addr}")
    
    # CORS preflight
    if request.method == 'OPTIONS':
        logger.info("✅ OPTIONS request - 204")
        return '', 204
    
    try:
        # Log des headers
        logger.debug(f"Headers: {dict(request.headers)}")
        logger.debug(f"Content-Type: {request.content_type}")
        
        # Validation du Content-Type
        if not request.is_json:
            logger.error(f"❌ Content-Type invalide: {request.content_type}")
            return jsonify({
                'success': False,
                'error': f'Content-Type doit être application/json (reçu: {request.content_type})'
            }), 400
        
        data = request.get_json()
        logger.debug(f"Données reçues: {data}")
        
        if not data:
            logger.error("❌ Corps JSON vide")
            return jsonify({
                'success': False,
                'error': 'Corps de requête JSON requis'
            }), 400
        
        # Extraction des paramètres
        concept = data.get('concept', '').strip()
        language = data.get('language', 'fr')
        detail_level = data.get('detail_level', 'moyen')
        
        logger.info(f"📝 Paramètres: concept='{concept}', langue={language}, détail={detail_level}")
        
        # Validation
        if language not in ['fr', 'en', 'es']:
            language = 'fr'
        
        if detail_level not in ['court', 'moyen', 'long']:
            detail_level = 'moyen'
        
        if not concept:
            return jsonify({
                'success': False,
                'error': 'Le paramètre "concept" est requis'
            }), 400
        
        # Traitement
        result = mathia.process_concept(concept, language, detail_level)
        
        if not result.get('success'):
            logger.error(f"❌ Échec: {result.get('error')}")
            return jsonify(result), 400  # Changé de 500 à 400
        
        logger.info(f"✅ Succès en {result.get('processing_time')}s")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"💥 Erreur serveur: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Erreur interne: {str(e)}',
            'details': traceback.format_exc() if app.debug else None
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Récupère les statistiques"""
    try:
        stats = mathia.stats.copy()
        stats['cache_size'] = mathia.cache.size()
        stats['cache_max_size'] = Config.CACHE_MAX_SIZE
        stats['demo_mode'] = DEMO_MODE
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Erreur stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'OK',
        'service': 'Mathia Explorer',
        'version': '4.2',
        'demo_mode': DEMO_MODE,
        'api_keys_configured': len(Config.API_KEYS) if not DEMO_MODE else 0,
        'cache_size': mathia.cache.size()
    }), 200

# Template HTML
MATHIA_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Explorateur Mathématique IA</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --gradient-start: #e63946;
            --gradient-end: #f77f00;
        }
        
        body {
            --bg-primary: linear-gradient(135deg, #e63946 0%, #f77f00 100%);
            --bg-secondary: rgba(255, 255, 255, 0.25);
            --bg-tertiary: rgba(255, 255, 255, 0.3);
            --text-primary: #ffffff;
            --text-secondary: rgba(255, 255, 255, 0.95);
            --text-tertiary: rgba(255, 255, 255, 0.9);
            --border-color: rgba(255, 255, 255, 0.3);
            --border-color-strong: rgba(255, 255, 255, 0.4);
            --shadow: rgba(0, 0, 0, 0.1);
            --shadow-strong: rgba(0, 0, 0, 0.15);
            --input-bg: rgba(255, 255, 255, 0.3);
            --input-border: rgba(255, 255, 255, 0.4);
            --input-focus-bg: rgba(255, 255, 255, 0.4);
            --input-focus-border: rgba(255, 255, 255, 0.6);
            --input-focus-shadow: rgba(255, 255, 255, 0.2);
            --button-bg: rgba(255, 255, 255, 0.25);
            --button-active: rgba(255, 255, 255, 0.5);
            --button-primary: rgba(255, 255, 255, 0.4);
            --placeholder-color: rgba(255, 255, 255, 0.8);
        }
        
        body[data-theme="dark"] {
            --bg-primary: #0d1b2a;
            --bg-secondary: #1b263b;
            --bg-tertiary: #415a77;
            --text-primary: #e0e1dd;
            --text-secondary: #cbd5e1;
            --text-tertiary: #94a3b8;
            --border-color: #415a77;
            --border-color-strong: #4a5f7f;
            --shadow: rgba(0, 0, 0, 0.3);
            --shadow-strong: rgba(0, 0, 0, 0.4);
            --input-bg: #0d1b2a;
            --input-border: #415a77;
            --input-focus-bg: #1b263b;
            --input-focus-border: #e63946;
            --input-focus-shadow: rgba(230, 57, 70, 0.2);
            --button-bg: #1b263b;
            --button-active: #e63946;
            --button-primary: #e63946;
            --placeholder-color: #94a3b8;
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
        
        .top-header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 1000;
            background: var(--bg-secondary);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border-color);
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 1.2rem;
            font-weight: 700;
            color: var(--text-primary);
            text-decoration: none;
        }
        
        .header-controls {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        
        .language-selector, .theme-toggle {
            background: var(--button-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            padding: 10px 15px;
            cursor: pointer;
            font-size: 0.9rem;
            color: var(--text-primary);
            transition: all 0.2s ease;
        }
        
        .theme-toggle {
            padding: 12px;
            font-size: 1.2rem;
        }
        
        .container {
            flex: 1;
            padding: 100px 30px 30px;
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 30px;
        }
        
        .title-section {
            text-align: center;
            margin-bottom: 20px;
        }
        
        .title {
            font-size: 2.8rem;
            font-weight: 700;
            margin-bottom: 10px;
            color: var(--text-primary);
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 1.15rem;
        }
        
        .stats {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        
        .stat-item {
            background: var(--bg-secondary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            padding: 10px 20px;
            border-radius: 15px;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        
        .form-section {
            background: var(--bg-secondary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 25px;
            padding: 30px;
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
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            border-radius: 20px;
            font-size: 1rem;
            color: var(--text-primary);
            outline: none;
            transition: all 0.3s ease;
        }
        
        .input:focus {
            background: var(--input-focus-bg);
            border-color: var(--input-focus-border);
            box-shadow: 0 0 0 3px var(--input-focus-shadow);
        }
        
        .input::placeholder {
            color: var(--placeholder-color);
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
            background: var(--button-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 8px 16px;
            font-size: 0.8rem;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .chip:hover {
            transform: translateY(-2px);
            background: var(--button-active);
        }
        
        .detail-selector {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .detail-btn {
            background: var(--button-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            padding: 12px 20px;
            font-size: 0.9rem;
            color: var(--text-tertiary);
            cursor: pointer;
            transition: all 0.2s ease;
            flex: 1;
            min-width: 150px;
        }
        
        .detail-btn:hover {
            transform: translateY(-2px);
        }
        
        .detail-btn.active {
            background: var(--button-active);
            color: var(--text-primary);
            border-color: var(--border-color-strong);
            font-weight: 600;
        }
        
        .controls {
            display: flex;
            justify-content: center;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }
        
        .btn {
            background: var(--button-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 18px 36px;
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .btn:hover {
            transform: translateY(-2px);
        }
        
        .btn-primary {
            background: var(--button-primary);
            color: #ffffff;
            border-color: var(--border-color-strong);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .status {
            background: var(--bg-secondary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 25px;
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
            background: var(--input-bg);
            border-radius: 10px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            border-radius: 10px;
            width: 0%;
            transition: width 0.3s ease;
            background: linear-gradient(90deg, var(--gradient-start), var(--gradient-end));
        }
        
        .result {
            background: var(--bg-secondary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 25px;
            padding: 30px;
            display: none;
        }
        
        .result.active {
            display: block;
            animation: slideUp 0.5s ease;
        }
        
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 15px;
        }
        
        .result-title {
            color: var(--text-primary);
            font-size: 1.3rem;
            font-weight: 600;
            padding-bottom: 15px;
            border-bottom: 2px solid var(--border-color);
            flex: 1;
            margin-right: 20px;
        }
        
        .copy-btn {
            background: var(--button-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 10px;
            cursor: pointer;
            font-size: 1rem;
            color: var(--text-primary);
            transition: all 0.2s ease;
        }
        
        .copy-btn:hover {
            transform: scale(1.1);
        }
        
        .result-meta {
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 20px;
        }
        
        .result-content {
            color: var(--text-primary);
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
        
        .result-content h2, .result-content h3 {
            margin-top: 20px;
            margin-bottom: 10px;
        }
        
        .cache-badge {
            display: inline-block;
            background: rgba(74, 222, 128, 0.2);
            border: 1px solid rgba(74, 222, 128, 0.4);
            color: #4ade80;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-left: 10px;
        }
        
        .demo-badge {
            display: inline-block;
            background: rgba(255, 193, 7, 0.2);
            border: 1px solid rgba(255, 193, 7, 0.4);
            color: #ffc107;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-left: 10px;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            margin-right: 10px;
            border: 3px solid var(--border-color);
            border-radius: 50%;
            border-top-color: var(--text-primary);
            animation: spin 1s ease-in-out infinite;
        }
        
        .notification {
            position: fixed;
            top: 90px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 15px;
            color: white;
            font-weight: 500;
            z-index: 1000;
            transform: translateX(400px);
            transition: all 0.3s ease;
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.error {
            background: rgba(214, 40, 40, 0.95);
        }
        
        .notification.success {
            background: rgba(34, 197, 94, 0.95);
        }
        
        .notification.info {
            background: rgba(247, 127, 0, 0.95);
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
        
        @media (max-width: 768px) {
            .top-header {
                padding: 15px 20px;
                flex-direction: column;
                gap: 15px;
            }
            
            .container {
                padding: 140px 20px 20px;
            }
            
            .title {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    <div class="top-header">
        <a href="#" class="logo" onclick="return false;">🔢 Mathia Explorer</a>
        
        <div class="header-controls">
            <select class="language-selector" id="languageSelector" onchange="changeLanguage()">
                <option value="fr">🇫🇷 Français</option>
                <option value="en">🇺🇸 English</option>
                <option value="es">🇪🇸 Español</option>
            </select>
            
            <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()">🌙</button>
        </div>
    </div>

    <div class="container">
        <div class="title-section">
            <h1 class="title" data-text-key="title">🔢 Mathia</h1>
            <p class="subtitle" data-text-key="subtitle">Explorateur de concepts mathématiques avec IA</p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-item">📊 <span id="totalRequests">0</span> <span data-text-key="requests">requêtes</span></div>
            <div class="stat-item">💾 <span id="cacheHits">0</span> <span data-text-key="cached">en cache</span></div>
            <div class="stat-item">🎯 <span id="conceptsExplored">0</span> <span data-text-key="concepts">concepts</span></div>
        </div>

        <div class="form-section">
            <form id="explorerForm" onsubmit="handleFormSubmit(event)">
                <div class="form-group">
                    <label class="label" for="concept">🔍 <span data-text-key="search_concept">Concept à explorer</span></label>
                    <input type="text" id="concept" class="input" 
                           data-placeholder-key="search_placeholder" required>
                    
                    <div class="suggestions">
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">💡 <span data-text-key="popular_suggestions">Suggestions populaires:</span></span>
                        <div class="suggestion-chips" id="suggestionChips"></div>
                    </div>
                </div>

                <div class="form-group">
                    <label class="label">📏 <span data-text-key="detail_level">Niveau de détail</span></label>
                    <div class="detail-selector">
                        <button type="button" class="detail-btn" onclick="selectDetail('court', this)">
                            📝 <span data-text-key="short">Court</span><br><small><span data-text-key="short_desc">150-200 mots</span></small>
                        </button>
                        <button type="button" class="detail-btn active" onclick="selectDetail('moyen', this)">
                            📄 <span data-text-key="medium">Moyen</span><br><small><span data-text-key="medium_desc">300-400 mots</span></small>
                        </button>
                        <button type="button" class="detail-btn" onclick="selectDetail('long', this)">
                            📚 <span data-text-key="long">Détaillé</span><br><small><span data-text-key="long_desc">500-600 mots</span></small>
                        </button>
                    </div>
                </div>

                <div class="controls">
                    <button type="submit" class="btn btn-primary" id="exploreBtn">
                        ✨ <span data-text-key="explore">Explorer le concept</span>
                    </button>
                    <button type="button" class="btn" onclick="clearAll()">
                        🗑️ <span data-text-key="clear">Effacer</span>
                    </button>
                </div>
            </form>
        </div>

        <div id="status" class="status">
            <div class="status-text">
                <span class="loading"></span>
                <span id="statusText" data-text-key="processing">Analyse en cours...</span>
            </div>
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
        </div>

        <div id="result" class="result">
            <div class="result-header">
                <div class="result-title" id="resultTitle">📖 <span data-text-key="generated_explanation">Explication générée</span></div>
                <button class="copy-btn" id="copyBtn" onclick="copyResult()" title="Copier">
                    📋
                </button>
            </div>
            <div class="result-meta" id="resultMeta"></div>
            <div class="result-content" id="resultContent"></div>
        </div>
    </div>

    <script>
        let isProcessing = false;
        let currentDetail = 'moyen';
        let currentLanguage = 'fr';
        let currentTheme = 'light';
        
        const translations = {
            fr: {
                title: "🔢 Mathia",
                subtitle: "Explorateur de concepts mathématiques avec IA",
                search_concept: "Concept à explorer",
                search_placeholder: "Fonction, dérivée, probabilité, matrice...",
                popular_suggestions: "Suggestions populaires:",
                detail_level: "Niveau de détail",
                short: "Court",
                medium: "Moyen",
                long: "Détaillé",
                short_desc: "150-200 mots",
                medium_desc: "300-400 mots", 
                long_desc: "500-600 mots",
                explore: "Explorer le concept",
                clear: "Effacer",
                processing: "Analyse en cours...",
                generated_explanation: "Explication générée",
                requests: "requêtes",
                cached: "en cache",
                concepts: "concepts",
                analyzing: "Analyse...",
                generating: "Génération...",
                completed: "Terminé !",
                copied: "Copié !",
                copy_error: "Échec de la copie",
                processing_concept: "Exploration en cours...",
                already_processing: "Une exploration est déjà en cours...",
                invalid_concept: "Veuillez entrer un concept valide (minimum 2 caractères)",
                explanation_generated: "Explication générée !",
                processing_error: "Erreur d'exploration",
                from_cache: "Depuis le cache",
                demo_mode: "Mode Démo",
                rate_limit_error: "Trop de requêtes. Patientez quelques instants."
            },
            en: {
                title: "🔢 Mathia",
                subtitle: "Mathematical concepts explorer with AI",
                search_concept: "Concept to explore",
                search_placeholder: "Function, derivative, probability, matrix...",
                popular_suggestions: "Popular suggestions:",
                detail_level: "Detail level",
                short: "Short",
                medium: "Medium",
                long: "Detailed",
                short_desc: "150-200 words",
                medium_desc: "300-400 words",
                long_desc: "500-600 words",
                explore: "Explore concept",
                clear: "Clear",
                processing: "Analyzing...",
                generated_explanation: "Generated explanation",
                requests: "requests",
                cached: "cached",
                concepts: "concepts",
                analyzing: "Analyzing...",
                generating: "Generating...",
                completed: "Completed!",
                copied: "Copied!",
                copy_error: "Copy failed",
                processing_concept: "Exploration in progress...",
                already_processing: "An exploration is already running...",
                invalid_concept: "Please enter a valid concept (minimum 2 characters)",
                explanation_generated: "Explanation generated!",
                processing_error: "Exploration error",
                from_cache: "From cache",
                demo_mode: "Demo Mode",
                rate_limit_error: "Too many requests. Please wait a moment."
            },
            es: {
                title: "🔢 Mathia",
                subtitle: "Explorador de conceptos matemáticos con IA",
                search_concept: "Concepto a explorar",
                search_placeholder: "Función, derivada, probabilidad, matriz...",
                popular_suggestions: "Sugerencias populares:",
                detail_level: "Nivel de detalle",
                short: "Corto",
                medium: "Medio",
                long: "Detallado",
                short_desc: "150-200 palabras",
                medium_desc: "300-400 palabras",
                long_desc: "500-600 palabras",
                explore: "Explorar concepto",
                clear: "Limpiar",
                processing: "Analizando...",
                generated_explanation: "Explicación generada",
                requests: "solicitudes",
                cached: "en caché", 
                concepts: "conceptos",
                analyzing: "Analizando...",
                generating: "Generando...",
                completed: "¡Completado!",
                copied: "¡Copiado!",
                copy_error: "Error al copiar",
                processing_concept: "Exploración en curso...",
                already_processing: "Ya hay una exploración en ejecución...",
                invalid_concept: "Por favor ingrese un concepto válido (mínimo 2 caracteres)",
                explanation_generated: "¡Explicación generada!",
                processing_error: "Error de exploración",
                from_cache: "Desde caché",
                demo_mode: "Modo Demo",
                rate_limit_error: "Demasiadas solicitudes. Espere un momento."
            }
        };

        const popularConcepts = {
            fr: ["Fonction", "Dérivée", "Intégrale", "Matrice", "Probabilité", "Limite", "Vecteur", "Équation"],
            en: ["Function", "Derivative", "Integral", "Matrix", "Probability", "Limit", "Vector", "Equation"],
            es: ["Función", "Derivada", "Integral", "Matriz", "Probabilidad", "Límite", "Vector", "Ecuación"]
        };

        document.addEventListener('DOMContentLoaded', function() {
            initializeApp();
        });

        function initializeApp() {
            console.log('🚀 Application initialisée');
            loadTheme();
            loadLanguage();
            initializeSuggestions();
            loadStats();
            updateTranslations();
            
            const conceptInput = document.getElementById('concept');
            if (conceptInput) conceptInput.focus();
        }

        function loadTheme() {
            const savedTheme = localStorage.getItem('mathia_theme') || 'light';
            currentTheme = savedTheme;
            if (currentTheme === 'dark') {
                document.body.setAttribute('data-theme', 'dark');
            }
            updateThemeToggle();
        }

        function loadLanguage() {
            const savedLanguage = localStorage.getItem('mathia_language') || 'fr';
            currentLanguage = savedLanguage;
            const selector = document.getElementById('languageSelector');
            if (selector) selector.value = currentLanguage;
            updateTranslations();
        }

        function toggleTheme() {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            if (currentTheme === 'dark') {
                document.body.setAttribute('data-theme', 'dark');
            } else {
                document.body.removeAttribute('data-theme');
            }
            
            localStorage.setItem('mathia_theme', currentTheme);
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
            if (selector) {
                currentLanguage = selector.value;
                localStorage.setItem('mathia_language', currentLanguage);
            }
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

            const conceptInput = document.getElementById('concept');
            if (conceptInput && translations[currentLanguage].search_placeholder) {
                conceptInput.placeholder = translations[currentLanguage].search_placeholder;
            }
        }

        function selectDetail(detail, element) {
            document.querySelectorAll('.detail-btn').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            currentDetail = detail;
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
                showNotification(translations[currentLanguage].copied, 'success');
                
                setTimeout(() => {
                    copyBtn.textContent = '📋';
                }, 2000);
            }).catch(function() {
                showNotification(translations[currentLanguage].copy_error, 'error');
            });
        }

        function handleFormSubmit(event) {
            event.preventDefault();
            console.log('📝 Formulaire soumis');
            
            if (isProcessing) {
                showNotification(translations[currentLanguage].already_processing, 'info');
                return false;
            }

            const conceptInput = document.getElementById('concept');
            const concept = conceptInput ? conceptInput.value.trim() : '';
            
            console.log('🔍 Concept:', concept);
            
            if (!concept || concept.length < 2) {
                showNotification(translations[currentLanguage].invalid_concept, 'error');
                if (conceptInput) conceptInput.focus();
                return false;
            }

            processConcept(concept, currentLanguage, currentDetail);
            return false;
        }

        function initializeSuggestions() {
            const container = document.getElementById('suggestionChips');
            if (!container) return;
            
            container.innerHTML = '';
            const concepts = popularConcepts[currentLanguage] || popularConcepts.fr;
            
            concepts.forEach(concept => {
                const chip = document.createElement('button');
                chip.className = 'chip';
                chip.textContent = concept;
                chip.type = 'button';
                chip.onclick = function() {
                    const conceptInput = document.getElementById('concept');
                    if (conceptInput) {
                        conceptInput.value = concept;
                        conceptInput.focus();
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
                    console.log('📊 Stats:', stats);
                    updateStatsDisplay(stats);
                }
            } catch (error) {
                console.log('⚠️ Stats error:', error);
            }
        }

        function updateStatsDisplay(stats) {
            const elements = {
                totalRequests: document.getElementById('totalRequests'),
                cacheHits: document.getElementById('cacheHits'),
                conceptsExplored: document.getElementById('conceptsExplored')
            };

            if (elements.totalRequests) elements.totalRequests.textContent = stats.requests || 0;
            if (elements.cacheHits) elements.cacheHits.textContent = stats.cache_hits || 0;
            if (elements.conceptsExplored) elements.conceptsExplored.textContent = stats.concepts_explored || 0;
        }

        async function processConcept(concept, language, detailLevel) {
            console.log('🚀 Traitement du concept:', concept);
            isProcessing = true;
            const exploreBtn = document.getElementById('exploreBtn');
            const exploreText = exploreBtn ? exploreBtn.querySelector('[data-text-key="explore"]') : null;
            
            if (exploreBtn) {
                exploreBtn.disabled = true;
                if (exploreText) exploreText.textContent = translations[currentLanguage].processing_concept;
            }
            
            showStatus(translations[currentLanguage].analyzing);
            hideResult();

            try {
                const requestData = {
                    concept: concept,
                    language: language,
                    detail_level: detailLevel
                };
                
                console.log('📤 Envoi requête:', requestData);
                
                updateProgress(20);
                updateStatus(translations[currentLanguage].analyzing);
                
                const response = await fetch('/api/explore', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });

                console.log('📥 Réponse status:', response.status);
                console.log('📥 Réponse headers:', [...response.headers.entries()]);

                updateProgress(60);
                updateStatus(translations[currentLanguage].generating);

                const contentType = response.headers.get('content-type');
                console.log('📋 Content-Type:', contentType);

                if (!response.ok) {
                    let errorMessage = `HTTP ${response.status}`;
                    
                    try {
                        if (contentType && contentType.includes('application/json')) {
                            const errorData = await response.json();
                            console.error('❌ Erreur JSON:', errorData);
                            errorMessage = errorData.error || errorMessage;
                        } else {
                            const errorText = await response.text();
                            console.error('❌ Erreur texte:', errorText.substring(0, 500));
                            errorMessage = errorText.substring(0, 200);
                        }
                    } catch (e) {
                        console.error('❌ Erreur parsing:', e);
                    }
                    
                    if (response.status === 429) {
                        throw new Error(translations[currentLanguage].rate_limit_error);
                    }
                    
                    if (response.status === 404) {
                        throw new Error('Endpoint non trouvé (404). Vérifiez que le serveur est bien démarré.');
                    }
                    
                    throw new Error(errorMessage);
                }

                let data;
                try {
                    data = await response.json();
                    console.log('✅ Données reçues:', data);
                } catch (e) {
                    console.error('❌ Erreur parsing JSON:', e);
                    throw new Error('Réponse invalide du serveur');
                }

                if (!data.success) {
                    throw new Error(data.error || 'Erreur inconnue');
                }

                updateProgress(100);
                updateStatus(translations[currentLanguage].completed);
                await sleep(500);

                showResult(data);
                hideStatus();
                
                setTimeout(loadStats, 500);
                showNotification(translations[currentLanguage].explanation_generated, 'success');

            } catch (error) {
                console.error('💥 Erreur complète:', error);
                console.error('💥 Stack:', error.stack);
                showNotification(error.message || translations[currentLanguage].processing_error, 'error');
                hideStatus();
            } finally {
                isProcessing = false;
                if (exploreBtn && exploreText) {
                    exploreBtn.disabled = false;
                    exploreText.textContent = translations[currentLanguage].explore;
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
                result: document.getElementById('result')
            };
            
            if (elements.title) {
                elements.title.innerHTML = '📖 <span data-text-key="generated_explanation">' + 
                    translations[currentLanguage].generated_explanation + '</span>';
            }
            
            if (elements.content) elements.content.innerHTML = data.explanation;
            
            let metaText = `🤖 ${data.source === 'demo' ? 'Demo' : 'Mistral AI'} • ${data.processing_time}s • ${data.detail_level}`;
            
            if (data.from_cache) {
                metaText += ` • <span class="cache-badge">💾 ${translations[currentLanguage].from_cache}</span>`;
            }
            
            if (data.demo_mode) {
                metaText += ` • <span class="demo-badge">⚠️ ${translations[currentLanguage].demo_mode}</span>`;
            }
            
            if (elements.meta) elements.meta.innerHTML = metaText;

            if (elements.result) elements.result.classList.add('active');
        }

        function hideResult() {
            const resultDiv = document.getElementById('result');
            if (resultDiv) resultDiv.classList.remove('active');
        }

        function clearAll() {
            const conceptInput = document.getElementById('concept');
            if (conceptInput) {
                conceptInput.value = '';
                conceptInput.focus();
            }
            hideStatus();
            hideResult();
            isProcessing = false;
            
            const exploreBtn = document.getElementById('exploreBtn');
            const exploreText = exploreBtn ? exploreBtn.querySelector('[data-text-key="explore"]') : null;
            if (exploreBtn) {
                exploreBtn.disabled = false;
                if (exploreText) exploreText.textContent = translations[currentLanguage].explore;
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

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
                const target = e.target;
                if (target && target.id === 'concept' && !isProcessing && target.value.trim()) {
                    e.preventDefault();
                    handleFormSubmit(e);
                }
            }
        });

        // Test de connexion au démarrage
        console.log('🔗 Test de connexion API...');
        fetch('/health')
            .then(r => r.json())
            .then(data => console.log('✅ Health check:', data))
            .catch(e => console.error('❌ Health check échoué:', e));
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("=" * 70)
    print("🔢 MATHIA V4.2 - Explorateur Mathématique IA (CORRIGÉ)")
    print("=" * 70)
    
    try:
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"\n⚙️  Configuration:")
        print(f"   • Port: {port}")
        print(f"   • Debug: {debug_mode}")
        print(f"   • Mode: {'DÉMO' if DEMO_MODE else 'PRODUCTION'}")
        if not DEMO_MODE:
            print(f"   • Clés API: {len(Config.API_KEYS)}")
        print(f"   • Cache Max: {Config.CACHE_MAX_SIZE} entrées")
        
        print("\n✨ Corrections apportées:")
        print("   ✅ Gestion d'erreurs renforcée")
        print("   ✅ Logs de debugging détaillés (console navigateur + serveur)")
        print("   ✅ Mode DÉMO si pas de clé API configurée")
        print("   ✅ Messages d'erreur explicites")
        print("   ✅ CORS corrigé")
        print("   ✅ Validation robuste des requêtes")
        print("   ✅ Health check au démarrage")
        
        if DEMO_MODE:
            print("\n⚠️  MODE DÉMONSTRATION ACTIVÉ")
            print("   L'application fonctionne sans API Mistral.")
            print("   Pour activer Mistral AI:")
            print("   1. Obtenez une clé sur: https://console.mistral.ai/")
            print("   2. Exécutez: export MISTRAL_API_KEY='votre_clé'")
            print("   3. Relancez l'application")
        
        print("\n📍 Routes:")
        print("   • GET  /            → Interface utilisateur")
        print("   • POST /api/explore → Exploration de concepts")
        print("   • GET  /api/stats   → Statistiques")
        print("   • GET  /health      → Health check")
        
        print("\n🔍 Debugging:")
        print("   • Ouvrez la console du navigateur (F12)")
        print("   • Regardez les logs serveur ci-dessous")
        print("   • Tous les détails y seront affichés")
        
        print("\n🚀 Démarrage du serveur...")
        print("=" * 70)
        print()
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
        
    except ImportError as e:
        print(f"\n❌ ERREUR: Dépendance manquante - {e}")
        print("   Installez: pip install flask mistralai markdown")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
