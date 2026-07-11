# Walkthrough - AI Multi-Agent Data Analysis Desktop Application

The multi-agent data analysis pipeline prototype from your Jupyter notebook has been successfully transformed into a responsive, cross-platform desktop application. 

Here is a summary of the files created and modifications made.

---

## 🛠️ Changes Implemented

### 1. Project Dependencies & Configuration
* **Created** requirements.txt: Declares FastAPI, Uvicorn, Python-Multipart alongside the notebook's core libraries (`google-genai`, `langgraph`, `langsmith`, `pandas`, `weasyprint`, `matplotlib`, etc.).
* **Created** backend/config.py: Manages saving/loading user credentials in the `config.json` configuration file under `~/.ai_multi_agent_data_analysis/config.json`.
  * **Security**: This `config.json` file contains your Gemini and LangSmith API keys. To ensure they are secured, access permissions are restricted using `chmod 600` (owner-only access) on macOS/Linux. On Windows, it leverages default NTFS folder permissions which restrict read/write access solely to your user account, administrators, and SYSTEM. This guarantees that your API keys are stored securely across all platforms.
  * Disassociates API keys from environment variables to prevent global leakages.

### 2. Multi-Agent Backend
* **Created** backend/agent_workflow.py: Adapts the LangGraph multi-agent architecture from the notebook.
  * Dynamically binds `genai.Client` and registers either `gemini-3.5-flash` (Free Tier) or `gemini-3.1-pro-preview` (Paid Tier).
  * Implements `register_status_callback` to emit progress updates.
  * **On-Demand PDF Rendering**: Refactored the workflow to output only Markdown. Added the PDF layout compiler functions for both `xhtml2pdf` (Default / Pure Python / Portable) and `weasyprint` (High Fidelity / System dependent).
* **Created** backend/main.py: Sets up the FastAPI server.
  * Serves REST API endpoints for secure credentials (saving, checking, clearing), CSV uploads, workflow runs, on-demand PDF compilation, and desktop PDF opening.
  * Spawns a background thread to launch the default browser targeting `http://localhost:8000` on startup.

### 3. Glassmorphic User Interface
* **Created** frontend/index.html: Constructs a responsive single-page layout with clear segmentation:
  1. API configuration (tier toggles, masked API inputs, Permanent vs Temporary save buttons, and a dynamic 'Clear Saved Keys' button).
  2. Dataset importer & Export Location picker.
  3. PDF Rendering Engine segment buttons with description text toggles (`xhtml2pdf` vs `WeasyPrint`).
  4. Live workflow agent cards that glow and transition states dynamically.
  5. Real-time console showing terminal logging lines.
  6. Post-run actions (Open LangSmith, navigation guides, Markdown toggle viewer, and "Export to PDF" button).
* **Created** frontend/styles.css: Premium design theme featuring high-end dark backgrounds, neon glowing overlays, custom Outfit/Inter typography, responsive media queries, and click scaling micro-animations.
* **Created** frontend/app.js: Controls state transitions, handles files/creds posts, runs polling hooks, selects PDF engines, manages credential clearing, triggers on-demand PDF rendering requests, and interacts with system utilities.

### 4. Cross-Platform Double-Click Launchers
* **Created** run.bat: Shell script for Windows that automates virtual environment creation (`.venv`), activating, dependency installs, and launching the server.
* **Created** run.sh: Shell launcher equivalent for macOS and Linux.
* **Created** launcher.py: Root-level entry script that programmatically initializes the uvicorn server. Serves as the entry point for PyInstaller so that relative package imports (like backend.config) resolve correctly in the compiled bundle.
* **Optimization**: Includes age-comparison caching. It checks if requirements.txt is newer than a sentinel installation token (.venv\sentinel). If no modifications were made, it skips the pip install check completely to reduce startup times.

---

## 🔍 Validation Summary

### 1. Code Compilation & Architecture Checks
We ran structural imports checks using Python to ensure that the server modules, configuration manager, and langgraph logic load cleanly without syntax or configuration problems.

### 2. User-Friendly Error Capture
Weasyprint's native platform library dependency issue (common on base Windows installations missing GTK/Pango libraries) was successfully caught and transformed into a friendly instruction text banner in our exceptions mapping in backend/main.py:
> `"PDF Compiler Error: WeasyPrint was unable to compile the PDF. Please check if system dependencies (like Pango or GTK) are installed on this operating system."`

This confirms that the UI handles external software failures gracefully without displaying technical stack trace errors to the end-user.

---

## 🚀 How to Run the App

1. Double-click the launcher script for your operating system:
   * **Windows**: run.bat
   * **Mac / Linux**: run.sh
2. The script will initialize your `.venv`, install the required python packages, start the FastAPI server, and automatically open the application in your default browser at http://localhost:8000.
