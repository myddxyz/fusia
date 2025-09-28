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
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

app = Flask(__name__)

class MathiaCore:
    """Cœur optimisé de Mathia - Assistant Mathématique IA"""
    
    def __init__(self):
        # Configuration des clés API Mistral avec rotation intelligente
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        self.current_key_index = 0
        self.key_errors = {i: 0 for i in range(len(self.api_keys))}  # Tracking d'erreurs
        
        # Variables symboliques étendues
        self.x, self.y, self.z, self.t = symbols('x y z t')
        self.n, self.k, self.a, self.b, self.c = symbols('n k a b c', integer=False)
        self.alpha, self.beta, self.gamma = symbols('alpha beta gamma')
        
        # Cache pour optimiser les performances
        self.calculation_cache = {}
        self.graph_cache = {}
        
        # Statistiques étendues
        self.stats = {
            'calculations': 0,
            'graphs_generated': 0,
            'chat_messages': 0,
            'cache_hits': 0,
            'average_response_time': 0
        }
        
        # Configuration matplotlib optimisée
        plt.style.use('dark_background')
        plt.rcParams.update({
            'font.size': 12,
            'axes.linewidth': 1.5,
            'lines.linewidth': 2.5,
            'figure.facecolor': '#1a1a1a',
            'axes.facecolor': '#2a2a2a'
        })
        
        # Pool de threads pour les calculs parallèles
        self.executor = ThreadPoolExecutor(max_workers=3)
        
    def get_best_mistral_client(self):
        """Obtient le meilleur client Mistral disponible basé sur les erreurs passées"""
        # Trier les clés par nombre d'erreurs (moins d'erreurs = meilleure priorité)
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
        
        # Fallback sur la première clé si toutes échouent
        return Mistral(api_key=self.api_keys[0])
    
    def create_cache_key(self, expression, operation):
        """Crée une clé de cache unique pour une expression et opération"""
        return f"{operation}:{hash(str(expression))}"
    
    def parse_expression_advanced(self, expr_str):
        """Parser avancé avec gestion de syntaxes multiples"""
        try:
            expr_str = expr_str.strip()
            
            # Remplacements étendus et intelligents
            replacements = [
                # Puissances et fonctions courantes
                (r'\^', '**'),
                (r'ln\s*\(', 'log('),
                (r'lg\s*\(', 'log('),
                (r'log10\s*\(', 'log('),
                # Trigonométrie
                (r'arcsin\s*\(', 'asin('),
                (r'arccos\s*\(', 'acos('),
                (r'arctan\s*\(', 'atan('),
                (r'tg\s*\(', 'tan('),
                (r'ctg\s*\(', 'cot('),
                # Hyperboliques
                (r'sh\s*\(', 'sinh('),
                (r'ch\s*\(', 'cosh('),
                (r'th\s*\(', 'tanh('),
                # Constantes
                (r'\be\b', 'E'),
                (r'pi\b', 'pi'),
                (r'π', 'pi'),
                # Opérateurs
                (r'×', '*'),
                (r'÷', '/'),
                (r'√', 'sqrt'),
            ]
            
            import re
            for pattern, replacement in replacements:
                expr_str = re.sub(pattern, replacement, expr_str)
            
            # Gestion des multiplications implicites (2x -> 2*x)
            expr_str = re.sub(r'(\d)([a-zA-Z])', r'\1*\2', expr_str)
            expr_str = re.sub(r'([a-zA-Z])(\d)', r'\1*\2', expr_str)
            expr_str = re.sub(r'(\))(\()', r')*\2', expr_str)
            
            expr = sympify(expr_str, evaluate=False)
            return expr, None
            
        except Exception as e:
            return None, str(e)
    
    def solve_expression_optimized(self, expr_str, operation='solve'):
        """Résolution optimisée avec cache et calcul parallèle"""
        start_time = time.time()
        
        # Vérifier le cache
        cache_key = self.create_cache_key(expr_str, operation)
        if cache_key in self.calculation_cache:
            self.stats['cache_hits'] += 1
            return self.calculation_cache[cache_key]
        
        try:
            expr, error = self.parse_expression_advanced(expr_str)
            if error:
                return {'success': False, 'error': f'Erreur de syntaxe: {error}'}
            
            result_data = {
                'success': True,
                'original': expr_str,
                'parsed': str(expr),
                'latex': latex(expr),
                'results': {},
                'metadata': {
                    'variables': [str(var) for var in expr.free_symbols],
                    'complexity': len(str(expr)),
                    'operation': operation
                }
            }
            
            # Calculs selon l'opération avec optimisations
            if operation == 'solve' or '=' in expr_str:
                if '=' in expr_str:
                    left, right = expr_str.split('=', 1)
                    equation = Eq(sympify(left.strip()), sympify(right.strip()))
                    solutions = solve(equation, self.x)
                else:
                    solutions = solve(expr, self.x)
                
                # Formatage intelligent des solutions
                formatted_solutions = []
                for sol in solutions:
                    if sol.is_real:
                        if sol.is_rational:
                            formatted_solutions.append(f"{sol} ≈ {float(sol):.6g}")
                        else:
                            formatted_solutions.append(str(sol))
                    else:
                        formatted_solutions.append(f"{sol} (complexe)")
                
                result_data['results']['solutions'] = formatted_solutions
                result_data['results']['solution_count'] = len(solutions)
                
            elif operation == 'analyze':
                # Analyse complète de la fonction
                result_data['results'].update(self._analyze_function_complete(expr))
                
            elif operation in ['expand', 'factor', 'simplify', 'derivative', 'integral']:
                result_data['results'].update(self._perform_operation(expr, operation))
            
            # Génération de graphique en parallèle
            try:
                graph_future = self.executor.submit(self.generate_graph_optimized, expr)
                graph_data = graph_future.result(timeout=5)  # Timeout de 5 secondes
                if graph_data:
                    result_data['graph'] = graph_data
                    self.stats['graphs_generated'] += 1
            except Exception as e:
                print(f"Erreur génération graphique: {e}")
            
            # Mise à jour des stats
            end_time = time.time()
            response_time = end_time - start_time
            self.stats['calculations'] += 1
            self.stats['average_response_time'] = (
                (self.stats['average_response_time'] * (self.stats['calculations'] - 1) + response_time) 
                / self.stats['calculations']
            )
            
            # Mise en cache
            self.calculation_cache[cache_key] = result_data
            
            return result_data
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _analyze_function_complete(self, expr):
        """Analyse complète d'une fonction mathématique"""
        results = {}
        
        try:
            # Domaine et image
            variables = list(expr.free_symbols)
            if len(variables) == 1:
                var = variables[0]
                
                # Dérivées
                first_deriv = diff(expr, var)
                second_deriv = diff(first_deriv, var)
                results['first_derivative'] = str(first_deriv)
                results['second_derivative'] = str(second_deriv)
                
                # Points critiques
                critical_points = solve(first_deriv, var)
                results['critical_points'] = [str(cp) for cp in critical_points[:5]]  # Limite à 5
                
                # Points d'inflexion
                inflection_points = solve(second_deriv, var)
                results['inflection_points'] = [str(ip) for ip in inflection_points[:5]]
                
                # Limites importantes
                try:
                    limit_inf = limit(expr, var, oo)
                    limit_neg_inf = limit(expr, var, -oo)
                    results['limit_infinity'] = str(limit_inf)
                    results['limit_negative_infinity'] = str(limit_neg_inf)
                except:
                    pass
                
                # Asymptotes
                try:
                    # Asymptotes verticales (zéros du dénominateur)
                    if expr.is_rational_function():
                        denom = fraction(expr)[1]
                        vertical_asymptotes = solve(denom, var)
                        results['vertical_asymptotes'] = [str(va) for va in vertical_asymptotes[:3]]
                except:
                    pass
                
        except Exception as e:
            results['analysis_error'] = str(e)
        
        return results
    
    def _perform_operation(self, expr, operation):
        """Effectue une opération mathématique spécifique"""
        results = {}
        
        try:
            if operation == 'expand':
                expanded = expand(expr)
                results['expanded'] = str(expanded)
                results['latex_expanded'] = latex(expanded)
                
            elif operation == 'factor':
                factored = factor(expr)
                results['factored'] = str(factored)
                results['latex_factored'] = latex(factored)
                
            elif operation == 'simplify':
                simplified = simplify(expr)
                results['simplified'] = str(simplified)
                results['latex_simplified'] = latex(simplified)
                
            elif operation == 'derivative':
                var = list(expr.free_symbols)[0] if expr.free_symbols else self.x
                derivative = diff(expr, var)
                results['derivative'] = str(derivative)
                results['latex_derivative'] = latex(derivative)
                
            elif operation == 'integral':
                var = list(expr.free_symbols)[0] if expr.free_symbols else self.x
                try:
                    integral = integrate(expr, var)
                    results['integral'] = str(integral)
                    results['latex_integral'] = latex(integral)
                except:
                    results['integral'] = "Primitive non calculable symboliquement"
                    
        except Exception as e:
            results['operation_error'] = str(e)
        
        return results
    
    def generate_graph_optimized(self, expr):
        """Génération de graphiques optimisée avec cache"""
        try:
            graph_key = f"graph:{hash(str(expr))}"
            if graph_key in self.graph_cache:
                return self.graph_cache[graph_key]
            
            variables = expr.free_symbols
            
            if not variables or (len(variables) == 1 and self.x in variables):
                graph_data = self._create_2d_plot_advanced(expr)
            elif len(variables) == 2 and {self.x, self.y}.issubset(variables):
                graph_data = self._create_3d_plot_advanced(expr)
            else:
                return None
            
            if graph_data:
                self.graph_cache[graph_key] = graph_data
            
            return graph_data
            
        except Exception as e:
            print(f"Erreur génération graphique optimisée: {e}")
            return None
    
    def _create_2d_plot_advanced(self, expr):
        """Crée un graphique 2D avancé avec style moderne"""
        try:
            fig, ax = plt.subplots(figsize=(12, 8), facecolor='#1a1a1a')
            ax.set_facecolor('#2a2a2a')
            
            # Détermination intelligente de la plage
            x_vals = np.linspace(-10, 10, 2000)
            
            # Conversion en fonction numpy avec gestion d'erreurs
            f = lambdify(self.x, expr, ['numpy', 'scipy'], cse=True)
            
            try:
                y_vals = f(x_vals)
                # Nettoyage des valeurs
                mask = np.isfinite(y_vals)
                x_clean = x_vals[mask]
                y_clean = y_vals[mask]
                
                if len(x_clean) > 0:
                    # Graphique principal avec gradient
                    ax.plot(x_clean, y_clean, color='#00d4ff', linewidth=3, 
                           alpha=0.9, label=f'f(x) = {expr}')
                    
                    # Ajout d'un effet d'ombre
                    ax.plot(x_clean, y_clean, color='#0099cc', linewidth=5, 
                           alpha=0.3, zorder=1)
                    
            except Exception:
                # Calcul point par point si échec
                y_vals = []
                x_vals_clean = []
                for x_val in x_vals[::10]:  # Échantillonnage réduit
                    try:
                        y_val = complex(expr.subs(self.x, x_val))
                        if y_val.imag == 0 and np.isfinite(y_val.real):
                            y_vals.append(y_val.real)
                            x_vals_clean.append(x_val)
                    except:
                        continue
                
                if len(y_vals) > 0:
                    ax.plot(x_vals_clean, y_vals, color='#00d4ff', linewidth=3, 
                           alpha=0.9, label=f'f(x) = {expr}')
            
            # Styling avancé
            ax.grid(True, alpha=0.2, color='white', linestyle='-', linewidth=0.5)
            ax.axhline(y=0, color='#ffffff', linewidth=1, alpha=0.8)
            ax.axvline(x=0, color='#ffffff', linewidth=1, alpha=0.8)
            
            ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
            ax.set_ylabel('f(x)', fontsize=14, color='white', fontweight='bold')
            ax.set_title(f'Graphique de f(x) = {expr}', fontsize=16, 
                        color='#00d4ff', fontweight='bold', pad=20)
            
            # Légende stylée
            legend = ax.legend(loc='upper right', frameon=True, fancybox=True, 
                             shadow=True, framealpha=0.9)
            legend.get_frame().set_facecolor('#3a3a3a')
            legend.get_frame().set_edgecolor('#00d4ff')
            
            # Bordures et ticks
            ax.tick_params(colors='white', labelsize=12)
            for spine in ax.spines.values():
                spine.set_color('#555555')
                spine.set_linewidth(1.5)
            
            plt.tight_layout()
            
            # Export optimisé
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', 
                       facecolor='#1a1a1a', edgecolor='none', dpi=100,
                       optimize=True)
            buffer.seek(0)
            graph_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return {
                'type': '2D',
                'image': graph_base64,
                'expression': str(expr),
                'resolution': '2000 points',
                'style': 'advanced'
            }
            
        except Exception as e:
            print(f"Erreur plot 2D avancé: {e}")
            return None
    
    def _create_3d_plot_advanced(self, expr):
        """Crée un graphique 3D avancé"""
        try:
            fig = plt.figure(figsize=(14, 10), facecolor='#1a1a1a')
            ax = fig.add_subplot(111, projection='3d')
            ax.set_facecolor('#2a2a2a')
            
            # Grille haute résolution
            x_vals = np.linspace(-5, 5, 80)
            y_vals = np.linspace(-5, 5, 80)
            X, Y = np.meshgrid(x_vals, y_vals)
            
            # Conversion optimisée
            f = lambdify((self.x, self.y), expr, ['numpy'], cse=True)
            
            try:
                Z = f(X, Y)
                Z = np.where(np.isfinite(Z), Z, np.nan)
                
                # Surface avec colormap moderne
                surface = ax.plot_surface(X, Y, Z, cmap='plasma', alpha=0.8, 
                                        linewidth=0, antialiased=True, 
                                        shade=True)
                
                # Contours projetés
                contours = ax.contour(X, Y, Z, levels=15, colors='white', 
                                    alpha=0.4, linewidths=1)
                
                # Styling 3D
                ax.set_xlabel('x', fontsize=12, color='white')
                ax.set_ylabel('y', fontsize=12, color='white')
                ax.set_zlabel('f(x,y)', fontsize=12, color='white')
                ax.set_title(f'Surface: f(x,y) = {expr}', fontsize=14, 
                           color='#00d4ff', pad=20)
                
                # Colorbar stylée
                cbar = fig.colorbar(surface, ax=ax, shrink=0.6, aspect=20)
                cbar.ax.tick_params(colors='white')
                
                # Éclairage
                ax.view_init(elev=25, azim=45)
                
            except Exception as e:
                print(f"Erreur calcul surface 3D: {e}")
                return None
            
            # Export optimisé
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', 
                       facecolor='#1a1a1a', edgecolor='none', dpi=100)
            buffer.seek(0)
            graph_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return {
                'type': '3D',
                'image': graph_base64,
                'expression': str(expr),
                'resolution': '80x80 points',
                'style': 'advanced'
            }
            
        except Exception as e:
            print(f"Erreur plot 3D avancé: {e}")
            return None
    
    def chat_with_mistral_optimized(self, message, context=None):
        """Chat optimisé avec formatage intelligent"""
        try:
            client = self.get_best_mistral_client()
            
            system_prompt = """Tu es Mathia, un assistant mathématique expert et moderne.

Règles de formatage IMPORTANTES:
- N'utilise JAMAIS d'astérisques (*) pour la mise en forme
- Utilise un langage naturel et fluide
- Structure tes réponses avec des tirets (-) ou des numéros quand nécessaire
- Explique de manière claire et accessible
- Donne des exemples concrets
- Sois concis mais complet

Tes domaines d'expertise:
- Algèbre et analyse avancée
- Calcul différentiel et intégral
- Géométrie analytique et trigonométrie
- Statistiques et probabilités
- Mathématiques discrètes et théorie des nombres
- Optimisation et recherche opérationnelle

Approche pédagogique: explique étape par étape, donne l'intuition derrière les concepts."""
            
            messages = [{"role": "system", "content": system_prompt}]
            
            if context:
                context_msg = f"Contexte du calcul: {context}"
                messages.append({"role": "assistant", "content": context_msg})
            
            messages.append({"role": "user", "content": message})
            
            response = client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.2,  # Réduction pour plus de cohérence
                max_tokens=1200,
                top_p=0.9
            )
            
            # Post-traitement pour enlever les astérisques
            response_text = response.choices[0].message.content.strip()
            response_text = response_text.replace('**', '').replace('*', '')
            
            # Mise à jour des stats et du tracking des clés
            self.stats['chat_messages'] += 1
            if self.current_key_index in self.key_errors:
                self.key_errors[self.current_key_index] = max(0, self.key_errors[self.current_key_index] - 1)
            
            return {
                'success': True, 
                'response': response_text,
                'response_time': 'optimized'
            }
            
        except Exception as e:
            # Incrémenter les erreurs pour cette clé
            if self.current_key_index in self.key_errors:
                self.key_errors[self.current_key_index] += 1
            return {'success': False, 'error': str(e)}

# Instance globale optimisée
mathia = MathiaCore()

@app.route('/')
def index():
    """Interface Mathia repensée et optimisée"""
    return render_template_string(MATHIA_TEMPLATE)

@app.route('/api/calculate', methods=['POST'])
def calculate():
    """API de calcul optimisée"""
    try:
        data = request.get_json()
        expression = data.get('expression', '').strip()
        operation = data.get('operation', 'solve')
        
        if not expression:
            return jsonify({'success': False, 'error': 'Expression requise'})
        
        result = mathia.solve_expression_optimized(expression, operation)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/chat', methods=['POST'])
def chat():
    """API de chat optimisée"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        context = data.get('context')
        
        if not message:
            return jsonify({'success': False, 'error': 'Message requis'})
        
        result = mathia.chat_with_mistral_optimized(message, context)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def get_stats():
    """API des statistiques étendues"""
    return jsonify(mathia.stats)

@app.route('/health')
def health_check():
    """Health check optimisé"""
    return jsonify({'status': 'OK', 'service': 'Mathia', 'version': '2.0'}), 200

# Template HTML moderne et optimisé
MATHIA_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Assistant Mathématique Avancé</title>
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
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --bg-dark: #0a0a0f;
            --bg-card: rgba(20, 20, 30, 0.95);
            --bg-input: rgba(30, 30, 45, 0.8);
            --text-primary: #ffffff;
            --text-secondary: #b8bcc8;
            --text-accent: #00d4ff;
            --border-subtle: rgba(255, 255, 255, 0.1);
            --border-focus: rgba(0, 212, 255, 0.5);
            --shadow-card: 0 20px 40px rgba(0, 0, 0, 0.4);
            --shadow-button: 0 8px 20px rgba(102, 126, 234, 0.3);
            --success: #00ff88;
            --error: #ff4757;
            --warning: #ffa502;
        }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-dark);
            background-image: 
                radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(255, 119, 198, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 40% 40%, rgba(120, 219, 226, 0.1) 0%, transparent 50%);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
        }
        
        /* Header moderne */
        .header {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(10, 10, 15, 0.95);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border-subtle);
            padding: 1rem 0;
        }
        
        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 1.8rem;
            font-weight: 800;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .nav-tabs {
            display: flex;
            gap: 0.5rem;
            background: rgba(30, 30, 45, 0.6);
            padding: 0.5rem;
            border-radius: 20px;
            border: 1px solid var(--border-subtle);
        }
        
        .nav-tab {
            padding: 0.8rem 1.5rem;
            background: transparent;
            border: none;
            border-radius: 15px;
            color: var(--text-secondary);
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            white-space: nowrap;
        }
        
        .nav-tab.active {
            background: var(--primary-gradient);
            color: white;
            box-shadow: var(--shadow-button);
            transform: translateY(-2px);
        }
        
        .nav-tab:hover:not(.active) {
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-primary);
        }
        
        .stats-display {
            display: flex;
            gap: 2rem;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        
        .stat-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        /* Container principal */
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        /* Sections de contenu */
        .content-section {
            display: none;
            animation: fadeIn 0.4s ease;
        }
        
        .content-section.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Section calculateur */
        .calculator-section {
            background: var(--bg-card);
            border-radius: 25px;
            padding: 2.5rem;
            margin-bottom: 2rem;
            border: 1px solid var(--border-subtle);
            box-shadow: var(--shadow-card);
            backdrop-filter: blur(20px);
        }
        
        .input-container {
            position: relative;
            margin-bottom: 2rem;
        }
        
        .math-input {
            width: 100%;
            padding: 1.2rem 1.5rem;
            background: var(--bg-input);
            border: 2px solid var(--border-subtle);
            border-radius: 15px;
            color: var(--text-primary);
            font-size: 1.1rem;
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }
        
        .math-input:focus {
            outline: none;
            border-color: var(--border-focus);
            box-shadow: 0 0 0 4px rgba(0, 212, 255, 0.1);
            background: rgba(30, 30, 45, 0.9);
        }
        
        .math-input::placeholder {
            color: var(--text-secondary);
            opacity: 0.7;
        }
        
        .input-suggestions {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            margin-top: 0.5rem;
            max-height: 200px;
            overflow-y: auto;
            z-index: 10;
            display: none;
        }
        
        .suggestion-item {
            padding: 0.8rem 1rem;
            cursor: pointer;
            border-bottom: 1px solid var(--border-subtle);
            transition: background 0.2s ease;
        }
        
        .suggestion-item:hover {
            background: rgba(255, 255, 255, 0.1);
        }
        
        .operation-buttons {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        .operation-btn {
            padding: 1rem;
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.8), rgba(118, 75, 162, 0.8));
            border: 1px solid var(--border-focus);
            border-radius: 12px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
            position: relative;
            overflow: hidden;
        }
        
        .operation-btn:before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: left 0.5s ease;
        }
        
        .operation-btn:hover:before {
            left: 100%;
        }
        
        .operation-btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }
        
        .operation-btn:active {
            transform: translateY(-1px);
        }
        
        .operation-btn.loading {
            opacity: 0.7;
            cursor: not-allowed;
        }
        
        /* Résultats */
        .results-container {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 2rem;
            margin-bottom: 2rem;
            border: 1px solid var(--border-subtle);
            display: none;
            position: relative;
            overflow: hidden;
        }
        
        .results-container.show {
            display: block;
            animation: slideInUp 0.5s ease;
        }
        
        @keyframes slideInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-subtle);
        }
        
        .result-title {
            font-size: 1.4rem;
            font-weight: 700;
            color: var(--text-accent);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .result-meta {
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        
        .result-content {
            display: grid;
            gap: 1.5rem;
        }
        
        .result-item {
            background: rgba(255, 255, 255, 0.05);
            padding: 1.5rem;
            border-radius: 12px;
            border-left: 4px solid var(--text-accent);
        }
        
        .result-label {
            font-weight: 600;
            color: var(--text-accent);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }
        
        .result-value {
            font-size: 1.1rem;
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-primary);
            word-break: break-all;
        }
        
        .graph-container {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 2rem;
            text-align: center;
            border: 1px solid var(--border-subtle);
            margin-top: 2rem;
        }
        
        .graph-container img {
            max-width: 100%;
            height: auto;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }
        
        .graph-info {
            margin-top: 1rem;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        
        /* Section chat */
        .chat-container {
            background: var(--bg-card);
            border-radius: 25px;
            padding: 2rem;
            height: 600px;
            display: flex;
            flex-direction: column;
            border: 1px solid var(--border-subtle);
            box-shadow: var(--shadow-card);
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            margin-bottom: 1.5rem;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 15px;
            border: 1px solid var(--border-subtle);
        }
        
        .chat-message {
            margin-bottom: 1.5rem;
            padding: 1rem 1.5rem;
            border-radius: 18px;
            max-width: 85%;
            word-wrap: break-word;
            animation: messageSlide 0.3s ease;
        }
        
        @keyframes messageSlide {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .chat-message.user {
            background: var(--primary-gradient);
            color: white;
            margin-left: auto;
            border-bottom-right-radius: 8px;
        }
        
        .chat-message.assistant {
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-primary);
            border: 1px solid var(--border-subtle);
            border-bottom-left-radius: 8px;
        }
        
        .message-sender {
            font-weight: 600;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            opacity: 0.8;
        }
        
        .message-content {
            line-height: 1.6;
        }
        
        .chat-input-container {
            display: flex;
            gap: 1rem;
            align-items: flex-end;
        }
        
        .chat-input {
            flex: 1;
            padding: 1rem 1.5rem;
            background: var(--bg-input);
            border: 2px solid var(--border-subtle);
            border-radius: 15px;
            color: var(--text-primary);
            resize: vertical;
            min-height: 60px;
            max-height: 150px;
            transition: all 0.3s ease;
        }
        
        .chat-input:focus {
            outline: none;
            border-color: var(--border-focus);
            box-shadow: 0 0 0 4px rgba(0, 212, 255, 0.1);
        }
        
        .chat-send-btn {
            padding: 1rem 2rem;
            background: var(--primary-gradient);
            border: none;
            border-radius: 15px;
            color: white;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            white-space: nowrap;
        }
        
        .chat-send-btn:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-button);
        }
        
        .chat-send-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        /* Section théorèmes */
        .theorems-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 2rem;
            margin-top: 2rem;
        }
        
        .theorem-card {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 2rem;
            border: 1px solid var(--border-subtle);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .theorem-card:hover {
            transform: translateY(-5px);
            box-shadow: var(--shadow-card);
            border-color: var(--border-focus);
        }
        
        .theorem-category {
            display: inline-block;
            padding: 0.5rem 1rem;
            background: var(--primary-gradient);
            color: white;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 1rem;
        }
        
        .theorem-title {
            font-size: 1.3rem;
            font-weight: 700;
            color: var(--text-accent);
            margin-bottom: 1rem;
        }
        
        .theorem-content {
            color: var(--text-secondary);
            line-height: 1.7;
            font-size: 1rem;
        }
        
        .theorem-formula {
            background: rgba(0, 212, 255, 0.1);
            padding: 1rem;
            border-radius: 10px;
            margin: 1rem 0;
            border-left: 3px solid var(--text-accent);
            font-family: 'JetBrains Mono', monospace;
        }
        
        /* Utilitaires */
        .loading-spinner {
            width: 20px;
            height: 20px;
            border: 3px solid var(--border-subtle);
            border-top: 3px solid var(--text-accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 0.5rem;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .notification {
            position: fixed;
            top: 90px;
            right: 20px;
            padding: 1rem 1.5rem;
            border-radius: 15px;
            color: white;
            font-weight: 600;
            z-index: 1000;
            transform: translateX(400px);
            transition: all 0.4s ease;
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-subtle);
            max-width: 350px;
            box-shadow: var(--shadow-card);
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
            background: var(--primary-gradient);
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .header-content {
                flex-direction: column;
                gap: 1rem;
                padding: 0 1rem;
            }
            
            .nav-tabs {
                width: 100%;
                justify-content: center;
                overflow-x: auto;
            }
            
            .stats-display {
                justify-content: center;
                flex-wrap: wrap;
            }
            
            .container {
                padding: 1rem;
            }
            
            .calculator-section,
            .chat-container {
                padding: 1.5rem;
            }
            
            .operation-buttons {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .theorems-grid {
                grid-template-columns: 1fr;
            }
            
            .chat-container {
                height: 500px;
            }
            
            .notification {
                right: 10px;
                top: 80px;
                max-width: calc(100vw - 20px);
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div class="logo">🔢 Mathia</div>
            
            <div class="nav-tabs">
                <button class="nav-tab active" data-tab="calculator">
                    Calculateur
                </button>
                <button class="nav-tab" data-tab="chat">
                    Assistant IA
                </button>
                <button class="nav-tab" data-tab="theorems">
                    Théorèmes
                </button>
            </div>
            
            <div class="stats-display">
                <div class="stat-item">
                    <span>📊</span>
                    <span id="calcCount">0</span> calculs
                </div>
                <div class="stat-item">
                    <span>📈</span>
                    <span id="graphCount">0</span> graphiques
                </div>
                <div class="stat-item">
                    <span>💬</span>
                    <span id="chatCount">0</span> messages
                </div>
            </div>
        </div>
    </div>

    <div class="container">
        <!-- Section Calculateur -->
        <div id="calculator" class="content-section active">
            <div class="calculator-section">
                <h2 style="margin-bottom: 2rem; color: var(--text-accent); font-size: 1.8rem; font-weight: 700;">
                    Calculateur Mathématique Avancé
                </h2>
                
                <div class="input-container">
                    <input type="text" id="mathInput" class="math-input" 
                           placeholder="Entrez votre expression mathématique (ex: x^2 + 3*x + 2, sin(x), x^2 + y^2 = 25)"
                           autocomplete="off">
                    <div id="suggestions" class="input-suggestions"></div>
                </div>
                
                <div class="operation-buttons">
                    <button class="operation-btn" data-operation="solve">
                        🎯 Résoudre
                    </button>
                    <button class="operation-btn" data-operation="analyze">
                        📊 Analyser
                    </button>
                    <button class="operation-btn" data-operation="simplify">
                        ✨ Simplifier
                    </button>
                    <button class="operation-btn" data-operation="expand">
                        📐 Développer
                    </button>
                    <button class="operation-btn" data-operation="factor">
                        🧩 Factoriser
                    </button>
                    <button class="operation-btn" data-operation="derivative">
                        📈 Dériver
                    </button>
                    <button class="operation-btn" data-operation="integral">
                        ∫ Intégrer
                    </button>
                </div>
                
                <div id="resultsContainer" class="results-container">
                    <div class="result-header">
                        <div class="result-title" id="resultTitle">
                            Résultats
                        </div>
                        <div class="result-meta" id="resultMeta"></div>
                    </div>
                    <div id="resultContent" class="result-content"></div>
                </div>
                
                <div id="graphContainer" class="graph-container" style="display: none;">
                    <div id="graphContent"></div>
                    <div class="graph-info" id="graphInfo"></div>
                </div>
            </div>
        </div>

        <!-- Section Chat IA -->
        <div id="chat" class="content-section">
            <div class="chat-container">
                <h2 style="margin-bottom: 1.5rem; color: var(--text-accent); font-size: 1.8rem; font-weight: 700;">
                    Assistant IA Mathématique
                </h2>
                
                <div id="chatMessages" class="chat-messages">
                    <div class="chat-message assistant">
                        <div class="message-sender">Mathia</div>
                        <div class="message-content">
                            Bonjour ! Je suis votre assistant mathématique avancé. Je peux vous aider avec tous vos problèmes mathématiques, expliquer des concepts complexes et vous guider dans vos calculs. Posez-moi vos questions !
                        </div>
                    </div>
                </div>
                
                <div class="chat-input-container">
                    <textarea id="chatInput" class="chat-input" 
                              placeholder="Posez votre question mathématique..."
                              rows="2"></textarea>
                    <button id="chatSendBtn" class="chat-send-btn">
                        Envoyer
                    </button>
                </div>
            </div>
        </div>

        <!-- Section Théorèmes -->
        <div id="theorems" class="content-section">
            <h2 style="margin-bottom: 2rem; color: var(--text-accent); font-size: 1.8rem; font-weight: 700; text-align: center;">
                Bibliothèque de Théorèmes et Formules
            </h2>
            
            <div class="theorems-grid">
                <div class="theorem-card">
                    <div class="theorem-category">Algèbre</div>
                    <div class="theorem-title">Identités Remarquables</div>
                    <div class="theorem-content">
                        Les formules fondamentales pour le développement et la factorisation :
                        <div class="theorem-formula">
                            (a + b)² = a² + 2ab + b²<br>
                            (a - b)² = a² - 2ab + b²<br>
                            (a + b)(a - b) = a² - b²<br>
                            (a + b)³ = a³ + 3a²b + 3ab² + b³
                        </div>
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-category">Analyse</div>
                    <div class="theorem-title">Dérivées Classiques</div>
                    <div class="theorem-content">
                        Formules de dérivation essentielles :
                        <div class="theorem-formula">
                            (x^n)' = n·x^(n-1)<br>
                            (sin x)' = cos x<br>
                            (cos x)' = -sin x<br>
                            (e^x)' = e^x<br>
                            (ln x)' = 1/x<br>
                            (u·v)' = u'v + uv'
                        </div>
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-category">Géométrie</div>
                    <div class="theorem-title">Théorème de Pythagore</div>
                    <div class="theorem-content">
                        Dans un triangle rectangle, le carré de l'hypoténuse est égal à la somme des carrés des deux autres côtés :
                        <div class="theorem-formula">
                            c² = a² + b²
                        </div>
                        Où c est l'hypoténuse et a, b sont les côtés de l'angle droit.
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-category">Trigonométrie</div>
                    <div class="theorem-title">Relations Trigonométriques</div>
                    <div class="theorem-content">
                        Identités fondamentales du cercle trigonométrique :
                        <div class="theorem-formula">
                            sin²x + cos²x = 1<br>
                            tan x = sin x / cos x<br>
                            sin(2x) = 2sin x cos x<br>
                            cos(2x) = cos²x - sin²x<br>
                            sin(a ± b) = sin a cos b ± cos a sin b
                        </div>
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-category">Analyse</div>
                    <div class="theorem-title">Primitives Usuelles</div>
                    <div class="theorem-content">
                        Intégrales des fonctions classiques :
                        <div class="theorem-formula">
                            ∫ x^n dx = x^(n+1)/(n+1) + C<br>
                            ∫ 1/x dx = ln|x| + C<br>
                            ∫ e^x dx = e^x + C<br>
                            ∫ sin x dx = -cos x + C<br>
                            ∫ cos x dx = sin x + C
                        </div>
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-category">Algèbre</div>
                    <div class="theorem-title">Résolution du Second Degré</div>
                    <div class="theorem-content">
                        Pour l'équation ax² + bx + c = 0 :
                        <div class="theorem-formula">
                            Δ = b² - 4ac<br>
                            Si Δ > 0: x = (-b ± √Δ) / 2a<br>
                            Si Δ = 0: x = -b / 2a<br>
                            Si Δ < 0: pas de solution réelle
                        </div>
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-category">Analyse</div>
                    <div class="theorem-title">Limites Remarquables</div>
                    <div class="theorem-content">
                        Limites importantes à retenir :
                        <div class="theorem-formula">
                            lim(x→0) sin x/x = 1<br>
                            lim(x→∞) (1 + 1/x)^x = e<br>
                            lim(x→0) (1+x)^(1/x) = e<br>
                            lim(x→0) (e^x - 1)/x = 1<br>
                            lim(x→0) ln(1+x)/x = 1
                        </div>
                    </div>
                </div>
                
                <div class="theorem-card">
                    <div class="theorem-category">Probabilités</div>
                    <div class="theorem-title">Lois de Probabilité</div>
                    <div class="theorem-content">
                        Formules essentielles du calcul probabiliste :
                        <div class="theorem-formula">
                            P(A ∪ B) = P(A) + P(B) - P(A ∩ B)<br>
                            P(A|B) = P(A ∩ B) / P(B)<br>
                            P(A ∩ B) = P(A|B) × P(B)<br>
                            E(X) = Σ x·P(X=x) (espérance)<br>
                            Var(X) = E(X²) - [E(X)]²
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentCalculation = null;
        let chatHistory = [];
        
        // Suggestions d'expressions mathématiques
        const mathSuggestions = [
            'x^2 + 3*x + 2',
            'sin(x) + cos(x)',
            'e^x - 1',
            'ln(x) + sqrt(x)',
            'x^3 - 2*x^2 + x - 1',
            '(x + 1)^2 = 9',
            'x^2 + y^2 = 25',
            'tan(x) = 1',
            'derivative of x^2 + sin(x)',
            'integral of x*exp(x)'
        ];
        
        // Initialisation
        document.addEventListener('DOMContentLoaded', function() {
            setupEventListeners();
            loadStats();
            setupAutoSuggestions();
            focusInput();
        });
        
        function setupEventListeners() {
            // Navigation entre onglets
            document.querySelectorAll('.nav-tab').forEach(tab => {
                tab.addEventListener('click', function() {
                    switchTab(this.dataset.tab);
                });
            });
            
            // Boutons d'opération
            document.querySelectorAll('.operation-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    performCalculation(this.dataset.operation);
                });
            });
            
            // Input mathématique
            const mathInput = document.getElementById('mathInput');
            mathInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    performCalculation('solve');
                }
            });
            
            // Chat
            const chatInput = document.getElementById('chatInput');
            const chatSendBtn = document.getElementById('chatSendBtn');
            
            chatInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendChatMessage();
                }
            });
            
            chatSendBtn.addEventListener('click', sendChatMessage);
        }
        
        function setupAutoSuggestions() {
            const input = document.getElementById('mathInput');
            const suggestionsDiv = document.getElementById('suggestions');
            
            input.addEventListener('input', function() {
                const value = this.value.toLowerCase();
                if (value.length < 2) {
                    suggestionsDiv.style.display = 'none';
                    return;
                }
                
                const matches = mathSuggestions.filter(suggestion => 
                    suggestion.toLowerCase().includes(value)
                ).slice(0, 5);
                
                if (matches.length > 0) {
                    suggestionsDiv.innerHTML = matches.map(match => 
                        `<div class="suggestion-item" onclick="selectSuggestion('${match}')">${match}</div>`
                    ).join('');
                    suggestionsDiv.style.display = 'block';
                } else {
                    suggestionsDiv.style.display = 'none';
                }
            });
            
            // Masquer les suggestions si clic ailleurs
            document.addEventListener('click', function(e) {
                if (!input.contains(e.target) && !suggestionsDiv.contains(e.target)) {
                    suggestionsDiv.style.display = 'none';
                }
            });
        }
        
        function selectSuggestion(suggestion) {
            document.getElementById('mathInput').value = suggestion;
            document.getElementById('suggestions').style.display = 'none';
            focusInput();
        }
        
        function switchTab(tabName) {
            // Mise à jour des onglets
            document.querySelectorAll('.nav-tab').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
            
            // Mise à jour du contenu
            document.querySelectorAll('.content-section').forEach(section => {
                section.classList.remove('active');
            });
            document.getElementById(tabName).classList.add('active');
            
            // Focus sur l'input approprié
            if (tabName === 'calculator') {
                setTimeout(() => focusInput(), 100);
            } else if (tabName === 'chat') {
                setTimeout(() => document.getElementById('chatInput').focus(), 100);
            }
        }
        
        function focusInput() {
            document.getElementById('mathInput').focus();
        }
        
        async function performCalculation(operation) {
            const input = document.getElementById('mathInput').value.trim();
            if (!input) {
                showNotification('Veuillez entrer une expression mathématique', 'error');
                focusInput();
                return;
            }
            
            // UI Loading
            setCalculationLoading(true, operation);
            hideResults();
            
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
                    showNotification('Calcul terminé avec succès !', 'success');
                } else {
                    showNotification(data.error, 'error');
                }
                
                await loadStats();
                
            } catch (error) {
                showNotification('Erreur de connexion: ' + error.message, 'error');
                console.error('Erreur calcul:', error);
            } finally {
                setCalculationLoading(false);
            }
        }
        
        function setCalculationLoading(loading, operation = '') {
            const buttons = document.querySelectorAll('.operation-btn');
            buttons.forEach(btn => {
                if (loading) {
                    btn.classList.add('loading');
                    btn.disabled = true;
                    if (btn.dataset.operation === operation) {
                        btn.innerHTML = '<div class="loading-spinner"></div>' + btn.textContent;
                    }
                } else {
                    btn.classList.remove('loading');
                    btn.disabled = false;
                    btn.innerHTML = btn.innerHTML.replace('<div class="loading-spinner"></div>', '');
                }
            });
        }
        
        function displayResults(data, operation) {
            const container = document.getElementById('resultsContainer');
            const title = document.getElementById('resultTitle');
            const meta = document.getElementById('resultMeta');
            const content = document.getElementById('resultContent');
            const graphContainer = document.getElementById('graphContainer');
            const graphContent = document.getElementById('graphContent');
            const graphInfo = document.getElementById('graphInfo');
            
            // Titre et métadonnées
            const operationTitles = {
                'solve': '🎯 Solutions',
                'analyze': '📊 Analyse Complète',
                'simplify': '✨ Forme Simplifiée',
                'expand': '📐 Forme Développée',
                'factor': '🧩 Forme Factorisée',
                'derivative': '📈 Dérivée',
                'integral': '∫ Primitive'
            };
            
            title.textContent = operationTitles[operation] || '🔍 Résultats';
            
            if (data.metadata) {
                const vars = data.metadata.variables.length > 0 ? 
                    data.metadata.variables.join(', ') : 'aucune';
                meta.textContent = `Variables: ${vars} • Complexité: ${data.metadata.complexity}`;
            }
            
            // Contenu des résultats
            let html = `
                <div class="result-item">
                    <div class="result-label">Expression originale</div>
                    <div class="result-value">${data.original}</div>
                </div>
                <div class="result-item">
                    <div class="result-label">Forme parsée</div>
                    <div class="result-value">${data.parsed}</div>
                </div>
            `;
            
            const results = data.results;
            
            // Affichage conditionnel selon les résultats
            if (results.solutions) {
                const solutionText = results.solutions.length > 0 ? 
                    results.solutions.join('<br>') : 
                    'Aucune solution réelle trouvée';
                html += `
                    <div class="result-item">
                        <div class="result-label">Solutions (${results.solution_count || results.solutions.length})</div>
                        <div class="result-value">${solutionText}</div>
                    </div>
                `;
            }
            
            if (results.expanded) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Forme développée</div>
                        <div class="result-value">${results.expanded}</div>
                    </div>
                `;
            }
            
            if (results.factored) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Forme factorisée</div>
                        <div class="result-value">${results.factored}</div>
                    </div>
                `;
            }
            
            if (results.simplified) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Forme simplifiée</div>
                        <div class="result-value">${results.simplified}</div>
                    </div>
                `;
            }
            
            if (results.derivative) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Dérivée</div>
                        <div class="result-value">${results.derivative}</div>
                    </div>
                `;
            }
            
            if (results.integral) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Primitive</div>
                        <div class="result-value">${results.integral}</div>
                    </div>
                `;
            }
            
            // Résultats d'analyse complète
            if (results.first_derivative) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Dérivée première</div>
                        <div class="result-value">${results.first_derivative}</div>
                    </div>
                `;
            }
            
            if (results.second_derivative) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Dérivée seconde</div>
                        <div class="result-value">${results.second_derivative}</div>
                    </div>
                `;
            }
            
            if (results.critical_points && results.critical_points.length > 0) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Points critiques</div>
                        <div class="result-value">${results.critical_points.join(', ')}</div>
                    </div>
                `;
            }
            
            if (results.limit_infinity) {
                html += `
                    <div class="result-item">
                        <div class="result-label">Limite en +∞</div>
                        <div class="result-value">${results.limit_infinity}</div>
                    </div>
                `;
            }
            
            content.innerHTML = html;
            container.classList.add('show');
            
            // Affichage du graphique
            if (data.graph) {
                graphContent.innerHTML = `
                    <h3 style="color: var(--text-accent); margin-bottom: 1rem;">
                        📊 Représentation Graphique
                    </h3>
                    <img src="data:image/png;base64,${data.graph.image}" alt="Graphique de la fonction">
                `;
                
                graphInfo.innerHTML = `
                    Type: ${data.graph.type} • 
                    Résolution: ${data.graph.resolution} • 
                    Style: ${data.graph.style}
                `;
                
                graphContainer.style.display = 'block';
            } else {
                graphContainer.style.display = 'none';
            }
            
            // Scroll vers les résultats
            setTimeout(() => {
                container.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);
        }
        
        function hideResults() {
            document.getElementById('resultsContainer').classList.remove('show');
            document.getElementById('graphContainer').style.display = 'none';
        }
        
        async function sendChatMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            const sendBtn = document.getElementById('chatSendBtn');
            const messagesContainer = document.getElementById('chatMessages');
            
            // Ajouter le message utilisateur
            addChatMessage('user', 'Vous', message);
            input.value = '';
            
            // UI loading
            sendBtn.disabled = true;
            sendBtn.innerHTML = '<div class="loading-spinner"></div>Réflexion...';
            
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
                    addChatMessage('assistant', 'Mathia', data.response);
                    chatHistory.push({ user: message, assistant: data.response });
                    showNotification('Réponse reçue !', 'success');
                } else {
                    addChatMessage('assistant', 'Mathia', 'Désolé, une erreur est survenue: ' + data.error);
                }
                
                await loadStats();
                
            } catch (error) {
                addChatMessage('assistant', 'Mathia', 'Erreur de connexion. Veuillez réessayer.');
                showNotification('Erreur de connexion', 'error');
            } finally {
                sendBtn.disabled = false;
                sendBtn.innerHTML = 'Envoyer';
                input.focus();
            }
        }
        
        function addChatMessage(type, sender, message) {
            const container = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${type}`;
            
            messageDiv.innerHTML = `
                <div class="message-sender">${sender}</div>
                <div class="message-content">${message}</div>
            `;
            
            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
        }
        
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                document.getElementById('calcCount').textContent = stats.calculations || 0;
                document.getElementById('graphCount').textContent = stats.graphs_generated || 0;
                document.getElementById('chatCount').textContent = stats.chat_messages || 0;
                
                // Animation des compteurs
                animateCounters();
                
            } catch (error) {
                console.log('Erreur chargement stats:', error);
            }
        }
        
        function animateCounters() {
            document.querySelectorAll('#calcCount, #graphCount, #chatCount').forEach(counter => {
                counter.style.transform = 'scale(1.1)';
                counter.style.color = 'var(--text-accent)';
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
            // Ctrl/Cmd + Enter pour calculer
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                if (document.getElementById('calculator').classList.contains('active')) {
                    performCalculation('solve');
                }
            }
            
            // Échap pour nettoyer les résultats
            if (e.key === 'Escape') {
                hideResults();
                document.getElementById('suggestions').style.display = 'none';
            }
            
            // Raccourcis pour les onglets (Ctrl/Cmd + 1, 2, 3)
            if ((e.ctrlKey || e.metaKey) && ['1', '2', '3'].includes(e.key)) {
                const tabs = ['calculator', 'chat', 'theorems'];
                const tabIndex = parseInt(e.key) - 1;
                if (tabs[tabIndex]) {
                    switchTab(tabs[tabIndex]);
                }
                e.preventDefault();
            }
        });
        
        // Gestion de la visibilité de la page (performance)
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                // Page cachée - économiser les ressources
                return;
            } else {
                // Page visible - mettre à jour les stats
                loadStats();
            }
        });
        
        // Auto-resize pour le textarea du chat
        document.getElementById('chatInput').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 150) + 'px';
        });
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("🔢 MATHIA V2.0 - Assistant Mathématique IA Avancé")
    print("=" * 60)
    
    try:
        # Vérification des dépendances critiques
        import sympy
        import matplotlib
        import numpy as np
        from mistralai import Mistral
        print("✅ Toutes les dépendances critiques sont installées")
        
        # Test de l'environnement matplotlib
        matplotlib.use('Agg')
        print("✅ Backend matplotlib configuré")
        
        # Configuration pour le déploiement
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port d'écoute: {port}")
        print(f"🔧 Mode debug: {debug_mode}")
        print(f"🔑 Clés API Mistral: {len(mathia.api_keys)} configurées")
        print(f"🧮 Cache: {len(mathia.calculation_cache)} entrées")
        print(f"📊 Graphiques en cache: {len(mathia.graph_cache)} entrées")
        print(f"⚡ Pool de threads: {mathia.executor._max_workers} workers")
        
        print("\n🎯 Fonctionnalités activées:")
        print("   • Calcul symbolique avancé avec cache")
        print("   • Génération de graphiques 2D/3D optimisée")
        print("   • Assistant IA avec rotation de clés")
        print("   • Interface moderne et responsive")
        print("   • Bibliothèque de théorèmes étendue")
        
        print("\n🚀 Démarrage du serveur...")
        
    except ImportError as e:
        print(f"❌ ERREUR: Dépendance manquante - {e}")
        print("\n💡 Installation requise:")
        print("   pip install flask sympy matplotlib numpy mistralai")
        exit(1)
    except Exception as e:
        print(f"⚠️ Avertissement: {e}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_mode,
        threaded=True
    )
