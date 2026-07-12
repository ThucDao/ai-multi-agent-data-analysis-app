import sys
import os
import io

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--pick-folder":
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected_dir = filedialog.askdirectory(title="Select Export Directory")
        root.destroy()
        if sys.__stdout__:
            sys.__stdout__.write(selected_dir + "\n")
            sys.__stdout__.flush()
        else:
            print(selected_dir)
        sys.exit(0)

# Redirect stdout/stderr to a physical log file in the artifacts directory for debugging noconsole runs
try:
    from pathlib import Path
    log_dir = Path("ada_artifacts")
    log_dir.mkdir(exist_ok=True)
    # Open log file in append mode with line-buffering (autoflush)
    log_file = open(log_dir / "app.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file
except Exception:
    import io
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

import uvicorn

# Add current project root to python path to resolve submodules
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.main import app

if __name__ == "__main__":
    # Start uvicorn server programmatically, disabling default logger config to prevent isatty issues
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, log_config=None)
