#!/usr/bin/env python3
"""
Test script to verify Letterboxd scraping is working
"""

import requests
import time
import json

def test_scraping():
    """Test the scraping functionality"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Letterboxd Scraping...")
    print("=" * 50)
    
    # Test 1: Health check
    print("\n1. Testing health check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Data Manager: {data.get('data_manager', 'unknown')}")
            print(f"   Stats: {data.get('stats', {})}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    # Test 2: Populate data (scraping)
    print("\n2. Testing data population (scraping)...")
    print("   This will scrape real data from Letterboxd profiles...")
    print("   This may take a few minutes...")
    
    try:
        response = requests.post(f"{base_url}/populate", timeout=300)  # 5 minute timeout
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Message: {data.get('message', 'Success')}")
        else:
            print(f"   Error: {response.text}")
    except requests.exceptions.Timeout:
        print("   ⏰ Timeout - Scraping took too long")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    # Test 3: Check stats after population
    print("\n3. Checking stats after population...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            stats = data.get('stats', {})
            print(f"   Total users: {stats.get('total_users', 0)}")
            print(f"   Total movies: {stats.get('total_movies', 0)}")
            print(f"   Total ratings: {stats.get('total_ratings', 0)}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    # Test 4: Test recommendations
    print("\n4. Testing recommendations...")
    test_users = ["gutomp4", "filmaria", "martinscorsese"]
    
    for user in test_users:
        print(f"\n   Testing recommendations for {user}...")
        try:
            response = requests.get(f"{base_url}/api/recomendacoes/{user}", timeout=30)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    recommendations = data.get('recomendacoes', {})
                    print(f"   Recommendations: {len(recommendations)} movies")
                    for movie, score in list(recommendations.items())[:3]:
                        print(f"     - {movie}: {score:.2f}")
                else:
                    print(f"   Error: {data.get('message', 'Unknown error')}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Error: {str(e)}")
    
    print("\n" + "=" * 50)
    print("✅ Scraping test completed!")
    print("\n💡 Tips:")
    print("   - If scraping fails, check your internet connection")
    print("   - Letterboxd may rate limit requests, try again later")
    print("   - Check the logs for detailed error messages")

if __name__ == "__main__":
    test_scraping()
