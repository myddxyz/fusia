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
from concurrent.futures import ThreadPoolExecutor
import traceback

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@dataclass
class UserInput:
    """Structure pour organiser l'entrée utilisateur"""
    message: str
    timestamp: datetime
    context: Optional[str] = None
    follow_up: bool = False

@dataclass
class MistralResponse:
    """Structure pour organiser la réponse de Mistral"""
    text: str
    raw_response: str
    success: bool
    visual_needed: bool = False
    math_data: Optional[Dict] = None
    error: Optional[str] = None

@dataclass
class GraphData:
    """Structure pour les données de graphique"""
    type: str
    expressions: List[str]
    parameters: Dict
    annotations: List[str]
    image_base64: Optional[str] = None

@dataclass
class FinalResponse:
    """Structure pour la réponse finale"""
    text: str
    graph: Optional[GraphData] = None
    suggestions: List[str] = None
    debug_info: Optional[Dict] = None

class InputHandler:
    """Module 1: Traitement et validation des entrées utilisateur"""
    
    def __init__(self):
        self.conversation_history = []
        
    def process_input(self, message: str, context: str = None) -> UserInput:
        """Traite et valide l'entrée utilisateur"""
        logger.info(f"InputHandler: Processing message: {message[:50]}...")
        
        # Nettoyage du message
        clean_message = message.strip()
        if not clean_message:
            raise ValueError("Message vide")
        
        # Détection de question de suivi
        follow_up_indicators = ['et si', 'que se passe', 'change', 'modifie', 'avec', 'maintenant']
        is_follow_up = any(indicator in clean_message.lower() for indicator in follow_up_indicators)
        
        user_input = UserInput(
            message=clean_message,
            timestamp=datetime.now(),
            context=context,
            follow_up=is_follow_up
        )
        
        # Ajouter à l'historique
        self.conversation_history.append(user_input)
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-15:]
        
        logger.info(f"InputHandler: Processed as {'follow-up' if is_follow_up else 'new'} question")
        return user_input

class MistralClient:
    """Module 2: Communication avec l'API Mistral"""
    
    def __init__(self):
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        self.current_key = 0
        self.key_errors = {i: 0 for i in range(len(self.api_keys))}
        
    def get_client(self):
        """Obtient le meilleur client Mistral disponible"""
        sorted_keys = sorted(range(len(self.api_keys)), key=lambda i: self.key_errors[i])
        
        for key_index in sorted_keys:
            try:
                client = Mistral(api_key=self.api_keys[key_index])
                self.current_key = key_index
                return client
            except Exception as e:
                self.key_errors[key_index] += 1
                logger.warning(f"MistralClient: Key {key_index} failed: {e}")
        
        return Mistral(api_key=self.api_keys[0])
    
    def send_request(self, user_input: UserInput, conversation_history: List) -> MistralResponse:
        """Envoie la requête à Mistral et récupère la réponse structurée"""
        logger.info(f"MistralClient: Sending request for: {user_input.message[:30]}...")
        
        try:
            client = self.get_client()
            
            # Construction du prompt système intelligent
            system_prompt = self._build_system_prompt(user_input)
            
            # Construction des messages avec historique
            messages = [{"role": "system", "content": system_prompt}]
            
            # Ajouter l'historique récent
            for hist in conversation_history[-3:]:
                if hasattr(hist, 'message'):
                    messages.append({"role": "user", "content": hist.message})
            
            messages.append({"role": "user", "content": user_input.message})
            
            response = client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.2,
                max_tokens=2000
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Réduire les erreurs de cette clé en cas de succès
            if self.current_key in self.key_errors:
                self.key_errors[self.current_key] = max(0, self.key_errors[self.current_key] - 1)
            
            logger.info("MistralClient: Response received successfully")
            
            return MistralResponse(
                text=response_text,
                raw_response=response_text,
                success=True
            )
            
        except Exception as e:
            logger.error(f"MistralClient: Error - {e}")
            if self.current_key in self.key_errors:
                self.key_errors[self.current_key] += 1
            
            return MistralResponse(
                text="",
                raw_response="",
                success=False,
                error=str(e)
            )
    
    def _build_system_prompt(self, user_input: UserInput) -> str:
        """Construit un prompt système adapté au contexte"""
        base_prompt = """Tu es Mathia, un assistant mathématique expert qui fournit des explications claires et identifie les besoins de visualisation.

IMPORTANT - FORMATAGE:
- N'utilise JAMAIS d'astérisques pour la mise en forme
- Pas de **gras** ni de *italique*
- Utilise un langage naturel et fluide
- Structure avec des tirets ou numéros si nécessaire

STRUCTURE DE RÉPONSE OBLIGATOIRE:
Réponds avec ce format JSON précis:
{
    "explanation": "Ton explication mathématique détaillée ici - SANS ASTERISQUES",
    "visual_needed": true/false,
    "visual_type": "function|statistics|geometry|analysis|comparison",
    "math_expressions": ["expression1", "expression2"],
    "key_points": ["point1", "point2", "point3"],
    "suggestions": ["suggestion1", "suggestion2"]
}

RÈGLES STRICTES:
- Explications claires et pédagogiques SANS astérisques
- Détection intelligente des besoins visuels
- Extraction précise des expressions mathématiques
- Points clés pour l'apprentissage
- Suggestions pour approfondir
- INTERDICTION ABSOLUE des astérisques dans tout le texte"""
        
        if user_input.follow_up:
            base_prompt += "\n\nCONTEXTE: Question de suivi - référence la conversation précédente."
        
        return base_prompt

class PostProcessor:
    """Module 3: Analyse et extraction des données de la réponse Mistral"""
    
    def __init__(self):
        self.x, self.y, self.z, self.t = symbols('x y z t')
        
    def process_response(self, mistral_response: MistralResponse) -> Tuple[str, bool, Dict]:
        """Analyse la réponse de Mistral et extrait les informations structurées"""
        logger.info("PostProcessor: Analyzing Mistral response")
        
        if not mistral_response.success:
            return mistral_response.text, False, {}
        
        try:
            # Tentative d'extraction JSON
            json_match = re.search(r'\{.*\}', mistral_response.raw_response, re.DOTALL)
            
            if json_match:
                response_data = json.loads(json_match.group())
                
                explanation = response_data.get('explanation', mistral_response.text)
                visual_needed = response_data.get('visual_needed', False)
                
                processed_data = {
                    'visual_type': response_data.get('visual_type', 'function'),
                    'expressions': response_data.get('math_expressions', []),
                    'key_points': response_data.get('key_points', []),
                    'suggestions': response_data.get('suggestions', [])
                }
                
                # Validation des expressions mathématiques
                processed_data['expressions'] = self._validate_expressions(processed_data['expressions'])
                
                logger.info(f"PostProcessor: Extracted {len(processed_data['expressions'])} expressions")
                
                return explanation, visual_needed, processed_data
            
            else:
                # Fallback: analyse heuristique
                explanation = mistral_response.text
                visual_needed, processed_data = self._heuristic_analysis(explanation)
                
                logger.info("PostProcessor: Used heuristic analysis")
                
                return explanation, visual_needed, processed_data
                
        except Exception as e:
            logger.error(f"PostProcessor: Error - {e}")
            
            # Fallback complet
            explanation = mistral_response.text
            visual_needed, processed_data = self._heuristic_analysis(explanation)
            
            return explanation, visual_needed, processed_data
    
    def _validate_expressions(self, expressions: List[str]) -> List[str]:
        """Valide et nettoie les expressions mathématiques"""
        validated = []
        
        for expr_str in expressions:
            try:
                # Nettoyage et remplacement
                cleaned = self._clean_expression(expr_str)
                
                # Test de parsing avec sympy
                expr = sympify(cleaned, evaluate=False)
                validated.append(str(expr))
                
            except Exception as e:
                logger.warning(f"PostProcessor: Invalid expression '{expr_str}': {e}")
                continue
        
        return validated
    
    def _clean_expression(self, expr_str: str) -> str:
        """Nettoie une expression mathématique"""
        replacements = [
            (r'\^', '**'),
            (r'ln\s*\(', 'log('),
            (r'sin\s*\(', 'sin('),
            (r'cos\s*\(', 'cos('),
            (r'tan\s*\(', 'tan('),
            (r'\be\b', 'E'),
            (r'pi\b', 'pi')
        ]
        
        cleaned = expr_str.strip()
        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned)
        
        return cleaned
    
    def _heuristic_analysis(self, text: str) -> Tuple[bool, Dict]:
        """Analyse heuristique si pas de JSON"""
        text_lower = text.lower()
        
        # Détection de besoins visuels
        visual_triggers = {
            'function': ['fonction', 'f(x)', 'graphique', 'courbe'],
            'statistics': ['moyenne', 'écart', 'distribution', 'probabilité'],
            'geometry': ['triangle', 'cercle', 'aire', 'angle'],
            'analysis': ['dérivée', 'intégrale', 'limite'],
            'comparison': ['comparer', 'différence', 'évolution']
        }
        
        visual_type = 'function'  # Par défaut
        visual_needed = False
        
        for v_type, keywords in visual_triggers.items():
            if any(keyword in text_lower for keyword in keywords):
                visual_type = v_type
                visual_needed = True
                break
        
        # Extraction d'expressions par regex
        expressions = []
        patterns = [
            r'f\([x-z]\)\s*=\s*([^.,!?]+)',
            r'([x-z]\^?\d*[\+\-\*/][^.,!?]+)',
            r'(sin\([^)]+\)|cos\([^)]+\)|tan\([^)]+\))',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            expressions.extend(matches)
        
        return visual_needed, {
            'visual_type': visual_type,
            'expressions': list(set(expressions))[:3],  # Max 3 expressions
            'key_points': [],
            'suggestions': []
        }

class GraphGenerator:
    """Module 4: Génération des visualisations"""
    
    def __init__(self):
        self.x, self.y, self.z = symbols('x y z')
        
        # Configuration matplotlib
        plt.style.use('dark_background')
        plt.rcParams.update({
            'font.size': 11,
            'axes.linewidth': 1.5,
            'lines.linewidth': 3,
            'figure.facecolor': '#0f0f23',
            'axes.facecolor': '#1a1a3a'
        })
    
    def generate_graph(self, visual_type: str, expressions: List[str], context: str = "") -> Optional[GraphData]:
        """Génère un graphique basé sur le type et les expressions"""
        logger.info(f"GraphGenerator: Creating {visual_type} graph with {len(expressions)} expressions")
        
        try:
            if visual_type == 'function' and expressions:
                return self._create_function_graph(expressions)
            elif visual_type == 'statistics':
                return self._create_statistics_graph(context)
            elif visual_type == 'geometry':
                return self._create_geometry_graph(context)
            elif visual_type == 'analysis' and expressions:
                return self._create_analysis_graph(expressions)
            elif visual_type == 'comparison' and expressions:
                return self._create_comparison_graph(expressions)
            else:
                return self._create_generic_graph(visual_type, expressions)
                
        except Exception as e:
            logger.error(f"GraphGenerator: Error - {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _create_function_graph(self, expressions: List[str]) -> GraphData:
        """Crée un graphique de fonction(s)"""
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='#0f0f23')
        ax.set_facecolor('#1a1a3a')
        
        colors = ['#00d4ff', '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4']
        x_vals = np.linspace(-10, 10, 2000)
        annotations = []
        
        plotted_count = 0
        for i, expr_str in enumerate(expressions[:3]):  # Max 3 fonctions
            try:
                # Conversion en fonction numpy
                expr = sympify(expr_str)
                f = lambdify(self.x, expr, ['numpy'], cse=True)
                
                y_vals = f(x_vals)
                
                # Nettoyage des valeurs
                mask = np.isfinite(y_vals)
                if not np.any(mask):
                    continue
                
                x_clean = x_vals[mask]
                y_clean = y_vals[mask]
                
                color = colors[i % len(colors)]
                
                # Plot principal avec effet
                ax.plot(x_clean, y_clean, color=color, linewidth=3, 
                       label=f'f(x) = {expr}', alpha=0.9, zorder=2)
                
                # Effet d'ombre
                ax.plot(x_clean, y_clean, color=color, linewidth=6, 
                       alpha=0.2, zorder=1)
                
                # Annotations automatiques
                try:
                    # Points remarquables
                    derivative = diff(expr, self.x)
                    critical_points = solve(derivative, self.x)
                    
                    for cp in critical_points[:2]:  # Max 2 points
                        if cp.is_real:
                            cp_val = float(cp.evalf())
                            if -10 <= cp_val <= 10:
                                y_cp = float(expr.subs(self.x, cp).evalf())
                                ax.plot(cp_val, y_cp, 'o', color=color, 
                                       markersize=8, markeredgewidth=2, 
                                       markeredgecolor='white', zorder=3)
                                annotations.append(f"Point critique en x={cp_val:.2f}")
                
                except:
                    pass
                
                plotted_count += 1
                
            except Exception as e:
                logger.warning(f"GraphGenerator: Failed to plot {expr_str}: {e}")
                continue
        
        if plotted_count == 0:
            # Fonction par défaut si aucune n'a pu être tracée
            y_default = np.sin(x_vals)
            ax.plot(x_vals, y_default, color='#00d4ff', linewidth=3, 
                   label='sin(x)', alpha=0.9)
            annotations.append("Fonction de démonstration")
        
        # Styling avancé
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.axhline(y=0, color='#ffffff', linewidth=1.5, alpha=0.8)
        ax.axvline(x=0, color='#ffffff', linewidth=1.5, alpha=0.8)
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('f(x)', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Graphique de Fonction(s)', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        # Légende
        if plotted_count > 0:
            legend = ax.legend(loc='best', frameon=True, fancybox=True, shadow=True)
            legend.get_frame().set_facecolor('#2a2a4a')
            legend.get_frame().set_edgecolor('#00d4ff')
            legend.get_frame().set_alpha(0.9)
        
        # Customisation des axes
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
            spine.set_linewidth(1.5)
        
        plt.tight_layout()
        image_b64 = self._save_to_base64()
        
        return GraphData(
            type='function',
            expressions=expressions,
            parameters={'x_range': [-10, 10], 'resolution': 2000},
            annotations=annotations,
            image_base64=image_b64
        )
    
    def _create_statistics_graph(self, context: str) -> GraphData:
        """Crée un graphique statistique"""
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='#0f0f23')
        ax.set_facecolor('#1a1a3a')
        
        # Données de démonstration
        np.random.seed(42)
        data1 = np.random.normal(100, 15, 1000)
        data2 = np.random.normal(110, 20, 800)
        
        # Histogrammes
        ax.hist(data1, bins=40, alpha=0.7, color='#00d4ff', 
               label='Distribution A', density=True, edgecolor='white', linewidth=0.5)
        ax.hist(data2, bins=40, alpha=0.7, color='#ff6b6b', 
               label='Distribution B', density=True, edgecolor='white', linewidth=0.5)
        
        # Lignes de moyenne
        ax.axvline(np.mean(data1), color='#00d4ff', linestyle='--', 
                  linewidth=2, alpha=0.8, label=f'Moyenne A: {np.mean(data1):.1f}')
        ax.axvline(np.mean(data2), color='#ff6b6b', linestyle='--', 
                  linewidth=2, alpha=0.8, label=f'Moyenne B: {np.mean(data2):.1f}')
        
        ax.set_xlabel('Valeurs', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('Densité de Probabilité', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Analyse de Distributions Statistiques', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        legend.get_frame().set_edgecolor('#00d4ff')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        plt.tight_layout()
        
        annotations = [
            f"Échantillon A: μ={np.mean(data1):.1f}, σ={np.std(data1):.1f}",
            f"Échantillon B: μ={np.mean(data2):.1f}, σ={np.std(data2):.1f}"
        ]
        
        return GraphData(
            type='statistics',
            expressions=[],
            parameters={'samples': [len(data1), len(data2)]},
            annotations=annotations,
            image_base64=self._save_to_base64()
        )
    
    def _create_geometry_graph(self, context: str) -> GraphData:
        """Crée un graphique géométrique"""
        fig, ax = plt.subplots(figsize=(10, 10), facecolor='#0f0f23')
        ax.set_facecolor('#1a1a3a')
        
        # Cercle unitaire
        theta = np.linspace(0, 2*np.pi, 200)
        circle_x = np.cos(theta)
        circle_y = np.sin(theta)
        
        ax.plot(circle_x, circle_y, color='#00d4ff', linewidth=3, 
               label='Cercle unitaire', alpha=0.9)
        
        # Triangle inscrit équilatéral
        triangle_angles = np.array([0, 2*np.pi/3, 4*np.pi/3, 0])
        triangle_x = np.cos(triangle_angles)
        triangle_y = np.sin(triangle_angles)
        
        ax.plot(triangle_x, triangle_y, color='#ff6b6b', linewidth=3, 
               label='Triangle équilatéral inscrit', marker='o', markersize=8)
        
        # Repères et annotations
        ax.axhline(y=0, color='#ffffff', linewidth=1.5, alpha=0.6)
        ax.axvline(x=0, color='#ffffff', linewidth=1.5, alpha=0.6)
        ax.plot(0, 0, 'o', color='#4ecdc4', markersize=10, 
               label='Centre O', markeredgewidth=2, markeredgecolor='white')
        
        # Points cardinaux
        cardinal_points = [(1, 0, '1'), (0, 1, 'i'), (-1, 0, '-1'), (0, -1, '-i')]
        for x, y, label in cardinal_points:
            ax.plot(x, y, 'o', color='white', markersize=6)
            ax.annotate(label, (x, y), xytext=(5, 5), textcoords='offset points',
                       color='white', fontweight='bold')
        
        ax.set_xlim(-1.5, 1.5)
        ax.set_ylim(-1.5, 1.5)
        ax.set_aspect('equal')
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('y', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Géométrie - Cercle Trigonométrique', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        plt.tight_layout()
        
        annotations = [
            "Rayon = 1",
            "Périmètre = 2π",
            "Triangle équilatéral: côté = √3"
        ]
        
        return GraphData(
            type='geometry',
            expressions=[],
            parameters={'radius': 1, 'inscribed': 'equilateral_triangle'},
            annotations=annotations,
            image_base64=self._save_to_base64()
        )
    
    def _create_analysis_graph(self, expressions: List[str]) -> GraphData:
        """Crée un graphique d'analyse (dérivées, intégrales)"""
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='#0f0f23')
        ax.set_facecolor('#1a1a3a')
        
        x_vals = np.linspace(-3, 3, 1000)
        
        if expressions:
            try:
                expr = sympify(expressions[0])
                f = lambdify(self.x, expr, 'numpy')
                
                # Fonction principale
                y_vals = f(x_vals)
                ax.plot(x_vals, y_vals, color='#00d4ff', linewidth=3, 
                       label=f'f(x) = {expr}', alpha=0.9)
                
                # Dérivée
                try:
                    derivative = diff(expr, self.x)
                    f_prime = lambdify(self.x, derivative, 'numpy')
                    y_prime_vals = f_prime(x_vals)
                    
                    ax.plot(x_vals, y_prime_vals, color='#ff6b6b', linewidth=3, 
                           label=f"f'(x) = {derivative}", alpha=0.9)
                    
                    # Points critiques
                    critical_points = solve(derivative, self.x)
                    for cp in critical_points[:3]:
                        if cp.is_real:
                            cp_val = float(cp.evalf())
                            if -3 <= cp_val <= 3:
                                y_cp = float(expr.subs(self.x, cp).evalf())
                                ax.plot(cp_val, y_cp, 'o', color='#4ecdc4', 
                                       markersize=12, markeredgewidth=2, markeredgecolor='white')
                
                except:
                    pass
                
            except:
                # Fonction de démonstration
                f = lambda x: x**3 - 2*x**2 + x
                f_prime = lambda x: 3*x**2 - 4*x + 1
                
                ax.plot(x_vals, f(x_vals), color='#00d4ff', linewidth=3, 
                       label='f(x) = x³ - 2x² + x', alpha=0.9)
                ax.plot(x_vals, f_prime(x_vals), color='#ff6b6b', linewidth=3, 
                       label="f'(x) = 3x² - 4x + 1", alpha=0.9)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.axhline(y=0, color='#ffffff', linewidth=1.5, alpha=0.8)
        ax.axvline(x=0, color='#ffffff', linewidth=1.5, alpha=0.8)
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('y', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Analyse - Fonction et sa Dérivée', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        legend = ax.legend(frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        plt.tight_layout()
        
        annotations = [
            "Points critiques marqués en bleu",
            "Dérivée nulle aux extrema locaux"
        ]
        
        return GraphData(
            type='analysis',
            expressions=expressions,
            parameters={'domain': [-3, 3]},
            annotations=annotations,
            image_base64=self._save_to_base64()
        )
    
    def _create_comparison_graph(self, expressions: List[str]) -> GraphData:
        """Crée un graphique de comparaison"""
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='#0f0f23')
        ax.set_facecolor('#1a1a3a')
        
        x_vals = np.linspace(0, 5, 1000)
        colors = ['#00d4ff', '#ff6b6b', '#4ecdc4', '#45b7d1']
        
        # Comparaisons standards si pas d'expressions spécifiques
        if not expressions:
            functions = [
                (lambda x: x, 'Linéaire: f(x) = x'),
                (lambda x: x**2, 'Quadratique: f(x) = x²'),
                (lambda x: np.exp(x), 'Exponentielle: f(x) = e^x'),
                (lambda x: np.log(x + 0.1), 'Logarithmique: f(x) = ln(x)')
            ]
        else:
            functions = []
            for expr_str in expressions[:4]:
                try:
                    expr = sympify(expr_str)
                    f = lambdify(self.x, expr, 'numpy')
                    functions.append((f, f'f(x) = {expr}'))
                except:
                    continue
            
            if not functions:
                functions = [(lambda x: x, 'Linéaire: f(x) = x')]
        
        for i, (func, label) in enumerate(functions):
            try:
                y_vals = func(x_vals)
                mask = np.isfinite(y_vals) & (y_vals < 1000)  # Éviter les valeurs trop grandes
                
                if np.any(mask):
                    ax.plot(x_vals[mask], y_vals[mask], color=colors[i % len(colors)], 
                           linewidth=3, label=label, alpha=0.9)
            except:
                continue
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('f(x)', fontsize=14, color='white', fontweight='bold')
        ax.set_title('Comparaison de Fonctions', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.set_yscale('log')  # Échelle log pour mieux voir les différences
        
        legend = ax.legend(frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        plt.tight_layout()
        
        annotations = [
            "Échelle logarithmique pour comparaison",
            "Différents types de croissance"
        ]
        
        return GraphData(
            type='comparison',
            expressions=expressions,
            parameters={'scale': 'log', 'domain': [0, 5]},
            annotations=annotations,
            image_base64=self._save_to_base64()
        )
    
    def _create_generic_graph(self, visual_type: str, expressions: List[str]) -> GraphData:
        """Crée un graphique générique"""
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='#0f0f23')
        ax.set_facecolor('#1a1a3a')
        
        # Graphique abstrait basé sur le concept
        x_vals = np.linspace(0, 4*np.pi, 1000)
        
        wave1 = np.sin(x_vals) * np.exp(-x_vals/15)
        wave2 = np.cos(x_vals * 1.2) * np.exp(-x_vals/20)
        
        ax.plot(x_vals, wave1, color='#00d4ff', linewidth=3, alpha=0.8, label='Concept A')
        ax.plot(x_vals, wave2, color='#ff6b6b', linewidth=3, alpha=0.8, label='Concept B')
        
        ax.fill_between(x_vals, wave1, alpha=0.2, color='#00d4ff')
        ax.fill_between(x_vals, wave2, alpha=0.2, color='#ff6b6b')
        
        ax.set_xlabel('x', fontsize=14, color='white', fontweight='bold')
        ax.set_ylabel('f(x)', fontsize=14, color='white', fontweight='bold')
        ax.set_title(f'Illustration - {visual_type.title()}', fontsize=16, 
                    color='#00d4ff', fontweight='bold', pad=20)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        
        legend = ax.legend(frameon=True, fancybox=True)
        legend.get_frame().set_facecolor('#2a2a4a')
        
        ax.tick_params(colors='white', labelsize=12)
        for spine in ax.spines.values():
            spine.set_color('#555577')
        
        plt.tight_layout()
        
        return GraphData(
            type=visual_type,
            expressions=expressions,
            parameters={},
            annotations=[f"Illustration conceptuelle de {visual_type}"],
            image_base64=self._save_to_base64()
        )
    
    def _save_to_base64(self) -> str:
        """Sauvegarde le graphique actuel en base64"""
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', 
                   facecolor='#0f0f23', edgecolor='none', dpi=100)
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        return image_base64

class ResponseBuilder:
    """Module 5: Construction de la réponse finale"""
    
    def __init__(self):
        self.stats = {
            'messages': 0,
            'visualizations': 0,
            'functions_analyzed': 0,
            'concepts_explained': 0
        }
    
    def build_response(self, explanation: str, graph_data: Optional[GraphData], 
                      processed_data: Dict, user_input: UserInput, 
                      debug_mode: bool = False) -> FinalResponse:
        """Assemble la réponse finale avec toutes les composantes"""
        logger.info("ResponseBuilder: Building final response")
        
        # Mise à jour des statistiques
        self.stats['messages'] += 1
        
        if graph_data:
            self.stats['visualizations'] += 1
        
        if processed_data.get('expressions'):
            self.stats['functions_analyzed'] += 1
        
        if any(word in explanation.lower() for word in ['concept', 'principe', 'théorème']):
            self.stats['concepts_explained'] += 1
        
        # Enrichissement du texte
        enriched_text = self._enrich_explanation(explanation, graph_data, processed_data)
        
        # Génération de suggestions
        suggestions = self._generate_suggestions(processed_data, user_input, graph_data)
        
        # Informations de debug
        debug_info = None
        if debug_mode:
            debug_info = {
                'user_input_type': 'follow_up' if user_input.follow_up else 'new',
                'expressions_found': len(processed_data.get('expressions', [])),
                'visual_generated': graph_data is not None,
                'visual_type': graph_data.type if graph_data else None,
                'processing_time': time.time(),
                'stats': self.stats.copy()
            }
        
        response = FinalResponse(
            text=enriched_text,
            graph=graph_data,
            suggestions=suggestions,
            debug_info=debug_info
        )
        
        logger.info(f"ResponseBuilder: Response built with {'graph' if graph_data else 'no graph'}")
        
        return response
    
    def _enrich_explanation(self, explanation: str, graph_data: Optional[GraphData], 
                          processed_data: Dict) -> str:
        """Enrichit l'explication avec des détails automatiques"""
        enriched = explanation
        
        # Ajouter des informations sur le graphique
        if graph_data:
            graph_info = f"\n\n📊 **Visualisation générée**: {graph_data.type.title()}"
            
            if graph_data.annotations:
                graph_info += f"\n🔍 **Points clés**: {', '.join(graph_data.annotations[:3])}"
            
            enriched += graph_info
        
        # Ajouter les points clés extraits
        if processed_data.get('key_points'):
            key_points = "\n\n💡 **Points importants à retenir**:\n"
            for i, point in enumerate(processed_data['key_points'][:3], 1):
                key_points += f"{i}. {point}\n"
            enriched += key_points
        
        return enriched
    
    def _generate_suggestions(self, processed_data: Dict, user_input: UserInput, 
                            graph_data: Optional[GraphData]) -> List[str]:
        """Génère des suggestions intelligentes pour la suite"""
        suggestions = []
        
        # Suggestions basées sur les expressions trouvées
        expressions = processed_data.get('expressions', [])
        if expressions:
            suggestions.append(f"Analyser la dérivée de {expressions[0]}")
            if len(expressions) == 1:
                suggestions.append(f"Comparer avec d'autres fonctions similaires")
            if 'x^2' in expressions[0] or 'x**2' in expressions[0]:
                suggestions.append("Explorer les propriétés des fonctions quadratiques")
        
        # Suggestions basées sur le type de visualisation
        if graph_data:
            if graph_data.type == 'function':
                suggestions.extend([
                    "Étudier les variations de cette fonction",
                    "Calculer l'aire sous la courbe"
                ])
            elif graph_data.type == 'statistics':
                suggestions.extend([
                    "Analyser la corrélation entre les variables",
                    "Effectuer un test statistique"
                ])
            elif graph_data.type == 'geometry':
                suggestions.extend([
                    "Calculer périmètres et aires",
                    "Explorer les propriétés trigonométriques"
                ])
        
        # Suggestions basées sur le contenu du message
        message_lower = user_input.message.lower()
        if 'dérivée' in message_lower:
            suggestions.append("Voir l'application aux tangentes et vitesses")
        if 'intégrale' in message_lower:
            suggestions.append("Calculer l'aire ou le volume correspondant")
        if 'limite' in message_lower:
            suggestions.append("Étudier la continuité de la fonction")
        
        # Suggestions depuis Mistral si disponibles
        mistral_suggestions = processed_data.get('suggestions', [])
        suggestions.extend(mistral_suggestions[:2])
        
        # Éliminer les doublons et limiter
        seen = set()
        unique_suggestions = []
        for suggestion in suggestions:
            if suggestion not in seen and len(unique_suggestions) < 4:
                seen.add(suggestion)
                unique_suggestions.append(suggestion)
        
        return unique_suggestions

class MathiaCore:
    """Contrôleur principal orchestrant tous les modules"""
    
    def __init__(self):
        self.input_handler = InputHandler()
        self.mistral_client = MistralClient()
        self.post_processor = PostProcessor()
        self.graph_generator = GraphGenerator()
        self.response_builder = ResponseBuilder()
        self.debug_mode = os.environ.get('MATHIA_DEBUG', 'false').lower() == 'true'
        
        logger.info("MathiaCore: Initialized with all modules")
    
    def process_message(self, message: str, context: str = None) -> Dict:
        """Flux principal: Question → Mistral → Post-traitement → Réponse"""
        start_time = time.time()
        
        try:
            logger.info(f"MathiaCore: Starting processing for: {message[:30]}...")
            
            # Module 1: InputHandler
            user_input = self.input_handler.process_input(message, context)
            
            # Module 2: MistralClient
            mistral_response = self.mistral_client.send_request(
                user_input, self.input_handler.conversation_history
            )
            
            if not mistral_response.success:
                return {
                    'success': False,
                    'error': mistral_response.error,
                    'response': 'Désolé, une erreur est survenue avec l\'IA. Pouvez-vous reformuler ?'
                }
            
            # Module 3: PostProcessor
            explanation, visual_needed, processed_data = self.post_processor.process_response(
                mistral_response
            )
            
            # Module 4: GraphGenerator (si nécessaire)
            graph_data = None
            if visual_needed and processed_data:
                graph_data = self.graph_generator.generate_graph(
                    processed_data.get('visual_type', 'function'),
                    processed_data.get('expressions', []),
                    explanation
                )
            
            # Module 5: ResponseBuilder
            final_response = self.response_builder.build_response(
                explanation, graph_data, processed_data, user_input, self.debug_mode
            )
            
            processing_time = time.time() - start_time
            logger.info(f"MathiaCore: Processing completed in {processing_time:.2f}s")
            
            return {
                'success': True,
                'response': final_response.text,
                'visual': graph_data.image_base64 if graph_data else None,
                'visual_type': graph_data.type if graph_data else None,
                'suggestions': final_response.suggestions,
                'math_detected': len(processed_data.get('expressions', [])) > 0,
                'processing_time': processing_time,
                'debug_info': final_response.debug_info if self.debug_mode else None
            }
            
        except Exception as e:
            logger.error(f"MathiaCore: Critical error - {e}")
            logger.error(traceback.format_exc())
            
            return {
                'success': False,
                'error': str(e),
                'response': 'Une erreur inattendue s\'est produite. Veuillez réessayer.',
                'debug_info': {'error': str(e), 'traceback': traceback.format_exc()} if self.debug_mode else None
            }
    
    def get_stats(self) -> Dict:
        """Retourne les statistiques consolidées"""
        return self.response_builder.stats

# Instance globale
mathia = MathiaCore()

@app.route('/')
def index():
    """Interface Mathia centrée sur le chat visuel"""
    return render_template_string(MATHIA_VISUAL_TEMPLATE)

@app.route('/api/chat', methods=['POST'])
def chat():
    """API principale de chat avec architecture modulaire"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        context = data.get('context')
        
        if not message:
            return jsonify({'success': False, 'error': 'Message requis'})
        
        result = mathia.process_message(message, context)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"API Chat: Error - {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def get_stats():
    """API des statistiques consolidées"""
    return jsonify(mathia.get_stats())

@app.route('/api/debug/<path:component>')
def debug_info(component):
    """API de debug pour chaque module"""
    if not mathia.debug_mode:
        return jsonify({'error': 'Debug mode disabled'}), 403
    
    debug_data = {}
    
    if component == 'input_handler':
        debug_data = {
            'conversation_length': len(mathia.input_handler.conversation_history),
            'last_inputs': [inp.message for inp in mathia.input_handler.conversation_history[-3:]]
        }
    elif component == 'mistral_client':
        debug_data = {
            'current_key': mathia.mistral_client.current_key,
            'key_errors': mathia.mistral_client.key_errors,
            'total_keys': len(mathia.mistral_client.api_keys)
        }
    elif component == 'stats':
        debug_data = mathia.get_stats()
    
    return jsonify(debug_data)

@app.route('/health')
def health_check():
    """Health check avec informations détaillées"""
    health_status = {
        'status': 'OK',
        'service': 'Mathia Visual Modular',
        'version': '4.0',
        'modules': {
            'input_handler': 'active',
            'mistral_client': 'active',
            'post_processor': 'active',
            'graph_generator': 'active',
            'response_builder': 'active'
        },
        'debug_mode': mathia.debug_mode,
        'stats': mathia.get_stats()
    }
    
    return jsonify(health_status), 200

# Template HTML identique mais avec ajouts pour le debug
MATHIA_VISUAL_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia Visual - Assistant Mathématique Modulaire</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <script>
        window.MathJax = {
            tex: { inlineMath: [[', '], ['\\\\(', '\\\\)']] },
            svg: { fontCache: 'global' }
        };
    </script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #0f0f23; --bg-secondary: #1a1a3a; --bg-tertiary: #2a2a4a;
            --text-primary: #ffffff; --text-secondary: #b8bcc8;
            --accent: #00d4ff; --accent-secondary: #667eea;
            --success: #00ff88; --error: #ff4757; --warning: #ffa502;
            --border: rgba(255, 255, 255, 0.1); --shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
        }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
            color: var(--text-primary); min-height: 100vh;
        }
        
        .header {
            position: sticky; top: 0; z-index: 100;
            background: rgba(15, 15, 35, 0.95); backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--border); padding: 1rem 0;
        }
        
        .header-content {
            max-width: 1200px; margin: 0 auto; padding: 0 2rem;
            display: flex; justify-content: space-between; align-items: center;
        }
        
        .logo { font-size: 2rem; font-weight: 800; color: var(--accent); }
        
        .stats { display: flex; gap: 2rem; font-size: 0.9rem; color: var(--text-secondary); }
        
        .stat-item {
            display: flex; align-items: center; gap: 0.5rem;
            padding: 0.5rem 1rem; background: var(--bg-tertiary);
            border-radius: 15px; border: 1px solid var(--border);
        }
        
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        
        .chat-container {
            background: var(--bg-secondary); border-radius: 25px; padding: 2rem;
            border: 1px solid var(--border); box-shadow: var(--shadow);
            display: flex; flex-direction: column; height: calc(100vh - 200px);
        }
        
        .chat-title { font-size: 1.5rem; font-weight: 700; color: var(--accent); margin-bottom: 1.5rem; text-align: center; }
        
        .chat-messages {
            flex: 1; overflow-y: auto; padding: 1rem; background: rgba(0, 0, 0, 0.2);
            border-radius: 15px; border: 1px solid var(--border); margin-bottom: 1.5rem; scroll-behavior: smooth;
        }
        
        .message { margin-bottom: 2rem; animation: messageSlide 0.4s ease; }
        @keyframes messageSlide { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        
        .message-user { display: flex; justify-content: flex-end; margin-bottom: 1rem; }
        .message-assistant { display: flex; justify-content: flex-start; margin-bottom: 2rem; }
        
        .message-bubble {
            max-width: 80%; padding: 1.2rem 1.8rem; border-radius: 20px;
            word-wrap: break-word; line-height: 1.6;
        }
        
        .message-user .message-bubble {
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            color: white; border-bottom-right-radius: 8px; box-shadow: 0 4px 15px rgba(0, 212, 255, 0.3);
        }
        
        .message-assistant .message-bubble {
            background: var(--bg-tertiary); color: var(--text-primary);
            border: 1px solid var(--border); border-bottom-left-radius: 8px;
        }
        
        .message-sender { font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.5rem; font-weight: 600; }
        
        .visual-container {
            margin-top: 1.5rem; padding: 1.5rem; background: rgba(0, 0, 0, 0.3);
            border-radius: 15px; border: 1px solid var(--border); text-align: center;
        }
        
        .visual-container img { max-width: 100%; height: auto; border-radius: 10px; box-shadow: 0 8px 25px rgba(0, 0, 0, 0.4); }
        
        .visual-label {
            color: var(--accent); font-size: 0.9rem; margin-bottom: 1rem; font-weight: 600;
            display: flex; align-items: center; justify-content: center; gap: 0.5rem;
        }
        
        .suggestions-container {
            margin-top: 1rem; display: flex; flex-wrap: wrap; gap: 0.5rem;
        }
        
        .suggestion-chip {
            background: rgba(0, 212, 255, 0.1); border: 1px solid var(--accent);
            padding: 0.4rem 0.8rem; border-radius: 15px; font-size: 0.8rem;
            cursor: pointer; transition: all 0.3s ease;
        }
        
        .suggestion-chip:hover {
            background: rgba(0, 212, 255, 0.2); transform: translateY(-1px);
        }
        
        .chat-input-container {
            display: flex; gap: 1rem; align-items: flex-end; background: var(--bg-tertiary);
            padding: 1.5rem; border-radius: 20px; border: 1px solid var(--border);
        }
        
        .chat-input {
            flex: 1; padding: 1.2rem 1.5rem; background: var(--bg-primary);
            border: 2px solid var(--border); border-radius: 15px; color: var(--text-primary);
            font-size: 1rem; resize: vertical; min-height: 60px; max-height: 150px;
            transition: all 0.3s ease; font-family: inherit;
        }
        
        .chat-input:focus {
            outline: none; border-color: var(--accent); box-shadow: 0 0 0 4px rgba(0, 212, 255, 0.1);
            background: rgba(26, 26, 58, 0.8);
        }
        
        .chat-input::placeholder { color: var(--text-secondary); opacity: 0.7; }
        
        .send-button {
            padding: 1.2rem 2rem; background: linear-gradient(135deg, var(--accent) 0%, var(--accent-secondary) 100%);
            border: none; border-radius: 15px; color: white; font-weight: 600;
            cursor: pointer; transition: all 0.3s ease; white-space: nowrap;
        }
        
        .send-button:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0, 212, 255, 0.4); }
        .send-button:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        
        .loading-spinner {
            width: 16px; height: 16px; border: 2px solid rgba(255, 255, 255, 0.3);
            border-top: 2px solid white; border-radius: 50%; animation: spin 1s linear infinite;
            display: inline-block; margin-right: 0.5rem;
        }
        
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        .notification {
            position: fixed; top: 100px; right: 20px; padding: 1rem 1.5rem; border-radius: 15px;
            color: white; font-weight: 600; z-index: 1000; transform: translateX(400px);
            transition: all 0.4s ease; max-width: 350px; box-shadow: var(--shadow); backdrop-filter: blur(20px);
        }
        
        .notification.show { transform: translateX(0); }
        .notification.success { background: linear-gradient(135deg, var(--success), #00cc77); }
        .notification.error { background: linear-gradient(135deg, var(--error), #cc3344); }
        .notification.info { background: linear-gradient(135deg, var(--accent), var(--accent-secondary)); }
        
        .help-message {
            background: rgba(0, 212, 255, 0.1); border: 1px solid var(--accent);
            border-radius: 15px; padding: 1.5rem; margin-bottom: 2rem; color: var(--text-primary);
        }
        
        .help-title { color: var(--accent); font-weight: 600; margin-bottom: 0.5rem; }
        
        .examples { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1rem; }
        
        .example {
            background: var(--bg-tertiary); padding: 1rem; border-radius: 10px; border: 1px solid var(--border);
            cursor: pointer; transition: all 0.3s ease; font-size: 0.9rem;
        }
        
        .example:hover {
            background: rgba(0, 212, 255, 0.1); border-color: var(--accent); transform: translateY(-2px);
        }
        
        .chat-messages::-webkit-scrollbar { width: 6px; }
        .chat-messages::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
        .chat-messages::-webkit-scrollbar-thumb { background: var(--accent); border-radius: 10px; }
        .chat-messages::-webkit-scrollbar-thumb:hover { background: var(--accent-secondary); }
        
        @media (max-width: 768px) {
            .header-content { flex-direction: column; gap: 1rem; padding: 0 1rem; }
            .stats { flex-direction: column; gap: 0.5rem; align-items: center; }
            .container { padding: 1rem; }
            .chat-container { height: calc(100vh - 250px); padding: 1.5rem; }
            .chat-input-container { flex-direction: column; gap: 1rem; }
            .message-bubble { max-width: 95%; }
            .examples { grid-template-columns: 1fr; }
            .notification { right: 10px; max-width: calc(100vw - 20px); }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div class="logo">🎨 Mathia Visual</div>
            <div class="stats">
                <div class="stat-item"><span>💬</span><span id="messageCount">0</span> messages</div>
                <div class="stat-item"><span>📊</span><span id="visualCount">0</span> visuels</div>
                <div class="stat-item"><span>🧮</span><span id="functionCount">0</span> fonctions</div>
                <div class="stat-item"><span>💡</span><span id="conceptCount">0</span> concepts</div>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="chat-container">
            <div class="chat-title">Assistant Mathématique Modulaire</div>
            
            <div id="chatMessages" class="chat-messages">
                <div class="help-message">
                    <div class="help-title">Mathia 4.0 - Architecture Modulaire</div>
                    <p>Assistant avec flux Question → Mistral → Post-traitement → Visualisation → Réponse enrichie</p>
                    
                    <div class="examples">
                        <div class="example" onclick="useExample('Explique f(x) = x² - 4x + 3 avec graphique')">📈 Fonction quadratique</div>
                        <div class="example" onclick="useExample('Compare sin(x), cos(x) et tan(x)')">📊 Comparaison trigonométrique</div>
                        <div class="example" onclick="useExample('Analyse statistique de deux échantillons')">📉 Statistiques</div>
                        <div class="example" onclick="useExample('Dérivée de e^x * ln(x)')">🔍 Calcul différentiel</div>
                        <div class="example" onclick="useExample('Géométrie du cercle et triangle inscrit')">🎯 Géométrie</div>
                        <div class="example" onclick="useExample('Intégrale de x*sin(x) par parties')">∫ Intégration</div>
                    </div>
                </div>
                
                <div class="message-assistant">
                    <div class="message-bubble">
                        <div class="message-sender">Mathia</div>
                        Salut ! Je suis Mathia avec architecture modulaire. Mon processus : analyse de votre question → consultation IA → extraction des données → génération de visualisations → réponse enrichie. Testez-moi !
                    </div>
                </div>
            </div>
            
            <div class="chat-input-container">
                <textarea id="chatInput" class="chat-input" 
                          placeholder="Question mathématique... (ex: 'Dérive f(x) = x³ + 2x² - 5x + 1 et trace le graphique')"
                          rows="2"></textarea>
                <button id="sendButton" class="send-button">Envoyer</button>
            </div>
        </div>
    </div>

    <script>
        let isLoading = false;
        
        document.addEventListener('DOMContentLoaded', function() {
            setupEventListeners();
            loadStats();
            focusChatInput();
        });
        
        function setupEventListeners() {
            const chatInput = document.getElementById('chatInput');
            const sendButton = document.getElementById('sendButton');
            
            chatInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
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
            setTimeout(() => document.getElementById('chatInput').focus(), 100);
        }
        
        async function sendMessage() {
            if (isLoading) return;
            
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            
            if (!message) {
                showNotification('Veuillez entrer un message', 'error');
                return;
            }
            
            addUserMessage(message);
            input.value = '';
            input.style.height = 'auto';
            
            setLoading(true);
            const tempId = addAssistantMessage('', true);
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                const data = await response.json();
                document.getElementById(tempId).remove();
                
                if (data.success) {
                    addAssistantMessage(data.response, false, data.visual, data.visual_type, data.suggestions);
                    
                    if (data.visual) {
                        showNotification('Visualisation générée !', 'success');
                    }
                    
                    if (data.debug_info) {
                        console.log('Debug Info:', data.debug_info);
                    }
                    
                    if (data.processing_time) {
                        showNotification(`Traité en ${data.processing_time.toFixed(2)}s`, 'info');
                    }
                } else {
                    addAssistantMessage('Erreur: ' + data.error, false);
                    showNotification('Erreur lors du traitement', 'error');
                }
                
                await loadStats();
                
            } catch (error) {
                document.getElementById(tempId).remove();
                addAssistantMessage('Erreur de connexion. Réessayez.', false);
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
        }
        
        function addAssistantMessage(message, isLoading = false, visualData = null, visualType = null, suggestions = null) {
            const container = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            messageDiv.id = messageId;
            messageDiv.className = 'message-assistant';
            
            let content = `
                <div class="message-bubble">
                    <div class="message-sender">Mathia</div>
                    ${isLoading ? '<div class="loading-spinner"></div>Analyse modulaire en cours...' : message}
            `;
            
            if (visualData && !isLoading) {
                const visualTypeLabels = {
                    'function': '📈 Graphique de Fonction',
                    'statistics': '📊 Analyse Statistique',
                    'geometry': '🎯 Illustration Géométrique',
                    'analysis': '🔍 Analyse Mathématique',
                    'comparison': '⚖️ Comparaison Visuelle'
                };
                
                const label = visualTypeLabels[visualType] || '📊 Visualisation';
                
                content += `
                    <div class="visual-container">
                        <div class="visual-label">${label}</div>
                        <img src="data:image/png;base64,${visualData}" alt="Visualisation mathématique">
                    </div>
                `;
            }
            
            if (suggestions && suggestions.length > 0 && !isLoading) {
                content += `
                    <div class="suggestions-container">
                        ${suggestions.map(suggestion => 
                            `<div class="suggestion-chip" onclick="useExample('${suggestion}')">${suggestion}</div>`
                        ).join('')}
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
                sendButton.innerHTML = '<div class="loading-spinner"></div>Traitement...';
            } else {
                sendButton.innerHTML = 'Envoyer';
            }
        }
        
        function scrollToBottom() {
            const container = document.getElementById('chatMessages');
            setTimeout(() => container.scrollTop = container.scrollHeight, 100);
        }
        
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                document.getElementById('messageCount').textContent = stats.messages || 0;
                document.getElementById('visualCount').textContent = stats.visualizations || 0;
                document.getElementById('functionCount').textContent = stats.functions_analyzed || 0;
                document.getElementById('conceptCount').textContent = stats.concepts_explained || 0;
                
                animateCounters();
                
            } catch (error) {
                console.log('Erreur stats:', error);
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
            if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
                e.preventDefault();
                if (confirm('Nettoyer la conversation ?')) {
                    const messagesContainer = document.getElementById('chatMessages');
                    const userMessages = messagesContainer.querySelectorAll('.message-user, .message-assistant:not(:first-child)');
                    userMessages.forEach(msg => msg.remove());
                    focusChatInput();
                }
            }
            
            if (e.key === 'Escape' && isLoading) {
                setLoading(false);
                focusChatInput();
            }
        });
        
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden) loadStats();
        });
        
        loadStats();
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("🎨 MATHIA VISUAL V4.0 - Architecture Modulaire")
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
        print(f"🧩 Debug mode: {mathia.debug_mode}")
        print(f"🔑 Clés Mistral: {len(mathia.mistral_client.api_keys)} configurées")
        
        print("\n🏗️ Architecture modulaire:")
        print("   1. InputHandler - Traitement des entrées utilisateur")
        print("   2. MistralClient - Communication avec l'IA")
        print("   3. PostProcessor - Extraction des données structurées")
        print("   4. GraphGenerator - Génération des visualisations")
        print("   5. ResponseBuilder - Assembly de la réponse finale")
        
        print("\n🎯 Flux de traitement:")
        print("   Question → Mistral → Post-traitement → Graph → Réponse enrichie")
        
        print("\n🚀 Fonctionnalités avancées:")
        print("   • Validation robuste des expressions mathématiques")
        print("   • Gestion d'erreurs à chaque étape")
        print("   • Cache intelligent et optimisations")
        print("   • Suggestions interactives contextuelles")
        print("   • Annotations automatiques des graphiques")
        print("   • API de debug pour le développement")
        print("   • Statistiques consolidées en temps réel")
        
        print("\n📊 Types de visualisations:")
        print("   • Fonctions 2D avec points critiques")
        print("   • Analyses statistiques (histogrammes, moyennes)")
        print("   • Géométrie (cercles, triangles, formes)")
        print("   • Calcul différentiel (fonctions + dérivées)")
        print("   • Comparaisons multi-fonctions")
        
        print("\n🚀 Démarrage du serveur modulaire...")
        
    except ImportError as e:
        print(f"❌ ERREUR: {e}")
        exit(1)
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True)
