#!/usr/bin/env bash
echo "========================================================"
echo "       Website Crawler - Non-Technical Dashboard"
echo "========================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed!"
    exit 1
fi

if [ ! -d "env" ]; then
    echo "Creating virtual environment 'env'..."
    python3 -m venv env
fi

if [ -f "env/bin/activate" ]; then
    source env/bin/activate
fi

echo "Installing/checking required packages..."
python3 -m pip install -q -r requirements.txt
python3 -m playwright install chromium >/dev/null

echo ""
echo "Starting Dashboard Server at http://localhost:8000 ..."
echo "Press Ctrl+C in this terminal window to stop."
echo ""

python3 server.py
