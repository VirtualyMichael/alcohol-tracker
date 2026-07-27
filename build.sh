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
VENV_PYINSTALLER="$PROJECT_ROOT/.venv/bin/pyinstaller"
EXE_PATH="$PROJECT_ROOT/dist/AlcoholTracker/AlcoholTracker"

echo "Alcohol Tracker build"
echo "Project: $PROJECT_ROOT"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "Creating local virtual environment..."
    python3 -m venv .venv
fi

echo "Installing/updating dependencies..."
"$VENV_PYTHON" -m pip install -r requirements.txt

echo "Checking Python syntax..."
"$VENV_PYTHON" -m py_compile \
    alcohol_tracker/__main__.py \
    alcohol_tracker/app.py \
    alcohol_tracker/core/calculations.py \
    alcohol_tracker/core/database.py \
    alcohol_tracker/core/paths.py \
    alcohol_tracker/core/settings.py \
    alcohol_tracker/ui/dialogs.py \
    alcohol_tracker/ui/theme.py \
    alcohol_tracker/ui/main_window.py \
    tests/test_core.py

if [ "$SKIP_TESTS" -eq 0 ]; then
    echo "Running tests..."
    "$VENV_PYTHON" -m unittest tests.test_core
fi

echo "Building windowed executable..."
"$VENV_PYINSTALLER" --noconfirm --windowed --name AlcoholTracker --paths . alcohol_tracker/__main__.py

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
