from flask import Flask, request, jsonify, render_template_string
import os
import json
import base64
import io
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import cm
import sympy as sp
from sympy import *
from sympy.plotting import plot, plot3d
from mistralai import Mistral
import time
import re
import random
from concurrent.futures import ThreadPoolExecutor
import threading

app = Flask(__name__)

class MathiaVisualCore:
    """Mathia - Assistant Mathématique Visuel avec IA Centrale"""
    
    def __init__(self):
        # Configuration des clés API Mistral
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        self.current_key_index = 0
        self.key_errors = {i: 0 for i in range(len(self.api_keys))}
        
        # Variables symboliques
        self.x, self.y, self.z, self.t = symbols('x y z t')
        self.n, self.k, self.a, self.b, self.c = symbols('n k a b c')
        
        # Cache et statistiques
        self.conversation_history = []
        self.visual_cache = {}
        self.stats = {
            'messages': 0,
            'visualizations': 0,
            'functions_analyzed': 0,
            'concepts_explained': 0
        }
        
        # Configuration matplotlib moderne
        plt.style.use('dark_background')
        plt.rcParams.update({
            'font.size': 11,
            'axes.linewidth': 1.5,
            'lines.linewidth': 2.8,
            'figure.facecolor': '#0f0f23',
            'axes.facecolor': '#1a1a3a'
        })
        
        self.executor = ThreadPoolExecutor(max_workers=2)
        
    def get_mistral_client(self):
        """Obtient le meilleur client Mistral disponible"""
        sorted_keys = sorted(range(len(self.api_keys)), key=lambda i: self.key_errors[i])
        
        for key_index in sorted_keys:
            try:
                key = self.api_keys[key_index]
                client = Mistral(api_key=key)
                self.current_key_index = key_index
                return client
            except Exception:
                self.key_errors[key_index] += 1
                continue
        
        return Mistral(api_key=self.api_keys[0])
    
    def analyze_message_for_visuals(self, message):
        """Analyse le message pour détecter les besoins de visualisation"""
        visual_triggers = {
            'function': ['fonction', 'f(x)', 'graphique', 'courbe', 'tracer', 'plot'],
            'equation': ['équation', 'résoudre', '=', 'solutions'],
            'statistics': ['données', 'statistique', 'moyenne', 'écart', 'distribution'],
            'geometry': ['triangle', 'cercle', 'géométrie', 'aire', 'périmètre'],
            'analysis': ['dérivée', 'intégrale', 'limite', 'asymptote'],
            'comparison': ['comparer', 'versus', 'différence', 'évolution']
        }
        
        message_lower = message.lower()
        detected_types = []
        
        for viz_type, keywords in visual_triggers.items():
            if any(keyword in message_lower for keyword in keywords):
                detected_types.append(viz_type)
        
        # Détection d'expressions mathématiques
        math_patterns = [
            r'[a-z]\([x-z]\)',  # f(x), g(y), etc.
            r'x\^?\d+',         # x^2, x2, etc.
            r'sin|cos|tan|log|exp|sqrt',  # fonctions
            r'\d+[\+\-\*/]\d+',  # opérations
        ]
        
        for pattern in math_patterns:
            if re.search(pattern, message_lower):
                if 'function' not in detected_types:
                    detected_types.append('function')
                break
        
        return detected_types
    
    def extract_math_expressions(self, text):
        """Extrait les expressions mathématiques du texte"""
        expressions = []
        
        # Patterns pour différents types d'expressions
        patterns = [
            r'([a-z]\([x-z]\)\s*=\s*[^,\.]+)',  # f(x) = ...
            r'(x\^?\d+[\+\-\*/][^,\.]+)',       # x^2 + 3x + 2
            r'(sin\([^)]+\)|cos\([^)]+\)|tan\([^)]+\))',  # fonctions trig
            r'(e\^[^,\s]+|exp\([^)]+\))',       # exponentielles
            r'(log\([^)]+\)|ln\([^)]+\))',      # logarithmes
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            expressions.extend(matches)
        
        return list(set(expressions))  # Supprimer les doublons
    
    def create_concept_visualization(self, concept, data=None):
        """Crée une visualisation pour illustrer un concept mathématique"""
        try:
            fig, ax = plt.subplots(figsize=(12, 8), facecolor='#0f0f23')
            ax.set_facecolor('#1a1a3a')
            
            if concept == 'function':
                return self._visualize_function_concept(ax, data)
            elif concept == 'statistics':
                return self._visualize_statistics_concept(ax, data)
            elif concept == 'geometry':
                return self._visualize_geometry_concept(ax, data)
            elif concept == 'analysis':
                return self._visualize_analysis_concept(ax, data)
            elif concept == 'comparison':
                return self._visualize_comparison_concept(ax, data)
            else:
                return self._visualize_generic_concept(ax, concept, data)
                
        except Exception as e:
            print(f"Erreur visualisation concept {concept}: {e}")
            return None
    
    def _visualize_function_concept(self, ax, data):
        """Visualise des fonctions mathématiques"""
        x_vals = np.linspace(-10, 10, 1000)
        
        # Fonctions de démonstration si aucune donnée spécifique
        if not data:
            functions = [
                (lambda x: np.sin(x), 'sin(x)', '#00d4ff'),
                (lambda x: np.cos(x), 'cos(x)', '#ff6b6b'),
                (lambda x: x**2 / 20, 'x²/20', '#4ecdc4'),
            ]
        else:
            functions = data
        
        for func, label, color in functions:
            try:
                y_vals = func(x_vals)
                mask = np.isfinite(y_vals)
                ax.plot(x_vals[mask], y_vals[mask], color=color, linewidth=3, 
                       label=label, alpha=0.9)
            except:
                continue
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.axhline(y=0, color='#ffffff', linewidth=1.5, alpha=0.8)
        ax.axvline(x=0, color='#ffffff', linewidth=1.5, alpha=0.8)
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('f(x)', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Visualisation de Fonctions', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        legend.get_frame().set_edgecolor('#00d4ff')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
            spine.set_linewidth(1.5)
        
        return self._save_plot_to_base64()
    
    def _visualize_statistics_concept(self, ax, data):
        """Visualise des concepts statistiques"""
        if not data:
            # Données de démonstration
            np.random.seed(42)
            data1 = np.random.normal(100, 15, 1000)
            data2 = np.random.normal(110, 20, 1000)
            
            ax.hist(data1, bins=30, alpha=0.7, color='#00d4ff', label='Série A', density=True)
            ax.hist(data2, bins=30, alpha=0.7, color='#ff6b6b', label='Série B', density=True)
        
        ax.set_xlabel('Valeurs', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('Densité', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Distribution Statistique', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        legend = ax.legend(frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        return self._save_plot_to_base64()
    
    def _visualize_geometry_concept(self, ax, data):
        """Visualise des concepts géométriques"""
        # Cercle et triangle de démonstration
        theta = np.linspace(0, 2*np.pi, 100)
        
        # Cercle
        circle_x = np.cos(theta)
        circle_y = np.sin(theta)
        ax.plot(circle_x, circle_y, color='#00d4ff', linewidth=3, label='Cercle unitaire')
        
        # Triangle inscrit
        triangle_angles = [0, 2*np.pi/3, 4*np.pi/3, 0]
        triangle_x = [np.cos(angle) for angle in triangle_angles]
        triangle_y = [np.sin(angle) for angle in triangle_angles]
        ax.plot(triangle_x, triangle_y, color='#ff6b6b', linewidth=3, label='Triangle équilatéral')
        
        # Axes et centre
        ax.axhline(y=0, color='#ffffff', linewidth=1, alpha=0.6)
        ax.axvline(x=0, color='#ffffff', linewidth=1, alpha=0.6)
        ax.plot(0, 0, 'o', color='#4ecdc4', markersize=8, label='Centre')
        
        ax.set_xlim(-1.5, 1.5)
        ax.set_ylim(-1.5, 1.5)
        ax.set_aspect('equal')
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('y', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Géométrie - Cercle et Triangle', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        legend = ax.legend(frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        return self._save_plot_to_base64()
    
    def _visualize_analysis_concept(self, ax, data):
        """Visualise des concepts d'analyse (dérivées, intégrales)"""
        x_vals = np.linspace(-3, 3, 1000)
        
        # Fonction principale
        f = lambda x: x**3 - 2*x**2 + x
        f_prime = lambda x: 3*x**2 - 4*x + 1
        
        y_vals = f(x_vals)
        y_prime_vals = f_prime(x_vals)
        
        ax.plot(x_vals, y_vals, color='#00d4ff', linewidth=3, label='f(x) = x³ - 2x² + x')
        ax.plot(x_vals, y_prime_vals, color='#ff6b6b', linewidth=3, label="f'(x) = 3x² - 4x + 1")
        
        # Points critiques
        critical_points = [1/3, 1]
        for cp in critical_points:
            ax.plot(cp, f(cp), 'o', color='#4ecdc4', markersize=10, markeredgewidth=2)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.axhline(y=0, color='#ffffff', linewidth=1, alpha=0.8)
        ax.axvline(x=0, color='#ffffff', linewidth=1, alpha=0.8)
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('y', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Analyse - Fonction et sa Dérivée', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        legend = ax.legend(frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        return self._save_plot_to_base64()
    
    def _visualize_comparison_concept(self, ax, data):
        """Visualise des comparaisons entre fonctions ou données"""
        x_vals = np.linspace(0, 10, 1000)
        
        # Comparaison de croissances
        linear = x_vals
        quadratic = x_vals**2 / 10
        exponential = np.exp(x_vals/3) / 10
        
        ax.plot(x_vals, linear, color='#00d4ff', linewidth=3, label='Linéaire: f(x) = x')
        ax.plot(x_vals, quadratic, color='#ff6b6b', linewidth=3, label='Quadratique: f(x) = x²/10')
        ax.plot(x_vals, exponential, color='#4ecdc4', linewidth=3, label='Exponentielle: f(x) = e^(x/3)/10')
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('f(x)', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Comparaison de Croissances', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        legend = ax.legend(frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        return self._save_plot_to_base64()
    
    def _visualize_generic_concept(self, ax, concept, data):
        """Visualisation générique pour autres concepts"""
        # Graphique abstrait basé sur le concept
        x_vals = np.linspace(0, 4*np.pi, 1000)
        
        # Différentes ondes selon le concept
        wave1 = np.sin(x_vals) * np.exp(-x_vals/10)
        wave2 = np.cos(x_vals * 1.5) * np.exp(-x_vals/15)
        
        ax.plot(x_vals, wave1, color='#00d4ff', linewidth=3, alpha=0.8)
        ax.plot(x_vals, wave2, color='#ff6b6b', linewidth=3, alpha=0.8)
        
        ax.fill_between(x_vals, wave1, alpha=0.3, color='#00d4ff')
        ax.fill_between(x_vals, wave2, alpha=0.3, color='#ff6b6b')
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('f(x)', fontsize=14, color='white', fontweight='bold')
        ax.set_title(f'Illustration - {concept.title()}', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        return self._save_plot_to_base64()
    
    def _save_plot_to_base64(self):
        """Sauvegarde le plot actuel en base64"""
        plt.tight_layout()
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', 
                   facecolor='#0f0f23', edgecolor='none', dpi=100)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        return image_base64
    
    def chat_with_visual_response(self, message):
        """Chat principal avec génération de visuels intelligents"""
        try:
            client = self.get_mistral_client()
            
            # Analyser le message pour détecter les besoins visuels
            visual_needs = self.analyze_message_for_visuals(message)
            math_expressions = self.extract_math_expressions(message)
            
            # Prompt système enrichi
            system_prompt = f"""Tu es Mathia, un assistant mathématique expert qui combine explications textuelles et visualisations.

IMPORTANT - Réponse structurée requise:
Réponds TOUJOURS avec cette structure JSON:
{{
    "text_response": "Ton explication claire et pédagogique ici",
    "visual_needed": {len(visual_needs) > 0 or len(math_expressions) > 0},
    "visual_type": "{visual_needs[0] if visual_needs else 'function'}",
    "math_expressions": {math_expressions},
    "key_concepts": ["concept1", "concept2"]
}}

Détecté dans le message:
- Besoins visuels: {visual_needs}
- Expressions mathématiques: {math_expressions}

Ton rôle:
1. Explique clairement les concepts mathématiques
2. Utilise un langage accessible mais précis  
3. Structure tes explications étape par étape
4. Suggère des visualisations pertinentes
5. Relie les concepts abstraits à des exemples concrets

Évite les formatages avec des astérisques. Utilise un langage naturel et fluide."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
            
            # Ajouter l'historique récent
            for hist_msg in self.conversation_history[-3:]:
                messages.extend([
                    {"role": "user", "content": hist_msg['user']},
                    {"role": "assistant", "content": hist_msg['assistant'][:500]}  # Limiter la taille
                ])
            
            messages.append({"role": "user", "content": message})
            
            response = client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.3,
                max_tokens=1500
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Tenter de parser la réponse JSON
            visual_data = None
            try:
                # Chercher le JSON dans la réponse
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    response_json = json.loads(json_match.group())
                    text_response = response_json.get('text_response', response_text)
                    visual_needed = response_json.get('visual_needed', len(visual_needs) > 0)
                    visual_type = response_json.get('visual_type', visual_needs[0] if visual_needs else 'function')
                    
                    if visual_needed:
                        visual_data = self.create_concept_visualization(visual_type, math_expressions)
                        if visual_data:
                            self.stats['visualizations'] += 1
                else:
                    text_response = response_text
                    # Générer un visuel basé sur l'analyse du message
                    if visual_needs:
                        visual_data = self.create_concept_visualization(visual_needs[0], math_expressions)
                        if visual_data:
                            self.stats['visualizations'] += 1
            except:
                text_response = response_text
                # Fallback: générer un visuel si des besoins ont été détectés
                if visual_needs:
                    visual_data = self.create_concept_visualization(visual_needs[0], math_expressions)
                    if visual_data:
                        self.stats['visualizations'] += 1
            
            # Nettoyer la réponse texte (supprimer le JSON s'il est présent)
            text_response = re.sub(r'\{.*\}', '', text_response, flags=re.DOTALL).strip()
            if not text_response:
                text_response = response_text
            
            # Ajouter à l'historique
            self.conversation_history.append({
                'user': message,
                'assistant': text_response,
                'visual': visual_data is not None,
                'timestamp': time.time()
            })
            
            # Limiter l'historique
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-15:]
            
            self.stats['messages'] += 1
            if math_expressions:
                self.stats['functions_analyzed'] += 1
            if any(concept in message.lower() for concept in ['concept', 'principe', 'théorème']):
                self.stats['concepts_explained'] += 1
            
            return {
                'success': True,
                'response': text_response,
                'visual': visual_data,
                'visual_type': visual_needs[0] if visual_needs else None,
                'math_detected': len(math_expressions) > 0
            }
            
        except Exception as e:
            print(f"Erreur chat visuel: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': 'Désolé, une erreur est survenue. Pouvez-vous reformuler votre question ?'
            }

# Instance globale
mathia = MathiaVisualCore()

@app.route('/')
def index():
    """Interface Mathia centrée sur le chat visuel"""
    return render_template_string(MATHIA_VISUAL_TEMPLATE)

@app.route('/api/chat', methods=['POST'])
def chat():
    """API principale de chat avec visuels"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message requis'})
        
        result = mathia.chat_with_visual_response(message)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def get_stats():
    """API des statistiques"""
    return jsonify(mathia.stats)

@app.route('/health')
def health_check():
    """Health check"""
    return jsonify({'status': 'OK', 'service': 'Mathia Visual', 'version': '3.0'}), 200

# Template HTML moderne centré sur le chat
MATHIA_VISUAL_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Assistant Mathématique Visuel</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script>
        window.MathJax = {
            tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']] },
            svg: { fontCache: 'global' }
        };
    </script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --bg-primary: #0f0f23;
            --bg-secondary: #1a1a3a;
            --bg-tertiary: #2a2a4a;
            --text-primary: #ffffff;
            --text-secondary: #b8bcc8;
            --accent: #00d4ff;
            --accent-secondary: #667eea;
            --success: #00ff88;
            --error: #ff4757;
            --border: rgba(255, 255, 255, 0.1);
            --shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        /* Header */
        .header {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(15, 15, 35, 0.95);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border);
            padding: 1rem 0;
        }
        
        .header-content {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 2rem;
            font-weight: 800;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .stats {
            display: flex;
            gap: 2rem;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        
        .stat-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: var(--bg-tertiary);
            border-radius: 15px;
            border: 1px solid var(--border);
        }
        
        /* Container principal */
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            display: grid;
            grid-template-columns: 1fr;
            gap: 2rem;
            min-height: calc(100vh - 100px);
        }
        
        /* Chat principal */
        .chat-container {
            background: var(--bg-secondary);
            border-radius: 25px;
            padding: 2rem;
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            display: flex;
            flex-direction: column;
            height: calc(100vh - 200px);
        }
        
        .chat-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--accent);
            margin-bottom: 1.5rem;
            text-align: center;
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 15px;
            border: 1px solid var(--border);
            margin-bottom: 1.5rem;
            scroll-behavior: smooth;
        }
        
        .message {
            margin-bottom: 2rem;
            animation: messageSlide 0.4s ease;
        }
        
        @keyframes messageSlide {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message-user {
            display: flex;
            justify-content: flex-end;
            margin-bottom: 1rem;
        }
        
        .message-assistant {
            display: flex;
            justify-content: flex-start;
            margin-bottom: 2rem;
        }
        
        .message-bubble {
            max-width: 80%;
            padding: 1.2rem 1.8rem;
            border-radius: 20px;
            word-wrap: break-word;
            line-height: 1.6;
        }
        
        .message-user .message-bubble {
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            color: white;
            border-bottom-right-radius: 8px;
            box-shadow: 0 4px 15px rgba(0, 212, 255, 0.3);
        }
        
        .message-assistant .message-bubble {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-bottom-left-radius: 8px;
        }
        
        .message-sender {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            font-weight: 600;
        }
        
        .visual-container {
            margin-top: 1.5rem;
            padding: 1.5rem;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 15px;
            border: 1px solid var(--border);
            text-align: center;
        }
        
        .visual-container img {
            max-width: 100%;
            height: auto;
            border-radius: 10px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.4);
        }
        
        .visual-label {
            color: var(--accent);
            font-size: 0.9rem;
            margin-bottom: 1rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }
        
        /* Input zone */
        .chat-input-container {
            display: flex;
            gap: 1rem;
            align-items: flex-end;
            background: var(--bg-tertiary);
            padding: 1.5rem;
            border-radius: 20px;
            border: 1px solid var(--border);
        }
        
        .chat-input {
            flex: 1;
            padding: 1.2rem 1.5rem;
            background: var(--bg-primary);
            border: 2px solid var(--border);
            border-radius: 15px;
            color: var(--text-primary);
            font-size: 1rem;
            resize: vertical;
            min-height: 60px;
            max-height: 150px;
            transition: all 0.3s ease;
            font-family: inherit;
        }
        
        .chat-input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 4px rgba(0, 212, 255, 0.1);
            background: rgba(26, 26, 58, 0.8);
        }
        
        .chat-input::placeholder {
            color: var(--text-secondary);
            opacity: 0.7;
        }
        
        .send-button {
            padding: 1.2rem 2rem;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            border: none;
            border-radius: 15px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            white-space: nowrap;
            position: relative;
            overflow: hidden;
        }
        
        .send-button:before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: left 0.5s ease;
        }
        
        .send-button:hover:before {
            left: 100%;
        }
        
        .send-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 212, 255, 0.4);
        }
        
        .send-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .loading-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top: 2px solid white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 0.5rem;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        /* Notifications */
        .notification {
            position: fixed;
            top: 100px;
            right: 20px;
            padding: 1rem 1.5rem;
            border-radius: 15px;
            color: white;
            font-weight: 600;
            z-index: 1000;
            transform: translateX(400px);
            transition: all 0.4s ease;
            max-width: 350px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(20px);
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.success {
            background: linear-gradient(135deg, var(--success), #00cc77);
        }
        
        .notification.error {
            background: linear-gradient(135deg, var(--error), #cc3344);
        }
        
        .notification.info {
            background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
        }
        
        /* Messages d'aide */
        .help-message {
            background: rgba(0, 212, 255, 0.1);
            border: 1px solid var(--accent);
            border-radius: 15px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            color: var(--text-primary);
        }
        
        .help-title {
            color: var(--accent);
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        
        .examples {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }
        
        .example {
            background: var(--bg-tertiary);
            padding: 1rem;
            border-radius: 10px;
            border: 1px solid var(--border);
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9rem;
        }
        
        .example:hover {
            background: rgba(0, 212, 255, 0.1);
            border-color: var(--accent);
            transform: translateY(-2px);
        }
        
        /* Scrollbar personnalisé */
        .chat-messages::-webkit-scrollbar {
            width: 6px;
        }
        
        .chat-messages::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
        }
        
        .chat-messages::-webkit-scrollbar-thumb {
            background: var(--accent);
            border-radius: 10px;
        }
        
        .chat-messages::-webkit-scrollbar-thumb:hover {
            background: var(--accent-secondary);
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .header-content {
                flex-direction: column;
                gap: 1rem;
                padding: 0 1rem;
            }
            
            .stats {
                flex-direction: column;
                gap: 0.5rem;
                align-items: center;
            }
            
            .container {
                padding: 1rem;
            }
            
            .chat-container {
                height: calc(100vh - 250px);
                padding: 1.5rem;
            }
            
            .chat-input-container {
                flex-direction: column;
                gap: 1rem;
            }
            
            .message-bubble {
                max-width: 95%;
            }
            
            .examples {
                grid-template-columns: 1fr;
            }
            
            .notification {
                right: 10px;
                max-width: calc(100vw - 20px);
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div class="logo">
                🎨 Mathia Visual
            </div>
            
            <div class="stats">
                <div class="stat-item">
                    <span>💬</span>
                    <span id="messageCount">0</span> messages
                </div>
                <div class="stat-item">
                    <span>📊</span>
                    <span id="visualCount">0</span> visuels
                </div>
                <div class="stat-item">
                    <span>🧮</span>
                    <span id="functionCount">0</span> fonctions
                </div>
                <div class="stat-item">
                    <span>💡</span>
                    <span id="conceptCount">0</span> concepts
                </div>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="chat-container">
            <div class="chat-title">Assistant Mathématique Visuel</div>
            
            <div id="chatMessages" class="chat-messages">
                <div class="help-message">
                    <div class="help-title">Bienvenue dans Mathia Visual !</div>
                    <p>Je suis votre assistant mathématique qui combine explications claires et visualisations intelligentes. Je peux créer des graphiques automatiquement pour illustrer vos questions.</p>
                    
                    <div class="examples">
                        <div class="example" onclick="useExample('Explique-moi la fonction f(x) = x² + 2x - 3')">
                            📈 Analyser une fonction quadratique
                        </div>
                        <div class="example" onclick="useExample('Compare les croissances linéaire, quadratique et exponentielle')">
                            📊 Comparer des croissances
                        </div>
                        <div class="example" onclick="useExample('Montre-moi les dérivées et leurs applications')">
                            🔍 Explorer le calcul différentiel
                        </div>
                        <div class="example" onclick="useExample('Visualise la distribution normale en statistiques')">
                            📉 Concepts statistiques
                        </div>
                        <div class="example" onclick="useExample('Explique la géométrie du cercle trigonométrique')">
                            🎯 Géométrie et trigonométrie
                        </div>
                        <div class="example" onclick="useExample('Qu'est-ce que l'intégration et à quoi ça sert ?')">
                            ∫ Calcul intégral
                        </div>
                    </div>
                </div>
                
                <div class="message-assistant">
                    <div class="message-bubble">
                        <div class="message-sender">Mathia</div>
                        Salut ! Je suis ravi de t'aider avec les mathématiques. Pose-moi n'importe quelle question et je créerai des visualisations pour t'aider à mieux comprendre. Que veux-tu explorer aujourd'hui ?
                    </div>
                </div>
            </div>
            
            <div class="chat-input-container">
                <textarea id="chatInput" class="chat-input" 
                          placeholder="Posez votre question mathématique... (ex: 'Montre-moi la fonction sin(x) et ses propriétés')"
                          rows="2"></textarea>
                <button id="sendButton" class="send-button">
                    Envoyer
                </button>
            </div>
        </div>
    </div>

    <script>
        let isLoading = false;
        let messageCount = 0;
        
        // Initialisation
        document.addEventListener('DOMContentLoaded', function() {
            setupEventListeners();
            loadStats();
            focusChatInput();
        });
        
        function setupEventListeners() {
            const chatInput = document.getElementById('chatInput');
            const sendButton = document.getElementById('sendButton');
            
            // Envoi avec Enter (Shift+Enter pour nouvelle ligne)
            chatInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // Auto-resize du textarea
            chatInput.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 150) + 'px';
            });
            
            sendButton.addEventListener('click', sendMessage);
        }
        
        function useExample(exampleText) {
            document.getElementById('chatInput').value = exampleText;
            focusChatInput();
        }
        
        function focusChatInput() {
            setTimeout(() => {
                document.getElementById('chatInput').focus();
            }, 100);
        }
        
        async function sendMessage() {
            if (isLoading) return;
            
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            
            if (!message) {
                showNotification('Veuillez entrer un message', 'error');
                return;
            }
            
            // Ajouter le message utilisateur
            addUserMessage(message);
            input.value = '';
            input.style.height = 'auto';
            
            // UI de chargement
            setLoading(true);
            const tempId = addAssistantMessage('', true);
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                const data = await response.json();
                
                // Supprimer le message temporaire
                document.getElementById(tempId).remove();
                
                if (data.success) {
                    addAssistantMessage(data.response, false, data.visual, data.visual_type);
                    
                    if (data.visual) {
                        showNotification('Visualisation générée !', 'success');
                    }
                    
                    if (data.math_detected) {
                        showNotification('Expression mathématique détectée', 'info');
                    }
                } else {
                    addAssistantMessage('Désolé, une erreur est survenue: ' + data.error, false);
                    showNotification('Erreur lors du traitement', 'error');
                }
                
                await loadStats();
                
            } catch (error) {
                document.getElementById(tempId).remove();
                addAssistantMessage('Erreur de connexion. Veuillez réessayer.', false);
                showNotification('Erreur de connexion', 'error');
                console.error('Erreur:', error);
            } finally {
                setLoading(false);
                focusChatInput();
            }
        }
        
        function addUserMessage(message) {
            const container = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message-user';
            
            messageDiv.innerHTML = `
                <div class="message-bubble">
                    <div class="message-sender">Vous</div>
                    ${message}
                </div>
            `;
            
            container.appendChild(messageDiv);
            scrollToBottom();
            messageCount++;
        }
        
        function addAssistantMessage(message, isLoading = false, visualData = null, visualType = null) {
            const container = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            messageDiv.id = messageId;
            messageDiv.className = 'message-assistant';
            
            let content = `
                <div class="message-bubble">
                    <div class="message-sender">Mathia</div>
                    ${isLoading ? '<div class="loading-spinner"></div>Réflexion en cours...' : message}
            `;
            
            if (visualData && !isLoading) {
                const visualTypeLabels = {
                    'function': '📈 Graphique de Fonction',
                    'statistics': '📊 Analyse Statistique',
                    'geometry': '🎯 Illustration Géométrique',
                    'analysis': '🔍 Analyse Mathématique',
                    'comparison': '⚖️ Comparaison Visual'
                };
                
                const label = visualTypeLabels[visualType] || '📊 Visualisation';
                
                content += `
                    <div class="visual-container">
                        <div class="visual-label">${label}</div>
                        <img src="data:image/png;base64,${visualData}" alt="Visualisation mathématique">
                    </div>
                `;
            }
            
            content += '</div>';
            messageDiv.innerHTML = content;
            
            container.appendChild(messageDiv);
            scrollToBottom();
            
            return messageId;
        }
        
        function setLoading(loading) {
            const sendButton = document.getElementById('sendButton');
            const chatInput = document.getElementById('chatInput');
            
            isLoading = loading;
            sendButton.disabled = loading;
            chatInput.disabled = loading;
            
            if (loading) {
                sendButton.innerHTML = '<div class="loading-spinner"></div>Envoi...';
            } else {
                sendButton.innerHTML = 'Envoyer';
            }
        }
        
        function scrollToBottom() {
            const container = document.getElementById('chatMessages');
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 100);
        }
        
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                document.getElementById('messageCount').textContent = stats.messages || 0;
                document.getElementById('visualCount').textContent = stats.visualizations || 0;
                document.getElementById('functionCount').textContent = stats.functions_analyzed || 0;
                document.getElementById('conceptCount').textContent = stats.concepts_explained || 0;
                
                // Animation des compteurs
                animateCounters();
                
            } catch (error) {
                console.log('Erreur chargement stats:', error);
            }
        }
        
        function animateCounters() {
            document.querySelectorAll('.stat-item span[id$="Count"]').forEach(counter => {
                counter.style.transform = 'scale(1.1)';
                counter.style.color = 'var(--accent)';
                setTimeout(() => {
                    counter.style.transform = 'scale(1)';
                    counter.style.color = '';
                }, 300);
            });
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
            }, 4000);
        }
        
        // Raccourcis clavier
        document.addEventListener('keydown', function(e) {
            // Ctrl/Cmd + L pour nettoyer le chat
            if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
                e.preventDefault();
                if (confirm('Voulez-vous nettoyer la conversation ?')) {
                    const messagesContainer = document.getElementById('chatMessages');
                    const messages = messagesContainer.querySelectorAll('.message-user, .message-assistant:not(.help-message)');
                    messages.forEach(msg => {
                        if (!msg.querySelector('.help-message')) {
                            msg.remove();
                        }
                    });
                    focusChatInput();
                }
            }
            
            // Escape pour annuler si en cours de chargement
            if (e.key === 'Escape' && isLoading) {
                setLoading(false);
                focusChatInput();
            }
        });
        
        // Gestion de la visibilité de la page
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden) {
                loadStats();
            }
        });
        
        // Chargement initial des stats
        loadStats();
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("🎨 MATHIA VISUAL V3.0 - Assistant Mathématique Visuel")
    print("=" * 60)
    
    try:
        # Vérifications
        import sympy
        import matplotlib
        import numpy as np
        from mistralai import Mistral
        print("✅ Dépendances installées")
        
        matplotlib.use('Agg')
        print("✅ Backend matplotlib configuré")
        
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port: {port}")
        print(f"🔧 Debug: {debug_mode}")
        print(f"🔑 Clés Mistral: {len(mathia.api_keys)} configurées")
        print(f"🎨 Cache visuels: {len(mathia.visual_cache)} entrées")
        print(f"💬 Historique: {len(mathia.conversation_history)} conversations")
        
        print("\n🚀 Fonctionnalités:")
        print("   • Chat central avec IA Mistral")
        print("   • Génération automatique de graphiques")
        print("   • Détection intelligente des besoins visuels")
        print("   • Visualisations contextuelles (fonctions, stats, géométrie)")
        print("   • Interface moderne responsive")
        print("   • Exemples interactifs pour démarrer")
        
        print("\n🎯 Types de visualisations supportées:")
        print("   • Fonctions mathématiques (2D/3D)")
        print("   • Analyses statistiques")
        print("   • Concepts géométriques")
        print("   • Calcul différentiel et intégral")
        print("   • Comparaisons de données")
        
        print("\n🚀 Démarrage du serveur...")
        
    except ImportError as e:
        print(f"❌ ERREUR: {e}")
        exit(1)
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        threaded=True
    )
