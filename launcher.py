import sys
import os
import uvicorn

# Add current project root to python path to resolve submodules
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.main import app

if __name__ == "__main__":
    # Start uvicorn server programmatically
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, log_level="info")
