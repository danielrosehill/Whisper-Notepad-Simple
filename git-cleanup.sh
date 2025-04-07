#!/bin/bash
# Script to clean up Git repository history by removing large files

echo "=== Git Repository Cleanup ==="
echo "This script will remove large files from Git history."
echo "WARNING: This will rewrite Git history. Make sure you have a backup!"
echo ""
echo "Press Enter to continue or Ctrl+C to abort..."
read

# Install BFG Repo-Cleaner if not already installed
if ! command -v bfg &> /dev/null; then
    echo "Installing BFG Repo-Cleaner..."
    mkdir -p ~/bin
    curl -Lo ~/bin/bfg.jar https://repo1.maven.org/maven2/com/madgag/bfg/1.14.0/bfg-1.14.0.jar
    echo '#!/bin/bash' > ~/bin/bfg
    echo 'java -jar ~/bin/bfg.jar "$@"' >> ~/bin/bfg
    chmod +x ~/bin/bfg
    export PATH=$PATH:~/bin
fi

# Create a backup
echo "Creating backup..."
cd "$(dirname "$0")"
REPO_DIR=$(pwd)
BACKUP_DIR="${REPO_DIR}_backup_$(date +%Y%m%d%H%M%S)"
cp -r "$REPO_DIR" "$BACKUP_DIR"
echo "Backup created at $BACKUP_DIR"

# Create a fresh clone for BFG to work on
echo "Creating fresh clone..."
cd ..
REPO_NAME=$(basename "$REPO_DIR")
TEMP_REPO="${REPO_NAME}_temp"
git clone --mirror "$REPO_DIR/.git" "$TEMP_REPO"
cd "$TEMP_REPO"

# Use BFG to remove large files and directories
echo "Removing large files and directories..."
bfg --delete-folders "{.venv,build,dist,__pycache__}" --no-blob-protection

# Clean up and optimize the repository
echo "Cleaning up repository..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Update the original repository
echo "Updating original repository..."
cd "$REPO_DIR"
git remote add temp "../$TEMP_REPO"
git fetch temp --tags
git reset --hard temp/main

# Clean up temporary repository
echo "Cleaning up..."
cd ..
rm -rf "$TEMP_REPO"

echo ""
echo "=== Cleanup Complete ==="
echo "The repository has been cleaned up. You may need to force push to remote:"
echo "git push origin --force --all"
echo "git push origin --force --tags"
echo ""
echo "Note: Everyone working with this repository will need to clone it again after this operation."
