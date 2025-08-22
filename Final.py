from flask import Flask, render_template, request, jsonify
import requests
import json
from mistralai import Mistral
import wikipedia
import os
import re

app = Flask(__name__)

class WikipediaMistralSummarizer:
    def __init__(self, mistral_api_key):
        """
        Initialise le résumeur avec la clé API Mistral
        """
        self.mistral_client = Mistral(api_key=mistral_api_key)
        # Configurer Wikipedia en français
        wikipedia.set_lang("fr")
    
    def markdown_to_html(self, text):
        """
        Convertit le Markdown simple en HTML de manière plus robuste
        """
        print(f"Texte original reçu: {repr(text[:200])}...")  # Debug
        
        # Nettoyer d'abord le texte
        text = text.strip()
        
        # Remplacer **texte** par <strong>texte</strong> (gras)
        text = re.sub(r'\*\*([^*]+?)\*\*', r'<strong>\1</strong>', text)
        print(f"Après gras: {repr(text[:200])}...")  # Debug
        
        # Remplacer *texte* par <em>texte</em> (italique) - après le gras pour éviter les conflits
        text = re.sub(r'\*([^*]+?)\*', r'<em>\1</em>', text)
        
        # Gérer les titres avec # (optionnel)
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        
        # Remplacer les listes à puces (- item ou * item)
        text = re.sub(r'^[-*] (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        
        # Encapsuler les listes dans <ul></ul>
        if '<li>' in text:
            # Trouver les séquences de <li> et les encapsuler
            lines = text.split('\n')
            result_lines = []
            in_list = False
            
            for line in lines:
                if '<li>' in line:
                    if not in_list:
                        result_lines.append('<ul>')
                        in_list = True
                    result_lines.append(line)
                else:
                    if in_list:
                        result_lines.append('</ul>')
                        in_list = False
                    result_lines.append(line)
            
            if in_list:
                result_lines.append('</ul>')
                
            text = '\n'.join(result_lines)
        
        # Convertir les doubles sauts de ligne en paragraphes
        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<') and not para.endswith('>'):
                para = f'<p>{para}</p>'
            elif para:
                formatted_paragraphs.append(para)
                continue
            if para:
                formatted_paragraphs.append(para)
        
        result = '\n'.join(formatted_paragraphs)
        
        # Nettoyer les paragraphes vides
        result = re.sub(r'<p>\s*</p>', '', result)
        result = re.sub(r'<p></p>', '', result)
        
        print(f"Résultat final: {repr(result[:200])}...")  # Debug
        return result
    
    def get_wikipedia_content(self, theme):
        """
        Récupère le contenu d'une page Wikipedia sur un thème donné
        """
        try:
            # Rechercher la page
            page = wikipedia.page(theme)
            return {
                'title': page.title,
                'content': page.content,
                'url': page.url
            }
        except wikipedia.exceptions.DisambiguationError as e:
            # Si plusieurs pages correspondent, prendre la première
            page = wikipedia.page(e.options[0])
            return {
                'title': page.title,
                'content': page.content,
                'url': page.url
            }
        except wikipedia.exceptions.PageError:
            return None
        except Exception as e:
            print(f"Erreur lors de la récupération Wikipedia: {e}")
            return None
    
    def summarize_with_mistral(self, title, content):
        """
        Utilise Mistral AI pour résumer le contenu Wikipedia
        """
        try:
            # Limiter le contenu si trop long
            max_chars = 8000
            if len(content) > max_chars:
                content = content[:max_chars] + "..."
            
            prompt = f"""
            Voici le contenu d'une page Wikipedia sur le sujet "{title}".
            
            Contenu:
            {content}
            
            Consigne: Fais un résumé clair et concis de cette page Wikipedia en français. 
            Le résumé doit être informatif, bien structuré et faire environ 200-300 mots.
            Mets en avant les points les plus importants.
            
            IMPORTANT: Ne utilise PAS de formatage Markdown (pas de **, *, #, etc.). 
            Écris en texte brut simple et lisible.
            """
            
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            response = self.mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.3
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Erreur lors du résumé avec Mistral: {e}")
            return None
    
    def answer_with_mistral_only(self, theme):
        """
        Utilise Mistral AI pour répondre directement sur un thème sans Wikipedia
        """
        try:
            prompt = f"""
            L'utilisateur me demande des informations sur le thème: "{theme}"
            
            Aucune page Wikipedia n'a été trouvée pour ce sujet.
            
            Consigne: Fournis une réponse complète et informative sur ce thème en français.
            Explique ce que c'est, donne des détails importants, du contexte historique si pertinent,
            et tout ce qui pourrait être utile à connaître sur ce sujet.
            Fais une réponse structurée d'environ 300-400 mots.
            
            IMPORTANT: Ne utilise PAS de formatage Markdown (pas de **, *, #, etc.). 
            Écris en texte brut simple et lisible.
            """
            
            messages = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            response = self.mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.3
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Erreur lors de la réponse avec Mistral: {e}")
            return None

    def process_theme(self, theme):
        """
        Traite un thème complet
        """
        # Récupérer le contenu Wikipedia
        wiki_data = self.get_wikipedia_content(theme)
        
        if not wiki_data:
            # Mistral répond sans Wikipedia
            mistral_response = self.answer_with_mistral_only(theme)
            
            if not mistral_response:
                return {
                    'success': False,
                    'error': 'Erreur lors de la génération de la réponse'
                }
            
            # Convertir le Markdown en HTML si nécessaire
            formatted_response = self.markdown_to_html(mistral_response)
            
            return {
                'success': True,
                'title': f"Réponse directe sur: {theme}",
                'summary': formatted_response,
                'url': None,
                'source': 'mistral_only'
            }
        
        # Résumer avec Mistral
        summary = self.summarize_with_mistral(wiki_data['title'], wiki_data['content'])
        
        if not summary:
            return {
                'success': False,
                'error': 'Erreur lors de la génération du résumé'
            }
        
        # Convertir le Markdown en HTML si nécessaire
        formatted_summary = self.markdown_to_html(summary)
        
        return {
            'success': True,
            'title': wiki_data['title'],
            'summary': formatted_summary,
            'url': wiki_data['url'],
            'source': 'wikipedia'
        }

@app.route('/')
def index():
    """Page d'accueil avec l'interface"""
    return '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wikipedia Summarizer - Mistral AI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .container {
            background: #e6e7ee;
            border-radius: 30px;
            padding: 40px;
            width: 100%;
            max-width: 800px;
            box-shadow: 
                20px 20px 60px #bebfc5,
                -20px -20px 60px #ffffff;
            position: relative;
            overflow: hidden;
        }

        .container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #667eea, #764ba2, #f093fb);
            border-radius: 30px 30px 0 0;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
        }

        .title {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
        }

        .subtitle {
            color: #8b8d97;
            font-size: 1.1rem;
            font-weight: 400;
        }

        .form-group {
            margin-bottom: 30px;
        }

        .label {
            display: block;
            color: #5a5c69;
            font-weight: 600;
            margin-bottom: 12px;
            font-size: 1rem;
        }

        .input {
            width: 100%;
            padding: 18px 24px;
            background: #e6e7ee;
            border: none;
            border-radius: 20px;
            font-size: 1rem;
            color: #5a5c69;
            box-shadow: 
                inset 8px 8px 16px #d1d2d9,
                inset -8px -8px 16px #fbfcff;
            transition: all 0.3s ease;
            outline: none;
        }

        .input:focus {
            box-shadow: 
                inset 12px 12px 20px #d1d2d9,
                inset -12px -12px 20px #fbfcff;
        }

        .input::placeholder {
            color: #a8aab7;
        }

        .btn {
            background: #e6e7ee;
            border: none;
            border-radius: 20px;
            padding: 18px 36px;
            font-size: 1.1rem;
            font-weight: 600;
            color: #5a5c69;
            cursor: pointer;
            box-shadow: 
                8px 8px 16px #d1d2d9,
                -8px -8px 16px #fbfcff;
            transition: all 0.2s ease;
            position: relative;
            overflow: hidden;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 
                12px 12px 20px #d1d2d9,
                -12px -12px 20px #fbfcff;
        }

        .btn:active {
            transform: translateY(0);
            box-shadow: 
                inset 4px 4px 8px #d1d2d9,
                inset -4px -4px 8px #fbfcff;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            box-shadow: 
                8px 8px 16px rgba(102, 126, 234, 0.3),
                -8px -8px 16px rgba(255, 255, 255, 0.8);
        }

        .btn-primary:hover {
            box-shadow: 
                12px 12px 20px rgba(102, 126, 234, 0.4),
                -12px -12px 20px rgba(255, 255, 255, 0.9);
        }

        .btn-secondary {
            margin-left: 15px;
        }

        .controls {
            display: flex;
            justify-content: center;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }

        .status {
            margin: 30px 0;
            padding: 20px;
            background: #e6e7ee;
            border-radius: 20px;
            box-shadow: 
                inset 6px 6px 12px #d1d2d9,
                inset -6px -6px 12px #fbfcff;
            display: none;
        }

        .status.active {
            display: block;
        }

        .status-text {
            color: #5a5c69;
            font-weight: 500;
            margin-bottom: 10px;
        }

        .progress-bar {
            width: 100%;
            height: 8px;
            background: #d1d2d9;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 
                inset 3px 3px 6px #bebfc5,
                inset -3px -3px 6px #ffffff;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 10px;
            width: 0%;
            transition: width 0.3s ease;
        }

        .result {
            margin-top: 30px;
            padding: 30px;
            background: #e6e7ee;
            border-radius: 25px;
            box-shadow: 
                inset 8px 8px 16px #d1d2d9,
                inset -8px -8px 16px #fbfcff;
            display: none;
        }

        .result.active {
            display: block;
            animation: slideUp 0.5s ease;
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .result-title {
            color: #5a5c69;
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #d1d2d9;
        }

        .result-content {
            color: #6c6e7e;
            line-height: 1.6;
            font-size: 1rem;
        }

        /* Styles pour le contenu HTML formaté */
        .result-content p {
            margin-bottom: 15px;
        }

        .result-content strong {
            color: #5a5c69;
            font-weight: 600;
        }

        .result-content em {
            font-style: italic;
            color: #667eea;
        }

        .result-content ul {
            margin: 15px 0;
            padding-left: 20px;
        }

        .result-content li {
            margin-bottom: 8px;
            list-style-type: disc;
        }

        .result-url {
            margin-top: 20px;
            padding: 15px;
            background: rgba(102, 126, 234, 0.1);
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .result-url a {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }

        .result-url a:hover {
            text-decoration: underline;
        }

        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #d1d2d9;
            border-radius: 50%;
            border-top-color: #667eea;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .error {
            background: rgba(231, 76, 60, 0.1);
            border-left: 4px solid #e74c3c;
            padding: 15px;
            border-radius: 15px;
            margin-top: 20px;
        }

        .success {
            background: rgba(46, 204, 113, 0.1);
            border-left: 4px solid #2ecc71;
        }

        @media (max-width: 768px) {
            .container {
                padding: 30px 20px;
                margin: 10px;
                border-radius: 25px;
            }

            .title {
                font-size: 2rem;
            }

            .controls {
                flex-direction: column;
            }

            .btn-secondary {
                margin-left: 0;
                margin-top: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">🌟 Wikipedia Summarizer</h1>
            <p class="subtitle">Résumés intelligents avec Mistral AI</p>
        </div>

        <form id="summarizerForm">
            <div class="form-group">
                <label class="label" for="apiKey">🔑 Clé API Mistral</label>
                <input 
                    type="password" 
                    id="apiKey" 
                    class="input" 
                    placeholder="Entrez votre clé API Mistral..."
                    required
                >
            </div>

            <div class="form-group">
                <label class="label" for="theme">🔍 Thème à rechercher</label>
                <input 
                    type="text" 
                    id="theme" 
                    class="input" 
                    placeholder="Intelligence artificielle, Paris, Einstein..."
                    required
                >
            </div>

            <div class="controls">
                <button type="submit" class="btn btn-primary">
                    ✨ Générer le résumé
                </button>
                <button type="button" class="btn btn-secondary" onclick="clearAll()">
                    🗑️ Effacer
                </button>
            </div>
        </form>

        <div id="status" class="status">
            <div class="status-text">
                <span id="statusText">Recherche en cours...</span>
            </div>
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
        </div>

        <div id="result" class="result">
            <div class="result-title" id="resultTitle">📖 Résumé généré</div>
            <div class="result-content" id="resultContent"></div>
            <div id="resultUrl" class="result-url" style="display: none;">
                <strong>🔗 Source:</strong> <a href="#" target="_blank" id="wikiLink"></a>
            </div>
        </div>
    </div>

    <script>
        let isProcessing = false;

        const form = document.getElementById('summarizerForm');
        const statusDiv = document.getElementById('status');
        const resultDiv = document.getElementById('result');
        const statusText = document.getElementById('statusText');
        const progressFill = document.getElementById('progressFill');
        const resultTitle = document.getElementById('resultTitle');
        const resultContent = document.getElementById('resultContent');
        const resultUrl = document.getElementById('resultUrl');
        const wikiLink = document.getElementById('wikiLink');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (isProcessing) return;

            const apiKey = document.getElementById('apiKey').value.trim();
            const theme = document.getElementById('theme').value.trim();

            if (!apiKey || !theme) {
                showError('⚠️ Veuillez remplir tous les champs');
                return;
            }

            await processTheme(apiKey, theme);
        });

        async function processTheme(apiKey, theme) {
            isProcessing = true;
            showStatus('🔍 Recherche en cours...', 0);
            hideResult();

            try {
                const response = await fetch('/api/summarize', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        api_key: apiKey,
                        theme: theme
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Erreur lors du traitement');
                }

                showStatus('✅ Résumé généré avec succès!', 100);
                
                setTimeout(() => {
                    showResult(data);
                    hideStatus();
                    isProcessing = false;
                }, 500);

            } catch (error) {
                showError('❌ ' + error.message);
                isProcessing = false;
            }
        }

        function showStatus(message, progress) {
            statusText.innerHTML = '<span class="loading"></span>' + message;
            progressFill.style.width = progress + '%';
            statusDiv.classList.add('active');
            statusDiv.style.display = 'block';
        }

        function hideStatus() {
            statusDiv.classList.remove('active');
            setTimeout(() => {
                statusDiv.style.display = 'none';
                progressFill.style.width = '0%';
            }, 300);
        }

        function showResult(data) {
            resultTitle.textContent = `📖 ${data.title}`;
            // Utiliser innerHTML au lieu de textContent pour interpréter le HTML
            resultContent.innerHTML = data.summary;
            console.log('Summary HTML:', data.summary); // Debug
            
            if (data.url) {
                wikiLink.href = data.url;
                wikiLink.textContent = data.url;
                resultUrl.style.display = 'block';
            } else {
                resultUrl.style.display = 'none';
            }

            resultDiv.classList.add('active');
            resultDiv.style.display = 'block';
        }

        function hideResult() {
            resultDiv.classList.remove('active');
            resultDiv.style.display = 'none';
        }

        function showError(message) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error';
            errorDiv.textContent = message;
            
            const container = document.querySelector('.container');
            container.appendChild(errorDiv);
            
            setTimeout(() => {
                errorDiv.remove();
            }, 5000);
        }

        function clearAll() {
            form.reset();
            hideStatus();
            hideResult();
            isProcessing = false;
        }
    </script>
</body>
</html>
    '''

@app.route('/api/summarize', methods=['POST'])
def summarize():
    """API endpoint pour traiter les résumés"""
    try:
        data = request.get_json()
        api_key = data.get('api_key')
        theme = data.get('theme')
        
        if not api_key or not theme:
            return jsonify({'error': 'Clé API et thème requis'}), 400
        
        # Créer l'instance du résumeur
        summarizer = WikipediaMistralSummarizer(api_key)
        
        # Traiter le thème
        result = summarizer.process_theme(theme)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 500
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🌟 Démarrage du serveur Wikipedia Summarizer")
    print("📱 Interface disponible sur: http://localhost:4000")
    print("🔑 N'oubliez pas votre clé API Mistral!")
    print("-" * 50)
    
    # Vérifier les dépendances
    try:
        from mistralai import Mistral
        import wikipedia
        print("✅ Toutes les dépendances sont installées")
    except ImportError as e:
        print(f"❌ Module manquant: {e}")
        print("Installez les dépendances avec:")
        print("pip install flask mistralai wikipedia")
        exit(1)
    
    app.run(debug=True, host='0.0.0.0', port=4000)