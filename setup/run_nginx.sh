#!/bin/bash
# run_nginx.sh - Starts Nginx in user space with custom configuration on port 8000

# Get current script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NGINX_RESOLVED_CONF="$SCRIPT_DIR/nginx_resolved.conf"
PID_FILE="$SCRIPT_DIR/nginx.pid"

echo "=== Nginx User-Space Control Script ==="

# Check if Nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "ERROR: Nginx is not installed. Please install Nginx (e.g. 'brew install nginx' on macOS)."
    exit 1
fi

# Detect operating system and generate resolved configuration
OS_TYPE="$(uname)"
if [ "$OS_TYPE" = "Darwin" ]; then
    echo "Detected macOS..."
    NGINX_CONF="$SCRIPT_DIR/coolflix_mac_nginx.conf"
    echo "Generating resolved Nginx configuration at $NGINX_RESOLVED_CONF..."
    sed "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" "$NGINX_CONF" > "$NGINX_RESOLVED_CONF"
else
    echo "Detected Linux..."
    NGINX_CONF="$SCRIPT_DIR/coolflix_lin_nginx.conf"
    echo "Generating resolved Nginx configuration at $NGINX_RESOLVED_CONF..."
    sed "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" "$NGINX_CONF" > "$NGINX_RESOLVED_CONF"
fi

# Stop any running Nginx using this configuration's PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping Nginx (PID: $PID)..."
        nginx -c "$NGINX_RESOLVED_CONF" -s stop 2>/dev/null || kill "$PID" 2>/dev/null || true
        # Wait a moment for it to stop
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

# Double check if port 8000 is still in use
PORT_PID=$(lsof -t -i :8000)
if [ ! -z "$PORT_PID" ]; then
    echo "Port 8000 is occupied by process: $PORT_PID"
    echo "Attempting to terminate the process occupying port 8000..."
    for pid in $PORT_PID; do
        kill -9 "$pid" 2>/dev/null || true
    done
    sleep 1
fi

# Create logs if they don't exist
touch "$SCRIPT_DIR/nginx_access.log"
touch "$SCRIPT_DIR/nginx_error.log"

# Start Nginx
echo "Starting Nginx with custom config: $NGINX_RESOLVED_CONF"
nginx -c "$NGINX_RESOLVED_CONF"

if [ $? -eq 0 ]; then
    echo "Nginx started successfully on port 8000!"
    echo "Logs are available at:"
    echo "  - Access log: $SCRIPT_DIR/nginx_access.log"
    echo "  - Error log: $SCRIPT_DIR/nginx_error.log"
else
    echo "ERROR: Failed to start Nginx."
    exit 1
fi
