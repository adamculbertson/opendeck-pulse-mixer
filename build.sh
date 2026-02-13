#!/bin/bash

set -euo pipefail

# Configuration
DEV_DIR="opendeck-pulse-mixer"
PLUGIN_NAME="me.adamculbertson.pulsemixer.sdPlugin"
OUTPUT_FILE="PulseMixer.streamDeckPlugin" # Using the official extension

echo "Building $PLUGIN_NAME..."

# Check if the script is being ran from within the dev dir
# If it is, then set the dev dir to the directory up a level
CURRENT_DIR=$(basename "$PWD")

if [[ "$CURRENT_DIR" == "$DEV_DIR" ]]; then
    DEV_DIR="../$DEV_DIR"
fi

# Create a temporary staging area
STAGING_DIR=$(mktemp -d)

# Copy files while excluding junk
rsync -av "$DEV_DIR/" "$STAGING_DIR/$PLUGIN_NAME" \
    --exclude "__pycache__" \
    --exclude "*.pyc" \
    --exclude ".idea" \
    --exclude "github" \
    --exclude ".venv" \
    --exclude ".git" \
    --exclude ".vscode" \
    --exclude ".gitignore" \
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
