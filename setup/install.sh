#!/bin/bash
# install.sh - One-click server installer for Netflix Clone

# Exit on error
set -e

echo "=== Netflix Clone Server One-Click Installer ==="

# Get current script directory (which is setup/) and parent project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Run folder initialization
echo "Running system folders setup..."
if [ -f "$SCRIPT_DIR/setup_folder.sh" ]; then
    bash "$SCRIPT_DIR/setup_folder.sh"
else
    echo "setup_folder.sh not found in $SCRIPT_DIR!"
    exit 1
fi

# Move into project root directory
cd "$PROJECT_DIR"

# Set up virtual environment
echo "Setting up Python virtual environment at $PROJECT_DIR/.venv..."
python3 -m venv .venv

echo "Installing backend dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Run django migrations
echo "Running database migrations..."
.venv/bin/python backend/manage.py migrate

# Compile and publish frontend using the dedicated script
echo "Running frontend compiler..."
if [ -f "$SCRIPT_DIR/build_frontend.sh" ]; then
    bash "$SCRIPT_DIR/build_frontend.sh"
else
    echo "build_frontend.sh not found in $SCRIPT_DIR!"
    exit 1
fi

# Generate Supervisor Configuration dynamically
SUPERVISOR_CONF="/etc/supervisor/conf.d/netflix_clone.conf"
echo "Generating Supervisor configuration file at $SUPERVISOR_CONF..."

# Find who the current user running gunicorn is (defaulting to eleven if empty/root)
RUN_USER=$(whoami)
if [ "$RUN_USER" = "root" ]; then
    RUN_USER="eleven"
fi

cat <<EOF | sudo tee "$SUPERVISOR_CONF" > /dev/null
[program:netflix_clone]
directory=$PROJECT_DIR/backend
command=$PROJECT_DIR/.venv/bin/gunicorn netflix_backend.wsgi:application --bind 0.0.0.0:8000 --workers 3
user=$RUN_USER
autostart=true
autorestart=true
stdout_logfile=/var/logs/netflix-clone/django.log
stderr_logfile=/var/logs/netflix-clone/django_err.log
environment=PATH="$PROJECT_DIR/.venv/bin"
EOF

# Restart Supervisor
echo "Restarting Supervisor service..."
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart netflix_clone

# Run crontab installation
echo "Running cron setup..."
if [ -f "$SCRIPT_DIR/install_cron.sh" ]; then
    bash "$SCRIPT_DIR/install_cron.sh"
else
    echo "install_cron.sh not found in $SCRIPT_DIR!"
    exit 1
fi


echo ""
echo "========================================================================="
echo "Netflix Clone Server successfully installed and started!"
echo "Server Port: 8000"
echo "Project Directory: $PROJECT_DIR"
echo "Logs Directory: /var/logs/netflix-clone/"
echo "Django App logs: /var/logs/netflix-clone/django_app.log"
echo "Supervisor Server stdout logs: /var/logs/netflix-clone/django.log"
echo "Supervisor Server stderr logs: /var/logs/netflix-clone/django_err.log"
echo "========================================================================="
