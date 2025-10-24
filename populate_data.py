#!/usr/bin/env python3
"""
Script to populate initial data by scraping Letterboxd profiles
Uses the existing scrap.py functions
"""

from data_manager import DataManager
from scrap import scrap, verify_letterboxd_user
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def scrape_user_data(data_manager, username):
    """Scrape a user's data from Letterboxd using existing scrap.py logic"""
    logger.info(f"Scraping data for user: {username}")
    
    # Verify user exists on Letterboxd
    if not verify_letterboxd_user(username):
        logger.error(f"User {username} not found on Letterboxd")
        return False
    
    try:
        # Add user to data manager
        user_id = data_manager.add_user(username)
        logger.info(f"User {username} added with ID {user_id}")
        
        # Use the existing scrap function logic but adapt for DataManager
        from bs4 import BeautifulSoup
        import requests
        
        base_url = f"https://letterboxd.com/{username}/films/by/date/page/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        watched_movies = []
        page = 1
        max_pages = 5  # Same as scrap.py
        
        logger.info(f"Starting scraping for user {username}")
        while page <= max_pages:
            url = f"{base_url}{page}/"
            logger.info(f"Accessing page {page}: {url}")
            
            try:
                response = requests.get(url, headers=headers, timeout=5)
                response.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"Error accessing page {page} for user {username}: {str(e)}")
                break
            
            soup = BeautifulSoup(response.text, "html.parser")
            movies = soup.find_all("li", class_="poster-container")
            logger.info(f"Found {len(movies)} movies on page {page}")
            
            if not movies:
                logger.info(f"No movies found on page {page}. Ending scraping.")
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
                    logger.info(f"Movie found: {title} (Rating: {rating})")
                except Exception as e:
                    logger.error(f"Error processing movie on page {page}: {str(e)}")
                    continue
            
            page += 1
            time.sleep(0.5)  # Same as scrap.py
        
        if not watched_movies:
            logger.warning(f"No movies found for user {username}")
            return False
        
        logger.info(f"Total movies found for {username}: {len(watched_movies)}")
        
        # Add scraped movies to data manager
        movies_inserted = 0
        ratings_inserted = 0
        
        for title, rating in watched_movies:
            try:
                movie_id = data_manager.add_movie(title)
                movies_inserted += 1
                if isinstance(rating, (float, int)):
                    data_manager.add_rating(user_id, movie_id, rating)
                    ratings_inserted += 1
            except Exception as e:
                logger.error(f"Error processing movie {title}: {str(e)}")
                continue
        
        logger.info(f"Summary for user {username}:")
        logger.info(f"- Movies inserted: {movies_inserted}")
        logger.info(f"- Ratings inserted: {ratings_inserted}")
        logger.info(f"User {username} data inserted successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"Error scraping user {username}: {str(e)}")
        return False

def populate_initial_data():
    """Populate the system by scraping real Letterboxd profiles"""
    data_manager = DataManager()
    
    # Real Letterboxd users to scrape
    users_to_scrape = [
        "gutomp4",
        "filmaria", 
        "martinscorsese",
        "quentintarantino",
        "wesanderson"
    ]
    
    logger.info("Starting to populate data by scraping Letterboxd profiles...")
    
    successful_users = 0
    failed_users = []
    
    # Scrape each user
    for username in users_to_scrape:
        logger.info(f"Processing user: {username}")
        
        if scrape_user_data(data_manager, username):
            successful_users += 1
            logger.info(f"✅ Successfully scraped {username}")
        else:
            failed_users.append(username)
            logger.error(f"❌ Failed to scrape {username}")
        
        # Small delay between users to be respectful
        time.sleep(2)
    
    # Get final stats
    stats = data_manager.get_stats()
    logger.info(f"Data population completed!")
    logger.info(f"Successfully scraped: {successful_users} users")
    logger.info(f"Failed users: {failed_users}")
    logger.info(f"Total users in system: {stats['total_users']}")
    logger.info(f"Total movies: {stats['total_movies']}")
    logger.info(f"Total ratings: {stats['total_ratings']}")
    
    # Show some popular movies
    if stats['total_ratings'] > 0:
        popular = data_manager.get_popular_movies(5)
        logger.info("Top 5 popular movies:")
        for title, avg_rating in popular:
            logger.info(f"  {title}: {avg_rating:.2f}")
    else:
        logger.warning("No ratings found in the system")

if __name__ == "__main__":
    populate_initial_data()
