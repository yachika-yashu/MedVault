import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Async workers: fewer than sync because each handles many concurrent requests.
# Each worker loads AI models (~1-2 GB RAM). Cap at 4 to avoid OOM on typical VMs.
workers = int(os.getenv("GUNICORN_WORKERS", min(multiprocessing.cpu_count() + 1, 4)))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

accesslog = "-"
errorlog = "-"
loglevel = "info"

# PDF ingestion (docling) can take 2-3 minutes. Must exceed the nginx proxy_read_timeout.
timeout = 300
keepalive = 5
