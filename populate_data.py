#!/usr/bin/env python3
"""
Script to populate initial data by scraping Letterboxd profiles
Uses the existing scrap.py functions
"""

import time
import sys
from typing import List, Tuple, Optional
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

from data_manager import DataManager
from scrap import verify_letterboxd_user

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def _parse_rating_from_element(rating_element) -> Optional[float]:
    if not rating_element:
        return None
    text = rating_element.get_text(strip=True)
    # Original scraping used stars and halves; keep same logic
    try:
        rating = text.count("★") * 1.0
        rating += text.count("½") / 2
        return float(rating) if rating > 0 else None
    except Exception:
        return None

def scrape_user_data(data_manager: DataManager, username: str, max_pages: int = 5) -> bool:
    """
    Scrape a Letterboxd user's watched films and insert into the provided DataManager.
    Returns True if at least one movie/rating was added, False otherwise.
    This function tries to be flexible about DataManager API (several common method names are supported).
    """
    if not verify_letterboxd_user(username):
        print(f"Usuário {username} não encontrado no Letterboxd")
        return False

    base_url = f"https://letterboxd.com/{username}/films/by/date/page/"
    watched: List[Tuple[str, Optional[float]]] = []
    page = 1

    try:
        while page <= max_pages:
            url = f"{base_url}{page}/"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=6)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"Erro ao acessar {url}: {e}", file=sys.stderr)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            posters = soup.find_all("li", class_="poster-container")
            if not posters:
                break

            for p in posters:
                try:
                    img = p.find("img")
                    if not img or not img.get("alt"):
                        continue
                    title = img["alt"].strip()
                    rating_el = p.find("span", class_="rating")
                    rating = _parse_rating_from_element(rating_el)
                    watched.append((title, rating))
                except Exception as e:
                    print(f"Erro ao processar poster: {e}", file=sys.stderr)
                    continue

            page += 1
            time.sleep(0.3)

    except Exception as e:
        print(f"Erro durante scraping do usuário {username}: {e}", file=sys.stderr)
        return False

    if not watched:
        print(f"Nenhum filme encontrado para {username}")
        return False

    inserted_any = False

    # Ensure user exists in data_manager
    try:
        if hasattr(data_manager, "user_exists"):
            if not data_manager.user_exists(username):
                if hasattr(data_manager, "add_user"):
                    data_manager.add_user(username)
                else:
                    # best-effort: try generic create_user
                    if hasattr(data_manager, "create_user"):
                        data_manager.create_user(username)
        else:
            if hasattr(data_manager, "add_user"):
                data_manager.add_user(username)
    except Exception as e:
        print(f"Erro ao garantir usuário no DataManager: {e}", file=sys.stderr)

    for title, rating in watched:
        try:
            # Try to add movie if DataManager supports it
            try:
                if hasattr(data_manager, "add_movie"):
                    data_manager.add_movie(title)
                elif hasattr(data_manager, "create_movie"):
                    data_manager.create_movie(title)
            except Exception:
                # ignore movie-add errors, maybe already exists
                pass

            # Try several ways to add rating
            added = False
            if rating is not None:
                try:
                    if hasattr(data_manager, "add_rating"):
                        # common signature: (username, title, rating)
                        data_manager.add_rating(username, title, rating)
                        added = True
                    elif hasattr(data_manager, "add_user_rating"):
                        data_manager.add_user_rating(username, title, rating)
                        added = True
                    else:
                        # Try by ids if methods exist
                        uid = None
                        mid = None
                        if hasattr(data_manager, "get_user_id"):
                            uid = data_manager.get_user_id(username)
                        if hasattr(data_manager, "get_movie_id"):
                            mid = data_manager.get_movie_id(title)
                        if uid is not None and mid is not None and hasattr(data_manager, "add_rating_by_ids"):
                            data_manager.add_rating_by_ids(uid, mid, rating)
                            added = True
                except Exception as e:
                    print(f"Erro ao inserir avaliação ({username}, {title}, {rating}): {e}", file=sys.stderr)

            # If no rating or adding rating not supported, still consider movie added
            if rating is None:
                inserted_any = True
            else:
                inserted_any = inserted_any or added

        except Exception as e:
            print(f"Erro ao processar {title}: {e}", file=sys.stderr)
            continue

    print(f"Scraping concluído para {username}. Filmes processados: {len(watched)}. Inserções efetivas: {inserted_any}")
    return inserted_any

def populate_initial_data(usernames: Optional[List[str]] = None) -> dict:
    """
    Populate initial data using a set of Letterboxd profiles.
    Returns a summary dict with counts.
    """
    dm = DataManager()
    seed_users = usernames or [
        "martinscorsese",
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
        "christophernolan"
    ]

    summary = {"attempted": 0, "successful": 0, "skipped": 0, "errors": []}

    for u in seed_users:
        summary["attempted"] += 1
        try:
            if not verify_letterboxd_user(u):
                summary["skipped"] += 1
                print(f"Usuário {u} não existe - pulando")
                continue

            # Ensure user exists
            try:
                if hasattr(dm, "user_exists") and dm.user_exists(u):
                    print(f"Usuário {u} já existe no DataManager")
                else:
                    if hasattr(dm, "add_user"):
                        dm.add_user(u)
                        print(f"Usuário {u} criado no DataManager")
            except Exception as e:
                print(f"Erro ao criar/garantir usuário {u}: {e}", file=sys.stderr)

            added = scrape_user_data(dm, u)
            if added:
                summary["successful"] += 1
            else:
                summary["skipped"] += 1

        except Exception as e:
            summary["errors"].append({"user": u, "error": str(e)})
            print(f"Erro ao popular dados para {u}: {e}", file=sys.stderr)
        time.sleep(0.5)

    print("Populate concluído:", summary)
    return summary

def main():
    """Main function to run the data population"""
    populate_initial_data()

if __name__ == "__main__":
    main()
