#!/bin/bash
# Railway startup script for proper port handling

set -e  # Exit on any error

# Get port from environment with fallback
PORT=${PORT:-8000}

echo "====== Railway Deployment Startup ======"
echo "Starting あにまんch scraping application on port $PORT"
echo "Current commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown') - Stable production version"
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo "Environment variables:"
echo "  PORT=$PORT"
echo "  NODE_ENV=${NODE_ENV:-production}"
echo "File verification:"
echo "  api/index.py exists: $([ -f api/index.py ] && echo 'YES' || echo 'NO')"
echo "  Python modules can import: $(python -c 'import api.index; print(\"SUCCESS\")' 2>/dev/null || echo 'FAILED')"
echo "========================================="

# Check if the API module exists
if [ ! -f "api/index.py" ]; then
    echo "ERROR: api/index.py not found!"
    exit 1
fi

# Step 2: Railway互換uvicorn設定でログストリーム統一
echo "Starting uvicorn server with Railway-compatible logging..."
echo "Using stdout for all log output to prevent Railway error classification"
exec uvicorn api.index:app \
    --host 0.0.0.0 \
    --port $PORT \
    --log-level info \
    --access-log \
    --no-use-colors \
    --no-server-header