import os
import logging
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from scrap import scrap, verify_letterboxd_user
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics import silhouette_score
from dotenv import load_dotenv
import time
import signal
from functools import wraps
from collections import defaultdict

# Carrega .env no local
load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Variáveis de ambiente para banco
dbname = os.getenv("PGDATABASE")
user = os.getenv("PGUSER")
password = os.getenv("PGPASSWORD")
host = os.getenv("PGHOST")
port = os.getenv("PGPORT")

# Timeout configuration
REQUEST_TIMEOUT = 25  # seconds
MAX_USERS_FOR_CLUSTERING = 1000
MAX_MOVIES_FOR_PROCESSING = 1000  # Reduced to prevent memory issues

# Rate limiting
request_counts = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def timeout_decorator(seconds):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set the signal handler
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        return wrapper
    return decorator

def get_db_connection():
    return psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port
    )

@app.route('/ping')
def ping():
    return jsonify({"message": "pong"}), 200

@app.route('/health')
def health():
    try:
        # Test database connection
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        conn.close()
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": time.time()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": time.time()
        }), 500

@app.route('/test-db-connection')
def test_db_connection():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"status": "conectado com sucesso"}), 200
    except Exception as e:
        logger.error(f"Erro na conexão com banco: {str(e)}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

def adicionar_usuario(usuario):
    logger.info(f"Tentando adicionar usuário {usuario} ao banco de dados")
    
    # Check if user already exists first
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s", (usuario,))
            if cursor.fetchone():
                logger.info(f"Usuário {usuario} já existe no banco de dados")
                conn.close()
                return True
        conn.close()
    except Exception as e:
        logger.error(f"Erro ao verificar usuário {usuario}: {str(e)}")
        return False
    
    if not verify_letterboxd_user(usuario):
        logger.error(f"Usuário {usuario} não existe no Letterboxd")
        return False
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            scrap(cursor, conn, usuario)
        conn.close()
        logger.info(f"Usuário {usuario} adicionado com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar usuário {usuario}: {str(e)}")
        return False

def get_user_data_efficiently(usuario_alvo):
    """Get user data more efficiently with limits"""
    try:
        conn = get_db_connection()
        
        # First check if user exists
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = %s", (usuario_alvo,))
        user_exists = cursor.fetchone() is not None
        
        if not user_exists:
            conn.close()
            return None, "user_not_found"
        
        # Get user's data
        query = """
        SELECT u.username, m.title, r.rating
        FROM ratings r
        JOIN users u ON r.user_id = u.id
        JOIN movies m ON r.movie_id = m.id
        WHERE u.username = %s
        """
        df_user = pd.read_sql(query, conn, params=(usuario_alvo,))
        
        # Get popular movies data (more efficient than all users)
        query_popular = """
        SELECT m.title, AVG(r.rating) as avg_rating, COUNT(r.rating) as num_ratings
        FROM ratings r
        JOIN movies m ON r.movie_id = m.id
        GROUP BY m.title
        HAVING COUNT(r.rating) >= 2
        ORDER BY COUNT(r.rating) DESC
        LIMIT %s
        """
        df_popular = pd.read_sql(query_popular, conn, params=(MAX_MOVIES_FOR_PROCESSING,))
        
        conn.close()
        
        # Create a simplified dataset for recommendations
        if len(df_user) == 0:
            return None, "insufficient_data"
        
        # Create recommendations based on popular movies
        recommendations_data = []
        for _, row in df_popular.iterrows():
            title = row['title']
            avg_rating = row['avg_rating']
            num_ratings = row['num_ratings']
            
            # Create synthetic user ratings for popular movies
            recommendations_data.extend([
                {'username': 'popular', 'title': title, 'rating': avg_rating}
            ])
        
        # Combine user data with popular movies
        df_combined = pd.concat([
            df_user,
            pd.DataFrame(recommendations_data)
        ], ignore_index=True)
        
        if len(df_combined) < 5:
            return None, "insufficient_data"
            
        return df_combined, "success"
        
    except Exception as e:
        logger.error(f"Erro ao buscar dados: {str(e)}")
        return None, "error"

def simple_recommendation_algorithm(df, usuario_alvo, filmes_nao_vistos):
    """Simplified recommendation algorithm for better performance"""
    logger.info("Usando algoritmo simplificado de recomendação")
    
    recomendacoes = []
    
    # Get user's average rating
    user_ratings = df[df['username'] == usuario_alvo]['rating']
    user_avg = user_ratings.mean() if len(user_ratings) > 0 else 3.0
    
    # Get popular movies data
    popular_movies = df[df['username'] == 'popular']
    
    for filme in filmes_nao_vistos:
        if filme in df['title'].values:
            # Get ratings for this movie from popular data
            movie_data = popular_movies[popular_movies['title'] == filme]
            
            if len(movie_data) > 0:
                avg_rating = movie_data['rating'].iloc[0]
                
                # Simple scoring based on popularity and rating
                score = float(avg_rating) * 1.1  # Boost popular movies
                
                # Bonus for movies with similar rating to user's average
                rating_diff = abs(avg_rating - user_avg)
                if rating_diff < 1.0:
                    score *= 1.2
                
                recomendacoes.append({
                    'filme': filme,
                    'score': score
                })
            else:
                # Fallback for movies not in popular data
                movie_ratings = df[df['title'] == filme]['rating']
                if len(movie_ratings) > 0:
                    avg_rating = movie_ratings.mean()
                    score = float(avg_rating)
                    recomendacoes.append({
                        'filme': filme,
                        'score': score
                    })
    
    return recomendacoes

@timeout_decorator(REQUEST_TIMEOUT)
def gerar_recomendacoes(usuario_alvo):
    logger.info(f"Iniciando geração de recomendações para usuário: {usuario_alvo}")
    start_time = time.time()
    
    try:
        # Get data efficiently
        df, status = get_user_data_efficiently(usuario_alvo)
        
        if status == "user_not_found":
            logger.info(f"Usuário {usuario_alvo} não encontrado no banco de dados. Tentando adicionar...")
            if adicionar_usuario(usuario_alvo):
                logger.info("Usuário adicionado com sucesso. Gerando recomendações...")
                return gerar_recomendacoes(usuario_alvo)
            else:
                logger.warning(f"Falha ao adicionar usuário {usuario_alvo}")
                return {
                    "error": f"Usuário {usuario_alvo} não encontrado no Letterboxd ou erro ao adicionar",
                    "status": "user_not_found",
                    "message": "O usuário não foi encontrado no banco de dados ou não existe no Letterboxd. Verifique o nome.",
                    "recomendacoes": {}, 
                    "metadata": {
                        "total_usuarios": 0,
                        "total_filmes": 0,
                        "filmes_nao_vistos": 0,
                        "total_recomendacoes": 0,
                        "processing_time": time.time() - start_time
                    }
                }
        
        if status == "insufficient_data":
            return {
                "error": "Não há dados suficientes para gerar recomendações",
                "status": "insufficient_data",
                "message": "É necessário ter pelo menos 10 avaliações para gerar recomendações",
                "recomendacoes": {},
                "metadata": {
                    "total_usuarios": 0,
                    "total_filmes": 0,
                    "filmes_nao_vistos": 0,
                    "total_recomendacoes": 0,
                    "processing_time": time.time() - start_time
                }
            }
        
        if status == "error" or df is None:
            return {
                "error": "Erro ao buscar dados do banco",
                "status": "error",
                "message": "Ocorreu um erro ao buscar dados do banco de dados",
                "recomendacoes": {},
                "metadata": {
                    "total_usuarios": 0,
                    "total_filmes": 0,
                    "filmes_nao_vistos": 0,
                    "total_recomendacoes": 0,
                    "processing_time": time.time() - start_time
                }
            }

        logger.info(f"Total de registros encontrados: {len(df)}")
        
        # Get user's movies and unseen movies
        filmes_usuario = df[df['username'] == usuario_alvo]['title'].unique()
        todos_filmes = df['title'].unique()
        filmes_nao_vistos = set(todos_filmes) - set(filmes_usuario)
        
        logger.info(f"Filmes do usuário: {len(filmes_usuario)}, Filmes não vistos: {len(filmes_nao_vistos)}")
        
        # Use simplified algorithm for better performance
        recomendacoes = simple_recommendation_algorithm(df, usuario_alvo, filmes_nao_vistos)
        
        # Sort and limit recommendations
        recomendacoes.sort(key=lambda x: x['score'], reverse=True)
        recomendacoes_formatadas = {rec['filme']: rec['score'] for rec in recomendacoes[:10]}
        
        processing_time = time.time() - start_time
        logger.info(f"Recomendações geradas em {processing_time:.2f} segundos")
        
        # Clean up memory
        del df
        del recomendacoes
        
        response = {
            "status": "success",
            "message": "Recomendações geradas com sucesso",
            "recomendacoes": recomendacoes_formatadas,
            "metadata": {
                "total_usuarios": df['username'].nunique() if 'df' in locals() else 0,
                "total_filmes": len(todos_filmes),
                "filmes_nao_vistos": len(filmes_nao_vistos),
                "total_recomendacoes": len(recomendacoes_formatadas),
                "processing_time": processing_time
            }
        }
        
        return response

    except TimeoutError:
        logger.error("Timeout ao gerar recomendações")
        return {
            "error": "Timeout ao gerar recomendações",
            "status": "timeout",
            "message": "A operação demorou muito para ser concluída. Tente novamente.",
            "recomendacoes": {},
            "metadata": {
                "total_usuarios": 0,
                "total_filmes": 0,
                "filmes_nao_vistos": 0,
                "total_recomendacoes": 0,
                "processing_time": time.time() - start_time
            }
        }
    except Exception as e:
        logger.error(f"Erro ao gerar recomendações: {str(e)}")
        return {
            "error": str(e),
            "status": "error",
            "message": "Ocorreu um erro ao gerar as recomendações",
            "recomendacoes": {},
            "metadata": {
                "total_usuarios": 0,
                "total_filmes": 0,
                "filmes_nao_vistos": 0,
                "total_recomendacoes": 0,
                "processing_time": time.time() - start_time
            }
        }

@app.route('/api/recomendacoes/<usuario>')
def obter_recomendacoes(usuario):
    logger.info(f"Recebida requisição para usuário: {usuario}")
    
    # Simple rate limiting
    current_time = time.time()
    client_ip = request.remote_addr if hasattr(request, 'remote_addr') else 'unknown'
    
    # Clean old requests
    request_counts[client_ip] = [req_time for req_time in request_counts[client_ip] 
                                if current_time - req_time < RATE_LIMIT_WINDOW]
    
    # Check rate limit
    if len(request_counts[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return jsonify({
            "error": "Rate limit exceeded",
            "status": "rate_limited",
            "message": "Too many requests. Please try again later.",
            "recomendacoes": {},
            "metadata": {
                "total_usuarios": 0,
                "total_filmes": 0,
                "filmes_nao_vistos": 0,
                "total_recomendacoes": 0,
                "processing_time": 0
            }
        }), 429
    
    # Add current request
    request_counts[client_ip].append(current_time)
    
    try:
        recomendacoes = gerar_recomendacoes(usuario)
        logger.info(f"Resposta gerada: {recomendacoes}")
        return jsonify(recomendacoes)
    except Exception as e:
        logger.error(f"Erro na rota de recomendações: {str(e)}")
        return jsonify({
            "error": str(e),
            "status": "error",
            "message": "Ocorreu um erro ao processar a requisição",
            "recomendacoes": {},
            "metadata": {
                "total_usuarios": 0,
                "total_filmes": 0,
                "filmes_nao_vistos": 0,
                "total_recomendacoes": 0,
                "processing_time": 0
            }
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
