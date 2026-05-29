#!/bin/bash
# setup_folder.sh - Script for initializing system folders for netflix-clone server

# Exit on error
set -e

echo "=== Initializing System Folders for Netflix Clone ==="

# Determine project root directory dynamically relative to this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="/var/logs/netflix-clone"

echo "Creating log directory at $LOG_DIR..."
sudo mkdir -p "$LOG_DIR"
# Make it writable for gunicorn and supervisor
sudo chmod -R 777 "$LOG_DIR"
sudo chown -R $(whoami) "$LOG_DIR" 2>/dev/null || true

echo "Ensuring project directory exists at $PROJECT_DIR..."
mkdir -p "$PROJECT_DIR"

echo "Folders setup completed successfully!"
