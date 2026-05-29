#!/bin/bash
# install_cron.sh - Script for setting up the crontab job for netflix-clone video transcoding

# Exit on error
set -e

echo "=== Installing Transcoder Cron Job ==="

# Get current script directory (setup/) and parent project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CRON_JOB="* * * * * cd $PROJECT_DIR/backend && ../.venv/bin/python manage.py run_transcoder >> /var/logs/netflix-clone/transcoder.log 2>&1"

# Check if the cron job already exists in crontab for this user
if (crontab -l 2>/dev/null | grep -F "run_transcoder") &>/dev/null; then
    echo "Transcoder cron job is already installed in crontab."
else
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Successfully added transcoder cron job to crontab:"
    echo "  $CRON_JOB"
fi
