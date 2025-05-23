import multiprocessing

bind = "0.0.0.0:8001"  # Changed from 8000 to 8001
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
max_requests = 1000
max_requests_jitter = 50
timeout = 120
keepalive = 5
