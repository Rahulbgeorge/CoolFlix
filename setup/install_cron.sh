#!/bin/bash
# install_cron.sh - Script for setting up the crontab job using django-crontab

# Exit on error
set -e

echo "=== Installing Transcoder Cron Job via django-crontab ==="

# Get current script directory (setup/) and parent project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR/backend"

# First, remove existing crontabs managed by django-crontab to prevent duplicates
../.venv/bin/python manage.py crontab remove || true

# Add crontab using django-crontab
../.venv/bin/python manage.py crontab add

echo "Successfully registered transcoder cron job via django-crontab."
