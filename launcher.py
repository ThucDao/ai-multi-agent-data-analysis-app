import sys
import os
import io
import uvicorn

# Redirect stdout/stderr if None (common in PyInstaller --noconsole mode on Windows)
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

# Add current project root to python path to resolve submodules
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.main import app

if __name__ == "__main__":
    # Start uvicorn server programmatically, disabling default logger config to prevent isatty issues
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, log_config=None)
