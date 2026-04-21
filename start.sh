#!/bin/bash
# Startup script for Render deployment

# Print environment info for debugging
echo "========================================="
echo "Starting FarmLink AI Application"
echo "========================================="
echo "Python version: $(python --version)"
echo "PORT: ${PORT:-10000}"
echo "FLASK_ENV: ${FLASK_ENV:-production}"
echo "DATABASE_URL: ${DATABASE_URL:0:30}..." # Only show first 30 chars for security
echo "========================================="

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL environment variable is not set!"
    echo "Please set it in your Render dashboard."
    exit 1
fi

# Set default PORT if not provided
export PORT=${PORT:-10000}

# Start gunicorn with config file
echo "Starting Gunicorn on port $PORT..."
exec gunicorn app:app -c gunicorn_config.py
