#!/bin/bash

# AI Multi-Agent Data Analysis App Launcher (Mac/Linux)
echo "======================================================="
echo "  AI Multi-Agent Data Analysis App Launcher (Unix)"
echo "======================================================="
echo ""

# Check for python3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 was not found. Please install Python 3.10+."
    exit 1
fi

# Create virtual env if it does not exist
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating Python virtual environment in .venv..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment."
        exit 1
    fi
fi

# Activate virtual env
echo "[INFO] Activating virtual environment..."
source .venv/bin/activate
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to activate virtual environment."
    exit 1
fi

# Install dependencies
INSTALL_DEPS=1
if [ -f ".venv/sentinel" ]; then
    if [ "requirements.txt" -ot ".venv/sentinel" ]; then
        INSTALL_DEPS=0
        echo "[INFO] Dependencies are up to date. Skipping installation."
    fi
fi

if [ $INSTALL_DEPS -eq 1 ]; then
    echo "[INFO] Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install requirements."
        exit 1
    fi
    touch ".venv/sentinel"
fi

# Launch backend
echo ""
echo "[INFO] Launching FastAPI Backend Server..."
echo "[INFO] The application will open automatically in your default browser."
echo "[INFO] Keep this terminal open to keep the application running."
echo "======================================================="
echo ""

python3 -m uvicorn backend.main:app --port 8000 --host 127.0.0.1
