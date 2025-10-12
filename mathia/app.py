from flask import Flask, request, jsonify, render_template_string
import os
import json
from mistralai import Mistral
import logging
import time
import hashlib
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class MathiaExplorer:
    """Explorateur mathématique avec IA Mistral"""
    
    def __init__(self):
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        self.current_key_index = 0
        self.cache = {}
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'concepts_explored': 0
        }
        self.current_language = 'fr'
        
        logger.info("Mathia Explorer initialized with Mistral AI")
    
    def get_mistral_client(self):
        """Obtient un client Mistral avec rotation des clés"""
        key = self.api_keys[self.current_key_index % len(self.api_keys)]
        self.current_key_index += 1
        return Mistral(api_key=key)
    
    def retry_with_different_keys(self, func, *args, **kwargs):
        """Retry avec toutes les clés API disponibles"""
        last_exception = None
        
        for attempt in range(len(self.api_keys)):
            try:
                logger.info(f"Tentative {attempt + 1} avec clé API")
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                logger.warning(f"Erreur avec clé {attempt + 1}: {str(e)}")
                last_exception = e
                self.current_key_index += 1
                if attempt < len(self.api_keys) - 1:
                    time.sleep(2)
                continue
        
        raise Exception(f"Toutes les clés API ont échoué. Dernière erreur: {str(last_exception)}")
    
    def get_cache_key(self, concept, language, detail_level):
        """Génère une clé de cache unique"""
        return hashlib.md5(f"{concept.lower().strip()}_{language}_{detail_level}".encode()).hexdigest()
    
    def markdown_to_html(self, text):
        """Convertit le Markdown en HTML"""
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
    
    def get_language_instruction(self, language):
        """Retourne l'instruction de langue"""
        instructions = {
            'fr': 'Réponds en français.',
            'en': 'Respond in English.',
            'es': 'Responde en español.'
        }
        return instructions.get(language, instructions['fr'])
    
    def explore_concept_with_ai(self, concept, language='fr', detail_level='moyen'):
        """Explore un concept mathématique avec Mistral AI"""
        def _explore():
            client = self.get_mistral_client()
            
            lang_instruction = self.get_language_instruction(language)
            
            word_counts = {
                'court': '150-200 mots',
                'moyen': '300-400 mots',
                'long': '500-600 mots'
            }
            word_count = word_counts.get(detail_level, word_counts['moyen'])
            
            prompt = f"""Tu es Mathia, un expert en mathématiques qui vulgarise les concepts de manière claire et pédagogique.

Concept à explorer: "{concept}"

{lang_instruction}

Fournis une explication complète et structurée du concept en {word_count}:

1. DÉFINITION (2-3 phrases claires)
   - Explique ce que c'est en termes simples
   - Donne le contexte mathématique

2. EXPLICATION DÉTAILLÉE (plusieurs paragraphes)
   - Développe le concept en profondeur
   - Explique les propriétés importantes
   - Montre comment ça fonctionne

3. EXEMPLES CONCRETS (3-5 exemples)
   - Donne des exemples mathématiques précis
   - Utilise des cas simples d'abord
   - Montre des applications pratiques

4. CONCEPTS LIÉS (liste de 4-6 concepts)
   - Mentionne les concepts connexes importants
   - Explique brièvement le lien

5. POURQUOI C'EST IMPORTANT
   - Applications dans la vie réelle
   - Importance en mathématiques

6. CONSEIL D'APPRENTISSAGE
   - Un conseil pratique pour mieux comprendre

Règles:
- Écris en paragraphes naturels, PAS en format liste à puces
- Utilise un langage accessible mais précis
- Sois pédagogique et encourageant
- Structure ton texte avec des transitions fluides
- Ne mets PAS d'astérisques ou de markdown
- Écris en texte brut

Réponse:"""

            try:
                response = client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1200
                )
            except Exception as e:
                if "429" in str(e) or "capacity" in str(e):
                    logger.warning("Rate limit, utilisation du modèle small...")
                    response = client.chat.complete(
                        model="mistral-small-latest",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7,
                        max_tokens=1200
                    )
                else:
                    raise e
            
            return response.choices[0].message.content.strip()
        
        return self.retry_with_different_keys(_explore)
    
    def process_concept(self, concept, language='fr', detail_level='moyen'):
        """Traite un concept mathématique complet"""
        logger.info(f"🔍 Exploration: '{concept}' (langue: {language}, détail: {detail_level})")
        self.stats['requests'] += 1
        start_time = time.time()
        
        if not concept or len(concept.strip()) < 2:
            return {
                'success': False,
                'error': 'Le concept doit contenir au moins 2 caractères'
            }
        
        concept = concept.strip()
        
        cache_key = self.get_cache_key(concept, language, detail_level)
        if cache_key in self.cache:
            logger.info("💾 Résultat trouvé en cache")
            self.stats['cache_hits'] += 1
            return self.cache[cache_key]
        
        try:
            logger.info(f"🤖 Génération avec Mistral pour: {concept}")
            ai_response = self.explore_concept_with_ai(concept, language, detail_level)
            
            if not ai_response:
                return {'success': False, 'error': 'Erreur lors de la génération de la réponse'}
            
            formatted_response = self.markdown_to_html(ai_response)
            
            result = {
                'success': True,
                'concept': concept.title(),
                'explanation': formatted_response,
                'processing_time': round(time.time() - start_time, 2),
                'detail_level': detail_level,
                'language': language,
                'source': 'mistral_ai'
            }
            
            self.cache[cache_key] = result
            self.stats['concepts_explored'] += 1
            logger.info(f"✅ Traitement terminé en {result['processing_time']}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur: {str(e)}")
            return {
                'success': False,
                'error': f'Erreur lors du traitement: {str(e)}'
            }

mathia = MathiaExplorer()

@app.route('/')
def index():
    """Interface principale de Mathia"""
    return render_template_string(MATHIA_TEMPLATE)

@app.route('/api/explore', methods=['POST'])
def explore():
    """API d'exploration de concepts"""
    try:
        logger.info("🚀 REQUÊTE /api/explore")
        
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type doit être application/json'}), 400
        
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        concept = data.get('concept')
        language = data.get('language', 'fr')
        detail_level = data.get('detail_level', 'moyen')
        
        if not concept or not concept.strip():
            return jsonify({'success': False, 'error': 'Concept requis'}), 400
        
        logger.info(f"🚀 EXPLORATION: '{concept}' ({language}, {detail_level})")
        
        result = mathia.process_concept(concept, language, detail_level)
        
        if not result.get('success'):
            error_msg = result.get('error', 'Erreur inconnue')
            logger.error(f"❌ ÉCHEC: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500
        
        logger.info(f"✅ SUCCÈS: {result.get('concept', 'Sans titre')}")
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"💥 ERREUR ENDPOINT: {error_msg}")
        return jsonify({'success': False, 'error': f'Erreur serveur: {error_msg}'}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Statistiques"""
    try:
        return jsonify(mathia.stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'OK',
        'service': 'Mathia Explorer',
        'version': '3.0'
    })

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
        
        .detail-btn:hover { 
            transform: translateY(-2px); 
            background: rgba(255, 255, 255, 0.35);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .detail-btn:hover {
            background: var(--bg-secondary);
            box-shadow: 0 8px 25px var(--shadow);
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
            background: var(--accent-hover);
            box-shadow: 0 10px 30px var(--shadow);
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
        <a href="/" class="back-button">
            <span>←</span>
            <span data-text-key="back_to_hub">Retour au Hub</span>
        </a>
        
        <div class="header-controls">
            <select class="language-selector" id="languageSelector" onchange="changeLanguage()">
                <option value="fr">🇫🇷 Français</option>
                <option value="en">🇺🇸 English</option>
                <option value="es">🇪🇸 Español</option>
            </select>
            
            <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()">🌙</button>
            <a href="#" class="author-link" data-text-key="by_mydd">by Mydd</a>
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
            <div class="result-meta" id="resultMeta">Source: Mistral AI • 2.3s • Moyen</div>
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
                back_to_hub: "Retour au Hub",
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
                by_mydd: "by Mydd",
                analyzing: "Analyse...",
                generating: "Génération...",
                completed: "Terminé !",
                copied: "Copié !",
                copy_error: "Échec de la copie",
                processing_concept: "Exploration en cours...",
                already_processing: "Une exploration est déjà en cours...",
                invalid_concept: "Veuillez entrer un concept valide (minimum 2 caractères)",
                explanation_generated: "Explication générée !",
                processing_error: "Erreur d'exploration"
            },
            en: {
                title: "🔢 Mathia",
                subtitle: "Mathematical concepts explorer with AI",
                back_to_hub: "Back to Hub",
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
                by_mydd: "by Mydd",
                analyzing: "Analyzing...",
                generating: "Generating...",
                completed: "Completed!",
                copied: "Copied!",
                copy_error: "Copy failed",
                processing_concept: "Exploration in progress...",
                already_processing: "An exploration is already running...",
                invalid_concept: "Please enter a valid concept (minimum 2 characters)",
                explanation_generated: "Explanation generated!",
                processing_error: "Exploration error"
            },
            es: {
                title: "🔢 Mathia",
                subtitle: "Explorador de conceptos matemáticos con IA",
                back_to_hub: "Volver al Hub",
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
                by_mydd: "by Mydd",
                analyzing: "Analizando...",
                generating: "Generando...",
                completed: "¡Completado!",
                copied: "¡Copiado!",
                copy_error: "Error al copiar",
                processing_concept: "Exploración en curso...",
                already_processing: "Ya hay una exploración en ejecución...",
                invalid_concept: "Por favor ingrese un concepto válido (mínimo 2 caracteres)",
                explanation_generated: "¡Explicación generada!",
                processing_error: "Error de exploración"
            }
        };

        const popularConcepts = {
            fr: ["Fonction", "Dérivée", "Intégrale", "Matrice", "Probabilité", "Limite", "Vecteur", "Équation", "Nombre complexe"],
            en: ["Function", "Derivative", "Integral", "Matrix", "Probability", "Limit", "Vector", "Equation", "Complex number"],
            es: ["Función", "Derivada", "Integral", "Matriz", "Probabilidad", "Límite", "Vector", "Ecuación", "Número complejo"]
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
            currentTheme = 'light';
            document.documentElement.setAttribute('data-theme', 'light');
            updateThemeToggle();
        }

        function loadLanguage() {
            currentLanguage = 'fr';
            const selector = document.getElementById('languageSelector');
            if (selector) selector.value = 'fr';
            updateTranslations();
        }

        function toggleTheme() {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', currentTheme);
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
            if (selector) currentLanguage = selector.value;
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
                showNotification(translations[currentLanguage].explanation_generated, 'success');

            } catch (error) {
                console.error('Error:', error);
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
                elements.title.innerHTML = '📖 <span data-text-key="generated_explanation">' + translations[currentLanguage].generated_explanation + '</span>';
            }
            if (elements.content) elements.content.innerHTML = data.explanation;
            
            let metaText = `🤖 Mistral AI • ${data.processing_time}s • ${data.detail_level}`;
            if (elements.meta) elements.meta.textContent = metaText;

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
    print("🔢 MATHIA V3.0 - Explorateur Mathématique avec IA")
    print("=" * 60)
    
    try:
        from mistralai import Mistral
        print("✅ Dépendances OK")
        
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port: {port}")
        print(f"🔧 Debug: {debug_mode}")
        print(f"🔑 Clés Mistral: {len(mathia.api_keys)} configurées")
        
        print("\n✨ Fonctionnalités:")
        print("   • Exploration automatique avec Mistral AI")
        print("   • Design moderne rouge/orange")
        print("   • Support multilingue (FR/EN/ES)")
        print("   • 3 niveaux de détail")
        print("   • Cache intelligent")
        
        print("\n🚀 Démarrage de Mathia...")
        
    except ImportError as e:
        print(f"❌ ERREUR: {e}")
        exit(1)
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
