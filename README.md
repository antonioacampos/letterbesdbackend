# Letterboxd Backend - Optimized for Railway

This is an optimized version of the Letterboxd recommendation backend designed to run efficiently on Railway without timeout or memory issues.

## Key Optimizations

### 1. **Timeout Handling**
- Added 25-second timeout for recommendation generation
- Proper timeout decorator with signal handling
- Graceful timeout responses

### 2. **Memory Optimization**
- Limited data processing (max 1000 movies)
- Efficient database queries with limits
- Memory cleanup after processing
- Simplified recommendation algorithm

### 3. **Performance Improvements**
- Reduced scraping timeouts (5s instead of 10s)
- Limited scraping to 5 pages per user
- Reduced sleep time between requests (0.5s)
- User existence check before scraping

### 4. **Railway-Specific Configuration**
- Gunicorn configuration optimized for Railway
- Proper worker settings and timeouts
- Health check endpoint
- Database connection retry logic

### 5. **Rate Limiting**
- 10 requests per minute per IP
- Prevents abuse and resource exhaustion

## API Endpoints

- `GET /ping` - Simple health check
- `GET /health` - Detailed health check with database status
- `GET /test-db-connection` - Test database connectivity
- `GET /api/recomendacoes/<username>` - Get movie recommendations

## Deployment

The application is configured to run on Railway with:

1. **Procfile** - Uses startup script
2. **gunicorn.conf.py** - Optimized Gunicorn settings
3. **start.sh** - Database connection retry logic

## Environment Variables

Required environment variables:
- `PGDATABASE` - Database name
- `PGUSER` - Database user
- `PGPASSWORD` - Database password
- `PGHOST` - Database host
- `PGPORT` - Database port

## Monitoring

The application includes:
- Detailed logging
- Processing time tracking
- Error handling with proper HTTP status codes
- Rate limiting information

## Troubleshooting

If you encounter timeout issues:
1. Check the `/health` endpoint for database connectivity
2. Verify the user exists on Letterboxd
3. Check logs for specific error messages
4. The application will return proper error responses instead of crashing 