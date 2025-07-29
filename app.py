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
import psutil

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
REQUEST_TIMEOUT = 15  # seconds - reduced for Railway
MAX_USERS_FOR_CLUSTERING = 500
MAX_MOVIES_FOR_PROCESSING = 500  # Further reduced to prevent memory issues

# Rate limiting
request_counts = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window

# Simple cache for user data
user_cache = {}
CACHE_EXPIRY = 300  # 5 minutes

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

@app.route('/api/test/<usuario>')
def test_user(usuario):
    """Quick test endpoint that doesn't do heavy processing"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = %s", (usuario,))
        user_exists = cursor.fetchone() is not None
        conn.close()
        
        return jsonify({
            "status": "success",
            "user_exists": user_exists,
            "username": usuario,
            "message": "User check completed"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "username": usuario
        }), 500

@app.route('/api/memory')
def memory_status():
    """Check memory usage"""
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return jsonify({
            "status": "success",
            "memory_mb": memory_info.rss / 1024 / 1024,
            "memory_percent": process.memory_percent(),
            "cpu_percent": process.cpu_percent(),
            "cache_size": len(user_cache),
            "timestamp": time.time()
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
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
        
        # Get user's watched movies
        query_user = """
        SELECT m.title, r.rating
        FROM ratings r
        JOIN users u ON r.user_id = u.id
        JOIN movies m ON r.movie_id = m.id
        WHERE u.username = %s
        """
        df_user = pd.read_sql(query_user, conn, params=(usuario_alvo,))
        
        # Get top popular movies (simplified approach)
        query_popular = """
        SELECT m.title, AVG(r.rating) as avg_rating, COUNT(r.rating) as num_ratings
        FROM ratings r
        JOIN movies m ON r.movie_id = m.id
        GROUP BY m.title
        HAVING COUNT(r.rating) >= 3
        ORDER BY COUNT(r.rating) DESC, AVG(r.rating) DESC
        LIMIT %s
        """
        df_popular = pd.read_sql(query_popular, conn, params=(MAX_MOVIES_FOR_PROCESSING,))
        
        conn.close()
        
        if len(df_user) == 0:
            return None, "insufficient_data"
            
        return {
            'user_movies': df_user,
            'popular_movies': df_popular
        }, "success"
        
    except Exception as e:
        logger.error(f"Erro ao buscar dados: {str(e)}")
        return None, "error"

def simple_recommendation_algorithm(data_dict, usuario_alvo):
    """Ultra-simplified recommendation algorithm for Railway performance"""
    logger.info("Usando algoritmo ultra-simplificado de recomendação")
    
    user_movies = data_dict['user_movies']
    popular_movies = data_dict['popular_movies']
    
    # Get user's average rating
    user_avg = user_movies['rating'].mean() if len(user_movies) > 0 else 3.0
    
    # Get user's watched movies
    user_watched = set(user_movies['title'].tolist())
    
    recomendacoes = []
    
    # Recommend from popular movies that user hasn't watched
    for _, row in popular_movies.iterrows():
        title = row['title']
        avg_rating = row['avg_rating']
        num_ratings = row['num_ratings']
        
        if title not in user_watched:
            # Simple scoring: rating + popularity bonus
            score = float(avg_rating) * (1 + 0.1 * min(num_ratings / 10, 2))
            
            # Bonus for movies with similar rating to user's average
            rating_diff = abs(avg_rating - user_avg)
            if rating_diff < 1.0:
                score *= 1.15
            
            recomendacoes.append({
                'filme': title,
                'score': score
            })
    
    return recomendacoes

@timeout_decorator(REQUEST_TIMEOUT)
def gerar_recomendacoes(usuario_alvo):
    logger.info(f"Iniciando geração de recomendações para usuário: {usuario_alvo}")
    start_time = time.time()
    
    # Quick fallback for immediate response
    def quick_fallback():
        return {
            "status": "success",
            "message": "Recomendações rápidas geradas (modo de emergência)",
            "recomendacoes": {
                "The Shawshank Redemption": 9.3,
                "The Godfather": 9.2,
                "Pulp Fiction": 8.9,
                "Fight Club": 8.8,
                "Forrest Gump": 8.8,
                "The Matrix": 8.7,
                "Goodfellas": 8.7,
                "The Silence of the Lambs": 8.6,
                "Interstellar": 8.6,
                "The Departed": 8.5
            },
            "metadata": {
                "total_usuarios": 1,
                "total_filmes": 10,
                "filmes_nao_vistos": 10,
                "total_recomendacoes": 10,
                "processing_time": time.time() - start_time,
                "mode": "fallback"
            }
        }
    
    try:
        # Check cache first
        current_time = time.time()
        if usuario_alvo in user_cache and (current_time - user_cache[usuario_alvo]['timestamp']) < CACHE_EXPIRY:
            logger.info(f"Usando dados em cache para usuário: {usuario_alvo}")
            data_dict = user_cache[usuario_alvo]['data']
            status = "success"
        else:
            # Get data efficiently
            data_dict, status = get_user_data_efficiently(usuario_alvo)
            if status == "success":
                user_cache[usuario_alvo] = {
                    'data': data_dict,
                    'timestamp': current_time
                }
        
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
        
        if status == "error" or data_dict is None:
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

        logger.info(f"Total de filmes do usuário: {len(data_dict['user_movies'])}")
        logger.info(f"Total de filmes populares: {len(data_dict['popular_movies'])}")
        
        # Use ultra-simplified algorithm for Railway performance
        recomendacoes = simple_recommendation_algorithm(data_dict, usuario_alvo)
        
        # Sort and limit recommendations
        recomendacoes.sort(key=lambda x: x['score'], reverse=True)
        recomendacoes_formatadas = {rec['filme']: rec['score'] for rec in recomendacoes[:10]}
        
        processing_time = time.time() - start_time
        logger.info(f"Recomendações geradas em {processing_time:.2f} segundos")
        
        # Clean up memory
        del data_dict
        del recomendacoes
        
        response = {
            "status": "success",
            "message": "Recomendações geradas com sucesso",
            "recomendacoes": recomendacoes_formatadas,
            "metadata": {
                "total_usuarios": 1,  # Just the target user
                "total_filmes": len(data_dict['popular_movies']) if 'data_dict' in locals() else 0,
                "filmes_nao_vistos": len(recomendacoes_formatadas),
                "total_recomendacoes": len(recomendacoes_formatadas),
                "processing_time": processing_time
            }
        }
        
        return response

    except TimeoutError:
        logger.error("Timeout ao gerar recomendações - usando fallback")
        return quick_fallback()
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
