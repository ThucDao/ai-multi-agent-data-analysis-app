import os
import sys
import platform
import subprocess
import traceback
import threading
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

from backend.config import save_credentials, check_credentials, load_credentials
from backend.agent_workflow import run_agent_workflow, set_client_and_model, register_status_callback

app = FastAPI(title="AI Multi-Agent Data Analysis App")

def get_resource_path(relative_path: str) -> str:
    """Gets the absolute path to resource, working both in dev and under PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative_path)
    return str(Path(relative_path).resolve())

# Global status dictionary for the active run
run_state = {
    "is_running": False,
    "completed": False,
    "active_agent": None,
    "message": "Idle",
    "error": None,
    "report_md": None,
    "report_pdf": None,
    "report_html": None
}

# Ensure folders exist
Path("ada_artifacts").mkdir(exist_ok=True)

# Mount frontend static files and artifacts
app.mount("/frontend", StaticFiles(directory=get_resource_path("frontend")), name="frontend")
app.mount("/ada_artifacts", StaticFiles(directory="ada_artifacts"), name="ada_artifacts")

class CredentialsPayload(BaseModel):
    gemini_api_key: str
    langsmith_api_key: str
    temporary: bool = False

import webbrowser
import time

# Global variable to track the last client heartbeat
last_heartbeat = time.time()
client_backgrounded = False

def heartbeat_watchdog():
    """Shuts down the backend cleanly if no active browser client pings are received."""
    # Give the browser tab plenty of time to boot up and load index.html on initial startup
    time.sleep(20)
    while True:
        time.sleep(2)
        if client_backgrounded:
            continue
        if time.time() - last_heartbeat > 10:
            print("[INFO] No active browser client detected (timeout). Shutting down background server process...")
            # Clean up temporary credentials if they exist
            try:
                from backend.config import load_credentials, clear_credentials
                creds = load_credentials()
                if creds.get("temporary"):
                    clear_credentials()
                    print("[INFO] Temporary credentials cleaned up successfully.")
            except Exception as e:
                print("[ERROR] Failed to clean up temporary credentials on auto-shutdown:", e)
            
            # Terminate the server process
            os._exit(0)

def open_browser():
    # Allow 1.5 seconds for FastAPI to boot up
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8000")

@app.on_event("startup")
def on_startup():
    # Clean up any leftover temporary credentials from a previous run
    try:
        from backend.config import load_credentials, clear_credentials
        creds = load_credentials()
        if creds.get("temporary"):
            clear_credentials()
            print("[INFO] Cleaned up temporary credentials from previous session on startup.")
    except Exception as e:
        print("[ERROR] Failed to clean up temporary credentials on startup:", e)

    # Close PyInstaller splash screen if active
    try:
        import pyi_splash
        pyi_splash.close()
        print("[INFO] Closed PyInstaller splash screen successfully.")
    except ImportError:
        pass

    # Start thread to open browser
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Start the watchdog thread on server boot
    threading.Thread(target=heartbeat_watchdog, daemon=True).start()

@app.on_event("shutdown")
def on_shutdown():
    """Cleans up temporary session credentials when the application is stopped."""
    try:
        from backend.config import load_credentials, clear_credentials
        creds = load_credentials()
        if creds.get("temporary"):
            clear_credentials()
            print("[INFO] Temporary credentials cleaned up successfully.")
    except Exception as e:
        print("[ERROR] Failed to clean up temporary credentials:", e)

@app.middleware("http")
async def update_heartbeat_middleware(request, call_next):
    global last_heartbeat
    last_heartbeat = time.time()
    return await call_next(request)

@app.post("/api/client-state")
def api_client_state(state: str):
    global last_heartbeat, client_backgrounded
    last_heartbeat = time.time()
    if state == "hidden":
        client_backgrounded = True
        print("[INFO] Client tab went to background. Suspending watchdog timeout.")
    elif state == "visible":
        client_backgrounded = False
        print("[INFO] Client tab returned to foreground. Resuming watchdog.")
    elif state == "closed":
        print("[INFO] Client tab closed. Shutting down background server process...")
        try:
            from backend.config import load_credentials, clear_credentials
            creds = load_credentials()
            if creds.get("temporary"):
                clear_credentials()
                print("[INFO] Temporary credentials cleaned up successfully.")
        except Exception as e:
            print("[ERROR] Failed to clean up temporary credentials on tab close:", e)
        os._exit(0)
    return {"status": "success", "state": state}

@app.post("/api/heartbeat")
def api_heartbeat():
    global last_heartbeat
    last_heartbeat = time.time()
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def serve_index():
    """Serves the frontend SPA index.html."""
    return FileResponse(get_resource_path("frontend/index.html"))

@app.get("/api/credentials")
def api_get_credentials():
    """Checks credentials existence status."""
    return check_credentials()

@app.post("/api/credentials")
def api_save_credentials(payload: CredentialsPayload):
    """Saves API credentials and validates input."""
    if not payload.gemini_api_key or not payload.langsmith_api_key:
        raise HTTPException(status_code=400, detail="Both Gemini and LangSmith API keys are required.")
    
    try:
        save_credentials(payload.gemini_api_key, payload.langsmith_api_key, payload.temporary)
        return {"status": "success", "message": "Credentials saved securely."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save credentials: {str(e)}")

@app.post("/api/credentials/clear")
def api_clear_credentials():
    """Clears all stored credentials from the configuration file."""
    try:
        from backend.config import clear_credentials
        clear_credentials()
        return {"status": "success", "message": "Credentials cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear credentials: {str(e)}")

@app.post("/api/upload-csv")
def api_upload_csv(file: UploadFile = File(...)):
    """Receives and saves a single CSV file upload."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
    
    try:
        dest_path = Path("ada_artifacts") / "workspace_data.csv"
        with open(dest_path, "wb") as buffer:
            buffer.write(file.file.read())
        return {"status": "success", "filename": file.filename, "path": str(dest_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

@app.post("/api/select-export-directory")
def api_select_export_directory():
    """Pops up a native directory selector dialog on the host computer via a safe subprocess."""
    try:
        import subprocess
        exe = sys.executable
        
        if getattr(sys, "frozen", False):
            cmd = [exe, "--pick-folder"]
        else:
            cmd = [exe, get_resource_path("launcher.py"), "--pick-folder"]
            
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            check=True
        )
        
        selected_dir = result.stdout.strip()
        if selected_dir:
            return {"status": "success", "directory": selected_dir}
        else:
            return {"status": "cancelled", "directory": ""}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open folder picker: {str(e)}. You can type the path manually in the text box."
        )

def agent_status_cb(agent: str, message: str, error: str | None = None):
    """Callback function used by agent graph nodes to update live status."""
    global run_state
    run_state["active_agent"] = agent
    run_state["message"] = message
    if error:
        run_state["error"] = error

def run_workflow_background(csv_path: str, tier: str, gemini_key: str, langsmith_key: str, export_path: str = None):
    """Worker function that runs in a separate thread to avoid blocking FastAPI requests."""
    global run_state
    try:
        # 1. Reset state
        run_state["is_running"] = True
        run_state["completed"] = False
        run_state["error"] = None
        run_state["active_agent"] = "profiler"
        run_state["message"] = "Initializing LangGraph agent flow..."
        run_state["report_md"] = None
        run_state["report_pdf"] = None

        # 2. Register callbacks and configure client
        register_status_callback(agent_status_cb)
        set_client_and_model(gemini_key, tier)

        # 3. Configure environment variables for LangSmith/LangChain tracing
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = langsmith_key
        os.environ["LANGSMITH_PROJECT"] = "auto-data-analysis"

        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = langsmith_key
        os.environ["LANGCHAIN_PROJECT"] = "auto-data-analysis"

        # 4. Invoke graph
        result = run_agent_workflow(csv_path)

        # 5. Handle output
        run_state["report_md"] = result["report_md"]
        run_state["report_pdf"] = result["report_pdf"]
        
        from backend.agent_workflow import md
        run_state["report_html"] = md.render(result["report_md"]) if result["report_md"] else None

        if result["ok"]:
            run_state["message"] = "Analysis finished successfully!"
            if export_path:
                try:
                    export_dir = Path(export_path)
                    if export_dir.exists() and export_dir.is_dir():
                        from datetime import datetime
                        import shutil
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
                        md_export = export_dir / f"report_{timestamp}.md"
                        pdf_export = export_dir / f"report_{timestamp}.pdf"
                        
                        if result["report_md"]:
                            with open(md_export, "w", encoding="utf-8") as f:
                                f.write(result["report_md"])
                        
                        if result["report_pdf"] and Path(result["report_pdf"]).exists():
                            src_pdf = Path(result["report_pdf"]).resolve()
                            dst_pdf = Path(pdf_export).resolve()
                            if src_pdf != dst_pdf:
                                shutil.copy2(src_pdf, dst_pdf)
                        
                        run_state["message"] += f" Exported reports to: {export_path}"
                    else:
                        run_state["message"] += " (Export folder not found/invalid)"
                except Exception as ex:
                    print("Failed to export files:", ex)
                    run_state["message"] += " (Failed to write to export folder)"
        else:
            # Code crashed, but we generated a report outline
            run_state["message"] = "Analysis finished, but errors occurred during code execution."
            if result["last_error"]:
                # Friendly error wrapper for coding crashes
                run_state["error"] = (
                    "The generated data analytics code crashed during runtime execution. "
                    "This usually happens due to unexpected NaN values or layout bugs in matplotlib. "
                    "A draft report has still been compiled with limited charts."
                )
        run_state["completed"] = True
        
    except Exception as e:
        traceback.print_exc()
        # Friendly error translations for common operational failures
        err_msg = str(e).lower()
        if "api key" in err_msg or "unauthorized" in err_msg or "invalid api" in err_msg:
            friendly = "API Authorization Failed: Please check that your Gemini API Key is correct and has access rights."
        elif "quota" in err_msg or "rate limit" in err_msg or "limit exceeded" in err_msg:
            friendly = "Quota Limit Exceeded: You have reached the API rate bounds. Please wait a moment or upgrade to a paid billing account."
        elif "weasyprint" in err_msg or "pango" in err_msg or "cairo" in err_msg:
            friendly = "PDF Compiler Error: WeasyPrint was unable to compile the PDF. Please check if system dependencies (like Pango or GTK) are installed on this operating system."
        else:
            friendly = f"Execution Interrupted: An unexpected error occurred while analyzing the dataset. Details: {str(e)}"
        
        run_state["error"] = friendly
        run_state["message"] = "Failed"
        run_state["completed"] = False
    finally:
        run_state["is_running"] = False

@app.post("/api/run-analysis")
def api_run_analysis(tier: str = Form(...), export_path: str = Form(None)):
    """Triggers the asynchronous multi-agent data-analysis flow."""
    global run_state
    if run_state["is_running"]:
        raise HTTPException(status_code=400, detail="An analysis run is already in progress.")

    creds = load_credentials()
    gemini_key = creds.get("GEMINI_API_KEY")
    langsmith_key = creds.get("LANGSMITH_API_KEY")

    if not gemini_key or not langsmith_key:
        raise HTTPException(status_code=400, detail="Missing API credentials. Please set them first in the UI.")

    csv_path = Path("ada_artifacts") / "workspace_data.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=400, detail="No dataset uploaded. Please select a CSV file first.")

    # Spawn thread to avoid holding the HTTP thread
    t = threading.Thread(
        target=run_workflow_background,
        args=(str(csv_path), tier, gemini_key, langsmith_key, export_path)
    )
    t.daemon = True
    t.start()

    return {"status": "success", "message": "Analysis started."}

@app.get("/api/run-status")
def api_get_status():
    """Returns the current state of the active run."""
    return run_state

@app.post("/api/open-pdf")
def api_open_pdf(payload: dict):
    """Opens a generated PDF file using the platform's default desktop PDF reader."""
    pdf_path = payload.get("pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=400, detail="pdf_path parameter is required.")

    path_obj = Path(pdf_path)
    if not path_obj.exists():
        raise HTTPException(status_code=404, detail="The generated PDF file does not exist on disk.")

    abs_path = str(path_obj.resolve())
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(abs_path)
        elif system == "Darwin":  # macOS
            subprocess.run(["open", abs_path])
        else:  # Linux
            subprocess.run(["xdg-open", abs_path])
        return {"status": "success", "message": f"Opened report in default reader: {abs_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open PDF file: {str(e)}")

class GeneratePDFPayload(BaseModel):
    report_md: str
    engine: str
    export_path: str | None = None

@app.post("/api/generate-pdf")
def api_generate_pdf(payload: GeneratePDFPayload):
    """Generates a PDF document on-demand using the specified engine."""
    if not payload.report_md:
        raise HTTPException(status_code=400, detail="report_md is required.")
    
    try:
        from backend.agent_workflow import render_pdf
        pdf_path = render_pdf(payload.report_md, payload.engine)
        
        exported_path = None
        if payload.export_path:
            export_dir = Path(payload.export_path)
            if export_dir.exists() and export_dir.is_dir():
                from datetime import datetime
                import shutil
                filename = Path(pdf_path).name
                exported_dest = export_dir / filename
                src_pdf = Path(pdf_path).resolve()
                dst_pdf = Path(exported_dest).resolve()
                if src_pdf != dst_pdf:
                    shutil.copy2(src_pdf, dst_pdf)
                exported_path = str(exported_dest.resolve())
                
        return {
            "status": "success", 
            "pdf_path": pdf_path, 
            "exported_path": exported_path
        }
    except Exception as e:
        traceback.print_exc()
        err_msg = str(e).lower()
        if "libgobject" in err_msg or "gobject" in err_msg or "pango" in err_msg:
            friendly = (
                "WeasyPrint Error: Missing system libraries (GTK/Pango). "
                "To use WeasyPrint, you must install GTK+ on your system. "
                "Otherwise, please select xhtml2pdf, which requires no extra installation."
            )
        else:
            friendly = f"PDF compilation failed: {str(e)}"
        raise HTTPException(status_code=500, detail=friendly)
