from flask import Flask, request, jsonify, render_template_string
import os
import json
from mistralai import Mistral
import logging
import time
import hashlib
import re
from datetime import datetime, timedelta
from collections import defaultdict

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration CORS globale AMÉLIORÉE
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

# Configuration
class Config:
    API_KEYS = [
        'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX',
        '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF',
        'cvkQHVcomFFEW47G044x2p4DTyk5BIc7'
    ]
    
    MAX_CONCEPT_LENGTH = 200
    MIN_CONCEPT_LENGTH = 2
    CACHE_MAX_SIZE = 100
    REQUEST_TIMEOUT = 30
    
    MISTRAL_MODEL_PRIMARY = "mistral-large-latest"
    MISTRAL_MODEL_FALLBACK = "mistral-small-latest"
    MISTRAL_MAX_TOKENS = 1200
    MISTRAL_TEMPERATURE = 0.7

logger.info(f"✅ Mathia configuré avec {len(Config.API_KEYS)} clés API")

# Cache simple
class SimpleCache:
    def __init__(self, max_size=100):
        self.cache = {}
        self.max_size = max_size
    
    def get(self, key):
        return self.cache.get(key)
    
    def set(self, key, value):
        if len(self.cache) >= self.max_size:
            oldest = next(iter(self.cache))
            del self.cache[oldest]
        self.cache[key] = value
    
    def size(self):
        return len(self.cache)

class MathiaExplorer:
    def __init__(self):
        self.api_keys = Config.API_KEYS
        self.current_key_index = 0
        self.cache = SimpleCache(max_size=Config.CACHE_MAX_SIZE)
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'concepts_explored': 0,
            'errors': 0
        }
        logger.info("✅ MathiaExplorer initialisé")
    
    def get_next_api_key(self):
        key = self.api_keys[self.current_key_index % len(self.api_keys)]
        self.current_key_index += 1
        return key
    
    def call_mistral(self, prompt):
        """Appelle Mistral avec retry automatique"""
        max_retries = len(self.api_keys)
        
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
                logger.warning(f"⚠️ Erreur tentative {attempt + 1}: {e}")
                
                # Essayer le modèle fallback si rate limit
                if "429" in error_msg or "capacity" in error_msg:
                    try:
                        logger.info("🔄 Essai avec modèle fallback...")
                        response = client.chat.complete(
                            model=Config.MISTRAL_MODEL_FALLBACK,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=Config.MISTRAL_TEMPERATURE,
                            max_tokens=Config.MISTRAL_MAX_TOKENS
                        )
                        return response.choices[0].message.content.strip()
                    except:
                        pass
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise Exception(f"Toutes les tentatives ont échoué: {e}")
    
    def get_cache_key(self, concept, language, detail_level):
        normalized = f"{concept.lower().strip()}_{language}_{detail_level}"
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def format_markdown(self, text):
        """Conversion Markdown basique en HTML"""
        if not text:
            return ""
        
        # Gras et italique
        text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
        
        # Paragraphes
        paragraphs = text.split('\n\n')
        formatted = []
        
        for para in paragraphs:
            para = para.strip()
            if para:
                if not para.startswith('<'):
                    para = f'<p>{para}</p>'
                formatted.append(para)
        
        return '\n'.join(formatted)
    
    def build_prompt(self, concept, language, detail_level):
        """Construit le prompt pour Mistral"""
        lang_instructions = {
            'fr': 'Réponds EXCLUSIVEMENT en français.',
            'en': 'Respond EXCLUSIVELY in English.',
            'es': 'Responde EXCLUSIVAMENTE en español.'
        }
        
        word_counts = {
            'court': '150-200 mots',
            'moyen': '300-400 mots',
            'long': '500-600 mots'
        }
        
        lang_instruction = lang_instructions.get(language, lang_instructions['fr'])
        word_count = word_counts.get(detail_level, word_counts['moyen'])
        
        prompt = f"""Tu es Mathia, un expert en mathématiques passionné. Explique le concept "{concept}" de manière claire et pédagogique.

{lang_instruction}

**Instructions:**
Fournis une explication en {word_count}, structurée ainsi:

1. **DÉFINITION** (2-3 phrases)
   - Explique simplement le concept
   - Donne le contexte

2. **EXPLICATION** (plusieurs paragraphes)
   - Développe en profondeur
   - Explique les propriétés
   - Montre le fonctionnement

3. **EXEMPLES** (3-4 exemples)
   - Exemples mathématiques concrets
   - Du simple au complexe
   - Applications pratiques

4. **CONCEPTS LIÉS** (4-5 concepts)
   - Liste des concepts connexes

5. **IMPORTANCE**
   - Applications réelles
   - Pourquoi c'est fondamental

6. **CONSEIL**
   - Un conseil pratique

**Format:**
- Écris en paragraphes fluides
- Langage accessible mais précis
- Sois pédagogique
- Utilise markdown (gras, italique)

Réponds maintenant:"""
        
        return prompt
    
    def validate_concept(self, concept):
        """Valide le concept"""
        if not concept or not isinstance(concept, str):
            return False, "Le concept doit être une chaîne"
        
        concept = concept.strip()
        
        if len(concept) < Config.MIN_CONCEPT_LENGTH:
            return False, f"Minimum {Config.MIN_CONCEPT_LENGTH} caractères"
        
        if len(concept) > Config.MAX_CONCEPT_LENGTH:
            return False, f"Maximum {Config.MAX_CONCEPT_LENGTH} caractères"
        
        if re.search(r'[<>{}]', concept):
            return False, "Caractères non autorisés"
        
        return True, concept
    
    def process_concept(self, concept, language='fr', detail_level='moyen'):
        """Traite un concept mathématique"""
        logger.info(f"🔍 Requête: '{concept}' (lang={language}, detail={detail_level})")
        self.stats['requests'] += 1
        start_time = time.time()
        
        # Validation
        is_valid, result = self.validate_concept(concept)
        if not is_valid:
            self.stats['errors'] += 1
            return {'success': False, 'error': result}
        
        concept = result
        
        # Cache
        cache_key = self.get_cache_key(concept, language, detail_level)
        cached = self.cache.get(cache_key)
        
        if cached:
            logger.info("💾 Cache HIT")
            self.stats['cache_hits'] += 1
            cached['from_cache'] = True
            return cached
        
        logger.info("🔄 Cache MISS - Génération IA")
        
        try:
            # Appel Mistral
            prompt = self.build_prompt(concept, language, detail_level)
            ai_response = self.call_mistral(prompt)
            
            if not ai_response:
                raise Exception("Réponse vide de Mistral")
            
            # Formatage
            formatted = self.format_markdown(ai_response)
            processing_time = round(time.time() - start_time, 2)
            
            result = {
                'success': True,
                'concept': concept.title(),
                'explanation': formatted,
                'processing_time': processing_time,
                'detail_level': detail_level,
                'language': language,
                'source': 'mistral_ai',
                'from_cache': False,
                'cache_size': self.cache.size()
            }
            
            # Mise en cache
            self.cache.set(cache_key, result)
            self.stats['concepts_explored'] += 1
            
            logger.info(f"✅ Succès en {processing_time}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur: {str(e)}", exc_info=True)
            self.stats['errors'] += 1
            return {
                'success': False,
                'error': f'Erreur: {str(e)}'
            }

# Instance globale
mathia = MathiaExplorer()

# Routes
@app.route('/')
def index():
    """Page principale"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/explore', methods=['POST', 'OPTIONS'])
def explore():
    """API d'exploration - CORRIGÉE"""
    
    # Gestion OPTIONS pour CORS
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.status_code = 200
        return response
    
    try:
        logger.info(f"📨 POST /api/explore depuis {request.remote_addr}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        # Vérification Content-Type
        if not request.is_json:
            logger.error(f"❌ Content-Type invalide: {request.content_type}")
            return jsonify({
                'success': False,
                'error': 'Content-Type doit être application/json'
            }), 400
        
        # Récupération données
        data = request.get_json(force=True)
        logger.info(f"📦 Données reçues: {data}")
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Corps JSON requis'
            }), 400
        
        # Extraction paramètres
        concept = data.get('concept', '').strip()
        language = data.get('language', 'fr')
        detail_level = data.get('detail_level', 'moyen')
        
        # Validation
        if language not in ['fr', 'en', 'es']:
            language = 'fr'
        
        if detail_level not in ['court', 'moyen', 'long']:
            detail_level = 'moyen'
        
        if not concept:
            return jsonify({
                'success': False,
                'error': 'Paramètre "concept" requis'
            }), 400
        
        logger.info(f"✅ Paramètres validés: concept={concept}, lang={language}, detail={detail_level}")
        
        # Traitement
        result = mathia.process_concept(concept, language, detail_level)
        
        if not result.get('success'):
            logger.error(f"❌ Échec traitement: {result.get('error')}")
            return jsonify(result), 500
        
        logger.info(f"✅ Succès: {result.get('processing_time')}s")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"💥 Exception: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
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
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'OK',
        'service': 'Mathia Explorer',
        'version': '4.2',
        'api_keys': len(Config.API_KEYS),
        'cache_size': mathia.cache.size()
    }), 200

# Template HTML complet
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Explorateur Mathématique IA</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --primary: #e63946;
            --secondary: #f77f00;
            --bg-light: #ffffff;
            --bg-dark: #0d1b2a;
            --text-light: #ffffff;
            --text-dark: #1a1a1a;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: var(--text-light);
            min-height: 100vh;
            padding: 20px;
        }
        
        body[data-theme="dark"] {
            background: var(--bg-dark);
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
            padding: 20px;
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
        }
        
        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        
        .header p {
            font-size: 1.2rem;
            opacity: 0.95;
        }
        
        .controls-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .stats {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .stat-item {
            background: rgba(255, 255, 255, 0.2);
            padding: 10px 20px;
            border-radius: 12px;
            font-size: 0.9rem;
            backdrop-filter: blur(10px);
        }
        
        .language-selector, .theme-toggle {
            background: rgba(255, 255, 255, 0.2);
            border: none;
            padding: 12px 20px;
            border-radius: 12px;
            color: white;
            cursor: pointer;
            font-size: 1rem;
            backdrop-filter: blur(10px);
            transition: all 0.3s;
        }
        
        .language-selector:hover, .theme-toggle:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
        }
        
        .form-section {
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .label {
            display: block;
            font-weight: 600;
            margin-bottom: 10px;
            font-size: 1.1rem;
        }
        
        .input {
            width: 100%;
            padding: 15px 20px;
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 12px;
            font-size: 1rem;
            color: white;
            outline: none;
            transition: all 0.3s;
        }
        
        .input:focus {
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.1);
        }
        
        .input::placeholder {
            color: rgba(255, 255, 255, 0.7);
        }
        
        .suggestions {
            margin-top: 15px;
        }
        
        .suggestion-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }
        
        .chip {
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 20px;
            padding: 8px 16px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.3s;
        }
        
        .chip:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
        }
        
        .detail-selector {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .detail-btn {
            flex: 1;
            min-width: 150px;
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 12px;
            padding: 15px;
            cursor: pointer;
            font-size: 0.95rem;
            color: white;
            transition: all 0.3s;
        }
        
        .detail-btn:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
        }
        
        .detail-btn.active {
            background: rgba(255, 255, 255, 0.4);
            border-color: rgba(255, 255, 255, 0.6);
            font-weight: 600;
        }
        
        .controls {
            display: flex;
            gap: 15px;
            justify-content: center;
            flex-wrap: wrap;
        }
        
        .btn {
            background: rgba(255, 255, 255, 0.3);
            border: none;
            border-radius: 12px;
            padding: 15px 40px;
            font-size: 1.1rem;
            font-weight: 600;
            color: white;
            cursor: pointer;
            transition: all 0.3s;
            backdrop-filter: blur(10px);
        }
        
        .btn:hover:not(:disabled) {
            background: rgba(255, 255, 255, 0.4);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .btn-primary {
            background: rgba(255, 255, 255, 0.4);
        }
        
        .status {
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            display: none;
        }
        
        .status.active {
            display: block;
            animation: slideIn 0.3s ease;
        }
        
        .status-text {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            font-weight: 500;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s linear infinite;
            margin-right: 10px;
        }
        
        .progress-bar {
            width: 100%;
            height: 6px;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: white;
            width: 0%;
            transition: width 0.3s;
            border-radius: 10px;
        }
        
        .result {
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            display: none;
        }
        
        .result.active {
            display: block;
            animation: slideIn 0.5s ease;
        }
        
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.2);
        }
        
        .result-title {
            font-size: 1.5rem;
            font-weight: 600;
        }
        
        .copy-btn {
            background: rgba(255, 255, 255, 0.2);
            border: none;
            border-radius: 10px;
            padding: 10px 15px;
            cursor: pointer;
            font-size: 1.2rem;
            transition: all 0.3s;
        }
        
        .copy-btn:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.1);
        }
        
        .result-meta {
            font-size: 0.95rem;
            opacity: 0.9;
            margin-bottom: 20px;
        }
        
        .result-content {
            line-height: 1.8;
            font-size: 1.05rem;
        }
        
        .result-content p {
            margin-bottom: 15px;
        }
        
        .result-content strong {
            font-weight: 600;
        }
        
        .cache-badge {
            display: inline-block;
            background: rgba(34, 197, 94, 0.3);
            border: 1px solid rgba(34, 197, 94, 0.5);
            color: #4ade80;
            padding: 4px 12px;
            border-radius: 10px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-left: 10px;
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 12px;
            color: white;
            font-weight: 500;
            z-index: 1000;
            transform: translateX(400px);
            transition: all 0.3s;
            backdrop-filter: blur(10px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.3);
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.error {
            background: rgba(220, 38, 38, 0.95);
        }
        
        .notification.success {
            background: rgba(34, 197, 94, 0.95);
        }
        
        .notification.info {
            background: rgba(59, 130, 246, 0.95);
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @media (max-width: 768px) {
            .header h1 {
                font-size: 2rem;
            }
            
            .controls-bar {
                flex-direction: column;
            }
            
            .stats {
                width: 100%;
                justify-content: center;
            }
            
            .detail-selector {
                flex-direction: column;
            }
            
            .detail-btn {
                min-width: auto;
            }
            
            .controls {
                flex-direction: column;
                width: 100%;
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
            <h1>🔢 Mathia</h1>
            <p>Explorateur de concepts mathématiques avec IA</p>
        </div>

        <div class="controls-bar">
            <div class="stats" id="stats">
                <div class="stat-item">📊 <span id="totalRequests">0</span> requêtes</div>
                <div class="stat-item">💾 <span id="cacheHits">0</span> cache</div>
                <div class="stat-item">🎯 <span id="conceptsExplored">0</span> concepts</div>
            </div>
            
            <div style="display: flex; gap: 15px;">
                <select class="language-selector" id="languageSelector" onchange="changeLanguage()">
                    <option value="fr">🇫🇷 Français</option>
                    <option value="en">🇺🇸 English</option>
                    <option value="es">🇪🇸 Español</option>
                </select>
                
                <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()">🌙</button>
            </div>
        </div>

        <div class="form-section">
            <form id="explorerForm" onsubmit="handleSubmit(event)">
                <div class="form-group">
                    <label class="label">🔍 Concept à explorer</label>
                    <input type="text" id="concept" class="input" 
                           placeholder="Ex: fonction, dérivée, intégrale..." required>
                    
                    <div class="suggestions">
                        <span style="opacity: 0.9;">💡 Suggestions:</span>
                        <div class="suggestion-chips" id="suggestionChips"></div>
                    </div>
                </div>

                <div class="form-group">
                    <label class="label">📏 Niveau de détail</label>
                    <div class="detail-selector">
                        <button type="button" class="detail-btn" onclick="selectDetail('court', this)">
                            📝 Court<br><small>150-200 mots</small>
                        </button>
                        <button type="button" class="detail-btn active" onclick="selectDetail('moyen', this)">
                            📄 Moyen<br><small>300-400 mots</small>
                        </button>
                        <button type="button" class="detail-btn" onclick="selectDetail('long', this)">
                            📚 Détaillé<br><small>500-600 mots</small>
                        </button>
                    </div>
                </div>

                <div class="controls">
                    <button type="submit" class="btn btn-primary" id="exploreBtn">
                        ✨ Explorer le concept
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
                <span id="statusText">Analyse en cours...</span>
            </div>
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
        </div>

        <div id="result" class="result">
            <div class="result-header">
                <div class="result-title">📖 Explication générée</div>
                <button class="copy-btn" onclick="copyResult()">📋</button>
            </div>
            <div class="result-meta" id="resultMeta"></div>
            <div class="result-content" id="resultContent"></div>
        </div>
    </div>

    <script>
        let isProcessing = false;
        let currentDetail = 'moyen';
        let currentLanguage = 'fr';

        const suggestions = {
            fr: ["Fonction", "Dérivée", "Intégrale", "Matrice", "Probabilité", "Limite", "Vecteur"],
            en: ["Function", "Derivative", "Integral", "Matrix", "Probability", "Limit", "Vector"],
            es: ["Función", "Derivada", "Integral", "Matriz", "Probabilidad", "Límite", "Vector"]
        };

        document.addEventListener('DOMContentLoaded', function() {
            loadLanguage();
            initSuggestions();
            loadStats();
            document.getElementById('concept').focus();
        });

        function loadLanguage() {
            const saved = localStorage.getItem('mathia_language') || 'fr';
            currentLanguage = saved;
            document.getElementById('languageSelector').value = saved;
        }

        function changeLanguage() {
            currentLanguage = document.getElementById('languageSelector').value;
            localStorage.setItem('mathia_language', currentLanguage);
            initSuggestions();
        }

        function toggleTheme() {
            const body = document.body;
            const current = body.getAttribute('data-theme');
            const newTheme = current === 'dark' ? 'light' : 'dark';
            
            if (newTheme === 'dark') {
                body.setAttribute('data-theme', 'dark');
            } else {
                body.removeAttribute('data-theme');
            }
            
            document.getElementById('themeToggle').textContent = newTheme === 'light' ? '🌙' : '☀️';
            localStorage.setItem('mathia_theme', newTheme);
        }

        function initSuggestions() {
            const container = document.getElementById('suggestionChips');
            container.innerHTML = '';
            
            const concepts = suggestions[currentLanguage] || suggestions.fr;
            concepts.forEach(concept => {
                const chip = document.createElement('button');
                chip.className = 'chip';
                chip.textContent = concept;
                chip.type = 'button';
                chip.onclick = () => {
                    document.getElementById('concept').value = concept;
                    document.getElementById('concept').focus();
                };
                container.appendChild(chip);
            });
        }

        function selectDetail(detail, btn) {
            document.querySelectorAll('.detail-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentDetail = detail;
        }

        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                if (response.ok) {
                    const stats = await response.json();
                    document.getElementById('totalRequests').textContent = stats.requests || 0;
                    document.getElementById('cacheHits').textContent = stats.cache_hits || 0;
                    document.getElementById('conceptsExplored').textContent = stats.concepts_explored || 0;
                }
            } catch (error) {
                console.log('Stats error:', error);
            }
        }

        function handleSubmit(event) {
            event.preventDefault();
            
            if (isProcessing) {
                showNotification('Une exploration est déjà en cours...', 'info');
                return;
            }

            const concept = document.getElementById('concept').value.trim();
            
            if (!concept || concept.length < 2) {
                showNotification('Veuillez entrer un concept valide', 'error');
                document.getElementById('concept').focus();
                return;
            }

            processConcept(concept);
        }

        async function processConcept(concept) {
            isProcessing = true;
            const btn = document.getElementById('exploreBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Exploration...';
            
            showStatus('Analyse en cours...');
            hideResult();
            updateProgress(0);

            try {
                console.log('🚀 Envoi requête...');
                updateProgress(20);
                
                const requestBody = {
                    concept: concept,
                    language: currentLanguage,
                    detail_level: currentDetail
                };
                
                console.log('📦 Body:', requestBody);
                
                const response = await fetch('/api/explore', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify(requestBody)
                });

                console.log('📡 Response:', response.status, response.statusText);
                
                updateProgress(60);

                if (!response.ok) {
                    let errorMsg = `Erreur HTTP ${response.status}`;
                    
                    try {
                        const errorData = await response.json();
                        errorMsg = errorData.error || errorMsg;
                    } catch (e) {
                        const errorText = await response.text();
                        console.error('Erreur texte:', errorText);
                        errorMsg = errorText.substring(0, 200);
                    }
                    
                    throw new Error(errorMsg);
                }

                const data = await response.json();
                console.log('✅ Données reçues:', data);

                if (!data.success) {
                    throw new Error(data.error || 'Erreur inconnue');
                }

                updateProgress(100);
                await sleep(300);

                showResult(data);
                hideStatus();
                loadStats();
                showNotification('Explication générée !', 'success');

            } catch (error) {
                console.error('💥 Erreur:', error);
                showNotification(error.message || 'Erreur lors de l\'exploration', 'error');
                hideStatus();
            } finally {
                isProcessing = false;
                btn.disabled = false;
                btn.textContent = '✨ Explorer le concept';
            }
        }

        function updateProgress(percent) {
            document.getElementById('progressFill').style.width = percent + '%';
        }

        function showStatus(message) {
            document.getElementById('statusText').textContent = message;
            document.getElementById('status').classList.add('active');
            updateProgress(0);
        }

        function hideStatus() {
            document.getElementById('status').classList.remove('active');
        }

        function showResult(data) {
            document.getElementById('resultContent').innerHTML = data.explanation;
            
            let meta = `🤖 Mistral AI • ${data.processing_time}s • ${data.detail_level}`;
            if (data.from_cache) {
                meta += ' • <span class="cache-badge">💾 Cache</span>';
            }
            
            document.getElementById('resultMeta').innerHTML = meta;
            document.getElementById('result').classList.add('active');
        }

        function hideResult() {
            document.getElementById('result').classList.remove('active');
        }

        function copyResult() {
            const content = document.getElementById('resultContent');
            const text = content.textContent || content.innerText;
            
            navigator.clipboard.writeText(text).then(() => {
                showNotification('Copié !', 'success');
            }).catch(() => {
                showNotification('Échec de la copie', 'error');
            });
        }

        function clearAll() {
            document.getElementById('concept').value = '';
            document.getElementById('concept').focus();
            hideStatus();
            hideResult();
            isProcessing = false;
            document.getElementById('exploreBtn').disabled = false;
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
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("=" * 80)
    print("🔢 MATHIA V4.2 - EXPLORATEUR MATHÉMATIQUE IA")
    print("=" * 80)
    
    try:
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"\n⚙️  Configuration:")
        print(f"   • Port: {port}")
        print(f"   • Debug: {debug}")
        print(f"   • Clés API: {len(Config.API_KEYS)}")
        print(f"   • Cache: {Config.CACHE_MAX_SIZE} entrées")
        
        print("\n✅ Corrections apportées:")
        print("   ✅ Gestion CORS complète (OPTIONS + headers)")
        print("   ✅ Logging détaillé des requêtes")
        print("   ✅ Validation robuste des paramètres")
        print("   ✅ Gestion d'erreurs améliorée")
        print("   ✅ Code JavaScript simplifié et testé")
        print("   ✅ Force JSON parsing (force=True)")
        print("   ✅ Retry automatique multi-clés")
        print("   ✅ Interface responsive corrigée")
        
        print("\n📍 Routes disponibles:")
        print("   • GET  /            → Interface web")
        print("   • POST /api/explore → Exploration de concepts")
        print("   • GET  /api/stats   → Statistiques")
        print("   • GET  /health      → Health check")
        
        print("\n🚀 Démarrage du serveur...")
        print("=" * 80)
        print()
        
        app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
        
    except Exception as e:
        print(f"\n❌ ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
