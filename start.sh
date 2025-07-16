#!/bin/bash
# Railway startup script for proper port handling

set -e  # Exit on any error

# Get port from environment with fallback
PORT=${PORT:-8000}

echo "====== Railway Deployment Startup ======"
echo "Starting あにまんch scraping application on port $PORT"
echo "Current commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo "Environment variables:"
echo "  PORT=$PORT"
echo "========================================="

# Check if the API module exists
if [ ! -f "api/index.py" ]; then
    echo "ERROR: api/index.py not found!"
    exit 1
fi

# Start the application with proper error handling
echo "Starting uvicorn server..."
exec uvicorn api.index:app --host 0.0.0.0 --port $PORT --log-level info