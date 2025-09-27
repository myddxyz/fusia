from flask import Flask, request, jsonify, send_from_directory
import os
import json
import re
import time
import hashlib
from mistralai import Mistral
import sympy as sp
from sympy import symbols, expand, factor, solve, diff, integrate, simplify, latex
from werkzeug.utils import secure_filename
import mimetypes

app = Flask(__name__)

class MathiaCore:
    def __init__(self):
        """Initialise Mathia avec les clés API Mistral"""
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        
        self.current_key_index = 0
        
        # Dossier pour la librairie de fichiers
        self.library_path = os.path.join(os.path.dirname(__file__), 'library')
        if not os.path.exists(self.library_path):
            os.makedirs(self.library_path)
        
        # Statistiques d'utilisation
        self.stats = {
            'math_calculations': 0,
            'chat_messages': 0,
            'library_uploads': 0,
            'library_downloads': 0
        }
        
        # Variable symbolique pour les calculs
        self.x = symbols('x')
    
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
                if attempt < len(self.api_keys) - 1:
                    time.sleep(2)
                continue
        
        raise Exception(f"Toutes les clés API ont échoué. Dernière erreur: {str(last_exception)}")
    
    def parse_function(self, func_str):
        """Parse une fonction mathématique depuis une chaîne"""
        try:
            # Nettoyer la chaîne
            func_str = func_str.replace('^', '**').replace(' ', '')
            
            # Remplacer les notations communes
            replacements = {
                'sin': 'sp.sin',
                'cos': 'sp.cos',
                'tan': 'sp.tan',
                'ln': 'sp.log',
                'log': 'sp.log',
                'sqrt': 'sp.sqrt',
                'exp': 'sp.exp'
            }
            
            for old, new in replacements.items():
                func_str = func_str.replace(old, new)
            
            # Parser avec sympy
            expr = sp.sympify(func_str)
            return expr
        except Exception as e:
            raise ValueError(f"Impossible de parser la fonction: {str(e)}")
    
    def quadratic_analysis(self, a, b, c):
        """Analyse complète d'une fonction quadratique ax² + bx + c"""
        try:
            a, b, c = float(a), float(b), float(c)
            
            if a == 0:
                return {'success': False, 'error': 'Ce n\'est pas une fonction quadratique (a = 0)'}
            
            # Expression symbolique
            expr = a * self.x**2 + b * self.x + c
            
            # Forme développée
            expanded_form = f"{a}x² + {b}x + {c}" if b >= 0 else f"{a}x² {b}x + {c}"
            
            # Discriminant
            discriminant = b**2 - 4*a*c
            
            # Sommet
            vertex_x = -b / (2*a)
            vertex_y = a * vertex_x**2 + b * vertex_x + c
            
            # Forme canonique
            canonical_form = f"{a}(x - {vertex_x})² + {vertex_y}"
            
            # Racines
            roots = []
            if discriminant > 0:
                root1 = (-b + discriminant**0.5) / (2*a)
                root2 = (-b - discriminant**0.5) / (2*a)
                roots = [root1, root2]
                factored_form = f"{a}(x - {root1})(x - {root2})"
            elif discriminant == 0:
                root = -b / (2*a)
                roots = [root]
                factored_form = f"{a}(x - {root})²"
            else:
                factored_form = "Pas de factorisation réelle"
            
            # Direction de la parabole
            direction = "vers le haut" if a > 0 else "vers le bas"
            
            # Dérivée
            derivative = diff(expr, self.x)
            
            result = {
                'success': True,
                'expression': str(expr),
                'expanded_form': expanded_form,
                'canonical_form': canonical_form,
                'factored_form': factored_form,
                'discriminant': discriminant,
                'vertex': {'x': vertex_x, 'y': vertex_y},
                'roots': roots,
                'direction': direction,
                'derivative': str(derivative),
                'coefficients': {'a': a, 'b': b, 'c': c}
            }
            
            self.stats['math_calculations'] += 1
            return result
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def general_calculation(self, expression, operation):
        """Effectue des calculs généraux sur des expressions"""
        try:
            expr = self.parse_function(expression)
            
            result_expr = None
            operation_name = ""
            
            if operation == 'simplify':
                result_expr = simplify(expr)
                operation_name = "Simplification"
            elif operation == 'expand':
                result_expr = expand(expr)
                operation_name = "Développement"
            elif operation == 'factor':
                result_expr = factor(expr)
                operation_name = "Factorisation"
            elif operation == 'derivative':
                result_expr = diff(expr, self.x)
                operation_name = "Dérivée"
            elif operation == 'integral':
                result_expr = integrate(expr, self.x)
                operation_name = "Primitive"
            elif operation == 'solve':
                result_expr = solve(expr, self.x)
                operation_name = "Solutions"
            else:
                return {'success': False, 'error': 'Opération non reconnue'}
            
            result = {
                'success': True,
                'original': str(expr),
                'result': str(result_expr),
                'operation': operation_name,
                'latex_original': latex(expr),
                'latex_result': latex(result_expr) if hasattr(result_expr, '__iter__') == False else str(result_expr)
            }
            
            self.stats['math_calculations'] += 1
            return result
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def chat_with_mistral(self, message, conversation_history=None):
        """Chat avec Mistral AI spécialisé en mathématiques"""
        def _chat():
            client = self.get_mistral_client()
            
            # Prompt spécialisé pour les mathématiques
            system_prompt = """Tu es Mathia, un assistant IA spécialisé en mathématiques.
Tu aides les utilisateurs avec :
- Résolution d'équations et systèmes
- Calcul différentiel et intégral
- Algèbre, géométrie, trigonométrie
- Statistiques et probabilités
- Explications détaillées des concepts mathématiques

Réponds toujours de manière claire et pédagogique. Si possible, donne des exemples concrets.
Tu peux utiliser des notations mathématiques standard."""
            
            # Construire l'historique de conversation
            messages = [{"role": "system", "content": system_prompt}]
            
            if conversation_history:
                for msg in conversation_history[-10:]:  # Garder les 10 derniers messages
                    messages.append(msg)
            
            messages.append({"role": "user", "content": message})
            
            try:
                response = client.chat.complete(
                    model="mistral-large-latest",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=800
                )
            except Exception as e:
                if "429" in str(e) or "capacity exceeded" in str(e):
                    print("Rate limit atteint, utilisation du modèle small...")
                    response = client.chat.complete(
                        model="mistral-small-latest",
                        messages=messages,
                        temperature=0.3,
                        max_tokens=800
                    )
                else:
                    raise e
            
            return response.choices[0].message.content.strip()
        
        try:
            response = self.retry_with_different_keys(_chat)
            self.stats['chat_messages'] += 1
            return {'success': True, 'response': response}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def upload_file(self, file, category="general"):
        """Upload un fichier dans la librairie"""
        try:
            if not file or file.filename == '':
                return {'success': False, 'error': 'Aucun fichier sélectionné'}
            
            # Sécuriser le nom de fichier
            filename = secure_filename(file.filename)
            
            # Créer le dossier de catégorie si nécessaire
            category_path = os.path.join(self.library_path, category)
            if not os.path.exists(category_path):
                os.makedirs(category_path)
            
            # Sauvegarder le fichier
            file_path = os.path.join(category_path, filename)
            file.save(file_path)
            
            # Obtenir les métadonnées
            file_info = {
                'filename': filename,
                'category': category,
                'size': os.path.getsize(file_path),
                'upload_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'mime_type': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            }
            
            self.stats['library_uploads'] += 1
            
            return {'success': True, 'file_info': file_info}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def list_library_files(self):
        """Liste tous les fichiers de la librairie"""
        try:
            files_list = []
            
            if not os.path.exists(self.library_path):
                return {'success': True, 'files': []}
            
            for root, dirs, files in os.walk(self.library_path):
                category = os.path.relpath(root, self.library_path)
                if category == '.':
                    category = 'general'
                
                for file in files:
                    file_path = os.path.join(root, file)
                    file_info = {
                        'filename': file,
                        'category': category,
                        'size': os.path.getsize(file_path),
                        'upload_date': time.ctime(os.path.getctime(file_path)),
                        'mime_type': mimetypes.guess_type(file)[0] or 'application/octet-stream'
                    }
                    files_list.append(file_info)
            
            return {'success': True, 'files': files_list}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_file_path(self, filename, category="general"):
        """Obtient le chemin complet d'un fichier"""
        file_path = os.path.join(self.library_path, category, secure_filename(filename))
        if os.path.exists(file_path):
            return file_path
        return None

# Instance globale de Mathia
mathia = MathiaCore()

@app.route('/')
def index():
    """Page d'accueil de Mathia"""
    return '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Assistant Mathématique IA</title>
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
            --success: #48bb78;
            --warning: #ed8936;
            --error: #f56565;
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
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            transition: all 0.3s ease;
        }
        
        [data-theme="dark"] body {
            background: var(--bg-primary);
            color: var(--text-primary);
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
            background: rgba(255, 255, 255, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.4);
            border-radius: 15px; padding: 10px 20px; 
            color: white; text-decoration: none;
            display: flex; align-items: center; gap: 10px; 
            font-weight: 600; font-size: 0.9rem;
            transition: all 0.3s ease;
            backdrop-filter: blur(20px);
        }
        
        [data-theme="dark"] .back-button {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }
        
        .back-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px var(--shadow);
        }
        
        .header-controls {
            display: flex; gap: 15px; align-items: center;
        }
        
        .theme-toggle {
            background: rgba(255, 255, 255, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.4);
            border-radius: 15px; padding: 12px; 
            cursor: pointer; font-size: 1.2rem; 
            transition: all 0.2s ease;
            color: white;
            backdrop-filter: blur(20px);
        }
        
        [data-theme="dark"] .theme-toggle {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }
        
        .theme-toggle:hover { 
            transform: translateY(-2px);
        }
        
        .author-link {
            font-size: 0.85rem; 
            color: rgba(255,255,255,0.9); 
            text-decoration: none;
            font-weight: 500; 
            transition: all 0.2s ease;
        }
        
        [data-theme="dark"] .author-link {
            color: var(--text-secondary);
        }
        
        .author-link:hover { 
            opacity: 1; 
            transform: translateY(-1px); 
        }
        
        .container {
            flex: 1; padding: 100px 30px 30px; max-width: 1400px; margin: 0 auto; width: 100%;
            display: flex; flex-direction: column; gap: 30px;
        }
        
        .title-section {
            text-align: center; margin-bottom: 20px;
        }
        
        .title {
            font-size: 3rem; font-weight: 700; margin-bottom: 10px;
            text-shadow: 0 4px 20px rgba(0,0,0,0.3);
            background: linear-gradient(135deg, #fff, #f0f8ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        [data-theme="dark"] .title {
            color: var(--text-primary);
            text-shadow: none;
            background: none;
            -webkit-text-fill-color: var(--text-primary);
        }
        
        .subtitle { 
            color: rgba(255,255,255,0.9); 
            font-size: 1.2rem; 
            margin-bottom: 15px;
        }
        
        [data-theme="dark"] .subtitle {
            color: var(--text-secondary);
        }
        
        .feature-description {
            color: rgba(255,255,255,0.8);
            font-size: 1rem;
            max-width: 600px;
            margin: 0 auto;
            line-height: 1.6;
        }
        
        [data-theme="dark"] .feature-description {
            color: var(--text-secondary);
        }
        
        .stats {
            display: flex; justify-content: center; gap: 20px; margin-bottom: 30px; flex-wrap: wrap;
        }
        
        .stat-item {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            padding: 15px 25px; border-radius: 20px;
            font-size: 0.9rem; color: rgba(255,255,255,0.95);
            font-weight: 600;
            text-align: center;
            min-width: 120px;
        }
        
        [data-theme="dark"] .stat-item {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-primary);
        }
        
        .nav-tabs {
            display: flex; justify-content: center; gap: 5px; margin-bottom: 30px;
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(20px);
            border-radius: 25px;
            padding: 10px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        [data-theme="dark"] .nav-tabs {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
        }
        
        .nav-tab {
            background: transparent;
            border: none;
            border-radius: 20px;
            padding: 15px 25px;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            color: rgba(255,255,255,0.8);
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        [data-theme="dark"] .nav-tab {
            color: var(--text-secondary);
        }
        
        .nav-tab.active {
            background: rgba(255, 255, 255, 0.3);
            color: white;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        
        [data-theme="dark"] .nav-tab.active {
            background: var(--accent);
            color: white;
        }
        
        .nav-tab:hover:not(.active) {
            background: rgba(255, 255, 255, 0.2);
            color: rgba(255,255,255,0.95);
        }
        
        [data-theme="dark"] .nav-tab:hover:not(.active) {
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }
        
        .content-section {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 25px;
            padding: 40px;
            min-height: 500px;
        }
        
        [data-theme="dark"] .content-section {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .label {
            display: block;
            color: white;
            font-weight: 600;
            margin-bottom: 12px;
            font-size: 1rem;
        }
        
        [data-theme="dark"] .label {
            color: var(--text-primary);
        }
        
        .input, .textarea, .select {
            width: 100%;
            padding: 18px 24px;
            background: rgba(255, 255, 255, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.4);
            border-radius: 20px;
            font-size: 1rem;
            color: white;
            outline: none;
            transition: all 0.3s ease;
            backdrop-filter: blur(20px);
        }
        
        [data-theme="dark"] .input,
        [data-theme="dark"] .textarea,
        [data-theme="dark"] .select {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            color: var(--text-primary);
        }
        
        .input:focus, .textarea:focus, .select:focus {
            background: rgba(255, 255, 255, 0.4);
            border-color: rgba(255, 255, 255, 0.6);
            box-shadow: 0 0 0 3px rgba(255,255,255,0.2);
        }
        
        [data-theme="dark"] .input:focus,
        [data-theme="dark"] .textarea:focus,
        [data-theme="dark"] .select:focus {
            background: var(--bg-secondary);
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
        }
        
        .input::placeholder, .textarea::placeholder {
            color: rgba(255,255,255,0.8);
        }
        
        [data-theme="dark"] .input::placeholder,
        [data-theme="dark"] .textarea::placeholder {
            color: var(--text-secondary);
        }
        
        .textarea {
            height: 120px;
            resize: vertical;
        }
        
        .btn {
            background: rgba(255, 255, 255, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.5);
            border-radius: 20px;
            padding: 15px 30px;
            font-size: 1rem;
            font-weight: 600;
            color: white;
            cursor: pointer;
            transition: all 0.2s ease;
            backdrop-filter: blur(20px);
            display: inline-flex;
            align-items: center;
            gap: 10px;
        }
        
        [data-theme="dark"] .btn {
            background: var(--accent);
            border: 1px solid var(--accent);
            color: white;
        }
        
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            background: rgba(255, 255, 255, 0.5);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
        }
        
        [data-theme="dark"] .btn:hover:not(:disabled) {
            background: #5a6fd8;
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .btn-secondary {
            background: rgba(255, 255, 255, 0.25);
            color: rgba(255,255,255,0.9);
        }
        
        [data-theme="dark"] .btn-secondary {
            background: var(--bg-primary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }
        
        .result-container {
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 20px;
            padding: 25px;
            margin-top: 25px;
            backdrop-filter: blur(15px);
        }
        
        [data-theme="dark"] .result-container {
            background: var(--bg-primary);
            border: 1px solid var(--border);
        }
        
        .result-title {
            color: white;
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        [data-theme="dark"] .result-title {
            color: var(--text-primary);
        }
        
        .result-content {
            color: rgba(255,255,255,0.95);
            line-height: 1.6;
        }
        
        [data-theme="dark"] .result-content {
            color: var(--text-primary);
        }
        
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 600px;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: rgba(255, 255, 255, 0.15);
            border-radius: 15px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
        }
        
        [data-theme="dark"] .chat-messages {
            background: var(--bg-primary);
        }
        
        .message {
            margin-bottom: 15px;
            padding: 15px 20px;
            border-radius: 15px;
            max-width: 80%;
        }
        
        .message.user {
            background: rgba(255, 255, 255, 0.3);
            margin-left: auto;
            text-align: right;
        }
        
        [data-theme="dark"] .message.user {
            background: var(--accent);
            color: white;
        }
        
        .message.assistant {
            background: rgba(255, 255, 255, 0.4);
        }
        
        [data-theme="dark"] .message.assistant {
            background: var(--bg-secondary);
        }
        
        .chat-input-container {
            display: flex;
            gap: 15px;
            align-items: flex-end;
        }
        
        .chat-input {
            flex: 1;
            min-height: 50px;
            max-height: 150px;
        }
        
        .file-upload-area {
            border: 2px dashed rgba(255, 255, 255, 0.4);
            border-radius: 15px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        [data-theme="dark"] .file-upload-area {
            border-color: var(--border);
        }
        
        .file-upload-area:hover {
            border-color: rgba(255, 255, 255, 0.6);
            background: rgba(255, 255, 255, 0.1);
        }
        
        [data-theme="dark"] .file-upload-area:hover {
            border-color: var(--accent);
            background: var(--bg-secondary);
        }
        
        .file-upload-area.dragover {
            border-color: var(--accent);
            background: rgba(102, 126, 234, 0.1);
        }
        
        .library-files {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 25px;
        }
        
        .file-item {
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 15px;
            padding: 20px;
            transition: all 0.3s ease;
        }
        
        [data-theme="dark"] .file-item {
            background: var(--bg-primary);
            border: 1px solid var(--border);
        }
        
        .file-item:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
        }
        
        .file-name {
            font-weight: 600;
            color: white;
            margin-bottom: 10px;
            word-break: break-word;
        }
        
        [data-theme="dark"] .file-name {
            color: var(--text-primary);
        }
        
        .file-meta {
            color: rgba(255,255,255,0.8);
            font-size: 0.9rem;
            margin-bottom: 15px;
        }
        
        [data-theme="dark"] .file-meta {
            color: var(--text-secondary);
        }
        
        .file-actions {
            display: flex;
            gap: 10px;
        }
        
        .btn-small {
            padding: 8px 15px;
            font-size: 0.85rem;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            margin-right: 10px;
            border: 3px solid rgba(255,255,255,0.4);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        
        [data-theme="dark"] .loading {
            border: 3px solid var(--text-secondary);
            border-top-color: var(--accent);
        }
        
        @keyframes spin { 
            to { transform: rotate(360deg); } 
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
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        
        .notification.show { transform: translateX(0); }
        .notification.error { background: rgba(239, 68, 68, 0.9); }
        .notification.success { background: rgba(34, 197, 94, 0.9); }
        .notification.info { background: rgba(59, 130, 246, 0.9); }
        
        .math-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        
        @media (max-width: 768px) {
            .top-header { padding: 15px 20px; flex-direction: column; gap: 15px; }
            .header-controls { width: 100%; justify-content: space-between; }
            .container { padding: 140px 20px 20px; }
            .title { font-size: 2.5rem; }
            .nav-tabs { flex-direction: column; }
            .math-grid { grid-template-columns: 1fr; gap: 20px; }
            .library-files { grid-template-columns: 1fr; }
            .chat-container { height: 400px; }
        }
    </style>
</head>
<body>
    <div class="top-header">
        <a href="/" class="back-button">
            <span>←</span>
            <span>Retour au Hub</span>
        </a>
        
        <div class="header-controls">
            <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()">🌙</button>
            <a href="#" class="author-link" onclick="showAuthorModal()">by Mydd</a>
        </div>
    </div>

    <div class="container">
        <div class="title-section">
            <h1 class="title">🔢 Mathia</h1>
            <p class="subtitle">Assistant Mathématique Intelligent</p>
            <p class="feature-description">
                Transformations automatiques, librairie de documents et chat IA spécialisé en mathématiques
            </p>
        </div>

        <div class="stats" id="stats">
            <div class="stat-item">
                <div>🧮 <span id="mathCalcs">0</span></div>
                <div style="font-size: 0.8rem; opacity: 0.8;">Calculs</div>
            </div>
            <div class="stat-item">
                <div>💬 <span id="chatMsgs">0</span></div>
                <div style="font-size: 0.8rem; opacity: 0.8;">Messages</div>
            </div>
            <div class="stat-item">
                <div>📚 <span id="libraryUploads">0</span></div>
                <div style="font-size: 0.8rem; opacity: 0.8;">Uploads</div>
            </div>
            <div class="stat-item">
                <div>📥 <span id="libraryDownloads">0</span></div>
                <div style="font-size: 0.8rem; opacity: 0.8;">Téléchargements</div>
            </div>
        </div>

        <div class="nav-tabs">
            <button class="nav-tab active" onclick="switchTab('calculator')">
                🧮 Calculatrice
            </button>
            <button class="nav-tab" onclick="switchTab('library')">
                📚 Librairie
            </button>
            <button class="nav-tab" onclick="switchTab('chat')">
                🤖 Chat IA
            </button>
        </div>

        <div class="content-section">
            <!-- Onglet Calculatrice -->
            <div id="calculator" class="tab-content active">
                <div class="math-grid">
                    <!-- Analyse de fonction quadratique -->
                    <div>
                        <h3 class="label">📊 Analyse de Fonction Quadratique</h3>
                        <form id="quadraticForm" onsubmit="analyzeQuadratic(event)">
                            <div class="form-group">
                                <label class="label">Coefficients (ax² + bx + c)</label>
                                <div style="display: flex; gap: 10px;">
                                    <input type="number" step="any" id="coeff_a" class="input" placeholder="a" required>
                                    <input type="number" step="any" id="coeff_b" class="input" placeholder="b" required>
                                    <input type="number" step="any" id="coeff_c" class="input" placeholder="c" required>
                                </div>
                            </div>
                            <button type="submit" class="btn">
                                <span class="loading" id="quadraticLoading" style="display: none;"></span>
                                🔍 Analyser
                            </button>
                        </form>
                        
                        <div id="quadraticResult" class="result-container" style="display: none;">
                            <div class="result-title">📈 Résultats de l'analyse</div>
                            <div id="quadraticContent" class="result-content"></div>
                        </div>
                    </div>
                    
                    <!-- Calculs généraux -->
                    <div>
                        <h3 class="label">⚡ Calculs Généraux</h3>
                        <form id="generalForm" onsubmit="performGeneralCalculation(event)">
                            <div class="form-group">
                                <label class="label">Expression mathématique</label>
                                <input type="text" id="expression" class="input" 
                                       placeholder="x^2 + 3*x + 2" required>
                                <small style="color: rgba(255,255,255,0.8); margin-top: 5px; display: block;">
                                    Utilisez x comme variable. Exemples: x^2, sin(x), ln(x)
                                </small>
                            </div>
                            
                            <div class="form-group">
                                <label class="label">Opération</label>
                                <select id="operation" class="select">
                                    <option value="simplify">Simplifier</option>
                                    <option value="expand">Développer</option>
                                    <option value="factor">Factoriser</option>
                                    <option value="derivative">Dérivée</option>
                                    <option value="integral">Primitive</option>
                                    <option value="solve">Résoudre = 0</option>
                                </select>
                            </div>
                            
                            <button type="submit" class="btn">
                                <span class="loading" id="generalLoading" style="display: none;"></span>
                                ⚡ Calculer
                            </button>
                        </form>
                        
                        <div id="generalResult" class="result-container" style="display: none;">
                            <div class="result-title">✨ Résultat</div>
                            <div id="generalContent" class="result-content"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Onglet Librairie -->
            <div id="library" class="tab-content">
                <h3 class="label">📚 Gestion de la Librairie</h3>
                
                <!-- Zone d'upload -->
                <div class="file-upload-area" id="uploadArea" onclick="document.getElementById('fileInput').click()">
                    <div style="font-size: 2rem; margin-bottom: 15px;">📁</div>
                    <div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 10px;">
                        Cliquez ou glissez vos fichiers ici
                    </div>
                    <div style="color: rgba(255,255,255,0.8);">
                        PDF, images, documents mathématiques...
                    </div>
                </div>
                
                <input type="file" id="fileInput" multiple style="display: none;" onchange="uploadFiles()">
                
                <div class="form-group" style="margin-top: 20px;">
                    <label class="label">Catégorie</label>
                    <select id="fileCategory" class="select">
                        <option value="general">Général</option>
                        <option value="cours">Cours</option>
                        <option value="exercices">Exercices</option>
                        <option value="formules">Formules</option>
                        <option value="examens">Examens</option>
                    </select>
                </div>
                
                <button class="btn btn-secondary" onclick="loadLibraryFiles()">
                    🔄 Actualiser la librairie
                </button>
                
                <!-- Liste des fichiers -->
                <div id="libraryFiles" class="library-files">
                    <!-- Les fichiers seront chargés ici -->
                </div>
            </div>

            <!-- Onglet Chat IA -->
            <div id="chat" class="tab-content">
                <h3 class="label">🤖 Chat avec Mathia</h3>
                
                <div class="chat-container">
                    <div class="chat-messages" id="chatMessages">
                        <div class="message assistant">
                            <strong>Mathia:</strong> Bonjour! Je suis Mathia, votre assistant mathématique IA. 
                            Posez-moi vos questions sur les mathématiques, les équations, la géométrie, 
                            les statistiques ou tout autre sujet mathématique!
                        </div>
                    </div>
                    
                    <div class="chat-input-container">
                        <textarea id="chatInput" class="input chat-input" 
                                placeholder="Posez votre question mathématique..." 
                                onkeydown="handleChatKeydown(event)"></textarea>
                        <button class="btn" onclick="sendChatMessage()" id="chatSendBtn">
                            <span class="loading" id="chatLoading" style="display: none;"></span>
                            📤 Envoyer
                        </button>
                    </div>
                </div>
                
                <div style="margin-top: 20px; text-align: center;">
                    <button class="btn btn-secondary" onclick="clearChatHistory()">
                        🗑️ Effacer l'historique
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentTheme = 'light';
        let conversationHistory = [];
        
        document.addEventListener('DOMContentLoaded', function() {
            initializeApp();
        });
        
        function initializeApp() {
            loadTheme();
            loadStats();
            setupFileUpload();
            loadLibraryFiles();
        }
        
        function loadTheme() {
            const savedTheme = localStorage.getItem('mathia-theme') || 'light';
            currentTheme = savedTheme;
            document.documentElement.setAttribute('data-theme', savedTheme);
            updateThemeToggle();
        }
        
        function toggleTheme() {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', currentTheme);
            localStorage.setItem('mathia-theme', currentTheme);
            updateThemeToggle();
        }
        
        function updateThemeToggle() {
            const toggle = document.getElementById('themeToggle');
            if (toggle) {
                toggle.textContent = currentTheme === 'light' ? '🌙' : '☀️';
            }
        }
        
        function switchTab(tabName) {
            // Cacher tous les onglets
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Désactiver tous les boutons
            document.querySelectorAll('.nav-tab').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Activer l'onglet sélectionné
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
        }
        
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                if (response.ok) {
                    const stats = await response.json();
                    updateStatsDisplay(stats);
                }
            } catch (error) {
                console.log('Erreur stats:', error);
            }
        }
        
        function updateStatsDisplay(stats) {
            document.getElementById('mathCalcs').textContent = stats.math_calculations || 0;
            document.getElementById('chatMsgs').textContent = stats.chat_messages || 0;
            document.getElementById('libraryUploads').textContent = stats.library_uploads || 0;
            document.getElementById('libraryDownloads').textContent = stats.library_downloads || 0;
        }
        
        // Fonctions pour les calculs mathématiques
        async function analyzeQuadratic(event) {
            event.preventDefault();
            
            const loading = document.getElementById('quadraticLoading');
            const resultDiv = document.getElementById('quadraticResult');
            const contentDiv = document.getElementById('quadraticContent');
            
            const a = document.getElementById('coeff_a').value;
            const b = document.getElementById('coeff_b').value;
            const c = document.getElementById('coeff_c').value;
            
            loading.style.display = 'inline-block';
            
            try {
                const response = await fetch('/api/calculate/quadratic', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ a: a, b: b, c: c })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    displayQuadraticResult(data, contentDiv);
                    resultDiv.style.display = 'block';
                    showNotification('Analyse terminée!', 'success');
                } else {
                    showNotification(data.error, 'error');
                }
            } catch (error) {
                showNotification('Erreur de calcul', 'error');
            } finally {
                loading.style.display = 'none';
                setTimeout(loadStats, 500);
            }
        }
        
        function displayQuadraticResult(data, container) {
            container.innerHTML = `
                <div style="margin-bottom: 20px;">
                    <strong>📐 Fonction:</strong> ${data.expanded_form}
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                    <div>
                        <strong>📊 Formes:</strong><br>
                        • Développée: ${data.expanded_form}<br>
                        • Canonique: ${data.canonical_form}<br>
                        • Factorisée: ${data.factored_form}
                    </div>
                    <div>
                        <strong>🎯 Propriétés:</strong><br>
                        • Discriminant: ${data.discriminant}<br>
                        • Sommet: (${data.vertex.x}, ${data.vertex.y})<br>
                        • Direction: ${data.direction}
                    </div>
                </div>
                
                <div>
                    <strong>🔍 Racines:</strong> ${data.roots.length > 0 ? data.roots.join(', ') : 'Aucune racine réelle'}<br>
                    <strong>📈 Dérivée:</strong> ${data.derivative}
                </div>
            `;
        }
        
        async function performGeneralCalculation(event) {
            event.preventDefault();
            
            const loading = document.getElementById('generalLoading');
            const resultDiv = document.getElementById('generalResult');
            const contentDiv = document.getElementById('generalContent');
            
            const expression = document.getElementById('expression').value;
            const operation = document.getElementById('operation').value;
            
            loading.style.display = 'inline-block';
            
            try {
                const response = await fetch('/api/calculate/general', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ expression: expression, operation: operation })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    displayGeneralResult(data, contentDiv);
                    resultDiv.style.display = 'block';
                    showNotification('Calcul terminé!', 'success');
                } else {
                    showNotification(data.error, 'error');
                }
            } catch (error) {
                showNotification('Erreur de calcul', 'error');
            } finally {
                loading.style.display = 'none';
                setTimeout(loadStats, 500);
            }
        }
        
        function displayGeneralResult(data, container) {
            container.innerHTML = `
                <div style="margin-bottom: 15px;">
                    <strong>🔢 Expression originale:</strong><br>
                    ${data.original}
                </div>
                
                <div style="margin-bottom: 15px;">
                    <strong>✨ ${data.operation}:</strong><br>
                    <span style="font-size: 1.1rem; color: var(--accent);">${data.result}</span>
                </div>
            `;
        }
        
        // Fonctions pour la librairie
        function setupFileUpload() {
            const uploadArea = document.getElementById('uploadArea');
            
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                uploadArea.addEventListener(eventName, preventDefaults, false);
            });
            
            ['dragenter', 'dragover'].forEach(eventName => {
                uploadArea.addEventListener(eventName, highlight, false);
            });
            
            ['dragleave', 'drop'].forEach(eventName => {
                uploadArea.addEventListener(eventName, unhighlight, false);
            });
            
            uploadArea.addEventListener('drop', handleDrop, false);
        }
        
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        function highlight() {
            document.getElementById('uploadArea').classList.add('dragover');
        }
        
        function unhighlight() {
            document.getElementById('uploadArea').classList.remove('dragover');
        }
        
        function handleDrop(e) {
            const files = e.dataTransfer.files;
            processFiles(files);
        }
        
        function uploadFiles() {
            const files = document.getElementById('fileInput').files;
            processFiles(files);
        }
        
        async function processFiles(files) {
            const category = document.getElementById('fileCategory').value;
            
            for (let file of files) {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('category', category);
                
                try {
                    const response = await fetch('/api/library/upload', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        showNotification(`Fichier ${file.name} uploadé!`, 'success');
                    } else {
                        showNotification(`Erreur: ${data.error}`, 'error');
                    }
                } catch (error) {
                    showNotification('Erreur d\'upload', 'error');
                }
            }
            
            setTimeout(() => {
                loadLibraryFiles();
                loadStats();
            }, 1000);
        }
        
        async function loadLibraryFiles() {
            try {
                const response = await fetch('/api/library/list');
                const data = await response.json();
                
                if (data.success) {
                    displayLibraryFiles(data.files);
                }
            } catch (error) {
                console.error('Erreur chargement librairie:', error);
            }
        }
        
        function displayLibraryFiles(files) {
            const container = document.getElementById('libraryFiles');
            
            if (files.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; color: rgba(255,255,255,0.7); grid-column: 1/-1;">
                        <div style="font-size: 2rem; margin-bottom: 15px;">📂</div>
                        <div>Aucun fichier dans la librairie</div>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = files.map(file => `
                <div class="file-item">
                    <div class="file-name">${getFileIcon(file.mime_type)} ${file.filename}</div>
                    <div class="file-meta">
                        📁 ${file.category} • 📏 ${formatFileSize(file.size)} • 📅 ${file.upload_date}
                    </div>
                    <div class="file-actions">
                        <button class="btn btn-small" onclick="downloadFile('${file.filename}', '${file.category}')">
                            📥 Télécharger
                        </button>
                    </div>
                </div>
            `).join('');
        }
        
        function getFileIcon(mimeType) {
            if (mimeType.includes('pdf')) return '📄';
            if (mimeType.includes('image')) return '🖼️';
            if (mimeType.includes('text')) return '📝';
            if (mimeType.includes('word')) return '📝';
            return '📄';
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function downloadFile(filename, category) {
            window.open(`/api/library/download/${category}/${filename}`, '_blank');
            setTimeout(() => {
                loadStats();
            }, 500);
        }
        
        // Fonctions pour le chat
        async function sendChatMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            const loading = document.getElementById('chatLoading');
            const sendBtn = document.getElementById('chatSendBtn');
            
            // Ajouter le message utilisateur
            addMessageToChat('user', message);
            input.value = '';
            
            // Désactiver l'interface
            loading.style.display = 'inline-block';
            sendBtn.disabled = true;
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        message: message,
                        history: conversationHistory 
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    addMessageToChat('assistant', data.response);
                    
                    // Ajouter à l'historique
                    conversationHistory.push({ role: 'user', content: message });
                    conversationHistory.push({ role: 'assistant', content: data.response });
                } else {
                    addMessageToChat('assistant', 'Désolé, une erreur est survenue: ' + data.error);
                }
            } catch (error) {
                addMessageToChat('assistant', 'Erreur de connexion. Veuillez réessayer.');
            } finally {
                loading.style.display = 'none';
                sendBtn.disabled = false;
                setTimeout(loadStats, 500);
            }
        }
        
        function addMessageToChat(sender, message) {
            const chatMessages = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}`;
            
            const senderName = sender === 'user' ? 'Vous' : 'Mathia';
            messageDiv.innerHTML = `<strong>${senderName}:</strong> ${message}`;
            
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        function handleChatKeydown(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendChatMessage();
            }
        }
        
        function clearChatHistory() {
            const chatMessages = document.getElementById('chatMessages');
            chatMessages.innerHTML = `
                <div class="message assistant">
                    <strong>Mathia:</strong> Bonjour! Je suis Mathia, votre assistant mathématique IA. 
                    Posez-moi vos questions sur les mathématiques, les équations, la géométrie, 
                    les statistiques ou tout autre sujet mathématique!
                </div>
            `;
            conversationHistory = [];
        }
        
        function showNotification(message, type = 'info') {
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
        
        function showAuthorModal() {
            alert('Mathia - Créé par Mydd, 16 ans. Assistant mathématique intelligent combinant calculs automatisés, gestion de documents et IA conversationnelle.');
        }
    </script>
</body>
</html>'''

# Routes API
@app.route('/api/calculate/quadratic', methods=['POST'])
def calculate_quadratic():
    """API pour l'analyse de fonctions quadratiques"""
    try:
        data = request.get_json()
        a = data.get('a')
        b = data.get('b') 
        c = data.get('c')
        
        if not all(x is not None for x in [a, b, c]):
            return jsonify({'success': False, 'error': 'Tous les coefficients sont requis'}), 400
        
        result = mathia.quadratic_analysis(a, b, c)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/calculate/general', methods=['POST'])
def calculate_general():
    """API pour les calculs généraux"""
    try:
        data = request.get_json()
        expression = data.get('expression')
        operation = data.get('operation')
        
        if not expression or not operation:
            return jsonify({'success': False, 'error': 'Expression et opération requises'}), 400
        
        result = mathia.general_calculation(expression, operation)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    """API pour le chat avec Mistral"""
    try:
        data = request.get_json()
        message = data.get('message')
        history = data.get('history', [])
        
        if not message:
            return jsonify({'success': False, 'error': 'Message requis'}), 400
        
        result = mathia.chat_with_mistral(message, history)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/library/upload', methods=['POST'])
def upload_file():
    """API pour uploader des fichiers"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Aucun fichier fourni'}), 400
        
        file = request.files['file']
        category = request.form.get('category', 'general')
        
        result = mathia.upload_file(file, category)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/library/list', methods=['GET'])
def list_files():
    """API pour lister les fichiers de la librairie"""
    try:
        result = mathia.list_library_files()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/library/download/<category>/<filename>')
def download_file(category, filename):
    """API pour télécharger des fichiers"""
    try:
        file_path = mathia.get_file_path(filename, category)
        
        if not file_path:
            return jsonify({'error': 'Fichier introuvable'}), 404
        
        # Incrémenter les stats
        mathia.stats['library_downloads'] += 1
        
        return send_from_directory(
            os.path.dirname(file_path), 
            os.path.basename(file_path), 
            as_attachment=True
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API pour les statistiques"""
    try:
        return jsonify(mathia.stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check pour Render"""
    return jsonify({'status': 'OK', 'service': 'Mathia'}), 200

if __name__ == '__main__':
    print("🔢 MATHIA - Assistant Mathématique IA")
    print("="*50)
    
    try:
        from mistralai import Mistral
        import sympy
        print("✅ Dépendances OK")
        
        # Configuration pour Render
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port: {port}")
        print(f"🔧 Debug: {debug_mode}")
        print(f"🔑 Clés API configurées: {len(mathia.api_keys)}")
        print(f"📚 Dossier librairie: {mathia.library_path}")
        
    except ImportError as e:
        print(f"❌ ERREUR: {e}")
        exit(1)
    except Exception as e:
        print(f"⚠️ Avertissement: {e}")
    
    print("🚀 DÉMARRAGE...")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )
