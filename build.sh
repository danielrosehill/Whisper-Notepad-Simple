#!/bin/bash
# Simple build script for Whisper Notepad Simple
# Creates a Linux executable using PyInstaller

echo "=== Building Whisper Notepad Simple ==="

# Install PyInstaller if not already installed
if ! uv pip show pyinstaller > /dev/null 2>&1; then
    echo "Installing PyInstaller..."
    uv pip install pyinstaller
fi

# Build the executable
echo "Building executable..."
pyinstaller --name="WhisperNotepadSimple" \
            --onefile \
            --windowed \
            --add-data="system-prompts:system-prompts" \
            whisper_notepad_simple.py

echo "Build complete! Executable is in the 'dist' directory."
