#!/bin/bash
# setup_folder.sh - Script for initializing system folders for netflix-clone server

echo "=== Initializing System Folders for Netflix Clone ==="

LOG_DIR="/var/logs/netflix-clone"
SERVER_DIR="/home/eleven/servers/netflix-clone"

echo "Creating log directory at $LOG_DIR..."
sudo mkdir -p "$LOG_DIR"
# Make it writable for gunicorn and supervisor
sudo chmod -R 777 "$LOG_DIR"
sudo chown -R $(whoami) "$LOG_DIR" 2>/dev/null || true

echo "Creating server directory at $SERVER_DIR..."
mkdir -p "$SERVER_DIR"

echo "Folders setup completed successfully!"
