#!/bin/bash
# Script to create a new release of Whisper Notepad Simple

# Get the current version from the Python file
CURRENT_VERSION=$(grep -oP 'APP_VERSION = "\K[^"]+' whisper_notepad_simple.py)

echo "=== Create Release for Whisper Notepad Simple ==="
echo "Current version: $CURRENT_VERSION"
echo ""

# Ask for new version if not provided
if [ -z "$1" ]; then
    read -p "Enter new version (leave empty to use $CURRENT_VERSION): " NEW_VERSION
    NEW_VERSION=${NEW_VERSION:-$CURRENT_VERSION}
else
    NEW_VERSION=$1
fi

# Update version in the Python file
sed -i "s/APP_VERSION = \"$CURRENT_VERSION\"/APP_VERSION = \"$NEW_VERSION\"/" whisper_notepad_simple.py
echo "Updated version in whisper_notepad_simple.py to $NEW_VERSION"

# Commit the version change
git add whisper_notepad_simple.py
git commit -m "Bump version to $NEW_VERSION"

# Create a tag
git tag -a "v$NEW_VERSION" -m "Version $NEW_VERSION"
echo "Created tag v$NEW_VERSION"

echo ""
echo "=== Release Preparation Complete ==="
echo "To push the release to GitHub, run:"
echo "git push origin main && git push origin v$NEW_VERSION"
echo ""
echo "This will trigger the GitHub Actions workflow to build and create a release."
