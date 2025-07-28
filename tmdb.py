import requests

api_key = "b3661e4adf34873a50fd784e23823462"
base_url = "https://api.themoviedb.org/3"

def get_movies_from_tmdb(page=1):
    url = f"{base_url}/discover/movie?api_key={api_key}&page={page}&sort_by=popularity.desc"
    
    response = requests.get(url)
     
    if response.status_code != 200:
        print(f"Erro ao acessar a API do TMDb: {response.status_code}")
        return None

    data = response.json()

    if not data['results']:
        return None

    movies = []
    
    for movie in data['results']:
        print(movie)
        title = movie.get("title")
        rating = movie.get("vote_average", "Sem avaliação")
        movies.append((title, rating))

    return movies

def main():
    page = 1
    all_movies = []

    while True:
        movies = get_movies_from_tmdb(page)
        
        if not movies:
            break

        all_movies.extend(movies)

        print(f"Página {page} capturada com {len(movies)} filmes.")
        page += 1

    print("\nTodos os filmes capturados:")
    for title, rating in all_movies:
        print(f"Filme: {title} | Avaliação: {rating}")

    print(f"\nTotal de filmes capturados: {len(all_movies)}")

if _name_ == "_main_":
    main()