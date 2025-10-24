# Gunicorn configuration for Railway deployment
import os
import multiprocessing

# Server socket
bind = "0.0.0.0:" + os.environ.get("PORT", "5000")
backlog = 2048

# Worker processes
workers = 1  # Single worker for heavy ML operations
worker_class = "sync"
worker_connections = 50
max_requests = 50
max_requests_jitter = 5
preload_app = False  # Disabled to reduce memory usage

# Timeout settings
timeout = 30
keepalive = 2
graceful_timeout = 30

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "letterboxd-backend"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (not needed for Railway)
keyfile = None
certfile = None

# Memory management
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Worker timeout
worker_tmp_dir = "/dev/shm"
worker_exit_on_app_exit = True 