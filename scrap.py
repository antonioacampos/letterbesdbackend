import psycopg2
from dotenv import load_dotenv
import os
import requests
from bs4 import BeautifulSoup
import sys
from contextlib import contextmanager
from typing import Optional, List, Tuple
import time

load_dotenv()

dbname = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")

required_env_vars = ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

print(f"Configurações do banco de dados:")
print(f"DB_NAME: {dbname}")
print(f"DB_USER: {user}")
print(f"DB_HOST: {host}")
print(f"DB_PORT: {port}")

@contextmanager
def get_db_connection():
    """Context manager para gerenciar a conexão com o banco de dados."""
    conn = None
    try:
        print("Tentando conectar ao banco de dados...")
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        print("Conexão com o banco de dados estabelecida com sucesso!")
        yield conn
    except psycopg2.Error as e:
        print(f"Erro ao conectar ao banco de dados: {e}", file=sys.stderr)
        raise
    finally:
        if conn is not None:
            print("Fechando conexão com o banco de dados...")
            conn.close()

def check_database_state(cursor) -> dict:
    """Verifica o estado atual do banco de dados."""
    try:
        print("Verificando estado do banco de dados...")
        cursor.execute("SELECT COUNT(*) FROM users;")
        users_count = cursor.fetchone()[0]
        print(f"Total de usuários: {users_count}")
        
        cursor.execute("SELECT COUNT(*) FROM movies;")
        movies_count = cursor.fetchone()[0]
        print(f"Total de filmes: {movies_count}")
        
        cursor.execute("SELECT COUNT(*) FROM ratings;")
        ratings_count = cursor.fetchone()[0]
        print(f"Total de avaliações: {ratings_count}")
        
        return {
            "users": users_count,
            "movies": movies_count,
            "ratings": ratings_count
        }
    except psycopg2.Error as e:
        print(f"Erro ao verificar estado do banco: {e}", file=sys.stderr)
        raise

def insert_user(cursor, conn, username: str) -> int:
    try:
        print(f"Tentando inserir usuário: {username}")
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            print(f"Usuário {username} já existe com ID: {existing_user[0]}")
            return existing_user[0]
            
        cursor.execute("INSERT INTO users (username) VALUES (%s) RETURNING id;", (username,))
        user_id = cursor.fetchone()[0]
        print(f"Usuário {username} inserido com sucesso. ID: {user_id}")
        return user_id
    except psycopg2.errors.UniqueViolation:
        print(f"Usuário {username} já existe. Buscando ID...")
        conn.rollback()
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()
        if result is None:
            raise Exception(f"Erro ao buscar usuário: {username}")
        print(f"ID do usuário {username} encontrado: {result[0]}")
        return result[0]
    except Exception as e:
        print(f"Erro ao inserir usuário {username}: {str(e)}")
        conn.rollback()
        raise

def insert_movie(cursor, conn, title: str) -> int:
    try:
        print(f"Tentando inserir filme: {title}")
        cursor.execute("SELECT id FROM movies WHERE title = %s", (title,))
        existing_movie = cursor.fetchone()
        
        if existing_movie:
            print(f"Filme {title} já existe com ID: {existing_movie[0]}")
            return existing_movie[0]
            
        cursor.execute("INSERT INTO movies (title) VALUES (%s) RETURNING id;", (title,))
        movie_id = cursor.fetchone()[0]
        print(f"Filme {title} inserido com sucesso. ID: {movie_id}")
        return movie_id
    except psycopg2.errors.UniqueViolation:
        print(f"Filme {title} já existe. Buscando ID...")
        conn.rollback()
        cursor.execute("SELECT id FROM movies WHERE title = %s", (title,))
        result = cursor.fetchone()
        if result is None:
            raise Exception(f"Erro ao buscar filme: {title}")
        print(f"ID do filme {title} encontrado: {result[0]}")
        return result[0]
    except Exception as e:
        print(f"Erro ao inserir filme {title}: {str(e)}")
        conn.rollback()
        raise

def insert_rating(cursor, conn, user_id: int, movie_id: int, rating: float) -> None:
    try:
        print(f"Tentando inserir avaliação: usuário {user_id}, filme {movie_id}, nota {rating}")
        cursor.execute(
            "SELECT id FROM ratings WHERE user_id = %s AND movie_id = %s",
            (user_id, movie_id)
        )
        existing_rating = cursor.fetchone()
        
        if existing_rating:
            print(f"Avaliação já existe para usuário {user_id} e filme {movie_id}")
            return
            
        cursor.execute(
            "INSERT INTO ratings (user_id, movie_id, rating) VALUES (%s, %s, %s);",
            (user_id, movie_id, rating)
        )
        print(f"Avaliação inserida com sucesso")
    except Exception as e:
        print(f"Erro ao inserir avaliação: {str(e)}")
        conn.rollback()
        raise

def verify_letterboxd_user(username: str) -> bool:
    """Verifica se um usuário existe no Letterboxd."""
    url = f"https://letterboxd.com/{username}/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False

def scrap(cursor, conn, username: str) -> None:
    if not verify_letterboxd_user(username):
        raise Exception(f"Usuário {username} não existe no Letterboxd")

    base_url = f"https://letterboxd.com/{username}/films/by/date/page/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    watched_movies: List[Tuple[str, Optional[float]]] = []
    page = 1

    try:
        print(f"\nIniciando scraping para usuário {username}")
        while True:
            url = f"{base_url}{page}/"
            print(f"Acessando página {page}: {url}")
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"Erro ao acessar página {page} para usuário {username}: {str(e)}", file=sys.stderr)
                break

            soup = BeautifulSoup(response.text, "html.parser")
            movies = soup.find_all("li", class_="poster-container")
            print(f"Encontrados {len(movies)} filmes na página {page}")

            if not movies:
                print(f"Nenhum filme encontrado na página {page}. Finalizando scraping.")
                break

            for movie in movies:
                try:
                    title = movie.find("img")["alt"]
                    rating_element = movie.find("span", class_="rating")
                    rating = None
                    if rating_element:
                        rating_text = rating_element.text.strip()
                        rating = rating_text.count("★") * 1.0
                        rating += rating_text.count("½") / 2
                    watched_movies.append((title, rating))
                    print(f"Filme encontrado: {title} (Nota: {rating})")
                except Exception as e:
                    print(f"Erro ao processar filme na página {page}: {str(e)}", file=sys.stderr)
                    continue

            page += 1
            time.sleep(1)

        if not watched_movies:
            raise Exception(f"Nenhum filme encontrado para o usuário {username}")

        print(f"\nTotal de filmes encontrados para {username}: {len(watched_movies)}")

        user_id = insert_user(cursor, conn, username)
        print(f"Usuário {username} inserido com ID {user_id}")

        movies_inserted = 0
        ratings_inserted = 0
        for title, rating in watched_movies:
            try:
                movie_id = insert_movie(cursor, conn, title)
                movies_inserted += 1
                if isinstance(rating, (float, int)):
                    insert_rating(cursor, conn, user_id, movie_id, rating)
                    ratings_inserted += 1
            except Exception as e:
                print(f"Erro ao processar filme {title}: {str(e)}", file=sys.stderr)
                continue

        conn.commit()
        print(f"\nResumo para usuário {username}:")
        print(f"- Filmes inseridos: {movies_inserted}")
        print(f"- Avaliações inseridas: {ratings_inserted}")
        print(f"Dados do usuário {username} inseridos com sucesso")

    except Exception as e:
        conn.rollback()
        raise Exception(f"Erro durante o scraping para usuário {username}: {str(e)}")

def main():
    usernames = ["martinscorsese",
  "quentintarantino",
  "wesanderson",
  "tarab",
  "steven_spielberg",
  "paulthomasanderson",
  "kathrynbigelow",
  "davidfincher",
  "emilymorgan",
  "charlize_theron",
  "robertdowneyjr",
  "jamescameron",
  "jenniferlawrence",
  "ridleyscott",
  "christophernolan"]
    valid_usernames = []

    print("Verificando usuários no Letterboxd...")
    for username in usernames:
        if verify_letterboxd_user(username):
            valid_usernames.append(username)
            print(f"Usuário {username} encontrado no Letterboxd")
        else:
            print(f"Usuário {username} não encontrado no Letterboxd - será ignorado")

    if not valid_usernames:
        print("Nenhum usuário válido encontrado. Encerrando.")
        return

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            print("\nEstado inicial do banco de dados:")
            initial_state = check_database_state(cursor)
            print(f"Users: {initial_state['users']}")
            print(f"Movies: {initial_state['movies']}")
            print(f"Ratings: {initial_state['ratings']}")
            
            for username in valid_usernames:
                try:
                    print(f"\nProcessando usuário: {username}")
                    scrap(cursor, conn, username)
                    
                    print(f"\nEstado do banco após processar {username}:")
                    current_state = check_database_state(cursor)
                    print(f"Users: {current_state['users']}")
                    print(f"Movies: {current_state['movies']}")
                    print(f"Ratings: {current_state['ratings']}")
                    
                except Exception as e:
                    print(f"Erro ao processar usuário {username}: {str(e)}", file=sys.stderr)
                    continue

    print("\nProcessamento concluído.")

if __name__ == "__main__":
    main()
