#!/bin/bash

# Startup script for Railway deployment

echo "Starting Letterboxd Backend..."

# Check if we're in Railway environment
if [ -n "$RAILWAY_ENVIRONMENT" ]; then
    echo "Running in Railway environment"
fi

# Wait for database to be ready (if needed)
echo "Checking database connection..."
python -c "
import psycopg2
import os
import time
from dotenv import load_dotenv

load_dotenv()

max_retries = 30
retry_count = 0

while retry_count < max_retries:
    try:
        conn = psycopg2.connect(
            dbname=os.getenv('PGDATABASE'),
            user=os.getenv('PGUSER'),
            password=os.getenv('PGPASSWORD'),
            host=os.getenv('PGHOST'),
            port=os.getenv('PGPORT')
        )
        conn.close()
        print('Database connection successful!')
        break
    except Exception as e:
        print(f'Database connection failed (attempt {retry_count + 1}/{max_retries}): {e}')
        retry_count += 1
        time.sleep(2)

if retry_count >= max_retries:
    print('Failed to connect to database after maximum retries')
    exit(1)
"

# Start the application
echo "Starting Gunicorn server..."
exec gunicorn --config gunicorn.conf.py app:app 