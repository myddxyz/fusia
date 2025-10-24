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

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS Configuration
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

# Configuration
class Config:
    # 🔑 Chargement des 3 clés API
    API_KEYS = []
    for i in range(1, 4):
        key = os.environ.get(f'MISTRAL_KEY_{i}')
        if key:
            API_KEYS.append(key.strip())
    
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
    
    # Rate limiting
    MAX_RETRIES_PER_KEY = 2
    RETRY_DELAY = 1  # secondes

# Vérification des clés API
if not Config.API_KEYS:
    logger.error("=" * 70)
    logger.error("❌ ERREUR CRITIQUE : AUCUNE CLÉ API MISTRAL CONFIGURÉE !")
    logger.error("=" * 70)
    logger.error("Définissez les variables d'environnement :")
    logger.error("  export MISTRAL_KEY_1='FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'")
    logger.error("  export MISTRAL_KEY_2='9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'")
    logger.error("  export MISTRAL_KEY_3='cvkQHVcomFFEW47G044x2p4DTyk5BIc7'")
    logger.error("=" * 70)
    raise RuntimeError("Clés API Mistral manquantes. Application arrêtée.")
else:
    logger.info("=" * 70)
    logger.info(f"✅ {len(Config.API_KEYS)} clé(s) API Mistral configurée(s)")
    for i, key in enumerate(Config.API_KEYS, 1):
        masked_key = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
        logger.info(f"   Clé {i}: {masked_key}")
    logger.info("=" * 70)

# Cache LRU
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
    """Explorateur mathématique avec IA Mistral (Production)"""
    
    def __init__(self):
        self.api_keys = Config.API_KEYS
        self.current_key_index = 0
        self.cache = LRUCache(max_size=Config.CACHE_MAX_SIZE)
        
        # Statistiques par clé
        self.key_stats = {i: {'used': 0, 'errors': 0, 'rate_limits': 0} 
                          for i in range(len(self.api_keys))}
        
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'concepts_explored': 0,
            'errors': 0,
            'avg_processing_time': 0,
            'total_api_calls': 0
        }
        self.processing_times = []
        
        logger.info("✅ Mathia Explorer initialisé en mode PRODUCTION")
    
    def get_next_key_index(self):
        """Rotation intelligente des clés"""
        index = self.current_key_index % len(self.api_keys)
        self.current_key_index += 1
        return index
    
    def call_mistral_with_retry(self, prompt):
        """Appelle Mistral avec rotation automatique des clés"""
        try:
            from mistralai import Mistral
        except ImportError:
            logger.error("❌ Module mistralai non installé: pip install mistralai")
            raise RuntimeError("Module mistralai manquant")
        
        last_exception = None
        keys_tried = []
        
        # Essayer toutes les clés disponibles
        for attempt in range(len(self.api_keys) * Config.MAX_RETRIES_PER_KEY):
            key_index = self.get_next_key_index()
            api_key = self.api_keys[key_index]
            
            # Éviter de réessayer immédiatement la même clé
            if len(keys_tried) > 0 and keys_tried[-1] == key_index:
                continue
            
            keys_tried.append(key_index)
            
            try:
                client = Mistral(api_key=api_key)
                
                logger.info(f"🔑 Utilisation clé #{key_index + 1} (tentative {attempt + 1})")
                self.key_stats[key_index]['used'] += 1
                self.stats['total_api_calls'] += 1
                
                # Tentative avec modèle principal
                response = client.chat.complete(
                    model=Config.MISTRAL_MODEL_PRIMARY,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=Config.MISTRAL_TEMPERATURE,
                    max_tokens=Config.MISTRAL_MAX_TOKENS
                )
                
                logger.info(f"✅ Succès avec clé #{key_index + 1}")
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                error_msg = str(e).lower()
                last_exception = e
                
                # Rate limit détecté
                if "429" in error_msg or "rate" in error_msg or "quota" in error_msg:
                    logger.warning(f"⚠️ Rate limit clé #{key_index + 1} - Passage à la suivante")
                    self.key_stats[key_index]['rate_limits'] += 1
                    
                    # Essayer avec le modèle fallback sur une autre clé
                    next_key_index = self.get_next_key_index()
                    try:
                        logger.info(f"🔄 Fallback: clé #{next_key_index + 1} + modèle {Config.MISTRAL_MODEL_FALLBACK}")
                        fallback_client = Mistral(api_key=self.api_keys[next_key_index])
                        
                        response = fallback_client.chat.complete(
                            model=Config.MISTRAL_MODEL_FALLBACK,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=Config.MISTRAL_TEMPERATURE,
                            max_tokens=Config.MISTRAL_MAX_TOKENS
                        )
                        
                        logger.info(f"✅ Fallback réussi avec clé #{next_key_index + 1}")
                        return response.choices[0].message.content.strip()
                    except Exception as fallback_error:
                        logger.warning(f"❌ Fallback échoué: {fallback_error}")
                        continue
                else:
                    # Autre erreur
                    logger.error(f"❌ Erreur clé #{key_index + 1}: {e}")
                    self.key_stats[key_index]['errors'] += 1
                
                # Attendre avant le prochain essai
                if attempt < len(self.api_keys) * Config.MAX_RETRIES_PER_KEY - 1:
                    time.sleep(Config.RETRY_DELAY)
        
        # Toutes les tentatives ont échoué
        logger.error(f"💥 ÉCHEC TOTAL après {len(keys_tried)} tentatives")
        logger.error(f"Clés essayées: {[i+1 for i in keys_tried]}")
        raise RuntimeError(f"Toutes les clés API ont échoué: {last_exception}")
    
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
            html = markdown.markdown(text, extensions=['extra', 'nl2br', 'tables'])
            return html
        except ImportError:
            logger.warning("⚠️ Module markdown non installé, fallback simple")
            # Fallback simple
            text = text.strip()
            text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
            text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
            text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
            text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
            
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

1. **DÉFINITION** (2-3 phrases claires)
2. **EXPLICATION DÉTAILLÉE** (plusieurs paragraphes pédagogiques)
3. **EXEMPLES CONCRETS** (3-5 exemples avec calculs détaillés)
4. **CONCEPTS LIÉS** (4-6 concepts connexes à explorer)
5. **IMPORTANCE** (applications pratiques et réelles)
6. **CONSEIL D'APPRENTISSAGE** (astuce pour mieux comprendre)

Utilise le markdown pour la mise en forme (titres ##, gras **, italique *, listes).
Sois clair, précis et pédagogique.

Réponds maintenant:"""
        
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
        logger.info(f"🔍 Nouvelle requête: '{concept}' (langue={language}, détail={detail_level})")
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
            logger.info("💾 Cache HIT - Réponse instantanée")
            self.stats['cache_hits'] += 1
            cached_result['from_cache'] = True
            cached_result['processing_time'] = round(time.time() - start_time, 2)
            return cached_result
        
        logger.info("🔄 Cache MISS - Appel API Mistral")
        
        try:
            # Construire le prompt
            prompt = self.build_prompt(concept, language, detail_level)
            
            # Appeler Mistral avec rotation des clés
            ai_response = self.call_mistral_with_retry(prompt)
            
            if not ai_response:
                raise RuntimeError("Réponse vide de l'API Mistral")
            
            # Convertir en HTML
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
                'source': 'mistral_ai',
                'model': Config.MISTRAL_MODEL_PRIMARY,
                'from_cache': False,
                'cache_size': self.cache.size()
            }
            
            # Mettre en cache
            self.cache.set(cache_key, result.copy())
            self.stats['concepts_explored'] += 1
            
            logger.info(f"✅ Traitement réussi en {processing_time}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur traitement: {str(e)}")
            logger.error(traceback.format_exc())
            self.stats['errors'] += 1
            return {
                'success': False,
                'error': f'Erreur lors du traitement: {str(e)}'
            }
    
    def get_detailed_stats(self):
        """Retourne les statistiques détaillées"""
        stats = self.stats.copy()
        stats['cache_size'] = self.cache.size()
        stats['cache_max_size'] = Config.CACHE_MAX_SIZE
        stats['api_keys_count'] = len(self.api_keys)
        stats['key_stats'] = self.key_stats
        return stats

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
        return '', 204
    
    try:
        # Validation Content-Type
        if not request.is_json:
            logger.error(f"❌ Content-Type invalide: {request.content_type}")
            return jsonify({
                'success': False,
                'error': f'Content-Type doit être application/json'
            }), 400
        
        data = request.get_json()
        
        if not data:
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
            return jsonify(result), 400
        
        logger.info(f"✅ Succès en {result.get('processing_time')}s")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"💥 Erreur serveur: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Erreur interne: {str(e)}'
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Récupère les statistiques détaillées"""
    try:
        stats = mathia.get_detailed_stats()
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
        'version': '5.0 PRODUCTION',
        'api_keys_configured': len(Config.API_KEYS),
        'cache_size': mathia.cache.size(),
        'total_requests': mathia.stats['requests']
    }), 200

# Template HTML (identique mais sans références au mode démo)
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
                generating: "Génération IA...",
                completed: "Terminé !",
                copied: "Copié !",
                copy_error: "Échec de la copie",
                processing_concept: "Exploration en cours...",
                already_processing: "Une exploration est déjà en cours...",
                invalid_concept: "Veuillez entrer un concept valide (minimum 2 caractères)",
                explanation_generated: "Explication générée par Mistral AI !",
                processing_error: "Erreur d'exploration",
                from_cache: "Depuis le cache",
                rate_limit_error: "Toutes les clés API sont saturées. Réessayez dans quelques instants."
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
                generating: "AI generating...",
                completed: "Completed!",
                copied: "Copied!",
                copy_error: "Copy failed",
                processing_concept: "Exploration in progress...",
                already_processing: "An exploration is already running...",
                invalid_concept: "Please enter a valid concept (minimum 2 characters)",
                explanation_generated: "Explanation generated by Mistral AI!",
                processing_error: "Exploration error",
                from_cache: "From cache",
                rate_limit_error: "All API keys are saturated. Try again in a few moments."
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
                generating: "Generando IA...",
                completed: "¡Completado!",
                copied: "¡Copiado!",
                copy_error: "Error al copiar",
                processing_concept: "Exploración en curso...",
                already_processing: "Ya hay una exploración en ejecución...",
                invalid_concept: "Por favor ingrese un concepto válido (mínimo 2 caracteres)",
                explanation_generated: "¡Explicación generada por Mistral AI!",
                processing_error: "Error de exploración",
                from_cache: "Desde caché",
                rate_limit_error: "Todas las claves API están saturadas. Intente nuevamente en unos momentos."
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
            console.log('🚀 Mathia Explorer v5.0 - PRODUCTION');
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
                    console.log('📊 Stats chargées:', stats);
                    updateStatsDisplay(stats);
                }
            } catch (error) {
                console.log('⚠️ Erreur chargement stats:', error);
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
                
                console.log('📤 Envoi requête à Mistral AI:', requestData);
                
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

                updateProgress(60);
                updateStatus(translations[currentLanguage].generating);

                if (!response.ok) {
                    let errorMessage = `HTTP ${response.status}`;
                    
                    try {
                        const errorData = await response.json();
                        console.error('❌ Erreur API:', errorData);
                        errorMessage = errorData.error || errorMessage;
                    } catch (e) {
                        const errorText = await response.text();
                        console.error('❌ Erreur texte:', errorText);
                        errorMessage = errorText.substring(0, 200);
                    }
                    
                    throw new Error(errorMessage);
                }

                const data = await response.json();
                console.log('✅ Données reçues de Mistral:', data);

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
            
            let metaText = `🤖 Mistral AI (${data.model || 'mistral-large'}) • ${data.processing_time}s • ${data.detail_level}`;
            
            if (data.from_cache) {
                metaText += ` • <span class="cache-badge">💾 ${translations[currentLanguage].from_cache}</span>`;
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
        console.log('🔗 Test de connexion API Mistral...');
        fetch('/health')
            .then(r => r.json())
            .then(data => {
                console.log('✅ Health check:', data);
                console.log(`✅ ${data.api_keys_configured} clé(s) API configurée(s)`);
            })
            .catch(e => console.error('❌ Health check échoué:', e));
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("=" * 70)
    print("🔢 MATHIA V5.0 - PRODUCTION")
    print("=" * 70)
    
    try:
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') == 'development'
        
        print(f"\n⚙️  Configuration:")
        print(f"   • Port: {port}")
        print(f"   • Debug: {debug_mode}")
        print(f"   • Mode: PRODUCTION")
        print(f"   • Clés API: {len(Config.API_KEYS)}")
        print(f"   • Cache Max: {Config.CACHE_MAX_SIZE} entrées")
        print(f"   • Modèle principal: {Config.MISTRAL_MODEL_PRIMARY}")
        print(f"   • Modèle fallback: {Config.MISTRAL_MODEL_FALLBACK}")
        
        print("\n✨ Fonctionnalités:")
        print("   ✅ Rotation automatique entre 3 clés API")
        print("   ✅ Gestion intelligente des rate limits")
        print("   ✅ Fallback automatique sur modèle alternatif")
        print("   ✅ Cache LRU haute performance")
        print("   ✅ Statistiques détaillées par clé")
        print("   ✅ Support multilingue (FR/EN/ES)")
        print("   ✅ Thème clair/sombre")
        
        print("\n📍 Routes:")
        print("   • GET  /            → Interface utilisateur")
        print("   • POST /api/explore → Exploration de concepts (Mistral AI)")
        print("   • GET  /api/stats   → Statistiques détaillées")
        print("   • GET  /health      → Health check")
        
        print("\n🚀 Démarrage du serveur...")
        print("=" * 70)
        print()
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
        
    except RuntimeError as e:
        print(f"\n❌ ERREUR CONFIGURATION: {e}")
        print("\n💡 Solution:")
        print("   export MISTRAL_KEY_1='FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'")
        print("   export MISTRAL_KEY_2='9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'")
        print("   export MISTRAL_KEY_3='cvkQHVcomFFEW47G044x2p4DTyk5BIc7'")
        print("   python mathia_app.py")
        exit(1)
    except ImportError as e:
        print(f"\n❌ ERREUR: Dépendance manquante - {e}")
        print("   Installez: pip install flask mistralai markdown")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
