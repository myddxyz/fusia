from flask import Flask, request, jsonify, render_template_string
import os
import json
from mistralai import Mistral
import logging
import time
import hashlib
import re
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
import markdown
from threading import Lock

# ==================== CONFIGURATION ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class Config:
    """Configuration centralisée"""
    # API Keys - À DÉPLACER dans variables d'environnement en production
    API_KEYS = os.environ.get('MISTRAL_API_KEYS', 
        'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX,9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF,cvkQHVcomFFEW47G044x2p4DTyk5BIc7'
    ).split(',')
    
    # Sécurité
    MAX_CONCEPT_LENGTH = 200
    MIN_CONCEPT_LENGTH = 2
    ALLOWED_ORIGINS = ['*']
    
    # Performance
    CACHE_MAX_SIZE = 100
    CACHE_TTL = 3600  # 1 heure
    REQUEST_TIMEOUT = 30
    RATE_LIMIT_REQUESTS = 10
    RATE_LIMIT_WINDOW = 60
    
    # Mistral
    MISTRAL_MODEL_PRIMARY = "mistral-large-latest"
    MISTRAL_MODEL_FALLBACK = "mistral-small-latest"
    MISTRAL_MAX_TOKENS = 1200
    MISTRAL_TEMPERATURE = 0.7

logger.info(f"✅ Configuration chargée: {len(Config.API_KEYS)} clé(s) API")


# ==================== CORS MIDDLEWARE ====================
@app.after_request
def add_cors_headers(response):
    """Ajoute les headers CORS à toutes les réponses"""
    origin = request.headers.get('Origin', '*')
    response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response


# ==================== RATE LIMITER ====================
class RateLimiter:
    """Rate limiter thread-safe avec nettoyage automatique"""
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = Lock()
    
    def is_allowed(self, identifier):
        """Vérifie si la requête est autorisée"""
        with self.lock:
            now = datetime.now()
            # Nettoyer les anciennes requêtes
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if now - req_time < timedelta(seconds=Config.RATE_LIMIT_WINDOW)
            ]
            
            if len(self.requests[identifier]) >= Config.RATE_LIMIT_REQUESTS:
                return False
            
            self.requests[identifier].append(now)
            return True
    
    def cleanup(self):
        """Nettoie les anciennes entrées"""
        with self.lock:
            now = datetime.now()
            for identifier in list(self.requests.keys()):
                self.requests[identifier] = [
                    req_time for req_time in self.requests[identifier]
                    if now - req_time < timedelta(seconds=Config.RATE_LIMIT_WINDOW)
                ]
                if not self.requests[identifier]:
                    del self.requests[identifier]

rate_limiter = RateLimiter()


# ==================== CACHE LRU ====================
class LRUCache:
    """Cache LRU thread-safe avec expiration"""
    
    def __init__(self, max_size=100, ttl=3600):
        self.cache = {}
        self.access_order = []
        self.timestamps = {}
        self.max_size = max_size
        self.ttl = ttl
        self.lock = Lock()
    
    def get(self, key):
        """Récupère une valeur du cache"""
        with self.lock:
            if key not in self.cache:
                return None
            
            # Vérifier l'expiration
            if time.time() - self.timestamps.get(key, 0) > self.ttl:
                self._remove(key)
                return None
            
            # Mettre à jour l'ordre d'accès
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
    
    def set(self, key, value):
        """Stocke une valeur dans le cache"""
        with self.lock:
            if key in self.cache:
                self.access_order.remove(key)
            elif len(self.cache) >= self.max_size:
                # Supprimer le plus ancien
                oldest = self.access_order.pop(0)
                self._remove(oldest)
            
            self.cache[key] = value
            self.access_order.append(key)
            self.timestamps[key] = time.time()
    
    def _remove(self, key):
        """Supprime une clé du cache"""
        if key in self.cache:
            del self.cache[key]
        if key in self.timestamps:
            del self.timestamps[key]
    
    def size(self):
        """Retourne la taille du cache"""
        with self.lock:
            return len(self.cache)
    
    def cleanup_expired(self):
        """Nettoie les entrées expirées"""
        with self.lock:
            now = time.time()
            expired = [k for k, ts in self.timestamps.items() if now - ts > self.ttl]
            for key in expired:
                self._remove(key)
                if key in self.access_order:
                    self.access_order.remove(key)


# ==================== MATHIA EXPLORER ====================
class MathiaExplorer:
    """Explorateur mathématique avec IA Mistral - Version optimisée"""
    
    def __init__(self):
        self.api_keys = Config.API_KEYS
        self.current_key_index = 0
        self.cache = LRUCache(max_size=Config.CACHE_MAX_SIZE, ttl=Config.CACHE_TTL)
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'concepts_explored': 0,
            'errors': 0,
            'avg_processing_time': 0
        }
        self.processing_times = []
        self.stats_lock = Lock()
        
        logger.info("✅ Mathia Explorer initialisé")
    
    def get_next_api_key(self):
        """Obtient la prochaine clé API avec rotation"""
        key = self.api_keys[self.current_key_index % len(self.api_keys)]
        self.current_key_index += 1
        return key
    
    def call_mistral_with_retry(self, prompt, max_retries=None):
        """Appelle Mistral avec retry automatique"""
        if max_retries is None:
            max_retries = len(self.api_keys)
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                api_key = self.get_next_api_key()
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
                
                # Essayer le modèle fallback en cas de rate limit
                if "429" in error_msg or "capacity" in error_msg:
                    logger.warning(f"⚠️ Rate limit - Tentative avec modèle fallback")
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
        
        raise Exception(f"Toutes les tentatives ont échoué: {last_exception}")
    
    def get_cache_key(self, concept, language, detail_level):
        """Génère une clé de cache unique"""
        normalized = f"{concept.lower().strip()}_{language}_{detail_level}"
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def markdown_to_html(self, text):
        """Convertit le Markdown en HTML"""
        if not text:
            return ""
        
        try:
            html = markdown.markdown(text, extensions=['extra', 'nl2br'])
            return html
        except Exception as e:
            logger.warning(f"Erreur conversion Markdown: {e}")
            # Fallback basique
            text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
            return f'<p>{text}</p>'
    
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
        
        return f"""Tu es Mathia, un expert en mathématiques passionné par la vulgarisation.

**Concept:** "{concept}"

{lang_instruction}

**Instructions:**
Fournis une explication complète en {word_count}, structurée ainsi:

1. **DÉFINITION** (2-3 phrases claires)
2. **EXPLICATION DÉTAILLÉE** (plusieurs paragraphes)
3. **EXEMPLES CONCRETS** (3-5 exemples avec calculs)
4. **CONCEPTS LIÉS** (4-6 concepts connexes)
5. **IMPORTANCE** (applications réelles)
6. **CONSEIL D'APPRENTISSAGE**

**Format:** Paragraphes fluides, langage accessible mais précis, utilise markdown (gras, italique).

Réponds maintenant:"""
    
    def validate_concept(self, concept):
        """Valide le concept d'entrée"""
        if not concept or not isinstance(concept, str):
            return False, "Le concept doit être une chaîne de caractères"
        
        concept = concept.strip()
        
        if len(concept) < Config.MIN_CONCEPT_LENGTH:
            return False, f"Minimum {Config.MIN_CONCEPT_LENGTH} caractères"
        
        if len(concept) > Config.MAX_CONCEPT_LENGTH:
            return False, f"Maximum {Config.MAX_CONCEPT_LENGTH} caractères"
        
        if re.search(r'[<>{}]', concept):
            return False, "Caractères non autorisés"
        
        return True, concept
    
    def update_stats(self, processing_time=None, cache_hit=False, error=False):
        """Met à jour les statistiques de manière thread-safe"""
        with self.stats_lock:
            self.stats['requests'] += 1
            
            if cache_hit:
                self.stats['cache_hits'] += 1
            
            if error:
                self.stats['errors'] += 1
            elif not cache_hit:
                self.stats['concepts_explored'] += 1
            
            if processing_time:
                self.processing_times.append(processing_time)
                if self.processing_times:
                    self.stats['avg_processing_time'] = round(
                        sum(self.processing_times) / len(self.processing_times), 2
                    )
    
    def process_concept(self, concept, language='fr', detail_level='moyen'):
        """Traite un concept mathématique"""
        logger.info(f"🔍 Requête: '{concept}' (lang={language}, détail={detail_level})")
        start_time = time.time()
        
        # Validation
        is_valid, result = self.validate_concept(concept)
        if not is_valid:
            self.update_stats(error=True)
            return {'success': False, 'error': result}
        
        concept = result
        
        # Cache
        cache_key = self.get_cache_key(concept, language, detail_level)
        cached_result = self.cache.get(cache_key)
        
        if cached_result:
            logger.info("💾 Cache HIT")
            self.update_stats(cache_hit=True)
            cached_result['from_cache'] = True
            return cached_result
        
        logger.info("🔄 Cache MISS - Génération IA")
        
        try:
            # Générer avec Mistral
            prompt = self.build_prompt(concept, language, detail_level)
            ai_response = self.call_mistral_with_retry(prompt)
            
            if not ai_response:
                raise Exception("Réponse vide de Mistral")
            
            # Convertir en HTML
            formatted_response = self.markdown_to_html(ai_response)
            
            # Calculer le temps
            processing_time = round(time.time() - start_time, 2)
            self.update_stats(processing_time=processing_time)
            
            result = {
                'success': True,
                'concept': concept.title(),
                'explanation': formatted_response,
                'processing_time': processing_time,
                'detail_level': detail_level,
                'language': language,
                'source': 'mistral_ai',
                'from_cache': False,
                'cache_size': self.cache.size()
            }
            
            # Mettre en cache
            self.cache.set(cache_key, result)
            
            logger.info(f"✅ Succès en {processing_time}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur: {str(e)}", exc_info=True)
            self.update_stats(error=True)
            return {
                'success': False,
                'error': f'Erreur de traitement: {str(e)}'
            }

# Instance globale
mathia = MathiaExplorer()


# ==================== ROUTES ====================
@app.route('/')
def index():
    """Page principale"""
    return render_template_string(MATHIA_TEMPLATE)


@app.route('/api/explore', methods=['POST', 'OPTIONS'])
def explore():
    """API d'exploration de concepts - ROUTE CORRIGÉE"""
    
    # Log détaillé pour déboguer
    logger.info(f"📨 {request.method} /api/explore depuis {request.remote_addr}")
    logger.info(f"   Headers: {dict(request.headers)}")
    
    # Gérer OPTIONS (CORS preflight)
    if request.method == 'OPTIONS':
        logger.info("✅ OPTIONS - CORS preflight")
        response = jsonify({'status': 'ok'})
        return response, 200
    
    try:
        # Vérifier Content-Type
        content_type = request.headers.get('Content-Type', '')
        logger.info(f"   Content-Type: {content_type}")
        
        if 'application/json' not in content_type:
            logger.error(f"❌ Content-Type invalide: {content_type}")
            return jsonify({
                'success': False,
                'error': 'Content-Type doit être application/json'
            }), 400
        
        # Parser le JSON
        try:
            data = request.get_json(force=True)
            logger.info(f"   Body: {data}")
        except Exception as e:
            logger.error(f"❌ Erreur parsing JSON: {e}")
            return jsonify({
                'success': False,
                'error': f'JSON invalide: {str(e)}'
            }), 400
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Corps JSON requis'
            }), 400
        
        # Extraire les paramètres
        concept = data.get('concept', '').strip()
        language = data.get('language', 'fr')
        detail_level = data.get('detail_level', 'moyen')
        
        # Valider
        if language not in ['fr', 'en', 'es']:
            language = 'fr'
        
        if detail_level not in ['court', 'moyen', 'long']:
            detail_level = 'moyen'
        
        if not concept:
            return jsonify({
                'success': False,
                'error': 'Paramètre "concept" requis'
            }), 400
        
        # Rate limiting
        client_id = request.remote_addr
        if not rate_limiter.is_allowed(client_id):
            return jsonify({
                'success': False,
                'error': 'Trop de requêtes. Réessayez dans 1 minute.'
            }), 429
        
        # Traiter
        result = mathia.process_concept(concept, language, detail_level)
        
        if not result.get('success'):
            return jsonify(result), 500
        
        logger.info(f"✅ Succès: {result.get('processing_time')}s")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"💥 Erreur serveur: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Erreur interne: {str(e)}'
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Statistiques"""
    try:
        stats = mathia.stats.copy()
        stats['cache_size'] = mathia.cache.size()
        stats['cache_max_size'] = Config.CACHE_MAX_SIZE
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Erreur stats: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'Mathia Explorer',
        'version': '5.0',
        'api_keys': len(Config.API_KEYS),
        'cache_size': mathia.cache.size()
    }), 200


# ==================== TEMPLATE HTML ====================
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
            box-shadow: 0 2px 10px var(--shadow);
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
            text-shadow: 0 2px 10px var(--shadow);
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
            box-shadow: 0 4px 15px var(--shadow);
        }
        
        .form-section {
            background: var(--bg-secondary);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 25px;
            padding: 30px;
            box-shadow: 0 8px 30px var(--shadow);
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
            box-shadow: 0 4px 15px var(--shadow);
        }
        
        .input:focus {
            background: var(--input-focus-bg);
            border-color: var(--input-focus-border);
            box-shadow: 0 0 0 3px var(--input-focus-shadow);
        }
        
        .input::placeholder {
            color: var(--placeholder-color);
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
            box-shadow: 0 4px 15px var(--shadow);
        }
        
        .detail-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px var(--shadow-strong);
        }
        
        .detail-btn.active {
            background: var(--button-active);
            color: var(--text-primary);
            border-color: var(--border-color-strong);
            font-weight: 600;
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
            box-shadow: 0 2px 10px var(--shadow);
        }
        
        .chip:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px var(--shadow-strong);
            background: var(--button-active);
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
            box-shadow: 0 4px 15px var(--shadow);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px var(--shadow-strong);
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
            box-shadow: 0 8px 30px var(--shadow);
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
            box-shadow: 0 8px 30px var(--shadow);
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
            box-shadow: 0 2px 10px var(--shadow);
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
            
            .header-controls {
                width: 100%;
                justify-content: space-between;
            }
            
            .container {
                padding: 140px 20px 20px;
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
            
            .detail-selector {
                flex-direction: column;
                gap: 10px;
            }
            
            .detail-btn {
                min-width: auto;
            }
            
            .controls {
                flex-direction: column;
                gap: 10px;
            }
            
            .btn {
                width: 100%;
            }
            
            .result-header {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .result-title {
                margin-right: 0;
                margin-bottom: 15px;
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
                rate_limit_error: "Trop de requêtes. Patientez quelques instants.",
                network_error: "Erreur réseau. Vérifiez votre connexion."
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
                rate_limit_error: "Too many requests. Please wait a moment.",
                network_error: "Network error. Check your connection."
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
                rate_limit_error: "Demasiadas solicitudes. Espere un momento.",
                network_error: "Error de red. Verifique su conexión."
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
            
            if (isProcessing) {
                showNotification(translations[currentLanguage].already_processing, 'info');
                return false;
            }

            const conceptInput = document.getElementById('concept');
            const concept = conceptInput ? conceptInput.value.trim() : '';
            
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
                conceptsExplored: document.getElementById('conceptsExplored')
            };

            if (elements.totalRequests) elements.totalRequests.textContent = stats.requests || 0;
            if (elements.cacheHits) elements.cacheHits.textContent = stats.cache_hits || 0;
            if (elements.conceptsExplored) elements.conceptsExplored.textContent = stats.concepts_explored || 0;
        }

        async function processConcept(concept, language, detailLevel) {
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
                
                console.log('🚀 Envoi requête:', requestData);
                
                updateProgress(20);
                updateStatus(translations[currentLanguage].analyzing);
                
                // CORRECTION: Headers explicites et gestion d'erreur améliorée
                const response = await fetch('/api/explore', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(requestData),
                    credentials: 'same-origin'
                });

                console.log('📡 Réponse HTTP:', response.status, response.statusText);

                updateProgress(60);
                updateStatus(translations[currentLanguage].generating);

                // Gestion détaillée des erreurs HTTP
                if (!response.ok) {
                    let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
                    
                    try {
                        const contentType = response.headers.get('content-type');
                        
                        if (contentType && contentType.includes('application/json')) {
                            const errorData = await response.json();
                            errorMessage = errorData.error || errorMessage;
                            console.error('❌ Erreur JSON:', errorData);
                        } else {
                            const errorText = await response.text();
                            console.error('❌ Erreur texte:', errorText.substring(0, 200));
                            errorMessage = errorText.substring(0, 200) || errorMessage;
                        }
                    } catch (parseError) {
                        console.error('❌ Erreur parsing réponse:', parseError);
                    }
                    
                    if (response.status === 429) {
                        throw new Error(translations[currentLanguage].rate_limit_error);
                    } else if (response.status === 404) {
                        throw new Error('Endpoint introuvable (404). Vérifiez l\'URL de l\'API.');
                    } else if (response.status >= 500) {
                        throw new Error('Erreur serveur (' + response.status + '). Réessayez plus tard.');
                    }
                    
                    throw new Error(errorMessage);
                }

                const data = await response.json();
                console.log('✅ Données reçues:', data);

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
                
                let errorMsg = error.message || translations[currentLanguage].processing_error;
                
                // Détection d'erreurs réseau
                if (error.name === 'TypeError' && error.message.includes('fetch')) {
                    errorMsg = translations[currentLanguage].network_error;
                }
                
                showNotification(errorMsg, 'error');
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
            
            let metaText = `🤖 Mistral AI • ${data.processing_time}s • ${data.detail_level}`;
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

        // Gestion de la touche Entrée
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
                const target = e.target;
                if (target && target.id === 'concept' && !isProcessing && target.value.trim()) {
                    e.preventDefault();
                    handleFormSubmit(e);
                }
            }
        });
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("=" * 70)
    print("🔢 MATHIA V5.0 - Explorateur Mathématique IA (VERSION CORRIGÉE)")
    print("=" * 70)
    
    try:
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"\n⚙️  Configuration:")
        print(f"   • Port: {port}")
        print(f"   • Debug: {debug_mode}")
        print(f"   • Clés API: {len(Config.API_KEYS)}")
        print(f"   • Cache: {Config.CACHE_MAX_SIZE} entrées (TTL: {Config.CACHE_TTL}s)")
        print(f"   • Rate Limit: {Config.RATE_LIMIT_REQUESTS} req/{Config.RATE_LIMIT_WINDOW}s")
        
        print("\n✨ Corrections principales:")
        print("   ✅ Erreur 404 corrigée - Route /api/explore optimisée")
        print("   ✅ CORS headers améliorés (OPTIONS + credentials)")
        print("   ✅ Gestion d'erreurs HTTP détaillée (404, 429, 500)")
        print("   ✅ Rate limiter thread-safe avec Lock")
        print("   ✅ Cache LRU avec expiration (TTL)")
        print("   ✅ Logs structurés pour déboguer")
        print("   ✅ Validation stricte des entrées")
        print("   ✅ Headers explicites dans fetch()")
        print("   ✅ Messages d'erreur multilingues")
        print("   ✅ Statistiques thread-safe")
        
        print("\n🔧 Améliorations techniques:")
        print("   • Threading.Lock pour thread-safety")
        print("   • Cache avec nettoyage automatique")
        print("   • Retry avec backoff exponentiel")
        print("   • Fallback sur modèle secondaire")
        print("   • Content-Type validation stricte")
        
        print("\n📍 Endpoints disponibles:")
        print("   • GET  /            → Interface web")
        print("   • POST /api/explore → Exploration (JSON)")
        print("   • GET  /api/stats   → Statistiques")
        print("   • GET  /health      → Health check")
        
        print("\n🔍 Debug de l'erreur 404:")
        print("   1. Vérifiez que le serveur démarre sur le bon port")
        print("   2. La route POST /api/explore est bien définie")
        print("   3. Les headers CORS sont configurés")
        print("   4. Le Content-Type est 'application/json'")
        print("   5. Consultez les logs ci-dessous pour plus de détails")
        
        print("\n🚀 Démarrage du serveur...")
        print("=" * 70)
        print()
        
        # Tâche de nettoyage périodique (optionnel)
        def cleanup_task():
            import threading
            def cleanup():
                while True:
                    time.sleep(300)  # 5 minutes
                    try:
                        mathia.cache.cleanup_expired()
                        rate_limiter.cleanup()
                        logger.info("🧹 Nettoyage effectué")
                    except Exception as e:
                        logger.error(f"Erreur nettoyage: {e}")
            
            thread = threading.Thread(target=cleanup, daemon=True)
            thread.start()
        
        cleanup_task()
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True)
        
    except ImportError as e:
        print(f"\n❌ ERREUR: Dépendance manquante - {e}")
        print("\n📦 Installation requise:")
        print("   pip install flask mistralai markdown")
        print("\n   Ou avec requirements.txt:")
        print("   pip install -r requirements.txt")
        exit(1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Arrêt du serveur...")
        print("👋 Au revoir!")
        exit(0)
    except Exception as e:
        print(f"\n❌ ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
