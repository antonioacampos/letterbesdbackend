"""
Data Manager - Handles data storage using JSON files instead of PostgreSQL
"""

import json
import os
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, "users.json")
        self.movies_file = os.path.join(data_dir, "movies.json")
        self.ratings_file = os.path.join(data_dir, "ratings.json")
        
        # Create data directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize files if they don't exist
        self._init_files()
    
    def _init_files(self):
        """Initialize JSON files if they don't exist"""
        if not os.path.exists(self.users_file):
            with open(self.users_file, 'w') as f:
                json.dump([], f)
        
        if not os.path.exists(self.movies_file):
            with open(self.movies_file, 'w') as f:
                json.dump([], f)
        
        if not os.path.exists(self.ratings_file):
            with open(self.ratings_file, 'w') as f:
                json.dump([], f)
    
    def _load_data(self, file_path: str) -> List[Dict]:
        """Load data from JSON file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _save_data(self, file_path: str, data: List[Dict]):
        """Save data to JSON file"""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_user_id(self, username: str) -> Optional[int]:
        """Get user ID by username"""
        users = self._load_data(self.users_file)
        for user in users:
            if user['username'] == username:
                return user['id']
        return None
    
    def add_user(self, username: str) -> int:
        """Add user and return user ID"""
        users = self._load_data(self.users_file)
        
        # Check if user already exists
        for user in users:
            if user['username'] == username:
                return user['id']
        
        # Add new user
        new_id = len(users) + 1
        users.append({
            'id': new_id,
            'username': username
        })
        self._save_data(self.users_file, users)
        return new_id
    
    def get_movie_id(self, title: str) -> Optional[int]:
        """Get movie ID by title"""
        movies = self._load_data(self.movies_file)
        for movie in movies:
            if movie['title'] == title:
                return movie['id']
        return None
    
    def add_movie(self, title: str) -> int:
        """Add movie and return movie ID"""
        movies = self._load_data(self.movies_file)
        
        # Check if movie already exists
        for movie in movies:
            if movie['title'] == title:
                return movie['id']
        
        # Add new movie
        new_id = len(movies) + 1
        movies.append({
            'id': new_id,
            'title': title
        })
        self._save_data(self.movies_file, movies)
        return new_id
    
    def add_rating(self, user_id: int, movie_id: int, rating: float):
        """Add rating"""
        ratings = self._load_data(self.ratings_file)
        
        # Check if rating already exists
        for rating_data in ratings:
            if rating_data['user_id'] == user_id and rating_data['movie_id'] == movie_id:
                rating_data['rating'] = rating
                self._save_data(self.ratings_file, ratings)
                return
        
        # Add new rating
        ratings.append({
            'user_id': user_id,
            'movie_id': movie_id,
            'rating': rating
        })
        self._save_data(self.ratings_file, ratings)
    
    def get_user_ratings(self, username: str) -> List[Tuple[str, float]]:
        """Get user ratings as list of (title, rating) tuples"""
        user_id = self.get_user_id(username)
        if not user_id:
            return []
        
        ratings = self._load_data(self.ratings_file)
        movies = self._load_data(self.movies_file)
        
        # Create movie ID to title mapping
        movie_id_to_title = {movie['id']: movie['title'] for movie in movies}
        
        # Get user's ratings
        user_ratings = []
        for rating_data in ratings:
            if rating_data['user_id'] == user_id:
                movie_title = movie_id_to_title.get(rating_data['movie_id'])
                if movie_title:
                    user_ratings.append((movie_title, rating_data['rating']))
        
        return user_ratings
    
    def get_all_ratings(self) -> List[Tuple[str, str, float]]:
        """Get all ratings as list of (username, title, rating) tuples"""
        users = self._load_data(self.users_file)
        movies = self._load_data(self.movies_file)
        ratings = self._load_data(self.ratings_file)
        
        # Create ID to name mappings
        user_id_to_name = {user['id']: user['username'] for user in users}
        movie_id_to_title = {movie['id']: movie['title'] for movie in movies}
        
        # Get all ratings
        all_ratings = []
        for rating_data in ratings:
            username = user_id_to_name.get(rating_data['user_id'])
            movie_title = movie_id_to_title.get(rating_data['movie_id'])
            if username and movie_title:
                all_ratings.append((username, movie_title, rating_data['rating']))
        
        return all_ratings
    
    def get_popular_movies(self, limit: int = 10) -> List[Tuple[str, float]]:
        """Get popular movies as list of (title, avg_rating) tuples"""
        all_ratings = self.get_all_ratings()
        
        # Group by movie title
        movie_ratings = {}
        for username, title, rating in all_ratings:
            if title not in movie_ratings:
                movie_ratings[title] = []
            movie_ratings[title].append(rating)
        
        # Calculate average ratings
        popular_movies = []
        for title, ratings in movie_ratings.items():
            if len(ratings) >= 2:  # At least 2 ratings
                avg_rating = sum(ratings) / len(ratings)
                popular_movies.append((title, avg_rating))
        
        # Sort by average rating and return top movies
        popular_movies.sort(key=lambda x: x[1], reverse=True)
        return popular_movies[:limit]
    
    def user_exists(self, username: str) -> bool:
        """Check if user exists"""
        return self.get_user_id(username) is not None
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        users = self._load_data(self.users_file)
        movies = self._load_data(self.movies_file)
        ratings = self._load_data(self.ratings_file)
        
        return {
            'total_users': len(users),
            'total_movies': len(movies),
            'total_ratings': len(ratings)
        }
