#!/bin/bash
# AI Input Box - Linux Build Script
# Requirements: pip install pyinstaller

# 1. Setup environment
PROJECT_ROOT=$(pwd)
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$PROJECT_ROOT/build"

echo "Cleaning old builds..."
rm -rf "$DIST_DIR" "$BUILD_DIR"

# 2. Run PyInstaller
# --onefile: Create a single executable
# --windowed: No console window
# --add-data: Include resources and config
# Note: Syntax for --add-data is "SourcePath:DestPath"

echo "Building VoxQuill..."
./.venv/bin/pyinstaller --noconfirm --onefile --windowed \
    --name "VoxQuill" \
    --icon "$PROJECT_ROOT/resource/main_small_color.png" \
    --add-data "$PROJECT_ROOT/ui/app.qss:ui" \
    --add-data "$PROJECT_ROOT/config:config" \
    --add-data "$PROJECT_ROOT/resource:resource" \
    --collect-all "sherpa_onnx" \
    --hidden-import "PyQt6.sip" \
    "$PROJECT_ROOT/main.py"

echo "Build complete! Executable is at: $DIST_DIR/VoxQuill"
echo "Note: Models should be kept in the same directory as the executable's 'models' folder, or download them on first run."
