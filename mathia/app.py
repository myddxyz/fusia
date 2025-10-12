from flask import Flask, request, jsonify, render_template_string
import os
import json
from mistralai import Mistral
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@dataclass
class MathConcept:
    """Structure pour un concept mathématique"""
    name: str
    definition: str
    category: str
    related_concepts: List[str]
    examples: List[str]
    difficulty: int  # 1-5
    keywords: List[str]

class MathiaExplorer:
    """Explorateur interactif de concepts mathématiques"""
    
    def __init__(self):
        self.api_keys = [
            os.environ.get('MISTRAL_KEY_1', 'FabLUUhEyzeKgHWxMQp2QWjcojqtfbMX'),
            os.environ.get('MISTRAL_KEY_2', '9Qgem2NC1g1sJ1gU5a7fCRJWasW3ytqF'),
            os.environ.get('MISTRAL_KEY_3', 'cvkQHVcomFFEW47G044x2p4DTyk5BIc7')
        ]
        self.current_key = 0
        self.concept_database = self._initialize_concepts()
        self.exploration_history = []
        
        logger.info("Mathia Explorer initialized")
    
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
    
    def _initialize_concepts(self):
        """Initialise la base de concepts mathématiques"""
        return {
            "fonction": MathConcept(
                name="Fonction",
                definition="Une fonction est une relation qui associe à chaque élément d'un ensemble de départ (domaine) exactement un élément d'un ensemble d'arrivée.",
                category="Analyse",
                related_concepts=["dérivée", "intégrale", "limite", "continuité", "domaine"],
                examples=["f(x) = x²", "f(x) = sin(x)", "f(x) = 2x + 3"],
                difficulty=2,
                keywords=["relation", "correspondance", "variable", "image", "antécédent"]
            ),
            "dérivée": MathConcept(
                name="Dérivée",
                definition="La dérivée d'une fonction mesure la vitesse à laquelle la fonction change. C'est le taux de variation instantané.",
                category="Analyse",
                related_concepts=["fonction", "tangente", "vitesse", "accélération", "intégrale"],
                examples=["d/dx(x²) = 2x", "d/dx(sin(x)) = cos(x)", "d/dx(eˣ) = eˣ"],
                difficulty=3,
                keywords=["variation", "pente", "tangente", "instantané", "limite"]
            ),
            "nombre complexe": MathConcept(
                name="Nombre Complexe",
                definition="Un nombre complexe est un nombre de la forme a + bi où a et b sont des nombres réels et i est l'unité imaginaire (i² = -1).",
                category="Algèbre",
                related_concepts=["nombre réel", "plan complexe", "module", "argument", "conjugué"],
                examples=["3 + 4i", "2i", "-1 + i", "5"],
                difficulty=3,
                keywords=["imaginaire", "réel", "partie", "module", "argument"]
            ),
            "probabilité": MathConcept(
                name="Probabilité",
                definition="La probabilité mesure la chance qu'un événement se produise. Elle est comprise entre 0 (impossible) et 1 (certain).",
                category="Statistiques",
                related_concepts=["événement", "variable aléatoire", "espérance", "variance", "loi"],
                examples=["P(pile) = 0.5 pour une pièce", "P(dé = 6) = 1/6", "P(A ∪ B)"],
                difficulty=2,
                keywords=["chance", "aléatoire", "fréquence", "événement", "mesure"]
            ),
            "matrice": MathConcept(
                name="Matrice",
                definition="Une matrice est un tableau rectangulaire de nombres organisés en lignes et en colonnes.",
                category="Algèbre Linéaire",
                related_concepts=["déterminant", "vecteur", "système", "transformation", "inverse"],
                examples=["[[1,2],[3,4]]", "matrice identité", "matrice nulle"],
                difficulty=3,
                keywords=["tableau", "lignes", "colonnes", "linéaire", "transformation"]
            ),
            "limite": MathConcept(
                name="Limite",
                definition="La limite d'une fonction en un point décrit le comportement de la fonction lorsque la variable s'approche de ce point.",
                category="Analyse",
                related_concepts=["fonction", "continuité", "asymptote", "infiniment petit", "dérivée"],
                examples=["lim(x→0) sin(x)/x = 1", "lim(x→∞) 1/x = 0"],
                difficulty=3,
                keywords=["approche", "tendance", "infini", "comportement", "voisinage"]
            ),
            "intégrale": MathConcept(
                name="Intégrale",
                definition="L'intégrale mesure l'aire sous une courbe. C'est l'opération inverse de la dérivée.",
                category="Analyse",
                related_concepts=["dérivée", "aire", "primitive", "fonction", "somme"],
                examples=["∫x² dx = x³/3 + C", "∫sin(x) dx = -cos(x) + C"],
                difficulty=3,
                keywords=["aire", "primitive", "accumulation", "somme", "antidérivée"]
            ),
            "vecteur": MathConcept(
                name="Vecteur",
                definition="Un vecteur est un objet mathématique caractérisé par une direction et une norme (longueur).",
                category="Algèbre Linéaire",
                related_concepts=["matrice", "norme", "produit scalaire", "base", "espace"],
                examples=["(3, 4)", "(1, 0, 0)", "vecteur vitesse"],
                difficulty=2,
                keywords=["direction", "norme", "composante", "flèche", "espace"]
            ),
            "équation": MathConcept(
                name="Équation",
                definition="Une équation est une égalité contenant une ou plusieurs inconnues à déterminer.",
                category="Algèbre",
                related_concepts=["inconnue", "solution", "système", "racine", "identité"],
                examples=["2x + 3 = 7", "x² - 5x + 6 = 0", "sin(x) = 0.5"],
                difficulty=1,
                keywords=["égalité", "inconnue", "résolution", "solution", "racine"]
            ),
            "ensemble": MathConcept(
                name="Ensemble",
                definition="Un ensemble est une collection d'objets mathématiques distincts, appelés éléments.",
                category="Fondements",
                related_concepts=["élément", "sous-ensemble", "union", "intersection", "cardinal"],
                examples=["ℕ (nombres naturels)", "{1, 2, 3}", "ensemble vide ∅"],
                difficulty=1,
                keywords=["collection", "élément", "appartenance", "inclusion", "cardinal"]
            )
        }
    
    def explore_concept(self, query: str) -> Dict:
        """Explore un concept mathématique"""
        try:
            # Nettoyer la requête
            query_clean = query.lower().strip()
            
            # Recherche exacte
            if query_clean in self.concept_database:
                concept = self.concept_database[query_clean]
                ai_explanation = self._get_ai_explanation(concept)
                
                self.exploration_history.append(query_clean)
                
                return {
                    'success': True,
                    'concept': {
                        'name': concept.name,
                        'definition': concept.definition,
                        'category': concept.category,
                        'related_concepts': concept.related_concepts,
                        'examples': concept.examples,
                        'difficulty': concept.difficulty,
                        'difficulty_text': self._get_difficulty_text(concept.difficulty)
                    },
                    'ai_explanation': ai_explanation,
                    'found_in_database': True
                }
            
            # Recherche par mots-clés
            matches = self._search_by_keywords(query_clean)
            if matches:
                best_match = matches[0]
                concept = self.concept_database[best_match]
                ai_explanation = self._get_ai_explanation(concept)
                
                return {
                    'success': True,
                    'concept': {
                        'name': concept.name,
                        'definition': concept.definition,
                        'category': concept.category,
                        'related_concepts': concept.related_concepts,
                        'examples': concept.examples,
                        'difficulty': concept.difficulty,
                        'difficulty_text': self._get_difficulty_text(concept.difficulty)
                    },
                    'ai_explanation': ai_explanation,
                    'found_in_database': True,
                    'search_hint': f"Concept trouvé via recherche: {best_match}"
                }
            
            # Si pas dans la base, utiliser l'IA
            ai_response = self._get_ai_concept_explanation(query)
            
            return {
                'success': True,
                'concept': {
                    'name': query.title(),
                    'definition': 'Concept généré par IA',
                    'category': 'Général',
                    'related_concepts': [],
                    'examples': [],
                    'difficulty': 0,
                    'difficulty_text': 'Variable'
                },
                'ai_explanation': ai_response,
                'found_in_database': False
            }
            
        except Exception as e:
            logger.error(f"Error exploring concept: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Erreur lors de l\'exploration du concept'
            }
    
    def _search_by_keywords(self, query: str) -> List[str]:
        """Recherche par mots-clés"""
        matches = []
        query_words = set(query.split())
        
        for concept_name, concept in self.concept_database.items():
            # Recherche dans le nom
            if query in concept_name:
                matches.append(concept_name)
                continue
            
            # Recherche dans les mots-clés
            keyword_matches = sum(1 for keyword in concept.keywords if keyword in query or query in keyword)
            if keyword_matches > 0:
                matches.append(concept_name)
        
        return matches
    
    def _get_difficulty_text(self, difficulty: int) -> str:
        """Convertit le niveau de difficulté en texte"""
        levels = {
            1: "Débutant",
            2: "Intermédiaire",
            3: "Avancé",
            4: "Expert",
            5: "Maître"
        }
        return levels.get(difficulty, "Inconnu")
    
    def _get_ai_explanation(self, concept: MathConcept) -> str:
        """Obtient une explication IA enrichie pour un concept"""
        try:
            client = self.get_mistral_client()
            
            prompt = f"""Tu es Mathia, un expert mathématique pédagogue.

Explique le concept de "{concept.name}" de manière claire et engageante.

Contexte:
- Définition: {concept.definition}
- Catégorie: {concept.category}
- Exemples: {', '.join(concept.examples)}

Ta réponse doit:
1. Donner une explication intuitive (2-3 phrases)
2. Expliquer pourquoi c'est important
3. Donner un conseil pour mieux comprendre
4. Être accessible et motivante

Reste concis (maximum 150 mots) et évite le jargon technique excessif."""

            response = client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"AI explanation error: {e}")
            return f"Le concept de {concept.name} est fondamental en mathématiques. {concept.definition}"
    
    def _get_ai_concept_explanation(self, query: str) -> str:
        """Obtient une explication IA pour un concept non répertorié"""
        try:
            client = self.get_mistral_client()
            
            prompt = f"""Tu es Mathia, un expert mathématique pédagogue.

Un utilisateur cherche à comprendre: "{query}"

Fournis une explication claire et structurée:
1. Définition simple (2-3 phrases)
2. Exemples concrets
3. Concepts liés
4. Application pratique

Reste pédagogique et accessible. Maximum 200 mots."""

            response = client.chat.complete(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=400
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"AI concept explanation error: {e}")
            return f"Je recherche des informations sur '{query}'. Ce concept semble lié aux mathématiques, mais j'ai besoin de plus de contexte pour vous donner une explication détaillée."
    
    def get_all_concepts(self) -> List[Dict]:
        """Retourne tous les concepts disponibles"""
        return [
            {
                'name': concept.name,
                'category': concept.category,
                'difficulty': concept.difficulty,
                'difficulty_text': self._get_difficulty_text(concept.difficulty)
            }
            for concept in self.concept_database.values()
        ]
    
    def get_concepts_by_category(self, category: str) -> List[Dict]:
        """Retourne les concepts d'une catégorie"""
        return [
            {
                'name': concept.name,
                'category': concept.category,
                'difficulty': concept.difficulty
            }
            for concept in self.concept_database.values()
            if concept.category.lower() == category.lower()
        ]

# Instance globale
mathia = MathiaExplorer()

@app.route('/')
def index():
    """Interface principale de Mathia"""
    return render_template_string(MATHIA_TEMPLATE)

@app.route('/api/explore', methods=['POST'])
def explore():
    """API d'exploration de concepts"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'success': False, 'error': 'Requête vide'})
        
        result = mathia.explore_concept(query)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Explore API error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/concepts', methods=['GET'])
def get_concepts():
    """Obtient la liste de tous les concepts"""
    try:
        concepts = mathia.get_all_concepts()
        return jsonify({'success': True, 'concepts': concepts})
    except Exception as e:
        logger.error(f"Concepts API error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/concepts/<category>', methods=['GET'])
def get_concepts_by_category(category):
    """Obtient les concepts d'une catégorie"""
    try:
        concepts = mathia.get_concepts_by_category(category)
        return jsonify({'success': True, 'concepts': concepts})
    except Exception as e:
        logger.error(f"Category API error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'OK',
        'service': 'Mathia Explorer',
        'version': '3.0',
        'concepts': len(mathia.concept_database)
    })

# Template HTML avec design moderne
MATHIA_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mathia - Explorateur de Concepts Mathématiques</title>
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
            padding: 20px;
        }
        
        .back-link {
            position: fixed;
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
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 80px 20px 40px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 50px;
        }
        
        .header h1 {
            font-size: 3.5rem;
            color: white;
            margin-bottom: 10px;
            text-shadow: 0 2px 20px rgba(0,0,0,0.2);
        }
        
        .header p {
            color: rgba(255,255,255,0.9);
            font-size: 1.3rem;
        }
        
        .search-container {
            max-width: 700px;
            margin: 0 auto 40px;
        }
        
        .search-box {
            position: relative;
        }
        
        .search-input {
            width: 100%;
            padding: 20px 60px 20px 25px;
            border: none;
            border-radius: 50px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 1.1rem;
            box-shadow: 20px 20px 60px var(--shadow-light), -20px -20px 60px var(--shadow-dark);
            transition: all 0.3s ease;
        }
        
        .search-input:focus {
            outline: none;
            box-shadow: inset 8px 8px 16px var(--shadow-light), inset -8px -8px 16px var(--shadow-dark);
        }
        
        .search-btn {
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            background: var(--gradient-main);
            border: none;
            color: white;
            padding: 12px 24px;
            border-radius: 30px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .search-btn:hover {
            transform: translateY(-50%) scale(1.05);
        }
        
        .suggestions {
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
        }
        
        .suggestion-tag {
            background: rgba(255,255,255,0.2);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }
        
        .suggestion-tag:hover {
            background: rgba(255,255,255,0.3);
            transform: translateY(-2px);
        }
        
        .content-area {
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 30px;
            margin-top: 40px;
        }
        
        .sidebar {
            background: var(--bg-primary);
            border-radius: 30px;
            padding: 30px;
            height: fit-content;
            box-shadow: 20px 20px 60px var(--shadow-light), -20px -20px 60px var(--shadow-dark);
        }
        
        .sidebar h3 {
            color: var(--accent);
            margin-bottom: 20px;
            font-size: 1.3rem;
        }
        
        .concept-list {
            list-style: none;
        }
        
        .concept-item {
            padding: 12px 15px;
            margin-bottom: 10px;
            background: var(--bg-primary);
            border-radius: 15px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 5px 5px 10px var(--shadow-light), -5px -5px 10px var(--shadow-dark);
        }
        
        .concept-item:hover {
            transform: translateX(5px);
            box-shadow: 8px 8px 16px var(--shadow-light), -8px -8px 16px var(--shadow-dark);
        }
        
        .concept-item .name {
            font-weight: 600;
            color: var(--text-primary);
            display: block;
            margin-bottom: 5px;
        }
        
        .concept-item .category {
            font-size: 0.85rem;
            color: var(--text-secondary);
        }
        
        .main-content {
            background: var(--bg-primary);
            border-radius: 30px;
            padding: 40px;
            min-height: 500px;
            box-shadow: 20px 20px 60px var(--shadow-light), -20px -20px 60px var(--shadow-dark);
        }
        
        .welcome-message {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }
        
        .welcome-message h2 {
            color: var(--accent);
            font-size: 2rem;
            margin-bottom: 20px;
        }
        
        .concept-card {
            animation: fadeIn 0.5s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .concept-header {
            border-bottom: 3px solid var(--accent);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        
        .concept-title {
            font-size: 2.5rem;
            color: var(--accent);
            margin-bottom: 10px;
        }
        
        .concept-meta {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        
        .meta-tag {
            background: var(--bg-secondary);
            padding: 8px 16px;
            border-radius: 15px;
            font-size: 0.9rem;
            color: var(--text-primary);
        }
        
        .concept-section {
            margin-bottom: 30px;
        }
        
        .section-title {
            font-size: 1.3rem;
            color: var(--accent);
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .section-content {
            background: var(--bg-tertiary);
            padding: 20px;
            border-radius: 15px;
            line-height: 1.8;
            border-left: 4px solid var(--accent);
        }
        
        .examples-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .example-card {
            background: var(--bg-tertiary);
            padding: 15px;
            border-radius: 12px;
            text-align: center;
            font-family: "Courier New", monospace;
            color: var(--text-primary);
            border: 2px solid var(--bg-secondary);
        }
        
        .related-concepts {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        
        .related-tag {
            background: var(--gradient-main);
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 500;
        }
        
        .related-tag:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .difficulty-indicator {
            display: flex;
            gap: 5px;
            align-items: center;
        }
        
        .difficulty-star {
            color: var(--warning);
            font-size: 1.2rem;
        }
        
        .difficulty-star.empty {
            color: var(--bg-secondary);
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(102, 126, 234, 0.3);
            border-radius: 50%;
            border-top-color: var(--accent);
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
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
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.success { background: var(--success); }
        .notification.error { background: var(--error); }
        .notification.info { background: var(--accent); }
        
        @media (max-width: 968px) {
            .content-area {
                grid-template-columns: 1fr;
            }
            
            .sidebar {
                order: 2;
            }
            
            .main-content {
                order: 1;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <a href="/" class="back-link">← Retour au Hub</a>
    
    <div class="container">
        <div class="header">
            <h1>🔢 Mathia</h1>
            <p>Explorateur Interactif de Concepts Mathématiques</p>
        </div>
        
        <div class="search-container">
            <div class="search-box">
                <input type="text" 
                       id="searchInput" 
                       class="search-input" 
                       placeholder="Quel concept voulez-vous explorer ? (ex: fonction, probabilité...)"
                       onkeypress="if(event.key==='Enter') exploreConcept()">
                <button class="search-btn" onclick="exploreConcept()">Explorer</button>
            </div>
            
            <div class="suggestions">
                <span class="suggestion-tag" onclick="quickExplore('fonction')">Fonction</span>
                <span class="suggestion-tag" onclick="quickExplore('dérivée')">Dérivée</span>
                <span class="suggestion-tag" onclick="quickExplore('probabilité')">Probabilité</span>
                <span class="suggestion-tag" onclick="quickExplore('vecteur')">Vecteur</span>
                <span class="suggestion-tag" onclick="quickExplore('matrice')">Matrice</span>
                <span class="suggestion-tag" onclick="quickExplore('nombre complexe')">Nombre Complexe</span>
            </div>
        </div>
        
        <div class="content-area">
            <div class="sidebar">
                <h3>📚 Concepts Disponibles</h3>
                <ul class="concept-list" id="conceptList">
                    <li class="concept-item" onclick="quickExplore('fonction')">
                        <span class="name">Fonction</span>
                        <span class="category">Analyse</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('dérivée')">
                        <span class="name">Dérivée</span>
                        <span class="category">Analyse</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('intégrale')">
                        <span class="name">Intégrale</span>
                        <span class="category">Analyse</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('limite')">
                        <span class="name">Limite</span>
                        <span class="category">Analyse</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('nombre complexe')">
                        <span class="name">Nombre Complexe</span>
                        <span class="category">Algèbre</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('matrice')">
                        <span class="name">Matrice</span>
                        <span class="category">Algèbre Linéaire</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('vecteur')">
                        <span class="name">Vecteur</span>
                        <span class="category">Algèbre Linéaire</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('probabilité')">
                        <span class="name">Probabilité</span>
                        <span class="category">Statistiques</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('équation')">
                        <span class="name">Équation</span>
                        <span class="category">Algèbre</span>
                    </li>
                    <li class="concept-item" onclick="quickExplore('ensemble')">
                        <span class="name">Ensemble</span>
                        <span class="category">Fondements</span>
                    </li>
                </ul>
            </div>
            
            <div class="main-content" id="mainContent">
                <div class="welcome-message">
                    <h2>👋 Bienvenue dans Mathia !</h2>
                    <p>Explorez les concepts mathématiques de manière interactive.</p>
                    <p>Tapez un concept dans la barre de recherche ou cliquez sur un concept dans la liste.</p>
                    <p style="margin-top: 30px; font-size: 1.5rem;">🔍</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentConcept = null;

        async function exploreConcept() {
            const input = document.getElementById('searchInput');
            const query = input.value.trim();
            
            if (!query) {
                showNotification('Veuillez entrer un concept à explorer', 'error');
                return;
            }
            
            const mainContent = document.getElementById('mainContent');
            mainContent.innerHTML = '<div style="text-align: center; padding: 60px;"><div class="loading"></div><p style="margin-top: 20px; color: var(--text-secondary);">Exploration en cours...</p></div>';
            
            try {
                const response = await fetch('/api/explore', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ query: query })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    currentConcept = data.concept;
                    displayConcept(data);
                    showNotification('Concept exploré avec succès !', 'success');
                } else {
                    mainContent.innerHTML = `
                        <div class="welcome-message">
                            <h2>❌ Erreur</h2>
                            <p>${data.error || 'Impossible de trouver ce concept'}</p>
                        </div>
                    `;
                    showNotification('Erreur lors de l\'exploration', 'error');
                }
                
            } catch (error) {
                console.error('Error:', error);
                mainContent.innerHTML = `
                    <div class="welcome-message">
                        <h2>❌ Erreur de connexion</h2>
                        <p>Impossible de se connecter au serveur</p>
                    </div>
                `;
                showNotification('Erreur de connexion', 'error');
            }
        }

        function displayConcept(data) {
            const concept = data.concept;
            const mainContent = document.getElementById('mainContent');
            
            // Générer les étoiles de difficulté
            let difficultyStars = '';
            for (let i = 1; i <= 5; i++) {
                difficultyStars += `<span class="difficulty-star ${i > concept.difficulty ? 'empty' : ''}">★</span>`;
            }
            
            // Générer les exemples
            let examplesHtml = '';
            if (concept.examples && concept.examples.length > 0) {
                examplesHtml = `
                    <div class="concept-section">
                        <h3 class="section-title">📝 Exemples</h3>
                        <div class="examples-grid">
                            ${concept.examples.map(ex => `<div class="example-card">${ex}</div>`).join('')}
                        </div>
                    </div>
                `;
            }
            
            // Générer les concepts liés
            let relatedHtml = '';
            if (concept.related_concepts && concept.related_concepts.length > 0) {
                relatedHtml = `
                    <div class="concept-section">
                        <h3 class="section-title">🔗 Concepts Liés</h3>
                        <div class="related-concepts">
                            ${concept.related_concepts.map(rc => `
                                <span class="related-tag" onclick="quickExplore('${rc}')">${rc}</span>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
            
            mainContent.innerHTML = `
                <div class="concept-card">
                    <div class="concept-header">
                        <h2 class="concept-title">${concept.name}</h2>
                        <div class="concept-meta">
                            <div class="meta-tag">📂 ${concept.category}</div>
                            <div class="meta-tag">
                                <div class="difficulty-indicator">
                                    ${difficultyStars}
                                    <span style="margin-left: 10px;">${concept.difficulty_text}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="concept-section">
                        <h3 class="section-title">📖 Définition</h3>
                        <div class="section-content">
                            ${concept.definition}
                        </div>
                    </div>
                    
                    <div class="concept-section">
                        <h3 class="section-title">💡 Explication Enrichie</h3>
                        <div class="section-content">
                            ${data.ai_explanation}
                        </div>
                    </div>
                    
                    ${examplesHtml}
                    ${relatedHtml}
                    
                    ${data.search_hint ? `
                        <div style="margin-top: 20px; padding: 15px; background: rgba(102, 126, 234, 0.1); border-radius: 15px; color: var(--text-secondary); font-size: 0.9rem;">
                            ℹ️ ${data.search_hint}
                        </div>
                    ` : ''}
                    
                    ${!data.found_in_database ? `
                        <div style="margin-top: 20px; padding: 15px; background: rgba(243, 156, 18, 0.1); border-radius: 15px; color: var(--text-secondary); font-size: 0.9rem;">
                            ⚠️ Ce concept a été généré par l'IA car il n'est pas encore dans notre base de données.
                        </div>
                    ` : ''}
                </div>
            `;
        }

        function quickExplore(concept) {
            document.getElementById('searchInput').value = concept;
            exploreConcept();
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

        // Auto-load concepts list
        async function loadConceptsList() {
            try {
                const response = await fetch('/api/concepts');
                const data = await response.json();
                
                if (data.success && data.concepts) {
                    const conceptList = document.getElementById('conceptList');
                    conceptList.innerHTML = data.concepts.map(concept => `
                        <li class="concept-item" onclick="quickExplore('${concept.name.toLowerCase()}')">
                            <span class="name">${concept.name}</span>
                            <span class="category">${concept.category}</span>
                        </li>
                    `).join('');
                }
            } catch (error) {
                console.error('Error loading concepts:', error);
            }
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            console.log('Mathia Explorer loaded');
            loadConceptsList();
        });
    </script>
</body>
</html>'''

if __name__ == '__main__':
    print("🔢 MATHIA V3.0 - Explorateur de Concepts Mathématiques")
    print("=" * 60)
    
    try:
        from mistralai import Mistral
        print("✅ Dépendances installées")
        
        port = int(os.environ.get('PORT', 5000))
        debug_mode = os.environ.get('FLASK_ENV') != 'production'
        
        print(f"🌐 Port: {port}")
        print(f"🔧 Debug: {debug_mode}")
        print(f"🔑 Clés Mistral: {len(mathia.api_keys)} configurées")
        print(f"📚 Concepts disponibles: {len(mathia.concept_database)}")
        
        print("\n🎯 Fonctionnalités:")
        print("   • Exploration interactive de concepts")
        print("   • Explications enrichies par IA")
        print("   • Réseau de concepts liés")
        print("   • Navigation intuitive")
        print("   • Base de 10+ concepts mathématiques")
        
        print("\n📂 Catégories:")
        categories = set(c.category for c in mathia.concept_database.values())
        for cat in categories:
            count = sum(1 for c in mathia.concept_database.values() if c.category == cat)
            print(f"   • {cat}: {count} concepts")
        
        print("\n🚀 Démarrage de Mathia...")
        
    except ImportError as e:
        print(f"❌ ERREUR: {e}")
        exit(1)
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
