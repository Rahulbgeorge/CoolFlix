#!/bin/bash
# install.sh - One-click server installer for Netflix Clone

# Exit on error
set -e

echo "=== Netflix Clone Server One-Click Installer ==="

# Define target paths
TARGET_DIR="/home/eleven/servers/netflix-clone"

# Get current script directory (which is now setup/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Run folder initialization
echo "Running system folders setup..."
if [ -f "$SCRIPT_DIR/setup_folder.sh" ]; then
    bash "$SCRIPT_DIR/setup_folder.sh"
else
    echo "setup_folder.sh not found in $SCRIPT_DIR!"
    exit 1
fi

# Copy codebase if parent of script dir is not the target directory
PARENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ "$PARENT_DIR" != "$TARGET_DIR" ]; then
    echo "Copying codebase from $PARENT_DIR to $TARGET_DIR..."
    rsync -av --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='db.sqlite3' "$PARENT_DIR/" "$TARGET_DIR/"
fi

# Move into target directory
cd "$TARGET_DIR"

# Set up virtual environment
echo "Setting up Python virtual environment at $TARGET_DIR/.venv..."
python3 -m venv .venv

echo "Installing backend dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Run django migrations
echo "Running database migrations..."
.venv/bin/python backend/manage.py migrate

# Compile and publish frontend using the dedicated script
echo "Running frontend compiler..."
if [ -f "setup/build_frontend.sh" ]; then
    bash "setup/build_frontend.sh"
else
    bash "$SCRIPT_DIR/build_frontend.sh"
fi

# Generate Supervisor Configuration
SUPERVISOR_CONF="/etc/supervisor/conf.d/netflix_clone.conf"
echo "Generating Supervisor configuration file at $SUPERVISOR_CONF..."

cat <<EOF | sudo tee "$SUPERVISOR_CONF" > /dev/null
[program:netflix_clone]
directory=$TARGET_DIR/backend
command=$TARGET_DIR/.venv/bin/gunicorn netflix_backend.wsgi:application --bind 0.0.0.0:8000 --workers 3
user=eleven
autostart=true
autorestart=true
stdout_logfile=/var/logs/netflix-clone/django.log
stderr_logfile=/var/logs/netflix-clone/django_err.log
environment=PATH="$TARGET_DIR/.venv/bin"
EOF

# Restart Supervisor
echo "Restarting Supervisor service..."
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart netflix_clone

echo ""
echo "========================================================================="
echo "Netflix Clone Server successfully installed and started!"
echo "Server Port: 8000"
echo "Logs Directory: /var/logs/netflix-clone/"
echo "Django App logs: /var/logs/netflix-clone/django_app.log"
echo "Supervisor Server stdout logs: /var/logs/netflix-clone/django.log"
echo "Supervisor Server stderr logs: /var/logs/netflix-clone/django_err.log"
echo "========================================================================="
