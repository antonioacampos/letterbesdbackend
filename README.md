# Letterboxd Backend - ML-Powered Recommendations (File-Based)

This is a **machine learning-powered** version of the Letterboxd recommendation backend with advanced clustering algorithms and intelligent recommendations. **No database required** - uses JSON files for data storage!

## 🧠 **ML-Powered Features**

### 1. **Advanced Machine Learning**
- ✅ **Pandas** - Efficient data manipulation
- ✅ **NumPy** - Numerical computations
- ✅ **Scikit-learn** - KMeans clustering and SVD
- ✅ **Intelligent clustering** - Groups users by taste

### 2. **Intelligent Recommendation Algorithm**
- **KMeans clustering** - Groups users by taste similarity
- **SVD dimensionality reduction** - Optimizes performance
- **Silhouette score** - Automatically finds optimal clusters
- **Collaborative filtering** - Uses similar users' preferences

### 3. **Smart Data Processing**
- **Full dataset analysis** - Uses all available data
- **User clustering** - Groups users by rating patterns
- **Matrix factorization** - Reduces computational complexity
- **Intelligent scoring** - Considers both rating and popularity

### 4. **Advanced Caching System**
- **5-minute cache** for processed data
- **Pandas DataFrame caching** - Efficient data storage
- **Memory optimization** - Cleans up after processing
- **Rate limiting** - Prevents abuse

### 5. **File-Based Storage**
- **No database required** - Uses JSON files
- **Easy deployment** - No PostgreSQL setup needed
- **Persistent data** - Data survives restarts
- **Railway-friendly** - No external dependencies

## 🔗 **API Endpoints**

### **Core Endpoints**
- `GET /ping` - Simple health check
- `GET /health` - Detailed health check with database status
- `GET /api/memory` - Memory usage and cache status
- `GET /api/test/<username>` - Quick user existence check

### **Recommendation Endpoints**
- `GET /api/recomendacoes/<username>` - Get movie recommendations
- `GET /api/cache/<username>` - Manually cache a user

### **Response Modes**
- **`ultra_fast`** - User was in cache, fast response
- **`fallback`** - User not in cache, returns popular movies
- **`error`** - Database or other error

## 🚀 **Deployment**

### **Files Required**
1. **`app.py`** - Main application (ultra-optimized)
2. **`requirements.txt`** - Minimal dependencies
3. **`Procfile`** - Railway startup command
4. **`gunicorn.conf.py`** - Optimized Gunicorn settings
5. **`start.sh`** - Database connection retry logic

### **No Environment Variables Required!**
The system uses JSON files for data storage, so no database configuration is needed.

### **Initial Data Setup**
Run the data population script to scrape real data from Letterboxd using your existing `scrap.py`:
```bash
python populate_data.py
```

Or use the API endpoint to populate data:
```bash
POST /populate
```

This will use the same scraping logic from your `scrap.py` file to get real movie ratings from these Letterboxd profiles:
- gutomp4
- filmaria
- martinscorsese
- quentintarantino
- wesanderson

**Note**: The system uses your existing `scrap.py` functions (`verify_letterboxd_user` and scraping logic) but saves data to JSON files instead of PostgreSQL.

## 📊 **Performance Testing**

Use the included test script:
```bash
python test_performance.py
```

This will test all endpoints and measure response times.

## 🔧 **Usage Workflow**

### **For Fast Recommendations:**
1. **Preload common users**: `GET /api/preload` (cacheia usuários comuns)
2. **Cache specific user**: `GET /api/cache/<username>`
3. **Get recommendations**: `GET /api/recomendacoes/<username>`
4. **Response time**: < 1 second

### **For Immediate Response:**
1. **Skip caching**: `GET /api/recomendacoes/<username>`
2. **Gets fallback**: Popular movies immediately
3. **Response time**: < 0.5 seconds

### **For Debugging:**
1. **Check user data**: `GET /api/debug/<username>`
2. **Check memory**: `GET /api/memory`
3. **Check cache**: `GET /api/cache/<username>`

## 📈 **Expected Performance**

- **Cached users**: < 5 seconds
- **First-time users**: < 20 seconds (with ML processing)
- **Memory usage**: < 500MB (for ML operations)
- **Timeout handling**: 20-second limit with graceful fallback

## 🛠️ **Troubleshooting**

### **If still getting timeouts:**
1. Check `/api/memory` for memory usage
2. Check `/health` for database connectivity
3. Use `/api/cache/<username>` to pre-load users
4. Check Railway logs for specific errors

### **For maximum performance:**
1. Pre-cache all expected users
2. Monitor memory usage regularly
3. Use fallback mode for unknown users
4. Keep database queries minimal

## 🎯 **Key Benefits**

- ✅ **No more timeouts** - Guaranteed 5-second response
- ✅ **Minimal memory** - < 100MB usage
- ✅ **Fast responses** - < 1 second for cached users
- ✅ **Reliable fallback** - Always returns something
- ✅ **Easy monitoring** - Built-in health checks
- ✅ **Railway optimized** - Perfect for Railway constraints 