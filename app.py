import os
import logging
import time
import signal
from functools import wraps
from collections import defaultdict

import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics import silhouette_score
import psutil
from dotenv import load_dotenv

from scrap import scrap, verify_letterboxd_user
from data_manager import DataManager

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load env vars
load_dotenv()

# Initialize data manager (uses JSON files instead of PostgreSQL)
data_manager = DataManager()

# Flask app setup
app = Flask(__name__)
CORS(app)

# Rate limiting config
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10
request_counts = defaultdict(list)

# Cache config
user_cache = {}
CACHE_EXPIRY = 300  # seconds cache expiry

# Timeout decorator for Railway-friendly execution
REQUEST_TIMEOUT = 20  # seconds

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def timeout_decorator(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        return wrapper
    return decorator

def get_db_connection():
    """Legacy function - now uses DataManager"""
    logger.debug("Using DataManager instead of PostgreSQL")
    return data_manager

def adicionar_usuario(usuario):
    logger.info(f"Tentando adicionar usuário {usuario} ao sistema")
    if not verify_letterboxd_user(usuario):
        logger.error(f"Usuário {usuario} não existe no Letterboxd")
        return False
    try:
        # Add user to data manager
        user_id = data_manager.add_user(usuario)
        logger.info(f"Usuário {usuario} adicionado com ID {user_id}")
        
        # Use the existing scrap function logic but adapt for DataManager
        from populate_data import scrape_user_data
        if scrape_user_data(data_manager, usuario):
            logger.info(f"Usuário {usuario} adicionado com dados reais do Letterboxd")
            return True
        else:
            logger.warning(f"Falha ao fazer scraping do usuário {usuario}, mas usuário foi adicionado")
            return True  # User was added, just no data scraped
        
    except Exception as e:
        logger.error(f"Erro ao adicionar usuário {usuario}: {str(e)}")
        return False

@timeout_decorator(REQUEST_TIMEOUT)
def gerar_recomendacoes(usuario_alvo):
    logger.info(f"Iniciando geração de recomendações para usuário: {usuario_alvo}")
    start_time = time.time()
    try:
        # Check cache first
        current_time = time.time()
        if usuario_alvo in user_cache and (current_time - user_cache[usuario_alvo]['timestamp']) < CACHE_EXPIRY:
            logger.debug(f"Usando dados em cache para usuário {usuario_alvo}")
            df = user_cache[usuario_alvo]['data']
        else:
            logger.debug("Buscando avaliações no DataManager")
            all_ratings = data_manager.get_all_ratings()
            
            # Convert to DataFrame
            df = pd.DataFrame(all_ratings, columns=['username', 'title', 'rating'])
            user_cache[usuario_alvo] = {'data': df, 'timestamp': time.time()}
            logger.debug("Cache atualizado")

        if df.empty or len(df) < 2:
            logger.warning("Dados insuficientes para recomendações")
            return {
                "error": "Dados insuficientes para gerar recomendações",
                "status": "insufficient_data",
                "message": "É necessário pelo menos 2 usuários com avaliações",
                "recomendacoes": {},
                "metadata": {}
            }

        # Garantir que usuário está no sistema
        if not data_manager.user_exists(usuario_alvo):
            logger.info(f"Usuário {usuario_alvo} não encontrado. Tentando adicionar...")
            if adicionar_usuario(usuario_alvo):
                logger.info("Usuário adicionado com sucesso. Gerando recomendações...")
                return gerar_recomendacoes(usuario_alvo)
            else:
                logger.warning(f"Falha ao adicionar usuário {usuario_alvo}")
                return {
                    "error": f"Usuário {usuario_alvo} não encontrado no Letterboxd",
                    "status": "user_not_found",
                    "message": "Verifique o nome do usuário.",
                    "recomendacoes": {}
                }

        # Criar matriz usuário-filme
        logger.debug("Criando matriz usuário-filme")
        rating_matrix = df.pivot_table(index='username', columns='title', values='rating', fill_value=0)

        filmes_usuario = set(df[df['username'] == usuario_alvo]['title'])
        todos_filmes = set(df['title'])
        filmes_nao_vistos = todos_filmes - filmes_usuario

        logger.debug(f"Filmes não vistos pelo usuário: {len(filmes_nao_vistos)}")

        # Pré-processamento e redução de dimensionalidade
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(rating_matrix)

        n_components = min(30, X_scaled.shape[1] - 1)
        if n_components > 0:
            svd = TruncatedSVD(n_components=n_components, random_state=42)
            X_reduced = svd.fit_transform(X_scaled)
        else:
            X_reduced = X_scaled

        # Definir clusters automaticamente com KMeans e silhouette score
        best_score = -1
        best_k = 2
        max_clusters = min(10, len(rating_matrix))
        for k in range(2, max_clusters + 1):
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X_reduced)
            score = silhouette_score(X_reduced, labels) if len(set(labels)) > 1 else -1
            if score > best_score:
                best_score = score
                best_k = k

        logger.info(f"Melhor número de clusters: {best_k}")

        kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=20)
        clusters = kmeans.fit_predict(X_reduced)
        rating_matrix['cluster'] = clusters

        cluster_usuario = rating_matrix.loc[usuario_alvo, 'cluster']
        logger.info(f"Usuário {usuario_alvo} está no cluster {cluster_usuario}")

        usuarios_cluster = rating_matrix[rating_matrix['cluster'] == cluster_usuario].index.tolist()
        if len(usuarios_cluster) < 2:
            logger.info("Poucos usuários no cluster, usando todos")
            usuarios_cluster = rating_matrix.index.tolist()

        # Calcular score para os filmes não vistos
        recomendacoes = []
        for filme in filmes_nao_vistos:
            if filme in rating_matrix.columns:
                avaliacoes = df[(df['title'] == filme) & (df['username'].isin(usuarios_cluster))]['rating']
                if len(avaliacoes) == 0:
                    continue
                media = avaliacoes.mean()
                count = len(avaliacoes)
                score = media * (1 + 0.1 * count)
                recomendacoes.append({'filme': filme, 'score': float(score)})

        # Completar com filmes populares se necessário
        recomendacoes.sort(key=lambda x: x['score'], reverse=True)
        if len(recomendacoes) < 10:
            filmes_potenciais = [f for f in todos_filmes if f not in [r['filme'] for r in recomendacoes]]
            populares = []
            for filme in filmes_potenciais:
                avaliacoes = df[df['title'] == filme]['rating']
                if len(avaliacoes) == 0:
                    continue
                media = avaliacoes.mean()
                count = len(avaliacoes)
                populares.append({'filme': filme, 'score': media * (1 + 0.1 * count)})
            populares.sort(key=lambda x: x['score'], reverse=True)
            recomendacoes.extend(populares[:10 - len(recomendacoes)])

        # Preparar resposta
        top_recomendacoes = {r['filme']: r['score'] for r in recomendacoes[:10]}

        processing_time = time.time() - start_time
        logger.info(f"Recomendações geradas para {usuario_alvo} em {processing_time:.2f}s")

        return {
            "status": "success",
            "message": "Recomendações geradas com sucesso",
            "recomendacoes": top_recomendacoes,
            "metadata": {
                "total_usuarios": len(rating_matrix),
                "total_filmes": len(todos_filmes),
                "filmes_nao_vistos": len(filmes_nao_vistos),
                "total_recomendacoes": len(top_recomendacoes),
                "processing_time": processing_time
            }
        }

    except TimeoutError:
        logger.error("Timeout ao gerar recomendações")
        return {
            "status": "timeout",
            "message": "Tempo excedido para gerar recomendações",
            "recomendacoes": {},
            "metadata": {}
        }
    except Exception as e:
        logger.error(f"Erro ao gerar recomendações: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "recomendacoes": {},
            "metadata": {}
        }


@app.route('/api/recomendacoes/<usuario>')
def api_recomendacoes(usuario):
    logger.info(f"Requisição recebida para recomendações do usuário: {usuario}")
    current_time = time.time()
    client_ip = request.remote_addr or 'unknown'

    # Rate limiting
    request_counts[client_ip] = [t for t in request_counts[client_ip] if current_time - t < RATE_LIMIT_WINDOW]
    if len(request_counts[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        logger.warning(f"Rate limit excedido para IP {client_ip}")
        return jsonify({
            "status": "rate_limited",
            "message": "Muitas requisições, tente novamente mais tarde",
            "recomendacoes": {},
            "metadata": {}
        }), 429
    request_counts[client_ip].append(current_time)

    recomendacoes = gerar_recomendacoes(usuario)
    logger.debug(f"Recomendações enviadas para {usuario}: {recomendacoes}")
    return jsonify(recomendacoes)


@app.route('/health')
def health_check():
    logger.debug("Health check solicitado")
    try:
        stats = data_manager.get_stats()
        return jsonify({
            "status": "healthy",
            "data_manager": "working",
            "stats": stats
        })
    except Exception as e:
        logger.error(f"Health check falhou: {str(e)}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/populate', methods=['POST'])
def populate_data():
    """Populate initial data"""
    try:
        from populate_data import populate_initial_data
        populate_initial_data()
        return jsonify({
            "status": "success",
            "message": "Data populated successfully"
        })
    except Exception as e:
        logger.error(f"Error populating data: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Iniciando aplicação na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
