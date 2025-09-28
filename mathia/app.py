from flask import Flask, request, jsonify, render_template_string
import os
import json
import base64
import io
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sympy as sp
from sympy import *
from mistralai import Mistral
import time
import re
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import traceback
import random

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration matplotlib avec style moderne
plt.style.use('dark_background')
plt.rcParams.update({
    'font.size': 12,
    'axes.linewidth': 2,
    'lines.linewidth': 3,
    'figure.facecolor': '#0f0f23',
    'axes.facecolor': '#1a1a3a',
    'text.color': 'white',
    'axes.labelcolor': 'white',
    'xtick.color': 'white',
    'ytick.color': 'white'
})

@dataclass
class UserProfile:
    """Profil utilisateur avec gamification"""
    level: int = 1
    xp: int = 0
    badges: List[str] = None
    problems_solved: int = 0
    streak: int = 0
    favorite_topics: List[str] = None
    
    def __post_init__(self):
        if self.badges is None:
            self.badges = []
        if self.favorite_topics is None:
            self.favorite_topics = []

@dataclass
class Problem:
    """Structure pour un problème mathématique"""
    id: str
    title: str
    description: str
    category: str
    difficulty: int  # 1-5
    solution_steps: List[str]
    answer: str
    hints: List[str]
    xp_reward: int

@dataclass
class GameElement:
    """Éléments de gamification"""
    name: str
    description: str
    icon: str
    condition: str
    reward_xp: int = 0

class MathiaCore:
    """Cœur de Mathia - Assistant mathématique gamifié"""
    
    def __init__(self):
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        self.current_key = 0
        self.user_profile = UserProfile()
        self.conversation_history = []
        self.problem_bank = self._initialize_problems()
        self.badges = self._initialize_badges()
        self.stats = {
            'problems_solved': 0,
            'graphs_generated': 0,
            'total_interactions': 0,
            'favorite_topic': 'algebra'
        }
        
        logger.info("Mathia Core initialized with gamification")
    
    def get_mistral_client(self):
        """Obtient un client Mistral fonctionnel"""
        for i in range(len(self.api_keys)):
            try:
                key_index = (self.current_key + i) % len(self.api_keys)
                client = Mistral(api_key=self.api_keys[key_index])
                self.current_key = key_index
                return client
            except Exception as e:
                logger.warning(f"Key {key_index} failed: {e}")
                continue
        
        return Mistral(api_key=self.api_keys[0])
    
    def _initialize_problems(self):
        """Initialise une banque de problèmes"""
        return [
            Problem(
                id="eq_linear_01",
                title="Équation linéaire",
                description="Résolvez: 3x + 7 = 22",
                category="algebra",
                difficulty=1,
                solution_steps=[
                    "3x + 7 = 22",
                    "3x = 22 - 7",
                    "3x = 15",
                    "x = 15/3 = 5"
                ],
                answer="x = 5",
                hints=["Isolez d'abord le terme en x", "Soustrayez 7 des deux côtés"],
                xp_reward=10
            ),
            Problem(
                id="func_quad_01",
                title="Fonction quadratique",
                description="Analysez f(x) = x² - 4x + 3",
                category="functions",
                difficulty=3,
                solution_steps=[
                    "f(x) = x² - 4x + 3",
                    "Forme canonique: f(x) = (x-2)² - 1",
                    "Sommet: (2, -1)",
                    "Racines: x = 1 et x = 3"
                ],
                answer="Sommet: (2,-1), Racines: 1 et 3",
                hints=["Complétez le carré", "Utilisez la formule quadratique"],
                xp_reward=30
            ),
            Problem(
                id="deriv_01",
                title="Dérivée simple",
                description="Calculez la dérivée de f(x) = x³ + 2x² - 5x + 1",
                category="calculus",
                difficulty=2,
                solution_steps=[
                    "f(x) = x³ + 2x² - 5x + 1",
                    "f'(x) = d/dx(x³) + d/dx(2x²) + d/dx(-5x) + d/dx(1)",
                    "f'(x) = 3x² + 4x - 5 + 0",
                    "f'(x) = 3x² + 4x - 5"
                ],
                answer="f'(x) = 3x² + 4x - 5",
                hints=["Utilisez la règle de puissance", "La dérivée d'une constante est 0"],
                xp_reward=20
            )
        ]
    
    def _initialize_badges(self):
        """Initialise le système de badges"""
        return [
            GameElement("Premier Pas", "Résoudre votre premier problème", "🎯", "problems_solved >= 1", 5),
            GameElement("Résolveur", "Résoudre 10 problèmes", "⚡", "problems_solved >= 10", 25),
            GameElement("Expert", "Résoudre 50 problèmes", "🏆", "problems_solved >= 50", 100),
            GameElement("Visualisateur", "Générer votre premier graphique", "📊", "graphs_generated >= 1", 10),
            GameElement("Série", "Résoudre 5 problèmes d'affilée", "🔥", "streak >= 5", 20),
            GameElement("Polyvalent", "Explorer 3 catégories différentes", "🎨", "len(favorite_topics) >= 3", 30)
        ]
    
    def process_mathematical_query(self, query: str, show_steps: bool = True) -> Dict:
        """Traite une requête mathématique avec IA et visualisation"""
        start_time = time.time()
        
        try:
            # Analyser la requête avec Mistral
            ai_response = self._get_ai_analysis(query)
            
            # Extraire les expressions mathématiques
            expressions = self._extract_math_expressions(ai_response)
            
            # Générer une visualisation si pertinente
            graph_data = None
            if self._needs_visualization(query, expressions):
                graph_data = self._generate_graph(expressions, query)
                if graph_data:
                    self.stats['graphs_generated'] += 1
                    self._check_badge_progress()
            
            # Résoudre étape par étape si demandé
            steps = []
            if show_steps and expressions:
                steps = self._solve_step_by_step(expressions[0])
            
            # Mise à jour des statistiques
            self.stats['total_interactions'] += 1
            processing_time = time.time() - start_time
            
            return {
                'success': True,
                'response': ai_response,
                'expressions': expressions,
                'solution_steps': steps,
                'graph': graph_data,
                'processing_time': processing_time,
                'user_level': self.user_profile.level,
                'user_xp': self.user_profile.xp,
                'new_badges': self._check_badge_progress()
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': 'Désolé, une erreur est survenue. Pouvez-vous reformuler votre question ?'
            }
    
    def _get_ai_analysis(self, query: str) -> str:
        """Obtient une analyse IA de la requête"""
        try:
            client = self.get_mistral_client()
            
            system_prompt = """Tu es Mathia, un assistant mathématique expert et bienveillant. 

RÈGLES IMPORTANTES:
- Explications claires et pédagogiques
- Détecte si une visualisation serait utile
- Structure tes réponses de façon logique
- Adapte ton niveau à la difficulté de la question
- Encourage l'apprentissage

Format de réponse souhaité:
1. Explication du concept
2. Résolution détaillée si applicable
3. Applications pratiques ou exemples
4. Suggestions pour approfondir

N'utilise pas d'astérisques pour la mise en forme."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
            
            response = client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.3,
                max_tokens=1500
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return f"Je peux vous aider avec cette question mathématique: {query}"
    
    def _extract_math_expressions(self, text: str) -> List[str]:
        """Extrait les expressions mathématiques du texte"""
        expressions = []
        
        # Patterns pour détecter les expressions mathématiques
        patterns = [
            r'f\([x-z]\)\s*=\s*([^.,\n]+)',  # f(x) = ...
            r'([x-z][\^²³⁴⁵]*[\+\-\*/][^.,\n]+)',  # expressions algébriques
            r'(sin\([^)]+\)|cos\([^)]+\)|tan\([^)]+\))',  # fonctions trigonométriques
            r'(e\^[^,\n]+|exp\([^)]+\))',  # exponentielles
            r'(ln\([^)]+\)|log\([^)]+\))',  # logarithmes
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            expressions.extend([match for match in matches if len(match.strip()) > 2])
        
        # Nettoyer et valider les expressions
        clean_expressions = []
        for expr in expressions[:3]:  # Maximum 3 expressions
            try:
                cleaned = self._clean_expression(expr)
                # Test avec sympy
                sympify(cleaned, evaluate=False)
                clean_expressions.append(cleaned)
            except:
                continue
        
        return clean_expressions
    
    def _clean_expression(self, expr: str) -> str:
        """Nettoie une expression mathématique"""
        expr = expr.strip()
        
        replacements = [
            (r'\^', '**'),
            (r'ln\s*\(', 'log('),
            (r'\be\b', 'E'),
            (r'pi\b', 'pi'),
            (r'²', '**2'),
            (r'³', '**3'),
            (r'⁴', '**4'),
            (r'⁵', '**5')
        ]
        
        for pattern, replacement in replacements:
            expr = re.sub(pattern, replacement, expr)
        
        return expr
    
    def _needs_visualization(self, query: str, expressions: List[str]) -> bool:
        """Détermine si une visualisation est nécessaire"""
        visual_keywords = [
            'graphique', 'courbe', 'trace', 'plot', 'visualise',
            'fonction', 'parabole', 'droite', 'surface',
            'compare', 'évolution', 'analyse'
        ]
        
        query_lower = query.lower()
        has_visual_keyword = any(keyword in query_lower for keyword in visual_keywords)
        has_expressions = len(expressions) > 0
        
        return has_visual_keyword or has_expressions
    
    def _generate_graph(self, expressions: List[str], context: str = "") -> Optional[str]:
        """Génère un graphique basé sur les expressions"""
        if not expressions:
            return None
            
        try:
            fig, ax = plt.subplots(figsize=(12, 8), facecolor='#0f0f23')
            ax.set_facecolor('#1a1a3a')
            
            x = symbols('x')
            x_vals = np.linspace(-10, 10, 1000)
            colors = ['#00d4ff', '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4']
            
            plotted = False
            for i, expr_str in enumerate(expressions[:3]):
                try:
                    expr = sympify(expr_str)
                    f = lambdify(x, expr, 'numpy')
                    
                    y_vals = f(x_vals)
                    
                    # Filtrer les valeurs infinies ou NaN
                    mask = np.isfinite(y_vals)
                    if not np.any(mask):
                        continue
                    
                    x_clean = x_vals[mask]
                    y_clean = y_vals[mask]
                    
                    color = colors[i % len(colors)]
                    
                    # Plot principal avec effet lumineux
                    ax.plot(x_clean, y_clean, color=color, linewidth=4, 
                           label=f'f(x) = {expr}', alpha=0.9, zorder=2)
                    
                    # Effet d'ombre
                    ax.plot(x_clean, y_clean, color=color, linewidth=8, 
                           alpha=0.3, zorder=1)
                    
                    # Points remarquables
                    try:
                        derivative = diff(expr, x)
                        critical_points = solve(derivative, x)
                        
                        for cp in critical_points[:2]:
                            if cp.is_real:
                                cp_val = float(cp.evalf())
                                if -10 <= cp_val <= 10:
                                    y_cp = float(expr.subs(x, cp).evalf())
                                    if abs(y_cp) < 100:  # Éviter les valeurs trop grandes
                                        ax.plot(cp_val, y_cp, 'o', color=color, 
                                               markersize=10, markeredgewidth=3, 
                                               markeredgecolor='white', zorder=3)
                    except:
                        pass
                    
                    plotted = True
                    
                except Exception as e:
                    logger.warning(f"Failed to plot {expr_str}: {e}")
                    continue
            
            if not plotted:
                # Graphique par défaut
                y_default = np.sin(x_vals) * np.exp(-x_vals**2/50)
                ax.plot(x_vals, y_default, color='#00d4ff', linewidth=4, 
                       label='Exemple: f(x)', alpha=0.9)
                plotted = True
            
            # Styling moderne
            ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
            ax.axhline(y=0, color='#ffffff', linewidth=2, alpha=0.8)
            ax.axvline(x=0, color='#ffffff', linewidth=2, alpha=0.8)
            
            ax.set_xlabel('x', fontsize=16, color='white', fontweight='bold')
            ax.set_ylabel('f(x)', fontsize=16, color='white', fontweight='bold')
            ax.set_title('Mathia - Analyse Graphique', fontsize=18, 
                        color='#00d4ff', fontweight='bold', pad=20)
            
            # Légende moderne
            if plotted:
                legend = ax.legend(loc='best', frameon=True, fancybox=True, shadow=True)
                legend.get_frame().set_facecolor('#2a2a4a')
                legend.get_frame().set_edgecolor('#00d4ff')
                legend.get_frame().set_alpha(0.9)
                for text in legend.get_texts():
                    text.set_color('white')
            
            # Bordures
            for spine in ax.spines.values():
                spine.set_color('#555577')
                spine.set_linewidth(2)
            
            ax.tick_params(colors='white', labelsize=12)
            
            plt.tight_layout()
            
            # Sauvegarde en base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', 
                       facecolor='#0f0f23', edgecolor='none', dpi=100)
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logger.error(f"Graph generation error: {e}")
            return None
    
    def _solve_step_by_step(self, expression: str) -> List[str]:
        """Résout une expression étape par étape"""
        try:
            x = symbols('x')
            expr = sympify(expression)
            
            steps = []
            steps.append(f"Expression initiale: {expr}")
            
            # Si c'est une équation (contient =), la résoudre
            if '=' in expression:
                sides = expression.split('=')
                if len(sides) == 2:
                    left = sympify(sides[0].strip())
                    right = sympify(sides[1].strip())
                    equation = Eq(left, right)
                    
                    steps.append(f"Équation: {equation}")
                    
                    solutions = solve(equation, x)
                    if solutions:
                        steps.append(f"Solution(s): {solutions}")
                    else:
                        steps.append("Pas de solution réelle trouvée")
            
            # Analyse de fonction
            else:
                # Dérivée
                try:
                    derivative = diff(expr, x)
                    steps.append(f"Dérivée: f'(x) = {derivative}")
                    
                    # Points critiques
                    critical_points = solve(derivative, x)
                    if critical_points:
                        steps.append(f"Points critiques: {critical_points}")
                except:
                    pass
                
                # Limites
                try:
                    limit_inf = limit(expr, x, oo)
                    limit_neg_inf = limit(expr, x, -oo)
                    if limit_inf != oo and limit_inf != -oo:
                        steps.append(f"Limite en +∞: {limit_inf}")
                    if limit_neg_inf != oo and limit_neg_inf != -oo:
                        steps.append(f"Limite en -∞: {limit_neg_inf}")
                except:
                    pass
            
            return steps[:5]  # Maximum 5 étapes
            
        except Exception as e:
            logger.error(f"Step-by-step error: {e}")
            return [f"Analyse de: {expression}"]
    
    def get_practice_problem(self, category: str = None, difficulty: int = None) -> Dict:
        """Obtient un problème d'entraînement"""
        available_problems = self.problem_bank
        
        if category:
            available_problems = [p for p in available_problems if p.category == category]
        
        if difficulty:
            available_problems = [p for p in available_problems if p.difficulty == difficulty]
        
        if not available_problems:
            available_problems = self.problem_bank
        
        problem = random.choice(available_problems)
        
        return {
            'id': problem.id,
            'title': problem.title,
            'description': problem.description,
            'category': problem.category,
            'difficulty': problem.difficulty,
            'hints': problem.hints,
            'xp_reward': problem.xp_reward
        }
    
    def submit_solution(self, problem_id: str, user_answer: str) -> Dict:
        """Vérifie une solution soumise"""
        problem = next((p for p in self.problem_bank if p.id == problem_id), None)
        
        if not problem:
            return {'success': False, 'message': 'Problème non trouvé'}
        
        # Comparaison simple (peut être améliorée)
        is_correct = self._compare_answers(problem.answer, user_answer)
        
        result = {
            'correct': is_correct,
            'expected_answer': problem.answer,
            'solution_steps': problem.solution_steps,
            'xp_earned': 0,
            'level_up': False,
            'new_badges': []
        }
        
        if is_correct:
            # Récompenses
            self.user_profile.xp += problem.xp_reward
            self.user_profile.problems_solved += 1
            self.user_profile.streak += 1
            result['xp_earned'] = problem.xp_reward
            
            # Vérifier level up
            new_level = self._calculate_level(self.user_profile.xp)
            if new_level > self.user_profile.level:
                self.user_profile.level = new_level
                result['level_up'] = True
            
            # Vérifier nouveaux badges
            result['new_badges'] = self._check_badge_progress()
            
            self.stats['problems_solved'] += 1
        else:
            self.user_profile.streak = 0
        
        return result
    
    def _compare_answers(self, expected: str, user_answer: str) -> bool:
        """Compare deux réponses mathématiques"""
        try:
            # Nettoyer les réponses
            expected_clean = expected.replace(' ', '').lower()
            user_clean = user_answer.replace(' ', '').lower()
            
            # Comparaison directe
            if expected_clean == user_clean:
                return True
            
            # Comparaison symbolique si possible
            try:
                expected_expr = sympify(expected)
                user_expr = sympify(user_answer)
                return simplify(expected_expr - user_expr) == 0
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"Answer comparison error: {e}")
            return False
    
    def _calculate_level(self, xp: int) -> int:
        """Calcule le niveau basé sur l'XP"""
        # Progression: 100 XP pour niveau 2, puis +50 XP par niveau
        if xp < 100:
            return 1
        return 2 + (xp - 100) // 50
    
    def _check_badge_progress(self) -> List[str]:
        """Vérifie et attribue de nouveaux badges"""
        new_badges = []
        
        for badge in self.badges:
            if badge.name not in self.user_profile.badges:
                # Évaluer la condition
                try:
                    condition_met = eval(badge.condition.replace('problems_solved', str(self.user_profile.problems_solved))
                                       .replace('graphs_generated', str(self.stats['graphs_generated']))
                                       .replace('streak', str(self.user_profile.streak))
                                       .replace('len(favorite_topics)', str(len(self.user_profile.favorite_topics))))
                    
                    if condition_met:
                        self.user_profile.badges.append(badge.name)
                        self.user_profile.xp += badge.reward_xp
                        new_badges.append({
                            'name': badge.name,
                            'description': badge.description,
                            'icon': badge.icon,
                            'xp_bonus': badge.reward_xp
                        })
                except:
                    pass
        
        return new_badges

# Instance globale
mathia = MathiaCore()

@app.route('/')
def index():
    """Interface principale de Mathia"""
    return render_template_string(MATHIA_TEMPLATE)

@app.route('/api/chat', methods=['POST'])
def chat():
    """API de chat principal"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        show_steps = data.get('show_steps', True)
        
        if not message:
            return jsonify({'success': False, 'error': 'Message requis'})
        
        result = mathia.process_mathematical_query(message, show_steps)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/calculate', methods=['POST'])
def calculate():
    """API de calcul (alias pour chat pour compatibilité)"""
    return chat()

@app.route('/api/practice', methods=['GET'])
def get_practice():
    """Obtient un problème d'entraînement"""
    try:
        category = request.args.get('category')
        difficulty = request.args.get('difficulty', type=int)
        
        problem = mathia.get_practice_problem(category, difficulty)
        return jsonify(problem)
        
    except Exception as e:
        logger.error(f"Practice API error: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/submit', methods=['POST'])
def submit():
    """Soumet une solution pour vérification"""
    try:
        data = request.get_json()
        problem_id = data.get('problem_id')
        user_answer = data.get('answer', '')
        
        if not problem_id or not user_answer:
            return jsonify({'success': False, 'error': 'Paramètres manquants'})
        
        result = mathia.submit_solution(problem_id, user_answer)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Submit API error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Obtient le profil utilisateur"""
    try:
        return jsonify({
            'level': mathia.user_profile.level,
            'xp': mathia.user_profile.xp,
            'badges': mathia.user_profile.badges,
            'problems_solved': mathia.user_profile.problems_solved,
            'streak': mathia.user_profile.streak,
            'next_level_xp': 100 + (mathia.user_profile.level - 1) * 50 if mathia.user_profile.level > 1 else 100
        })
    except Exception as e:
        logger.error(f"Profile API error: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Statistiques globales"""
    return jsonify(mathia.stats)

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'OK',
        'service': 'Mathia',
        'version': '2.0',
        'features': ['gamification', 'ai_analysis', 'step_solving', 'visualization']
    })

# Template HTML principal avec design moderne et gamification
MATHIA_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Assistant Mathématique Gamifié</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --bg-primary: #e6e7ee;
            --bg-secondary: #d1d2d9;
            --bg-tertiary: #fbfcff;
            --text-primary: #5a5c69;
            --text-secondary: #8b8d97;
            --accent: #667eea;
            --accent-secondary: #764ba2;
            --success: #00d09c;
            --warning: #f39c12;
            --error: #e74c3c;
            --shadow-light: #bebfc5;
            --shadow-dark: #ffffff;
            --gradient-main: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
        }
        
        body {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--gradient-main);
            min-height: 100vh;
            color: var(--text-primary);
        }
        
        .back-link {
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(255, 255, 255, 0.1);
            padding: 12px 24px;
            border-radius: 25px;
            color: white;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            z-index: 1000;
        }
        
        .back-link:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 80px 20px 20px;
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 30px;
            min-height: 100vh;
        }
        
        .sidebar {
            background: var(--bg-primary);
            border-radius: 30px;
            padding: 30px;
            height: fit-content;
            position: sticky;
            top: 100px;
            box-shadow: 20px 20px 60px var(--shadow-light), -20px -20px 60px var(--shadow-dark);
        }
        
        .profile-card {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: var(--bg-primary);
            border-radius: 20px;
            box-shadow: inset 8px 8px 16px var(--shadow-light), inset -8px -8px 16px var(--shadow-dark);
        }
        
        .avatar {
            width: 80px;
            height: 80px;
            background: var(--gradient-main);
            border-radius: 50%;
            margin: 0 auto 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            color: white;
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
        }
        
        .level-badge {
            background: var(--gradient-main);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
            margin: 10px 0;
            display: inline-block;
        }
        
        .xp-bar {
            background: var(--bg-secondary);
            height: 10px;
            border-radius: 10px;
            margin: 10px 0;
            overflow: hidden;
            box-shadow: inset 4px 4px 8px var(--shadow-light), inset -4px -4px 8px var(--shadow-dark);
        }
        
        .xp-fill {
            height: 100%;
            background: var(--gradient-main);
            border-radius: 10px;
            transition: width 0.5s ease;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: var(--bg-primary);
            padding: 15px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
        }
        
        .stat-value {
            font-size: 1.8rem;
            font-weight: bold;
            color: var(--accent);
            display: block;
        }
        
        .stat-label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 5px;
        }
        
        .badges-section h3 {
            color: var(--accent);
            margin-bottom: 15px;
            font-size: 1.2rem;
        }
        
        .badges-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
            gap: 10px;
        }
        
        .badge {
            background: var(--bg-primary);
            padding: 15px 10px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        .badge.earned {
            background: var(--gradient-main);
            color: white;
            transform: scale(1.05);
        }
        
        .badge:hover {
            transform: translateY(-2px) scale(1.02);
        }
        
        .badge-icon {
            font-size: 1.5rem;
            margin-bottom: 5px;
        }
        
        .badge-name {
            font-size: 0.7rem;
            font-weight: 600;
        }
        
        .main-content {
            background: var(--bg-primary);
            border-radius: 30px;
            padding: 40px;
            box-shadow: 20px 20px 60px var(--shadow-light), -20px -20px 60px var(--shadow-dark);
            display: flex;
            flex-direction: column;
            min-height: calc(100vh - 140px);
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .header h1 {
            font-size: 3rem;
            background: var(--gradient-main);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }
        
        .header p {
            color: var(--text-secondary);
            font-size: 1.2rem;
        }
        
        .mode-selector {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .mode-btn {
            background: var(--bg-primary);
            border: none;
            padding: 15px 30px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 600;
            color: var(--text-primary);
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
        }
        
        .mode-btn.active {
            background: var(--gradient-main);
            color: white;
            transform: translateY(-2px);
            box-shadow: 12px 12px 20px var(--shadow-light), -12px -12px 20px var(--shadow-dark);
        }
        
        .mode-btn:hover:not(.active) {
            transform: translateY(-1px);
        }
        
        .chat-section {
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        
        .messages {
            flex: 1;
            background: var(--bg-primary);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 20px;
            max-height: 500px;
            overflow-y: auto;
            box-shadow: inset 8px 8px 16px var(--shadow-light), inset -8px -8px 16px var(--shadow-dark);
        }
        
        .message {
            margin-bottom: 20px;
            animation: slideIn 0.3s ease;
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message.user {
            text-align: right;
        }
        
        .message.assistant {
            text-align: left;
        }
        
        .message-bubble {
            display: inline-block;
            max-width: 80%;
            padding: 15px 20px;
            border-radius: 20px;
            word-wrap: break-word;
        }
        
        .message.user .message-bubble {
            background: var(--gradient-main);
            color: white;
            border-bottom-right-radius: 5px;
        }
        
        .message.assistant .message-bubble {
            background: var(--bg-tertiary);
            border: 2px solid var(--bg-secondary);
            border-bottom-left-radius: 5px;
        }
        
        .message-steps {
            background: var(--bg-tertiary);
            border-radius: 15px;
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid var(--accent);
        }
        
        .step {
            padding: 8px 0;
            border-bottom: 1px solid var(--bg-secondary);
        }
        
        .step:last-child {
            border-bottom: none;
        }
        
        .step-number {
            background: var(--accent);
            color: white;
            width: 25px;
            height: 25px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            font-weight: bold;
            margin-right: 10px;
        }
        
        .graph-container {
            background: var(--bg-tertiary);
            border-radius: 15px;
            padding: 20px;
            margin: 15px 0;
            text-align: center;
            border: 2px solid var(--bg-secondary);
        }
        
        .graph-container img {
            max-width: 100%;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
        }
        
        .input-area {
            display: flex;
            gap: 15px;
            align-items: flex-end;
        }
        
        .input-group {
            flex: 1;
        }
        
        .input-field {
            width: 100%;
            padding: 15px 20px;
            border: none;
            border-radius: 20px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 1rem;
            resize: vertical;
            min-height: 60px;
            box-shadow: inset 8px 8px 16px var(--shadow-light), inset -8px -8px 16px var(--shadow-dark);
            transition: all 0.3s ease;
        }
        
        .input-field:focus {
            outline: none;
            box-shadow: inset 4px 4px 8px var(--shadow-light), inset -4px -4px 8px var(--shadow-dark), 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        .input-field::placeholder {
            color: var(--text-secondary);
        }
        
        .send-btn {
            background: var(--gradient-main);
            border: none;
            color: white;
            padding: 15px 25px;
            border-radius: 20px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
            white-space: nowrap;
        }
        
        .send-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 12px 12px 20px var(--shadow-light), -12px -12px 20px var(--shadow-dark);
        }
        
        .send-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .practice-section {
            display: none;
        }
        
        .practice-section.active {
            display: block;
        }
        
        .problem-card {
            background: var(--bg-primary);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
        }
        
        .problem-header {
            display: flex;
            justify-content: between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .problem-title {
            font-size: 1.5rem;
            color: var(--accent);
            margin-bottom: 10px;
        }
        
        .difficulty-stars {
            color: var(--warning);
            font-size: 1.2rem;
        }
        
        .problem-description {
            font-size: 1.1rem;
            line-height: 1.6;
            margin-bottom: 25px;
            background: var(--bg-tertiary);
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid var(--accent);
        }
        
        .hint-section {
            margin: 20px 0;
        }
        
        .hint-btn {
            background: var(--bg-secondary);
            border: none;
            padding: 10px 20px;
            border-radius: 15px;
            cursor: pointer;
            color: var(--text-primary);
            margin-bottom: 10px;
            transition: all 0.3s ease;
        }
        
        .hint-btn:hover {
            background: var(--accent);
            color: white;
        }
        
        .hint-content {
            background: var(--bg-tertiary);
            padding: 15px;
            border-radius: 10px;
            margin-top: 10px;
            display: none;
            border-left: 3px solid var(--warning);
        }
        
        .solution-input {
            display: flex;
            gap: 15px;
            margin-top: 20px;
        }
        
        .submit-btn {
            background: var(--success);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 15px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .submit-btn:hover {
            background: #00b894;
            transform: translateY(-1px);
        }
        
        .result-card {
            margin-top: 20px;
            padding: 20px;
            border-radius: 15px;
            display: none;
        }
        
        .result-card.correct {
            background: rgba(0, 208, 156, 0.1);
            border: 2px solid var(--success);
        }
        
        .result-card.incorrect {
            background: rgba(231, 76, 60, 0.1);
            border: 2px solid var(--error);
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            border-radius: 15px;
            color: white;
            font-weight: 600;
            transform: translateX(400px);
            transition: transform 0.3s ease;
            z-index: 1000;
            max-width: 350px;
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.success {
            background: var(--success);
        }
        
        .notification.error {
            background: var(--error);
        }
        
        .notification.warning {
            background: var(--warning);
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .examples-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        
        .example-card {
            background: var(--bg-primary);
            padding: 20px;
            border-radius: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
        }
        
        .example-card:hover {
            transform: translateY(-5px);
            box-shadow: 12px 12px 24px var(--shadow-light), -12px -12px 24px var(--shadow-dark);
        }
        
        .example-title {
            font-weight: 600;
            color: var(--accent);
            margin-bottom: 10px;
        }
        
        .example-desc {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }
        
        /* Responsive Design */
        @media (max-width: 968px) {
            .container {
                grid-template-columns: 1fr;
                gap: 20px;
                padding: 20px;
            }
            
            .sidebar {
                position: static;
                order: 2;
            }
            
            .main-content {
                order: 1;
                min-height: auto;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .mode-selector {
                flex-wrap: wrap;
                gap: 10px;
            }
            
            .mode-btn {
                padding: 12px 20px;
                font-size: 0.9rem;
            }
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .main-content, .sidebar {
                padding: 20px;
                border-radius: 20px;
            }
            
            .input-area {
                flex-direction: column;
                gap: 10px;
            }
            
            .send-btn {
                align-self: stretch;
            }
            
            .examples-grid {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <a href="/" class="back-link">← Retour au Hub</a>
    
    <div class="container">
        <!-- Sidebar avec profil et gamification -->
        <div class="sidebar">
            <div class="profile-card">
                <div class="avatar" id="userAvatar">🤖</div>
                <div class="level-badge" id="userLevel">Niveau 1</div>
                <div class="xp-bar">
                    <div class="xp-fill" id="xpFill" style="width: 0%"></div>
                </div>
                <div style="font-size: 0.8rem; color: var(--text-secondary);" id="xpText">0 / 100 XP</div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <span class="stat-value" id="problemsSolved">0</span>
                    <div class="stat-label">Problèmes</div>
                </div>
                <div class="stat-card">
                    <span class="stat-value" id="currentStreak">0</span>
                    <div class="stat-label">Série</div>
                </div>
            </div>
            
            <div class="badges-section">
                <h3>Badges</h3>
                <div class="badges-grid" id="badgesContainer">
                    <div class="badge">
                        <div class="badge-icon">🎯</div>
                        <div class="badge-name">Premier Pas</div>
                    </div>
                    <div class="badge">
                        <div class="badge-icon">⚡</div>
                        <div class="badge-name">Résolveur</div>
                    </div>
                    <div class="badge">
                        <div class="badge-icon">🏆</div>
                        <div class="badge-name">Expert</div>
                    </div>
                    <div class="badge">
                        <div class="badge-icon">📊</div>
                        <div class="badge-name">Visualisateur</div>
                    </div>
                    <div class="badge">
                        <div class="badge-icon">🔥</div>
                        <div class="badge-name">Série</div>
                    </div>
                    <div class="badge">
                        <div class="badge-icon">🎨</div>
                        <div class="badge-name">Polyvalent</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Contenu principal -->
        <div class="main-content">
            <div class="header">
                <h1>Mathia</h1>
                <p>Votre assistant mathématique personnel et gamifié</p>
            </div>
            
            <!-- Sélecteur de mode -->
            <div class="mode-selector">
                <button class="mode-btn active" data-mode="chat">💬 Chat Libre</button>
                <button class="mode-btn" data-mode="practice">🎯 Entraînement</button>
            </div>
            
            <!-- Section Chat -->
            <div class="chat-section" id="chatSection">
                <div class="messages" id="messages">
                    <div class="message assistant">
                        <div class="message-bubble">
                            Salut ! Je suis Mathia, votre assistant mathématique gamifié. Posez-moi vos questions ou choisissez un problème d'entraînement pour gagner de l'XP et débloquer des badges !
                        </div>
                    </div>
                    
                    <!-- Exemples interactifs -->
                    <div class="examples-grid">
                        <div class="example-card" data-example="Résous l'équation 2x + 5 = 13">
                            <div class="example-title">Équation Simple</div>
                            <div class="example-desc">2x + 5 = 13</div>
                        </div>
                        <div class="example-card" data-example="Trace la fonction f(x) = x² - 4x + 3">
                            <div class="example-title">Fonction Quadratique</div>
                            <div class="example-desc">f(x) = x² - 4x + 3</div>
                        </div>
                        <div class="example-card" data-example="Calcule la dérivée de x³ + 2x² - 5x">
                            <div class="example-title">Dérivée</div>
                            <div class="example-desc">d/dx(x³ + 2x² - 5x)</div>
                        </div>
                        <div class="example-card" data-example="Analyse les limites de ln(x) quand x tend vers 0">
                            <div class="example-title">Limites</div>
                            <div class="example-desc">lim(x→0) ln(x)</div>
                        </div>
                    </div>
                </div>
                
                <div class="input-area">
                    <div class="input-group">
                        <textarea id="messageInput" class="input-field" 
                                placeholder="Posez votre question mathématique... (ex: 'Résous 3x + 7 = 22' ou 'Trace f(x) = sin(x)')"
                                rows="3"></textarea>
                    </div>
                    <button id="sendBtn" class="send-btn">Envoyer</button>
                </div>
            </div>
            
            <!-- Section Entraînement -->
            <div class="practice-section" id="practiceSection">
                <div id="problemContainer">
                    <div class="problem-card">
                        <div class="problem-header">
                            <div>
                                <h3 class="problem-title" id="problemTitle">Chargement...</h3>
                                <div class="difficulty-stars" id="problemDifficulty"></div>
                            </div>
                            <button class="mode-btn" id="newProblemBtn">Nouveau Problème</button>
                        </div>
                        <div class="problem-description" id="problemDescription">
                            Chargement du problème...
                        </div>
                        
                        <div class="hint-section" id="hintSection" style="display: none;">
                            <button class="hint-btn" id="hintBtn">💡 Voir un indice</button>
                            <div class="hint-content" id="hintContent"></div>
                        </div>
                        
                        <div class="solution-input">
                            <input type="text" id="answerInput" class="input-field" 
                                   placeholder="Votre réponse..." style="min-height: auto;">
                            <button id="submitBtn" class="submit-btn">Vérifier</button>
                        </div>
                        
                        <div class="result-card" id="resultCard">
                            <div id="resultContent"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        class Mathia {
            constructor() {
                this.currentMode = 'chat';
                this.currentProblem = null;
                this.hintIndex = 0;
                this.userProfile = {
                    level: 1,
                    xp: 0,
                    badges: [],
                    problemsSolved: 0,
                    streak: 0
                };
                
                this.init();
            }
            
            init() {
                this.setupEventListeners();
                this.loadUserProfile();
                this.loadNewProblem();
            }
            
            setupEventListeners() {
                // Mode switching
                document.querySelectorAll('.mode-btn').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        if (e.target.dataset.mode) {
                            this.switchMode(e.target.dataset.mode);
                        }
                    });
                });
                
                // Chat functionality
                document.getElementById('sendBtn').addEventListener('click', () => this.sendMessage());
                document.getElementById('messageInput').addEventListener('keypress', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        this.sendMessage();
                    }
                });
                
                // Example cards
                document.querySelectorAll('.example-card').forEach(card => {
                    card.addEventListener('click', () => {
                        const example = card.dataset.example;
                        document.getElementById('messageInput').value = example;
                        this.sendMessage();
                    });
                });
                
                // Practice functionality
                document.getElementById('newProblemBtn').addEventListener('click', () => this.loadNewProblem());
                document.getElementById('submitBtn').addEventListener('click', () => this.submitAnswer());
                document.getElementById('hintBtn').addEventListener('click', () => this.showHint());
                
                document.getElementById('answerInput').addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        this.submitAnswer();
                    }
                });
            }
            
            switchMode(mode) {
                // Update buttons
                document.querySelectorAll('.mode-btn').forEach(btn => {
                    btn.classList.remove('active');
                    if (btn.dataset.mode === mode) {
                        btn.classList.add('active');
                    }
                });
                
                // Update sections
                document.getElementById('chatSection').style.display = mode === 'chat' ? 'flex' : 'none';
                document.getElementById('practiceSection').classList.toggle('active', mode === 'practice');
                
                this.currentMode = mode;
                
                if (mode === 'practice' && !this.currentProblem) {
                    this.loadNewProblem();
                }
            }
            
            async sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                
                if (!message) return;
                
                // Add user message
                this.addMessage('user', message);
                input.value = '';
                
                // Show loading
                const loadingId = this.addMessage('assistant', '<span class="loading"></span> Analyse en cours...');
                
                try {
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            message: message,
                            show_steps: true
                        })
                    });
                    
                    const data = await response.json();
                    
                    // Remove loading message
                    document.getElementById(loadingId).remove();
                    
                    if (data.success) {
                        // Add AI response
                        let responseContent = data.response;
                        
                        // Add solution steps if available
                        if (data.solution_steps && data.solution_steps.length > 0) {
                            responseContent += '<div class="message-steps">';
                            data.solution_steps.forEach((step, index) => {
                                responseContent += `<div class="step"><span class="step-number">${index + 1}</span>${step}</div>`;
                            });
                            responseContent += '</div>';
                        }
                        
                        this.addMessage('assistant', responseContent);
                        
                        // Add graph if available
                        if (data.graph) {
                            this.addGraph(data.graph);
                        }
                        
                        // Update profile with new badges/XP
                        if (data.new_badges && data.new_badges.length > 0) {
                            this.showBadgeNotifications(data.new_badges);
                        }
                        
                        this.updateProfile(data);
                        
                    } else {
                        this.addMessage('assistant', `Erreur: ${data.error}`);
                    }
                    
                } catch (error) {
                    document.getElementById(loadingId).remove();
                    this.addMessage('assistant', 'Désolé, une erreur de connexion s\'est produite. Veuillez réessayer.');
                    console.error('Chat error:', error);
                }
            }
            
            addMessage(type, content) {
                const messages = document.getElementById('messages');
                const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
                
                const messageDiv = document.createElement('div');
                messageDiv.id = messageId;
                messageDiv.className = `message ${type}`;
                messageDiv.innerHTML = `<div class="message-bubble">${content}</div>`;
                
                messages.appendChild(messageDiv);
                messages.scrollTop = messages.scrollHeight;
                
                return messageId;
            }
            
            addGraph(graphData) {
                const messages = document.getElementById('messages');
                const graphDiv = document.createElement('div');
                graphDiv.className = 'graph-container';
                graphDiv.innerHTML = `
                    <h4 style="color: var(--accent); margin-bottom: 15px;">📊 Visualisation Graphique</h4>
                    <img src="data:image/png;base64,${graphData}" alt="Graphique mathématique">
                `;
                messages.appendChild(graphDiv);
                messages.scrollTop = messages.scrollHeight;
            }
            
            async loadNewProblem() {
                try {
                    const response = await fetch('/api/practice');
                    const problem = await response.json();
                    
                    this.currentProblem = problem;
                    this.hintIndex = 0;
                    
                    document.getElementById('problemTitle').textContent = problem.title;
                    document.getElementById('problemDescription').textContent = problem.description;
                    
                    // Update difficulty stars
                    const stars = '★'.repeat(problem.difficulty) + '☆'.repeat(5 - problem.difficulty);
                    document.getElementById('problemDifficulty').textContent = stars;
                    
                    // Reset hint section
                    document.getElementById('hintSection').style.display = problem.hints && problem.hints.length > 0 ? 'block' : 'none';
                    document.getElementById('hintContent').style.display = 'none';
                    document.getElementById('hintBtn').textContent = '💡 Voir un indice';
                    
                    // Reset answer input
                    document.getElementById('answerInput').value = '';
                    document.getElementById('resultCard').style.display = 'none';
                    
                } catch (error) {
                    console.error('Problem loading error:', error);
                    this.showNotification('Erreur lors du chargement du problème', 'error');
                }
            }
            
            showHint() {
                if (!this.currentProblem || !this.currentProblem.hints) return;
                
                const hintContent = document.getElementById('hintContent');
                const hintBtn = document.getElementById('hintBtn');
                
                if (this.hintIndex < this.currentProblem.hints.length) {
                    hintContent.textContent = this.currentProblem.hints[this.hintIndex];
                    hintContent.style.display = 'block';
                    this.hintIndex++;
                    
                    if (this.hintIndex >= this.currentProblem.hints.length) {
                        hintBtn.textContent = '💡 Tous les indices utilisés';
                        hintBtn.disabled = true;
                    } else {
                        hintBtn.textContent = `💡 Indice suivant (${this.hintIndex + 1}/${this.currentProblem.hints.length})`;
                    }
                }
            }
            
            async submitAnswer() {
                if (!this.currentProblem) return;
                
                const answer = document.getElementById('answerInput').value.trim();
                if (!answer) {
                    this.showNotification('Veuillez entrer une réponse', 'warning');
                    return;
                }
                
                try {
                    const response = await fetch('/api/submit', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            problem_id: this.currentProblem.id,
                            answer: answer
                        })
                    });
                    
                    const result = await response.json();
                    
                    this.showResult(result);
                    
                    if (result.correct) {
                        this.userProfile.problemsSolved++;
                        this.userProfile.xp += result.xp_earned || 0;
                        this.userProfile.streak++;
                        
                        this.showNotification(`Correct ! +${result.xp_earned} XP`, 'success');
                        
                        if (result.level_up) {
                            this.userProfile.level++;
                            this.showNotification(`🎉 Niveau ${this.userProfile.level} atteint !`, 'success');
                        }
                        
                        if (result.new_badges && result.new_badges.length > 0) {
                            this.showBadgeNotifications(result.new_badges);
                        }
                    } else {
                        this.userProfile.streak = 0;
                        this.showNotification('Pas tout à fait... Regardez la solution !', 'error');
                    }
                    
                    this.updateProfileDisplay();
                    
                } catch (error) {
                    console.error('Submit error:', error);
                    this.showNotification('Erreur lors de la vérification', 'error');
                }
            }
            
            showResult(result) {
                const resultCard = document.getElementById('resultCard');
                const resultContent = document.getElementById('resultContent');
                
                resultCard.className = `result-card ${result.correct ? 'correct' : 'incorrect'}`;
                resultCard.style.display = 'block';
                
                let content = `
                    <h4>${result.correct ? '✅ Correct !' : '❌ Incorrect'}</h4>
                    <p><strong>Réponse attendue:</strong> ${result.expected_answer}</p>
                `;
                
                if (result.solution_steps) {
                    content += '<div style="margin-top: 15px;"><strong>Solution détaillée:</strong>';
                    result.solution_steps.forEach((step, index) => {
                        content += `<div style="margin: 5px 0; padding-left: 20px;">${index + 1}. ${step}</div>`;
                    });
                    content += '</div>';
                }
                
                if (result.correct && result.xp_earned) {
                    content += `<div style="margin-top: 15px; color: var(--success);"><strong>+${result.xp_earned} XP gagnés !</strong></div>`;
                }
                
                resultContent.innerHTML = content;
            }
            
            async loadUserProfile() {
                try {
                    const response = await fetch('/api/profile');
                    const profile = await response.json();
                    
                    this.userProfile = { ...this.userProfile, ...profile };
                    this.updateProfileDisplay();
                    
                } catch (error) {
                    console.error('Profile loading error:', error);
                }
            }
            
            updateProfile(data) {
                if (data.user_level) this.userProfile.level = data.user_level;
                if (data.user_xp) this.userProfile.xp = data.user_xp;
                if (data.new_badges) {
                    data.new_badges.forEach(badge => {
                        if (!this.userProfile.badges.includes(badge.name)) {
                            this.userProfile.badges.push(badge.name);
                        }
                    });
                }
                
                this.updateProfileDisplay();
            }
            
            updateProfileDisplay() {
                // Update level
                document.getElementById('userLevel').textContent = `Niveau ${this.userProfile.level}`;
                
                // Update XP bar
                const nextLevelXP = this.userProfile.level === 1 ? 100 : 100 + (this.userProfile.level - 1) * 50;
                const currentLevelXP = this.userProfile.level === 1 ? 0 : 100 + (this.userProfile.level - 2) * 50;
                const progressXP = this.userProfile.xp - currentLevelXP;
                const neededXP = nextLevelXP - currentLevelXP;
                const percentage = Math.min((progressXP / neededXP) * 100, 100);
                
                document.getElementById('xpFill').style.width = `${percentage}%`;
                document.getElementById('xpText').textContent = `${this.userProfile.xp} / ${nextLevelXP} XP`;
                
                // Update stats
                document.getElementById('problemsSolved').textContent = this.userProfile.problemsSolved;
                document.getElementById('currentStreak').textContent = this.userProfile.streak;
                
                // Update badges
                const badgeElements = document.querySelectorAll('.badge');
                const badgeNames = ['Premier Pas', 'Résolveur', 'Expert', 'Visualisateur', 'Série', 'Polyvalent'];
                
                badgeElements.forEach((badge, index) => {
                    const badgeName = badgeNames[index];
                    if (this.userProfile.badges.includes(badgeName)) {
                        badge.classList.add('earned');
                    }
                });
            }
            
            showBadgeNotifications(badges) {
                badges.forEach((badge, index) => {
                    setTimeout(() => {
                        this.showNotification(`🏆 Badge débloqué: ${badge.name}!`, 'success');
                    }, index * 1000);
                });
            }
            
            showNotification(message, type = 'info') {
                // Remove existing notifications
                document.querySelectorAll('.notification').forEach(n => n.remove());
                
                const notification = document.createElement('div');
                notification.className = `notification ${type}`;
                notification.textContent = message;
                
                document.body.appendChild(notification);
                
                // Show notification
                setTimeout(() => notification.classList.add('show'), 100);
                
                // Hide notification after 4 seconds
                setTimeout(() => {
                    notification.classList.remove('show');
                    setTimeout(() => notification.remove(), 300);
                }, 4000);
            }
        }
        
        // Initialize Mathia when page loads
        document.addEventListener('DOMContentLoaded', () => {
            window.mathia = new Mathia();
        });
        
        // Auto-resize textarea
        document.getElementById('messageInput').addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        });
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("🎲 MATHIA V2.0 - Assistant Mathématique Gamifié")
    print("=" * 60)
    
    try:
        import sympy, matplotlib, numpy as np
        from mistralai import Mistral
        print("✅ Dépendances installées")
        
        matplotlib.use('Agg')
        print("✅ Backend matplotlib configuré")
        
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port: {port}")
        print(f"🔧 Debug: {debug_mode}")
        print(f"🔑 Clés Mistral: {len(mathia.api_keys)} configurées")
        
        print("\n🎮 Fonctionnalités:")
        print("   • Chat intelligent avec IA Mistral")
        print("   • Résolution étape par étape")
        print("   • Graphiques interactifs")
        print("   • Système de gamification (XP, niveaux, badges)")
        print("   • Problèmes d'entraînement guidés")
        print("   • Interface responsive moderne")
        
        print("\n🏆 Système de récompenses:")
        print("   • XP pour chaque problème résolu")
        print("   • Progression par niveaux")
        print("   • 6 badges à débloquer")
        print("   • Suivi des séries de victoires")
        
        print("\n📊 Types de problèmes:")
        print("   • Équations linéaires et quadratiques")
        print("   • Fonctions et graphiques")
        print("   • Calcul différentiel")
        print("   • Analyse de limites")
        print("   • Et bien plus...")
        
        print("\n🚀 Démarrage de Mathia...")
        
    except ImportError as e:
        print(f"❌ ERREUR: {e}")
        exit(1)
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
