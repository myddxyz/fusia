from flask import Flask, request, jsonify, render_template_string
import os
import json
import base64
import io
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Backend sans interface graphique
import matplotlib.pyplot as plt
from matplotlib import cm
import sympy as sp
from sympy import *
from sympy.plotting import plot, plot3d
from mistralai import Mistral
import time

app = Flask(__name__)

class MathiaCore:
    """Cœur de l'application Mathia - Assistant Mathématique IA"""
    
    def __init__(self):
        # Configuration des clés API Mistral
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        self.current_key_index = 0
        
        # Variables symboliques
        self.x, self.y, self.z, self.t = symbols('x y z t')
        self.n, self.k = symbols('n k', integer=True)
        
        # Statistiques
        self.stats = {
            'calculations': 0,
            'graphs_generated': 0,
            'chat_messages': 0
        }
        
        # Configuration matplotlib
        plt.style.use('dark_background')
        
    def get_mistral_client(self):
        """Obtient un client Mistral avec rotation des clés"""
        key = self.api_keys[self.current_key_index % len(self.api_keys)]
        self.current_key_index += 1
        return Mistral(api_key=key)
    
    def parse_expression(self, expr_str):
        """Parse une expression mathématique avec gestion d'erreurs robuste"""
        try:
            # Nettoyage de base
            expr_str = expr_str.strip()
            
            # Remplacements courants pour rendre l'expression compatible avec sympy
            replacements = [
                ('^', '**'),           # Puissances
                ('ln', 'log'),         # Logarithme naturel
                ('lg', 'log'),         # Logarithme
                ('arcsin', 'asin'),    # Arc sinus
                ('arccos', 'acos'),    # Arc cosinus
                ('arctan', 'atan'),    # Arc tangente
                ('tg', 'tan'),         # Tangente
                ('ctg', 'cot'),        # Cotangente
                ('sh', 'sinh'),        # Sinus hyperbolique
                ('ch', 'cosh'),        # Cosinus hyperbolique
                ('th', 'tanh'),        # Tangente hyperbolique
            ]
            
            for old, new in replacements:
                expr_str = expr_str.replace(old, new)
            
            # Parser avec sympy
            expr = sympify(expr_str)
            return expr, None
            
        except Exception as e:
            return None, str(e)
    
    def solve_expression(self, expr_str, operation='solve'):
        """Résout une expression mathématique selon l'opération demandée"""
        try:
            expr, error = self.parse_expression(expr_str)
            if error:
                return {'success': False, 'error': f'Erreur de parsing: {error}'}
            
            result_data = {
                'success': True,
                'original': expr_str,
                'parsed': str(expr),
                'latex': latex(expr),
                'results': {}
            }
            
            # Différents types d'opérations
            if operation == 'solve' or '=' in expr_str:
                # Résoudre une équation
                if '=' in expr_str:
                    left, right = expr_str.split('=', 1)
                    equation = Eq(sympify(left.strip()), sympify(right.strip()))
                    solutions = solve(equation, self.x)
                else:
                    solutions = solve(expr, self.x)
                result_data['results']['solutions'] = [str(sol) for sol in solutions]
                
            elif operation == 'expand':
                expanded = expand(expr)
                result_data['results']['expanded'] = str(expanded)
                result_data['results']['latex_expanded'] = latex(expanded)
                
            elif operation == 'factor':
                factored = factor(expr)
                result_data['results']['factored'] = str(factored)
                result_data['results']['latex_factored'] = latex(factored)
                
            elif operation == 'simplify':
                simplified = simplify(expr)
                result_data['results']['simplified'] = str(simplified)
                result_data['results']['latex_simplified'] = latex(simplified)
                
            elif operation == 'derivative':
                derivative = diff(expr, self.x)
                result_data['results']['derivative'] = str(derivative)
                result_data['results']['latex_derivative'] = latex(derivative)
                
            elif operation == 'integral':
                integral = integrate(expr, self.x)
                result_data['results']['integral'] = str(integral)
                result_data['results']['latex_integral'] = latex(integral)
                
            elif operation == 'limit':
                # Limite quand x tend vers 0 par défaut
                limit_val = limit(expr, self.x, 0)
                result_data['results']['limit'] = str(limit_val)
                
            elif operation == 'series':
                # Développement en série de Taylor
                series_expansion = series(expr, self.x, 0, n=6)
                result_data['results']['series'] = str(series_expansion)
                
            # Toujours essayer de générer un graphique si possible
            graph_data = self.generate_graph(expr)
            if graph_data:
                result_data['graph'] = graph_data
                self.stats['graphs_generated'] += 1
            
            self.stats['calculations'] += 1
            return result_data
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def generate_graph(self, expr):
        """Génère un graphique pour une expression donnée"""
        try:
            # Vérifier si l'expression contient uniquement x
            variables = expr.free_symbols
            if not variables or (len(variables) == 1 and self.x in variables):
                return self._plot_2d(expr)
            elif len(variables) == 2 and {self.x, self.y}.issubset(variables):
                return self._plot_3d(expr)
            else:
                return None
                
        except Exception as e:
            print(f"Erreur génération graphique: {e}")
            return None
    
    def _plot_2d(self, expr):
        """Génère un graphique 2D"""
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Déterminer la plage de x appropriée
            x_vals = np.linspace(-10, 10, 1000)
            
            # Convertir l'expression sympy en fonction numpy
            f = lambdify(self.x, expr, 'numpy')
            
            # Calculer y en gérant les erreurs potentielles
            try:
                y_vals = f(x_vals)
                # Filtrer les valeurs infinies ou NaN
                mask = np.isfinite(y_vals)
                x_filtered = x_vals[mask]
                y_filtered = y_vals[mask]
                
                if len(x_filtered) > 0:
                    ax.plot(x_filtered, y_filtered, 'cyan', linewidth=2, label=f'f(x) = {expr}')
                    
            except Exception:
                # Si le calcul direct échoue, essayer point par point
                y_vals = []
                x_vals_clean = []
                for x_val in x_vals:
                    try:
                        y_val = float(expr.subs(self.x, x_val))
                        if np.isfinite(y_val):
                            y_vals.append(y_val)
                            x_vals_clean.append(x_val)
                    except:
                        continue
                
                if len(y_vals) > 0:
                    ax.plot(x_vals_clean, y_vals, 'cyan', linewidth=2, label=f'f(x) = {expr}')
            
            # Stylisation
            ax.grid(True, alpha=0.3)
            ax.axhline(y=0, color='white', linewidth=0.5)
            ax.axvline(x=0, color='white', linewidth=0.5)
            ax.set_xlabel('x', fontsize=12)
            ax.set_ylabel('f(x)', fontsize=12)
            ax.set_title(f'Graphique de f(x) = {expr}', fontsize=14, color='white')
            ax.legend()
            
            # Convertir en base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', 
                       facecolor='#1a1a1a', edgecolor='none', dpi=100)
            buffer.seek(0)
            graph_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return {
                'type': '2D',
                'image': graph_base64,
                'expression': str(expr)
            }
            
        except Exception as e:
            print(f"Erreur plot 2D: {e}")
            return None
    
    def _plot_3d(self, expr):
        """Génère un graphique 3D (surface)"""
        try:
            fig = plt.figure(figsize=(12, 8))
            ax = fig.add_subplot(111, projection='3d')
            
            # Créer une grille
            x_vals = np.linspace(-5, 5, 50)
            y_vals = np.linspace(-5, 5, 50)
            X, Y = np.meshgrid(x_vals, y_vals)
            
            # Convertir l'expression en fonction numpy
            f = lambdify((self.x, self.y), expr, 'numpy')
            
            try:
                Z = f(X, Y)
                # Filtrer les valeurs infinies
                Z = np.where(np.isfinite(Z), Z, np.nan)
                
                surface = ax.plot_surface(X, Y, Z, cmap=cm.plasma, alpha=0.8, 
                                        linewidth=0, antialiased=True)
                
                ax.set_xlabel('x')
                ax.set_ylabel('y')
                ax.set_zlabel('f(x,y)')
                ax.set_title(f'Surface: f(x,y) = {expr}', color='white')
                
                fig.colorbar(surface, ax=ax, shrink=0.5)
                
            except Exception as e:
                print(f"Erreur calcul surface 3D: {e}")
                return None
            
            # Convertir en base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', 
                       facecolor='#1a1a1a', edgecolor='none', dpi=100)
            buffer.seek(0)
            graph_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return {
                'type': '3D',
                'image': graph_base64,
                'expression': str(expr)
            }
            
        except Exception as e:
            print(f"Erreur plot 3D: {e}")
            return None
    
    def chat_with_mistral(self, message, context=None):
        """Chat avec Mistral AI spécialisé en mathématiques"""
        try:
            client = self.get_mistral_client()
            
            system_prompt = """Tu es Mathia, un assistant IA expert en mathématiques. 
            Tu aides les utilisateurs à comprendre les concepts mathématiques, résoudre des problèmes,
            et expliquer les résultats de manière claire et pédagogique.
            
            Tes spécialités incluent :
            - Algèbre et analyse
            - Géométrie et trigonométrie  
            - Calcul différentiel et intégral
            - Statistiques et probabilités
            - Mathématiques discrètes
            - Théorie des nombres
            
            Réponds toujours de façon précise, avec des explications étape par étape quand nécessaire.
            Tu peux utiliser des notations mathématiques standard."""
            
            messages = [{"role": "system", "content": system_prompt}]
            
            # Ajouter le contexte si fourni (résultats de calculs)
            if context:
                context_msg = f"Contexte du calcul précédent: {context}"
                messages.append({"role": "assistant", "content": context_msg})
            
            messages.append({"role": "user", "content": message})
            
            response = client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.3,
                max_tokens=1000
            )
            
            self.stats['chat_messages'] += 1
            return {
                'success': True, 
                'response': response.choices[0].message.content.strip()
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Instance globale
mathia = MathiaCore()

@app.route('/')
def index():
    """Interface principale de Mathia"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/calculate', methods=['POST'])
def calculate():
    """API principale pour les calculs mathématiques"""
    try:
        data = request.get_json()
        expression = data.get('expression', '').strip()
        operation = data.get('operation', 'solve')
        
        if not expression:
            return jsonify({'success': False, 'error': 'Expression requise'})
        
        result = mathia.solve_expression(expression, operation)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/chat', methods=['POST'])
def chat():
    """API pour le chat avec Mistral"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        context = data.get('context')
        
        if not message:
            return jsonify({'success': False, 'error': 'Message requis'})
        
        result = mathia.chat_with_mistral(message, context)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def get_stats():
    """API pour les statistiques"""
    return jsonify(mathia.stats)

@app.route('/health')
def health_check():
    """Health check pour le déploiement"""
    return jsonify({'status': 'OK', 'service': 'Mathia'})

# Template HTML intégré
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Assistant Mathématique IA</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/mathjs/11.11.0/math.min.js"></script>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script>
        window.MathJax = {
            tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']] },
            svg: { fontCache: 'global' }
        };
    </script>
    <style>
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #1a1a1a;
            --bg-tertiary: #2a2a2a;
            --text-primary: #ffffff;
            --text-secondary: #cccccc;
            --accent: #00d4ff;
            --accent-secondary: #0099cc;
            --success: #00ff88;
            --error: #ff4444;
            --border: #333;
            --shadow: rgba(0, 212, 255, 0.2);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.6;
        }
        
        .header {
            background: rgba(26, 26, 26, 0.95);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            position: sticky;
            top: 0;
            z-index: 100;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 1.8rem;
            font-weight: bold;
            color: var(--accent);
            text-decoration: none;
        }
        
        .stats {
            display: flex;
            gap: 2rem;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .main-section {
            background: var(--bg-secondary);
            border-radius: 20px;
            padding: 2rem;
            margin-bottom: 2rem;
            border: 1px solid var(--border);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }
        
        .input-group {
            margin-bottom: 1.5rem;
        }
        
        .label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .input-field {
            width: 100%;
            padding: 1rem;
            background: var(--bg-tertiary);
            border: 2px solid var(--border);
            border-radius: 10px;
            color: var(--text-primary);
            font-size: 1rem;
            transition: all 0.3s ease;
        }
        
        .input-field:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--shadow);
        }
        
        .input-field::placeholder {
            color: #666;
        }
        
        .button-group {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            margin-bottom: 2rem;
        }
        
        .btn {
            padding: 0.8rem 1.5rem;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .btn:hover {
            background: var(--accent-secondary);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px var(--shadow);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .btn-secondary {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }
        
        .btn-secondary:hover {
            background: var(--border);
        }
        
        .result-section {
            background: var(--bg-tertiary);
            border-radius: 15px;
            padding: 2rem;
            margin: 2rem 0;
            border: 1px solid var(--border);
            display: none;
        }
        
        .result-section.show {
            display: block;
            animation: fadeInUp 0.5s ease;
        }
        
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .result-title {
            font-size: 1.3rem;
            font-weight: bold;
            color: var(--accent);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .result-content {
            color: var(--text-primary);
        }
        
        .result-item {
            margin-bottom: 1rem;
            padding: 1rem;
            background: var(--bg-secondary);
            border-radius: 8px;
            border-left: 4px solid var(--accent);
        }
        
        .graph-container {
            text-align: center;
            margin-top: 2rem;
        }
        
        .graph-container img {
            max-width: 100%;
            height: auto;
            border-radius: 10px;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.3);
        }
        
        .chat-section {
            display: grid;
            grid-template-columns: 1fr;
            gap: 1rem;
            margin-top: 2rem;
        }
        
        .chat-messages {
            background: var(--bg-tertiary);
            border-radius: 15px;
            padding: 1.5rem;
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid var(--border);
        }
        
        .message {
            margin-bottom: 1rem;
            padding: 1rem;
            border-radius: 10px;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }
        
        .message.user {
            background: var(--accent);
            color: white;
            margin-left: 2rem;
        }
        
        .message.assistant {
            background: var(--bg-secondary);
            color: var(--text-primary);
            margin-right: 2rem;
            border: 1px solid var(--border);
        }
        
        .chat-input-container {
            display: flex;
            gap: 1rem;
        }
        
        .chat-input {
            flex: 1;
            min-height: 60px;
            resize: vertical;
        }
        
        .theorems-section {
            background: var(--bg-secondary);
            border-radius: 20px;
            padding: 2rem;
            margin: 2rem 0;
            border: 1px solid var(--border);
        }
        
        .theorem-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 1.5rem;
            margin-top: 1rem;
        }
        
        .theorem-card {
            background: var(--bg-tertiary);
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid var(--border);
            border-left: 4px solid var(--accent);
        }
        
        .theorem-title {
            font-weight: bold;
            color: var(--accent);
            margin-bottom: 0.8rem;
            font-size: 1.1rem;
        }
        
        .theorem-content {
            color: var(--text-secondary);
            line-height: 1.6;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid var(--border);
            border-radius: 50%;
            border-top-color: var(--accent);
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .error {
            background: rgba(255, 68, 68, 0.1);
            color: var(--error);
            border-color: var(--error);
        }
        
        .success {
            background: rgba(0, 255, 136, 0.1);
            color: var(--success);
            border-color: var(--success);
        }
        
        @media (max-width: 768px) {
            .container { padding: 1rem; }
            .header { padding: 1rem; flex-direction: column; gap: 1rem; }
            .stats { justify-content: center; }
            .button-group { justify-content: center; }
            .theorem-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <header class="header">
        <a href="/" class="logo">🔢 Mathia</a>
        <div class="stats">
            <div>📊 <span id="calcCount">0</span> calculs</div>
            <div>📈 <span id="graphCount">0</span> graphiques</div>
            <div>💬 <span id="chatCount">0</span> messages</div>
        </div>
    </header>

    <div class="container">
        <!-- Section principale de calcul -->
        <div class="main-section">
            <h2>🧮 Calculateur Mathématique Universel</h2>
            <p style="color: var(--text-secondary); margin-bottom: 2rem;">
                Entrez n'importe quelle expression mathématique. Mathia la résoudra et générera automatiquement le graphique correspondant.
            </p>
            
            <div class="input-group">
                <label class="label">Expression mathématique</label>
                <input type="text" id="mathInput" class="input-field" 
                       placeholder="Ex: x^2 + 3*x + 2, sin(x), x^2 + y^2 = 25, etc."
                       onkeypress="handleKeyPress(event)">
                <small style="color: #666; margin-top: 0.5rem; display: block;">
                    Utilisez x, y comme variables. Opérateurs: +, -, *, /, ^, sin, cos, tan, ln, sqrt, etc.
                </small>
            </div>
            
            <div class="button-group">
                <button class="btn" onclick="calculate('solve')">
                    <span>🎯</span> Résoudre
                </button>
                <button class="btn" onclick="calculate('simplify')">
                    <span>✨</span> Simplifier
                </button>
                <button class="btn" onclick="calculate('expand')">
                    <span>📐</span> Développer
                </button>
                <button class="btn" onclick="calculate('factor')">
                    <span>🧩</span> Factoriser
                </button>
                <button class="btn" onclick="calculate('derivative')">
                    <span>📈</span> Dériver
                </button>
                <button class="btn" onclick="calculate('integral')">
                    <span>∫</span> Intégrer
                </button>
            </div>
            
            <div id="resultSection" class="result-section">
                <div class="result-title">
                    <span>🎯</span>
                    <span id="resultTitle">Résultats</span>
                </div>
                <div id="resultContent" class="result-content"></div>
                <div id="graphContainer" class="graph-container"></div>
            </div>
        </div>

        <!-- Section Chat IA -->
        <div class="main-section">
            <h2>🤖 Assistant IA Mathématique</h2>
            <p style="color: var(--text-secondary); margin-bottom: 2rem;">
                Posez vos questions mathématiques à Mathia. Il peut expliquer vos résultats et vous aider à comprendre.
            </p>
            
            <div class="chat-section">
                <div id="chatMessages" class="chat-messages">
                    <div class="message assistant">
                        <strong>Mathia:</strong> Bonjour ! Je suis votre assistant mathématique IA. 
                        Posez-moi vos questions sur les mathématiques, demandez des explications ou 
                        de l'aide pour résoudre des problèmes !
                    </div>
                </div>
                
                <div class="chat-input-container">
                    <textarea id="chatInput" class="input-field chat-input" 
                              placeholder="Posez votre question mathématique..."
                              onkeypress="handleChatKeyPress(event)"></textarea>
                    <button class="btn" onclick="sendChatMessage()" id="chatBtn">
                        <span>📤</span> Envoyer
                    </button>
                </div>
            </div>
        </div>

        <!-- Section Théorèmes et Définitions -->
        <div class="theorems-section">
            <h2>📚 Théorèmes et Définitions Fondamentaux</h2>
            <div class="theorem-grid">
                <div class="theorem-card">
                    <div class="theorem-title">Théorème de Pythagore</div>
                    <div class="theorem-content">
                        Dans un triangle rectangle, le carré de l'hypoténuse est égal à la somme des carrés des deux autres côtés : a² + b² = c²
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-title">Identités Trigonométriques</div>
                    <div class="theorem-content">
                        sin²(x) + cos²(x) = 1<br>
                        tan(x) = sin(x) / cos(x)<br>
                        sin(2x) = 2sin(x)cos(x)<br>
                        cos(2x) = cos²(x) - sin²(x)
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-title">Dérivées Fondamentales</div>
                    <div class="theorem-content">
                        d/dx[x^n] = n·x^(n-1)<br>
                        d/dx[sin(x)] = cos(x)<br>
                        d/dx[cos(x)] = -sin(x)<br>
                        d/dx[e^x] = e^x<br>
                        d/dx[ln(x)] = 1/x
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-title">Formule Quadratique</div>
                    <div class="theorem-content">
                        Pour ax² + bx + c = 0 :<br>
                        x = (-b ± √(b² - 4ac)) / 2a<br>
                        Discriminant Δ = b² - 4ac
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-title">Limites Remarquables</div>
                    <div class="theorem-content">
                        lim(x→0) sin(x)/x = 1<br>
                        lim(x→∞) (1 + 1/x)^x = e<br>
                        lim(x→0) (e^x - 1)/x = 1<br>
                        lim(x→0) ln(1+x)/x = 1
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-title">Développements de Taylor</div>
                    <div class="theorem-content">
                        e^x = 1 + x + x²/2! + x³/3! + ...<br>
                        sin(x) = x - x³/3! + x⁵/5! - ...<br>
                        cos(x) = 1 - x²/2! + x⁴/4! - ...<br>
                        ln(1+x) = x - x²/2 + x³/3 - ...
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-title">Théorème Fondamental du Calcul</div>
                    <div class="theorem-content">
                        Si F'(x) = f(x), alors :<br>
                        ∫[a,b] f(x)dx = F(b) - F(a)<br>
                        d/dx ∫[a,x] f(t)dt = f(x)
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-title">Inégalités Importantes</div>
                    <div class="theorem-content">
                        Inégalité de Cauchy-Schwarz<br>
                        Inégalité triangulaire : |a + b| ≤ |a| + |b|<br>
                        Inégalité arithmético-géométrique<br>
                        |ab| ≤ (a² + b²)/2
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentCalculation = null;
        
        // Initialisation
        document.addEventListener('DOMContentLoaded', function() {
            loadStats();
            document.getElementById('mathInput').focus();
        });
        
        // Gestion des touches
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                calculate('solve');
            }
        }
        
        function handleChatKeyPress(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendChatMessage();
            }
        }
        
        // Fonction principale de calcul
        async function calculate(operation) {
            const input = document.getElementById('mathInput').value.trim();
            if (!input) {
                showError('Veuillez entrer une expression mathématique');
                return;
            }
            
            const resultSection = document.getElementById('resultSection');
            const resultContent = document.getElementById('resultContent');
            const resultTitle = document.getElementById('resultTitle');
            const graphContainer = document.getElementById('graphContainer');
            
            // Afficher le loading
            resultTitle.innerHTML = `<span class="loading"></span> Calcul en cours...`;
            resultContent.innerHTML = '';
            graphContainer.innerHTML = '';
            resultSection.classList.add('show');
            
            try {
                const response = await fetch('/api/calculate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        expression: input, 
                        operation: operation 
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    displayResults(data, operation);
                    currentCalculation = data;
                    loadStats();
                } else {
                    showError(data.error);
                }
                
            } catch (error) {
                showError('Erreur de connexion: ' + error.message);
            }
        }
        
        // Affichage des résultats
        function displayResults(data, operation) {
            const resultTitle = document.getElementById('resultTitle');
            const resultContent = document.getElementById('resultContent');
            const graphContainer = document.getElementById('graphContainer');
            
            // Titre selon l'opération
            const titles = {
                'solve': '🎯 Solutions',
                'simplify': '✨ Forme Simplifiée',
                'expand': '📐 Forme Développée',
                'factor': '🧩 Forme Factorisée',
                'derivative': '📈 Dérivée',
                'integral': '∫ Primitive'
            };
            
            resultTitle.textContent = titles[operation] || '🎯 Résultats';
            
            let html = `
                <div class="result-item">
                    <strong>Expression originale :</strong> ${data.original}
                </div>
                <div class="result-item">
                    <strong>Forme parsée :</strong> ${data.parsed}
                </div>
            `;
            
            // Afficher les résultats selon le type d'opération
            const results = data.results;
            
            if (results.solutions) {
                html += `
                    <div class="result-item success">
                        <strong>Solutions :</strong> ${results.solutions.length > 0 ? results.solutions.join(', ') : 'Aucune solution réelle'}
                    </div>
                `;
            }
            
            if (results.expanded) {
                html += `
                    <div class="result-item success">
                        <strong>Forme développée :</strong> ${results.expanded}
                    </div>
                `;
            }
            
            if (results.factored) {
                html += `
                    <div class="result-item success">
                        <strong>Forme factorisée :</strong> ${results.factored}
                    </div>
                `;
            }
            
            if (results.simplified) {
                html += `
                    <div class="result-item success">
                        <strong>Forme simplifiée :</strong> ${results.simplified}
                    </div>
                `;
            }
            
            if (results.derivative) {
                html += `
                    <div class="result-item success">
                        <strong>Dérivée :</strong> ${results.derivative}
                    </div>
                `;
            }
            
            if (results.integral) {
                html += `
                    <div class="result-item success">
                        <strong>Primitive :</strong> ${results.integral}
                    </div>
                `;
            }
            
            if (results.limit) {
                html += `
                    <div class="result-item success">
                        <strong>Limite :</strong> ${results.limit}
                    </div>
                `;
            }
            
            if (results.series) {
                html += `
                    <div class="result-item success">
                        <strong>Série de Taylor :</strong> ${results.series}
                    </div>
                `;
            }
            
            resultContent.innerHTML = html;
            
            // Afficher le graphique si disponible
            if (data.graph) {
                graphContainer.innerHTML = `
                    <div class="result-title">📊 Graphique</div>
                    <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                        ${data.graph.type} - ${data.graph.expression}
                    </p>
                    <img src="data:image/png;base64,${data.graph.image}" alt="Graphique de la fonction">
                `;
            }
        }
        
        // Chat avec l'IA
        async function sendChatMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            const chatMessages = document.getElementById('chatMessages');
            const chatBtn = document.getElementById('chatBtn');
            
            // Ajouter le message utilisateur
            addChatMessage('user', message);
            input.value = '';
            
            // Désactiver le bouton
            chatBtn.disabled = true;
            chatBtn.innerHTML = '<span class="loading"></span> Réflexion...';
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        message: message,
                        context: currentCalculation ? JSON.stringify(currentCalculation) : null
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    addChatMessage('assistant', data.response);
                    loadStats();
                } else {
                    addChatMessage('assistant', `Erreur: ${data.error}`);
                }
                
            } catch (error) {
                addChatMessage('assistant', `Erreur de connexion: ${error.message}`);
            } finally {
                chatBtn.disabled = false;
                chatBtn.innerHTML = '<span>📤</span> Envoyer';
            }
        }
        
        function addChatMessage(sender, message) {
            const chatMessages = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}`;
            
            const senderName = sender === 'user' ? 'Vous' : 'Mathia';
            messageDiv.innerHTML = `<strong>${senderName}:</strong> ${message}`;
            
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        // Charger les statistiques
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                document.getElementById('calcCount').textContent = stats.calculations || 0;
                document.getElementById('graphCount').textContent = stats.graphs_generated || 0;
                document.getElementById('chatCount').textContent = stats.chat_messages || 0;
            } catch (error) {
                console.log('Erreur chargement stats:', error);
            }
        }
        
        function showError(message) {
            const resultSection = document.getElementById('resultSection');
            const resultTitle = document.getElementById('resultTitle');
            const resultContent = document.getElementById('resultContent');
            
            resultTitle.textContent = '❌ Erreur';
            resultContent.innerHTML = `
                <div class="result-item error">
                    <strong>Erreur :</strong> ${message}
                </div>
            `;
            resultSection.classList.add('show');
        }
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("🔢 MATHIA - Assistant Mathématique IA")
    print("=" * 50)
    
    try:
        # Vérification des dépendances
        import sympy
        import matplotlib
        import numpy as np
        from mistralai import Mistral
        print("✅ Toutes les dépendances sont installées")
        
        # Configuration pour le déploiement
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port: {port}")
        print(f"🔧 Mode debug: {debug_mode}")
        print(f"🔑 Clés API Mistral: {len(mathia.api_keys)} configurées")
        print("🚀 Démarrage du serveur...")
        
    except ImportError as e:
        print(f"❌ ERREUR: Dépendance manquante - {e}")
        print("💡 Installez les dépendances avec: pip install flask sympy matplotlib numpy mistralai")
        exit(1)
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode
    )
