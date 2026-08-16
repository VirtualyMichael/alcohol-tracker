#!/usr/bin/env bash
set -euo pipefail

SKIP_TESTS=0
NO_SHORTCUT=0
for arg in "$@"; do
    case "$arg" in
        --skip-tests) SKIP_TESTS=1 ;;
        --no-shortcut) NO_SHORTCUT=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
NUITKA_BUILD_DIR="$PROJECT_ROOT/build_nuitka"
DIST_DIR="$PROJECT_ROOT/dist/AlcoholTracker"
EXE_PATH="$DIST_DIR/AlcoholTracker"
VERSION="1.3.0.0"

echo "Alcohol Tracker build $VERSION"
echo "Project: $PROJECT_ROOT"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Creating local virtual environment..."
    python3 -m venv .venv
fi

echo "Installing/updating dependencies..."
"$VENV_PYTHON" -m pip install --disable-pip-version-check -r requirements.txt

echo "Checking Python syntax..."
"$VENV_PYTHON" -m compileall -q alcohol_tracker tests

if [ "$SKIP_TESTS" -eq 0 ]; then
    echo "Running tests..."
    "$VENV_PYTHON" -m unittest discover -s tests
fi

# --standalone, never --onefile: a onefile build unpacks itself into a temp
# directory and executes from there on every launch, which is what generic
# "dropper" heuristics look for. See packaging/windows/ANTIVIRUS.md.
echo "Building windowed executable (Nuitka, native compile)..."
rm -rf "$NUITKA_BUILD_DIR"
"$VENV_PYTHON" -m nuitka \
    --standalone \
    --python-flag=-m \
    --deployment \
    --lto=yes \
    --jobs=0 \
    --enable-plugin=pyside6 \
    --output-dir="$NUITKA_BUILD_DIR" \
    --output-filename=AlcoholTracker \
    --product-name="Alcohol Tracker" \
    --file-version="$VERSION" \
    --product-version="$VERSION" \
    --file-description="Alcohol Tracker - personal drink journal" \
    --copyright="Alcohol Tracker Project" \
    --assume-yes-for-downloads \
    alcohol_tracker

BUILT_DIST="$NUITKA_BUILD_DIR/alcohol_tracker.dist"
if [ ! -d "$BUILT_DIST" ]; then
    echo "Build finished but Nuitka output was not found at $BUILT_DIST" >&2
    exit 1
fi

rm -rf "$DIST_DIR"
mkdir -p "$(dirname "$DIST_DIR")"
mv "$BUILT_DIST" "$DIST_DIR"
rm -rf "$NUITKA_BUILD_DIR"

if [ ! -f "$EXE_PATH" ]; then
    echo "Build finished but executable was not found at $EXE_PATH" >&2
    exit 1
fi
chmod +x "$EXE_PATH"

if [ "$NO_SHORTCUT" -eq 0 ]; then
    echo "Creating/updating application launcher..."
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$APPS_DIR"
    DESKTOP_FILE="$APPS_DIR/alcohol-tracker.desktop"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Alcohol Tracker
Comment=Local dark-mode journal with editable ingestion history
Exec=$EXE_PATH
Terminal=false
Categories=Utility;
EOF
    chmod +x "$DESKTOP_FILE"
    echo "Launcher: $DESKTOP_FILE"
fi

echo "Build complete: $EXE_PATH"
