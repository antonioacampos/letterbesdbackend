#!/bin/bash

echo "🚀 Deploying Letterboxd Backend to Railway..."

# Check if we have the necessary files
echo "📋 Checking deployment files..."
if [ ! -f "app.py" ]; then
    echo "❌ app.py not found!"
    exit 1
fi

if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt not found!"
    exit 1
fi

if [ ! -f "Procfile" ]; then
    echo "❌ Procfile not found!"
    exit 1
fi

if [ ! -f "gunicorn.conf.py" ]; then
    echo "❌ gunicorn.conf.py not found!"
    exit 1
fi

echo "✅ All deployment files found!"

# Check environment variables
echo "🔧 Checking environment variables..."
required_vars=("PGDATABASE" "PGUSER" "PGPASSWORD" "PGHOST" "PGPORT")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "⚠️  Missing environment variables: ${missing_vars[*]}"
    echo "   These will need to be set in Railway dashboard"
else
    echo "✅ All environment variables are set"
fi

echo ""
echo "📦 Deployment Summary:"
echo "   - Flask app with optimized recommendation algorithm"
echo "   - Gunicorn configuration for Railway"
echo "   - Timeout handling (15s max)"
echo "   - Memory optimization (500 movies max)"
echo "   - Rate limiting (10 requests/minute)"
echo "   - Caching system (5 minutes)"
echo "   - Fallback recommendations"
echo ""
echo "🔗 API Endpoints:"
echo "   - GET /ping - Health check"
echo "   - GET /health - Detailed health check"
echo "   - GET /api/test/<username> - Quick user test"
echo "   - GET /api/memory - Memory usage"
echo "   - GET /api/recomendacoes/<username> - Recommendations"
echo ""
echo "✅ Ready for Railway deployment!"
echo ""
echo "💡 Tips:"
echo "   - Monitor /api/memory for memory usage"
echo "   - Use /api/test/<username> to check if user exists"
echo "   - Check /health for system status"
echo "   - If recommendations timeout, fallback will be used" 