#!/bin/bash
# Build script for Voice Notepad With Transformations
# Creates a standalone executable using PyInstaller

set -e  # Exit on error

# Default configuration
BUILD_MODE="onefile"  # Options: onefile, onedir
DEBUG_MODE=false
CLEAN_BUILD=true
OUTPUT_NAME="Voice-Notepad"
ICON_PATH="screenshots/1.png"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            BUILD_MODE="onedir"
            shift
            ;;
        --file)
            BUILD_MODE="onefile"
            shift
            ;;
        --debug)
            DEBUG_MODE=true
            shift
            ;;
        --no-clean)
            CLEAN_BUILD=false
            shift
            ;;
        --name=*)
            OUTPUT_NAME="${1#*=}"
            shift
            ;;
        --help)
            echo "Usage: ./build.sh [options]"
            echo "Options:"
            echo "  --dir                Build as directory instead of single file"
            echo "  --file               Build as single file (default)"
            echo "  --debug              Include debug information in build"
            echo "  --no-clean           Don't clean up build files after completion"
            echo "  --name=NAME          Specify output name (default: Voice-Notepad)"
            echo "  --help               Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for available options"
            exit 1
            ;;
    esac
done

echo "=== Voice Notepad With Transformations Build Script ==="
echo "Build configuration:"
echo "  - Build mode: $BUILD_MODE"
echo "  - Debug mode: $DEBUG_MODE"
echo "  - Clean build: $CLEAN_BUILD"
echo "  - Output name: $OUTPUT_NAME"
echo ""
echo "Starting build process..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is required but not installed."
    exit 1
fi

# Create and activate virtual environment
echo "Creating virtual environment..."
python3 -m venv build_env
source build_env/bin/activate

# Install or upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install required packages
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# Install PyInstaller
echo "Installing PyInstaller..."
pip install pyinstaller

# Check if system-prompts directory exists
if [ ! -d "system-prompts" ]; then
    echo "Error: system-prompts directory not found. Make sure you're running this script from the project root."
    exit 1
fi

# Create build directory if it doesn't exist
mkdir -p dist

# Prepare PyInstaller command
PYINSTALLER_CMD="pyinstaller --name=\"$OUTPUT_NAME\""

# Add build mode
if [ "$BUILD_MODE" = "onefile" ]; then
    PYINSTALLER_CMD="$PYINSTALLER_CMD --onefile"
else
    PYINSTALLER_CMD="$PYINSTALLER_CMD --onedir"
fi

# Add windowed mode (no console)
PYINSTALLER_CMD="$PYINSTALLER_CMD --windowed"

# Add data files
PYINSTALLER_CMD="$PYINSTALLER_CMD --add-data=\"system-prompts:system-prompts\""

# Add icon if it exists
if [ -f "$ICON_PATH" ]; then
    PYINSTALLER_CMD="$PYINSTALLER_CMD --icon=\"$ICON_PATH\""
fi

# Add debug flag if needed
if [ "$DEBUG_MODE" = true ]; then
    PYINSTALLER_CMD="$PYINSTALLER_CMD --debug"
fi

# Add clean flag
PYINSTALLER_CMD="$PYINSTALLER_CMD --clean"

# Add main script
PYINSTALLER_CMD="$PYINSTALLER_CMD voice_notepad.py"

# Build the executable
echo "Building executable with PyInstaller..."
echo "Running: $PYINSTALLER_CMD"
eval $PYINSTALLER_CMD

# Clean up if requested
if [ "$CLEAN_BUILD" = true ]; then
    echo "Cleaning up build files..."
    rm -rf build
    rm -f "$OUTPUT_NAME.spec"
else
    echo "Skipping cleanup as requested with --no-clean"
fi

echo "=== Build completed successfully! ==="
if [ "$BUILD_MODE" = "onefile" ]; then
    echo "Executable is located at: ./dist/$OUTPUT_NAME"
    echo "Run it with: ./dist/$OUTPUT_NAME"
else
    echo "Application directory is located at: ./dist/$OUTPUT_NAME"
    echo "Run it with: ./dist/$OUTPUT_NAME/$OUTPUT_NAME"
fi

# Deactivate virtual environment
deactivate

# Make the build script executable if it isn't already
chmod +x build.sh
