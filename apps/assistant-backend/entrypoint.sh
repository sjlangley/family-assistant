#!/bin/sh
set -e

# Use PORT environment variable or default to 8080
PORT=${PORT:-8080}

# Start gunicorn with uvicorn workers
exec gunicorn --bind ":${PORT}" --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 0 assistant.app:app
