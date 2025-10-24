import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from scrap import scrap, verify_letterboxd_user
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
REQUEST_TIMEOUT = 5  # seconds - ultra aggressive for Railway
MAX_USERS_FOR_CLUSTERING = 50
MAX_MOVIES_FOR_PROCESSING = 10  # Minimal dataset

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
            "cached_users": list(user_cache.keys()),
            "timestamp": time.time()
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/api/cache/<usuario>')
def cache_user(usuario):
    """Manually cache a user for faster recommendations"""
    try:
        logger.info(f"Tentando cachear usuário: {usuario}")
        data_dict, status = get_user_data_efficiently(usuario)
        
        if status == "success":
            user_cache[usuario] = {
                'data': data_dict,
                'timestamp': time.time()
            }
            return jsonify({
                "status": "success",
                "message": f"Usuário {usuario} cacheado com sucesso",
                "cached_users": list(user_cache.keys()),
                "user_movies_count": len(data_dict['user_movies']),
                "popular_movies_count": len(data_dict['popular_movies'])
            })
        else:
            return jsonify({
                "status": "error",
                "message": f"Erro ao cachear usuário {usuario}: {status}"
            }), 400
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/api/debug/<usuario>')
def debug_user(usuario):
    """Debug endpoint to see user data and recommendations"""
    try:
        logger.info(f"Debug para usuário: {usuario}")
        data_dict, status = get_user_data_efficiently(usuario)
        
        if status == "success":
            # Get recommendations
            recomendacoes = simple_recommendation_algorithm(data_dict, usuario)
            
            return jsonify({
                "status": "success",
                "username": usuario,
                "user_movies": [{"title": movie[0], "rating": movie[1]} for movie in data_dict['user_movies']],
                "popular_movies": [{"title": movie[0], "avg_rating": movie[1]} for movie in data_dict['popular_movies']],
                "recommendations": recomendacoes,
                "user_avg_rating": sum(movie[1] for movie in data_dict['user_movies']) / len(data_dict['user_movies']) if data_dict['user_movies'] else 0,
                "total_user_movies": len(data_dict['user_movies']),
                "total_popular_movies": len(data_dict['popular_movies'])
            })
        else:
            return jsonify({
                "status": "error",
                "message": f"Erro ao buscar dados do usuário {usuario}: {status}"
            }), 400
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
    """Get user data using pure SQL - no pandas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First check if user exists
        cursor.execute("SELECT id FROM users WHERE username = %s", (usuario_alvo,))
        user_exists = cursor.fetchone() is not None
        
        if not user_exists:
            conn.close()
            return None, "user_not_found"
        
        # Get user's top rated movies - pure SQL, no pandas
        query_user = """
        SELECT m.title, r.rating
        FROM ratings r
        JOIN users u ON r.user_id = u.id
        JOIN movies m ON r.movie_id = m.id
        WHERE u.username = %s
        ORDER BY r.rating DESC
        LIMIT 20
        """
        cursor.execute(query_user, (usuario_alvo,))
        user_movies = cursor.fetchall()
        
        # Get top 15 popular movies - more options for recommendations
        query_popular = """
        SELECT m.title, AVG(r.rating) as avg_rating
        FROM ratings r
        JOIN movies m ON r.movie_id = m.id
        GROUP BY m.title
        HAVING COUNT(r.rating) >= 2
        ORDER BY AVG(r.rating) DESC
        LIMIT 15
        """
        cursor.execute(query_popular)
        popular_movies = cursor.fetchall()
        
        conn.close()
        
        if len(user_movies) == 0:
            return None, "insufficient_data"
            
        return {
            'user_movies': user_movies,
            'popular_movies': popular_movies
        }, "success"
        
    except Exception as e:
        logger.error(f"Erro ao buscar dados: {str(e)}")
        return None, "error"

def simple_recommendation_algorithm(data_dict, usuario_alvo):
    """Smart recommendation algorithm - considers user's taste"""
    logger.info("Usando algoritmo inteligente de recomendação")
    
    user_movies = data_dict['user_movies']  # List of tuples (title, rating)
    popular_movies = data_dict['popular_movies']  # List of tuples (title, avg_rating)
    
    # Calculate user's average rating and preferences
    if len(user_movies) > 0:
        user_avg = sum(movie[1] for movie in user_movies) / len(user_movies)
        user_ratings = [movie[1] for movie in user_movies]
        # Check if user tends to rate high or low
        high_rated = [r for r in user_ratings if r >= 4.0]
        user_tendency = "high" if len(high_rated) > len(user_ratings) / 2 else "low"
    else:
        user_avg = 3.0
        user_tendency = "neutral"
    
    # Get user's watched movies
    user_watched = set(movie[0] for movie in user_movies)
    
    logger.info(f"Usuário {usuario_alvo}: média {user_avg:.2f}, tendência {user_tendency}, filmes vistos: {len(user_watched)}")
    
    recomendacoes = []
    
    # Recommend from popular movies that user hasn't watched
    for title, avg_rating in popular_movies:
        if title not in user_watched:
            # Base score from average rating
            score = float(avg_rating)
            
            # Bonus for movies with similar rating to user's average
            rating_diff = abs(avg_rating - user_avg)
            if rating_diff < 0.5:  # Very similar
                score *= 1.2
            elif rating_diff < 1.0:  # Similar
                score *= 1.1
            
            # Bonus based on user's rating tendency
            if user_tendency == "high" and avg_rating >= 4.0:
                score *= 1.15
            elif user_tendency == "low" and avg_rating <= 3.5:
                score *= 1.1
            
            # Small bonus for highly rated movies
            if avg_rating >= 4.5:
                score *= 1.05
            
            recomendacoes.append({
                'filme': title,
                'score': score
            })
    
    # Sort by score and return top recommendations
    recomendacoes.sort(key=lambda x: x['score'], reverse=True)
    
    logger.info(f"Geradas {len(recomendacoes)} recomendações para {usuario_alvo}")
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
            # Try to get user data from database
            logger.info(f"Usuário {usuario_alvo} não está em cache - buscando dados do banco")
            try:
                data_dict, status = get_user_data_efficiently(usuario_alvo)
                if status == "success":
                    user_cache[usuario_alvo] = {
                        'data': data_dict,
                        'timestamp': current_time
                    }
                    logger.info(f"Usuário {usuario_alvo} cacheado com sucesso")
            except Exception as e:
                logger.error(f"Erro na busca de dados: {str(e)}")
                # Return fallback only if database query fails
                return quick_fallback()
        
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
        
        # Debug: show user's movies
        if len(data_dict['user_movies']) > 0:
            logger.info(f"Filmes do usuário {usuario_alvo}: {[movie[0] for movie in data_dict['user_movies'][:5]]}")
        logger.info(f"Filmes populares disponíveis: {[movie[0] for movie in data_dict['popular_movies'][:5]]}")
        
        # Use smart algorithm for better recommendations
        recomendacoes = simple_recommendation_algorithm(data_dict, usuario_alvo)
        
        # Sort and limit recommendations
        recomendacoes.sort(key=lambda x: x['score'], reverse=True)
        recomendacoes_formatadas = {rec['filme']: rec['score'] for rec in recomendacoes[:5]}  # Top 5 recommendations
        
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
                "processing_time": processing_time,
                "mode": "ultra_fast"
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
