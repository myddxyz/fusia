from flask import Flask, send_from_directory, redirect, request, jsonify
import os
import sys
from werkzeug.middleware.proxy_fix import ProxyFix

# Créer l'app Flask principale
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Ajouter le dossier summarizer au path pour pouvoir importer l'app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'summarizer'))

# Importer l'app du summarizer
try:
    from app import app as summarizer_app, summarizer
    print("✅ App Wikisummarizer importée avec succès")
except ImportError as e:
    print(f"❌ Erreur import Wikisummarizer: {e}")
    summarizer_app = None
    summarizer = None

@app.route('/')
def hub():
    """Servir le hub (index.html)"""
    return send_from_directory('.', 'index.html')

@app.route('/wikisummarizer')
def wikisummarizer():
    """Servir l'interface Wikisummarizer directement"""
    # Solution simple : on récupère le HTML directement du code source
    html_interface = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wikipedia Summarizer Pro</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #e6e7ee; --bg-secondary: #d1d2d9; --bg-tertiary: #fbfcff;
            --text-primary: #5a5c69; --text-secondary: #8b8d97;
            --accent: #667eea; --accent-secondary: #764ba2;
            --shadow-light: #bebfc5; --shadow-dark: #ffffff;
        }
        
        body {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            min-height: 100vh; padding: 20px;
            display: flex; align-items: center; justify-content: center;
        }
        
        .back-link {
            position: absolute; top: 20px; left: 20px;
            background: rgba(255,255,255,0.1); padding: 10px 20px;
            border-radius: 15px; color: white; text-decoration: none;
            transition: all 0.3s ease; backdrop-filter: blur(10px);
        }
        
        .back-link:hover {
            background: rgba(255,255,255,0.2); transform: translateY(-2px);
        }
        
        .container {
            background: var(--bg-primary); border-radius: 30px; padding: 40px;
            width: 100%; max-width: 900px; text-align: center;
            box-shadow: 20px 20px 60px var(--shadow-light), -20px -20px 60px var(--shadow-dark);
        }
        
        h1 { font-size: 2.5rem; margin-bottom: 20px; color: var(--accent); }
        p { color: var(--text-secondary); margin-bottom: 30px; font-size: 1.1rem; }
        
        .message {
            padding: 30px; background: var(--bg-primary); border-radius: 20px;
            box-shadow: inset 8px 8px 16px var(--shadow-light), inset -8px -8px 16px var(--shadow-dark);
        }
    </style>
</head>
<body>
    <a href="/" class="back-link">← Retour au Hub</a>
    <div class="container">
        <h1>Wikipedia Summarizer Pro</h1>
        <div class="message">
            <p>L'interface complète de Wikisummarizer sera bientôt intégrée ici.</p>
            <p>En attendant, l'API fonctionne parfaitement pour les résumés intelligents.</p>
        </div>
    </div>
</body>
</html>'''
    return html_interface

# Supprimer l'ancienne route wikisummarizer-interface qui posait problème

# Routes API du Wikisummarizer
@app.route('/api/summarize', methods=['POST'])
def api_summarize():
    """Proxy vers l'API du summarizer"""
    if summarizer_app and summarizer:
        return summarizer_app.view_functions['summarize']()
    else:
        return jsonify({'success': False, 'error': 'Wikisummarizer non disponible'}), 500

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Proxy vers les stats du summarizer"""
    if summarizer_app and summarizer:
        return summarizer_app.view_functions['get_stats']()
    else:
        return jsonify({'error': 'Wikisummarizer non disponible'}), 500

# Routes pour servir les fichiers statiques (si besoin)
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Servir les fichiers statiques"""
    return send_from_directory('static', filename)

# Health check
@app.route('/health')
def health_check():
    """Health check pour Render"""
    status = {
        'status': 'OK',
        'service': 'Fusia Hub',
        'wikisummarizer': 'available' if summarizer_app else 'unavailable'
    }
    return jsonify(status), 200

# Route pour Mathia (pour le futur)
@app.route('/mathia')
def mathia():
    """Page Mathia (en développement)"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Mathia - En développement</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            .container { max-width: 600px; margin: 0 auto; }
            h1 { color: #667eea; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔢 Mathia</h1>
            <p>Cette fonctionnalité est en cours de développement.</p>
            <a href="/" style="color: #667eea; text-decoration: none;">← Retour au Hub</a>
        </div>
    </body>
    </html>
    """

if __name__ == '__main__':
    print("🌐 FUSIA HUB - Démarrage")
    print("="*50)
    
    # Configuration pour Render
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    
    print(f"🌐 Port: {port}")
    print(f"🔧 Debug: {debug_mode}")
    print(f"📊 Wikisummarizer: {'✅' if summarizer_app else '❌'}")
    
    print("🚀 DÉMARRAGE...")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )
