# Letterboxd Backend - Ultra-Optimized for Railway

This is an **ultra-optimized** version of the Letterboxd recommendation backend designed to run efficiently on Railway without timeout or memory issues.

## 🚀 **Ultra-Performance Optimizations**

### 1. **Zero Dependencies on Heavy Libraries**
- ❌ **Removed pandas** - Uses pure Python lists and SQL
- ❌ **Removed numpy** - Uses built-in Python functions
- ❌ **Removed scikit-learn** - Uses simple algorithms
- ✅ **Pure Python + SQL** - Maximum performance

### 2. **Aggressive Timeout Handling**
- **5-second timeout** for recommendation generation
- **10-second Gunicorn timeout**
- **Immediate fallback** if not in cache
- **No database queries** for uncached users

### 3. **Ultra-Minimal Data Processing**
- **Only 20 user movies** (top rated)
- **Only 5 popular movies** for recommendations
- **Only 3 final recommendations**
- **Pure SQL queries** - no pandas overhead

### 4. **Smart Caching System**
- **5-minute cache** for user data
- **Immediate fallback** for uncached users
- **Manual cache endpoint** for pre-loading users
- **Memory monitoring** endpoint

### 5. **Railway-Optimized Configuration**
- **2 workers only** (reduced memory usage)
- **No preload_app** (saves memory)
- **Minimal worker connections**
- **Aggressive timeouts**

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

### **Environment Variables**
```
PGDATABASE=your_database
PGUSER=your_user
PGPASSWORD=your_password
PGHOST=your_host
PGPORT=your_port
```

## 📊 **Performance Testing**

Use the included test script:
```bash
python test_performance.py
```

This will test all endpoints and measure response times.

## 🔧 **Usage Workflow**

### **For Fast Recommendations:**
1. **Cache the user first**: `GET /api/cache/<username>`
2. **Get recommendations**: `GET /api/recomendacoes/<username>`
3. **Response time**: < 1 second

### **For Immediate Response:**
1. **Skip caching**: `GET /api/recomendacoes/<username>`
2. **Gets fallback**: Popular movies immediately
3. **Response time**: < 0.5 seconds

## 📈 **Expected Performance**

- **Cached users**: < 1 second
- **Uncached users**: < 0.5 seconds (fallback)
- **Memory usage**: < 100MB
- **No timeouts**: Guaranteed response

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