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

# Configuration du logging structuré
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS Configuration globale
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Configuration
class Config:
    # Clés API Mistral (hardcodées pour facilité d'utilisation)
    API_KEYS = [
        'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX',
        '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF',
        'cvkQHVcomFFEW47G044x2p4DTyk5BIc7'
    ]
    
    # Sécurité
    MAX_CONCEPT_LENGTH = 200
    MIN_CONCEPT_LENGTH = 2
    ALLOWED_ORIGINS = '*'
    
    # Performance
    CACHE_MAX_SIZE = 100
    REQUEST_TIMEOUT = 30
    RATE_LIMIT_REQUESTS = 10
    RATE_LIMIT_WINDOW = 60  # secondes
    
    # Mistral
    MISTRAL_MODEL_PRIMARY = "mistral-large-latest"
    MISTRAL_MODEL_FALLBACK = "mistral-small-latest"
    MISTRAL_MAX_TOKENS = 1200
    MISTRAL_TEMPERATURE = 0.7

logger.info(f"✅ {len(Config.API_KEYS)} clé(s) API Mistral configurée(s)")


# Rate Limiting Simple
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
    
    def is_allowed(self, identifier):
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

rate_limiter = RateLimiter()


# Décorateur pour rate limiting
def require_rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        identifier = request.remote_addr
        if not rate_limiter.is_allowed(identifier):
            return jsonify({
                'success': False,
                'error': 'Trop de requêtes. Veuillez patienter.'
            }), 429
        return f(*args, **kwargs)
    return decorated_function


# Cache LRU simple
class LRUCache:
    def __init__(self, max_size=100):
        self.cache = {}
        self.access_order = []
        self.max_size = max_size
    
    def get(self, key):
        if key in self.cache:
            # Mettre à jour l'ordre d'accès
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def set(self, key, value):
        if key in self.cache:
            self.access_order.remove(key)
        elif len(self.cache) >= self.max_size:
            # Supprimer le plus ancien
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
        
        self.cache[key] = value
        self.access_order.append(key)
    
    def size(self):
        return len(self.cache)


class MathiaExplorer:
    """Explorateur mathématique avec IA Mistral - Version optimisée"""
    
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
    
    def get_next_api_key(self):
        """Obtient la prochaine clé API avec rotation circulaire"""
        key = self.api_keys[self.current_key_index % len(self.api_keys)]
        self.current_key_index += 1
        return key
    
    def call_mistral_with_retry(self, prompt, max_retries=None):
        """Appelle Mistral avec retry sur toutes les clés disponibles"""
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
                
                # Si rate limit ou capacity, essayer le modèle fallback
                if "429" in error_msg or "capacity" in error_msg:
                    logger.warning(f"⚠️ Rate limit/Capacity - Tentative avec modèle fallback")
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
                    time.sleep(2 ** attempt)  # Backoff exponentiel
        
        raise Exception(f"Toutes les tentatives ont échoué: {last_exception}")
    
    def get_cache_key(self, concept, language, detail_level):
        """Génère une clé de cache unique et normalisée"""
        normalized = f"{concept.lower().strip()}_{language}_{detail_level}"
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def markdown_to_html(self, text):
        """Convertit le Markdown en HTML de manière robuste"""
        if not text:
            return ""
        
        # Utiliser la bibliothèque markdown pour une conversion complète
        try:
            html = markdown.markdown(
                text,
                extensions=['extra', 'nl2br']
            )
            return html
        except:
            # Fallback vers la conversion basique
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
        
        prompt = f"""Tu es Mathia, un expert en mathématiques passionné par la vulgarisation. Ta mission est d'expliquer des concepts mathématiques de manière claire, structurée et accessible.

**Concept à explorer:** "{concept}"

{lang_instruction}

**Instructions:**
Fournis une explication complète en {word_count}, structurée ainsi:

1. **DÉFINITION** (2-3 phrases claires)
   - Explique ce qu'est le concept en termes simples
   - Donne le contexte mathématique

2. **EXPLICATION DÉTAILLÉE** (plusieurs paragraphes)
   - Développe le concept en profondeur
   - Explique les propriétés importantes
   - Montre le fonctionnement

3. **EXEMPLES CONCRETS** (3-5 exemples)
   - Exemples mathématiques précis avec calculs
   - Cas simples puis plus complexes
   - Applications pratiques

4. **CONCEPTS LIÉS** (4-6 concepts)
   - Liste des concepts connexes
   - Lien avec le concept principal

5. **IMPORTANCE**
   - Applications réelles
   - Pourquoi c'est fondamental en mathématiques

6. **CONSEIL D'APPRENTISSAGE**
   - Un conseil pratique pour la compréhension

**Format:**
- Écris en paragraphes naturels et fluides
- Utilise un langage accessible mais précis
- Sois pédagogique et encourageant
- Structure avec des transitions
- Utilise le markdown pour la mise en forme (gras, italique)
- Évite les listes à puces, privilégie la prose

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
        
        # Vérifier les caractères suspects
        if re.search(r'[<>{}]', concept):
            return False, "Le concept contient des caractères non autorisés"
        
        return True, concept
    
    def process_concept(self, concept, language='fr', detail_level='moyen'):
        """Traite un concept mathématique complet"""
        logger.info(f"🔍 Nouvelle requête: '{concept}' (langue={language}, détail={detail_level})")
        self.stats['requests'] += 1
        start_time = time.time()
        
        # Validation
        is_valid, result = self.validate_concept(concept)
        if not is_valid:
            self.stats['errors'] += 1
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
        
        logger.info("🔄 Cache MISS - Génération avec Mistral")
        
        try:
            # Construire et exécuter le prompt
            prompt = self.build_prompt(concept, language, detail_level)
            ai_response = self.call_mistral_with_retry(prompt)
            
            if not ai_response:
                raise Exception("Réponse vide de Mistral")
            
            # Convertir en HTML
            formatted_response = self.markdown_to_html(ai_response)
            
            # Calculer le temps de traitement
            processing_time = round(time.time() - start_time, 2)
            self.processing_times.append(processing_time)
            
            # Mettre à jour les statistiques
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
                'from_cache': False,
                'cache_size': self.cache.size()
            }
            
            # Mettre en cache
            self.cache.set(cache_key, result)
            self.stats['concepts_explored'] += 1
            
            logger.info(f"✅ Succès en {processing_time}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur: {str(e)}", exc_info=True)
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
@require_rate_limit
def explore():
    """API d'exploration de concepts - CORRIGÉ"""
    
    logger.info(f"📨 Requête reçue: {request.method} depuis {request.remote_addr}")
    
    # CORS preflight
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        # Log détaillé pour débogage
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Validation du Content-Type
        if not request.is_json:
            logger.error(f"❌ Content-Type invalide: {request.content_type}")
            return jsonify({
                'success': False,
                'error': 'Content-Type doit être application/json'
            }), 400
        
        data = request.get_json()
        
        if not data:
            logger.error("❌ Corps JSON vide")
            return jsonify({
                'success': False,
                'error': 'Corps de requête JSON requis'
            }), 400
        
        # Extraction et validation des paramètres
        concept = data.get('concept', '').strip()
        language = data.get('language', 'fr')
        detail_level = data.get('detail_level', 'moyen')
        
        logger.info(f"📝 Paramètres reçus: concept='{concept}', language={language}, detail_level={detail_level}")
        
        # Validation de la langue
        if language not in ['fr', 'en', 'es']:
            logger.warning(f"Langue invalide: {language}, utilisation de 'fr'")
            language = 'fr'
        
        # Validation du niveau de détail
        if detail_level not in ['court', 'moyen', 'long']:
            logger.warning(f"Niveau invalide: {detail_level}, utilisation de 'moyen'")
            detail_level = 'moyen'
        
        if not concept:
            logger.error("❌ Concept manquant")
            return jsonify({
                'success': False,
                'error': 'Le paramètre "concept" est requis'
            }), 400
        
        # Traitement
        logger.info(f"🚀 Démarrage du traitement...")
        result = mathia.process_concept(concept, language, detail_level)
        
        if not result.get('success'):
            logger.error(f"❌ Échec du traitement: {result.get('error')}")
            return jsonify(result), 500
        
        logger.info(f"✅ Traitement réussi en {result.get('processing_time')}s")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"💥 Erreur endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Erreur interne du serveur: {str(e)}'
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Récupère les statistiques"""
    try:
        stats = mathia.stats.copy()
        stats['cache_size'] = mathia.cache.size()
        stats['cache_max_size'] = Config.CACHE_MAX_SIZE
        logger.info(f"📊 Stats demandées: {stats}")
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Erreur stats: {str(e)}")
        return jsonify({'error': 'Erreur lors de la récupération des stats'}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    health_data = {
        'status': 'OK',
        'service': 'Mathia Explorer',
        'version': '4.0',
        'api_keys_configured': len(Config.API_KEYS),
        'cache_size': mathia.cache.size(),
        'stats': mathia.stats
    }
    logger.info(f"❤️ Health check: {health_data['status']}")
    return jsonify(health_data), 200


# Template HTML complet avec tous les styles et fonctionnalités
MATHIA_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Explorateur Mathématique IA</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #f0f4f8;
            --bg-secondary: #dbe4ec;
            --bg-tertiary: #ffffff;
            --text-primary: #0d1b2a;
            --text-secondary: #415a77;
            --accent: #e63946;
            --accent-secondary: #f77f00;
            --accent-hover: #d62828;
            --border: #cbd5e1;
            --shadow: rgba(230, 57, 70, 0.15);
        }
        
        [data-theme="dark"] {
            --bg-primary: #0d1b2a;
            --bg-secondary: #1b263b;
            --bg-tertiary: #415a77;
            --text-primary: #e0e1dd;
            --text-secondary: #cbd5e1;
            --accent: #e63946;
            --accent-secondary: #f77f00;
            --accent-hover: #ff4757;
            --border: #415a77;
            --shadow: rgba(230, 57, 70, 0.25);
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
            background: linear-gradient(135deg, #e63946 0%, #f77f00 100%);
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
            background: rgba(13, 27, 42, 0.95);
            border-bottom: 1px solid var(--border);
        }
        
        .logo {
            font-size: 1.2rem;
            font-weight: 700;
            color: white;
            text-decoration: none;
        }
        
        [data-theme="dark"] .logo {
            color: var(--text-primary);
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
        
        .container {
            flex: 1; padding: 100px 30px 30px; max-width: 1200px; margin: 0 auto; width: 100%;
            display: flex; flex-direction: column; gap: 30px;
        }
        
        .title-section {
            text-align: center; margin-bottom: 20px;
        }
        
        .title {
            font-size: 2.8rem; font-weight: 700; margin-bottom: 10px; color: white;
            text-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        
        [data-theme="dark"] .title {
            color: var(--text-primary);
            text-shadow: none;
        }
        
        .subtitle { 
            color: rgba(255,255,255,0.95); 
            font-size: 1.15rem; 
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
            box-shadow: 0 0 0 3px rgba(230, 57, 70, 0.2);
        }
        
        .input::placeholder { color: rgba(255,255,255,0.8); }
        
        [data-theme="dark"] .input::placeholder {
            color: var(--text-secondary);
        }
        
        .detail-selector { display: flex; gap: 15px; flex-wrap: wrap; }
        
        .detail-btn {
            background: rgba(255, 255, 255, 0.25);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 15px; padding: 12px 20px; font-size: 0.9rem; 
            color: rgba(255,255,255,0.9);
            cursor: pointer; transition: all 0.2s ease; flex: 1; min-width: 150px;
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .detail-btn {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-primary);
            backdrop-filter: none;
        }
        
        .detail-btn.active {
            background: rgba(255, 255, 255, 0.5); 
            color: white; 
            border-color: rgba(255, 255, 255, 0.6);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
        }
        
        [data-theme="dark"] .detail-btn.active {
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
        
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        
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
            background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
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
        
        .result-meta { color: rgba(255,255,255,0.9); font-size: 0.9rem; margin-bottom: 20px; }
        
        [data-theme="dark"] .result-meta {
            color: var(--text-secondary);
        }
        
        .result-content { 
            color: rgba(255,255,255,0.95); 
            line-height: 1.7; 
            font-size: 1rem; 
        }
        
        [data-theme="dark"] .result-content {
            color: var(--text-primary);
        }
        
        .result-content p { margin-bottom: 15px; }
        .result-content strong { color: white; font-weight: 600; }
        
        [data-theme="dark"] .result-content strong {
            color: var(--text-primary);
        }
        
        .cache-badge {
            display: inline-block;
            background: rgba(74, 222, 128, 0.3);
            border: 1px solid rgba(74, 222, 128, 0.5);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-left: 10px;
        }
        
        [data-theme="dark"] .cache-badge {
            background: rgba(74, 222, 128, 0.2);
            border-color: rgba(74, 222, 128, 0.4);
            color: #4ade80;
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
        
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        
        .notification {
            position: fixed; top: 90px; right: 20px; padding: 15px 25px;
            border-radius: 15px; color: white; font-weight: 500; z-index: 1000;
            transform: translateX(400px); transition: all 0.3s ease;
            backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.3);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }
        
        .notification.show { transform: translateX(0); }
        .notification.error { background: rgba(214, 40, 40, 0.95); }
        .notification.success { background: rgba(34, 197, 94, 0.95); }
        .notification.info { background: rgba(247, 127, 0, 0.95); }
        
        @media (max-width: 768px) {
            .top-header { padding: 15px 20px; flex-direction: column; gap: 15px; }
            .header-controls { width: 100%; justify-content: space-between; }
            .container { padding: 140px 20px 20px; }
            .title { font-size: 2rem; }
            .stats { gap: 10px; }
            .stat-item { padding: 8px 15px; font-size: 0.8rem; }
            .detail-selector { flex-direction: column; gap: 10px; }
            .detail-btn { min-width: auto; }
            .controls { flex-direction: column; gap: 10px; }
            .btn { width: 100%; }
            .result-header { flex-direction: column; align-items: flex-start; }
            .result-title { margin-right: 0; margin-bottom: 15px; }
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
                        <span style="color: rgba(255,255,255,0.9); font-size: 0.9rem;">💡 <span data-text-key="popular_suggestions">Suggestions populaires:</span></span>
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
            document.documentElement.setAttribute('data-theme', currentTheme);
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
            document.documentElement.setAttribute('data-theme', currentTheme);
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
                
                const response = await fetch('/api/explore', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });

                console.log('📡 Réponse HTTP:', response.status, response.statusText);

                updateProgress(60);
                updateStatus(translations[currentLanguage].generating);

                if (!response.ok) {
                    let errorMessage = `HTTP ${response.status}`;
                    try {
                        const contentType = response.headers.get('content-type');
                        if (contentType && contentType.includes('application/json')) {
                            const errorData = await response.json();
                            errorMessage = errorData.error || errorMessage;
                            console.error('❌ Erreur serveur:', errorData);
                        } else {
                            const errorText = await response.text();
                            console.error('❌ Réponse non-JSON:', errorText);
                        }
                    } catch (e) {
                        console.error('Error parsing error response:', e);
                    }
                    
                    if (response.status === 429) {
                        throw new Error(translations[currentLanguage].rate_limit_error);
                    }
                    
                    throw new Error(errorMessage);
                }

                const data = await response.json();
                console.log('✅ Données reçues:', data);

                if (!data.success) {
                    throw new Error(data.error || 'Unknown error');
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
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("=" * 70)
    print("🔢 MATHIA V4.0 - Explorateur Mathématique avec IA")
    print("=" * 70)
    
    try:
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"\n⚙️  Configuration:")
        print(f"   • Port: {port}")
        print(f"   • Debug: {debug_mode}")
        print(f"   • Clés API: {len(Config.API_KEYS)}")
        print(f"   • Cache Max: {Config.CACHE_MAX_SIZE} entrées")
        print(f"   • Rate Limit: {Config.RATE_LIMIT_REQUESTS} req/{Config.RATE_LIMIT_WINDOW}s")
        
        print("\n✨ Fonctionnalités:")
        print("   • Exploration avec Mistral AI (Large + Small fallback)")
        print("   • Cache LRU intelligent")
        print("   • Rate limiting par IP")
        print("   • Conversion Markdown → HTML")
        print("   • Support multilingue (FR/EN/ES)")
        print("   • 3 niveaux de détail")
        print("   • Statistiques en temps réel")
        print("   • Thème clair/sombre persistant")
        
        print("\n📍 Routes:")
        print("   • GET  /            → Interface utilisateur")
        print("   • POST /api/explore → Exploration de concepts")
        print("   • GET  /api/stats   → Statistiques")
        print("   • GET  /health      → Health check")
        
        print("\n🚀 Démarrage du serveur...")
        print("=" * 70)
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
        
    except ImportError as e:
        print(f"\n❌ ERREUR: Dépendance manquante - {e}")
        print("   Installez: pip install flask mistralai markdown")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERREUR FATALE: {e}")
        exit(1)
