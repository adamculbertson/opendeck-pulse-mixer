#!/bin/bash

set -euo pipefail

# Configuration
DEV_DIR="PulseMixer"
PLUGIN_NAME="me.adamculbertson.pulsemixer.sdPlugin"
OUTPUT_FILE="PulseMixer.streamDeckPlugin" # Using the official extension

echo "Building $PLUGIN_NAME..."

# Create a temporary staging area
STAGING_DIR=$(mktemp -d)

# Copy files while excluding junk
rsync -av "$DEV_DIR/" "$STAGING_DIR/$PLUGIN_NAME" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    --exclude ".idea" \
    --exclude "github" \
    --exlude ".venv" \
    --exclude ".git" \
    --exclude ".vscode" \
    --exlude ".gitignore" \
    --exclude "build.sh" \
    --exclude "*.zip"

# Jump to temp dir, zip everything, and come back
pushd "$STAGING_DIR" > /dev/null
zip -r "$(pwd)/$OUTPUT_FILE" "$PLUGIN_NAME"
popd > /dev/null

# Move the final product to the project dir
mv "$STAGING_DIR/$OUTPUT_FILE" .

# Cleanup
rm -rf "$STAGING_DIR"

echo "Done! Created $OUTPUT_FILE"
