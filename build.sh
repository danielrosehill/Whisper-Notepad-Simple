#!/bin/bash
# Simple build script for Whisper Notepad Simple
# Creates a Linux executable using PyInstaller

echo "=== Building Whisper Notepad Simple ==="

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install requirements
echo "Installing requirements..."
uv pip install -r requirements.txt

# Install PyInstaller if not already installed
if ! uv pip show pyinstaller > /dev/null 2>&1; then
    echo "Installing PyInstaller..."
    uv pip install pyinstaller
fi

# Clean previous build
echo "Cleaning previous build..."
rm -rf build dist

# Build the executable
echo "Building executable..."
pyinstaller --name="WhisperNotepadSimple" \
            --onefile \
            --windowed \
            --hidden-import=sounddevice \
            --hidden-import=soundfile \
            --hidden-import=numpy \
            --add-data="system-prompts:system-prompts" \
            whisper_notepad_simple.py

echo "Build complete! Executable is in the 'dist' directory."

# Deactivate virtual environment
deactivate
