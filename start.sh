#!/bin/bash
# Railway startup script for proper port handling
PORT=${PORT:-8000}
echo "Starting application on port $PORT"
echo "Current commit: eb72c28 - Fixed port handling"
exec uvicorn api.index:app --host 0.0.0.0 --port $PORT