#!/bin/bash
# build_frontend.sh - Compiles the React frontend and copies the assets to the Django backend media directory

# Exit on error
set -e

# Target paths
TARGET_DIR="/home/eleven/servers/netflix-clone"
FRONTEND_DIR="$TARGET_DIR/frontend"
BACKEND_MEDIA_DIR="$TARGET_DIR/backend/media/frontend"

echo "=== Compiling React Frontend and Publishing to Backend ==="

# Check if target directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
    # Fallback to local script relative path if not on target server
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    TARGET_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    FRONTEND_DIR="$TARGET_DIR/frontend"
    BACKEND_MEDIA_DIR="$TARGET_DIR/backend/media/frontend"
fi

echo "Frontend directory: $FRONTEND_DIR"
echo "Backend media target: $BACKEND_MEDIA_DIR"

# Navigate to frontend and compile
cd "$FRONTEND_DIR"
echo "Running npm install..."
npm install

echo "Compiling Vite React bundle with base path '/media/frontend/'..."
npm run build -- --base=/media/frontend/

# Copy compiled files to backend media folder
echo "Clearing previous build assets..."
rm -rf "$BACKEND_MEDIA_DIR"
mkdir -p "$BACKEND_MEDIA_DIR"

echo "Copying built assets to $BACKEND_MEDIA_DIR..."
cp -r dist/* "$BACKEND_MEDIA_DIR/"

echo "Frontend compiled and published successfully!"
