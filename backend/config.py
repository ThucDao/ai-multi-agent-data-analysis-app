import json
from pathlib import Path
import os

CONFIG_DIR = Path.home() / ".ai_multi_agent_data_analysis"
CONFIG_FILE = CONFIG_DIR / "config.json"

def get_config_path() -> Path:
    """Returns the absolute path to the configuration file."""
    return CONFIG_FILE

def save_credentials(gemini_key: str, langsmith_key: str, temporary: bool = False):
    """Saves the Gemini and LangSmith API keys securely in the home directory."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Try to set owner-only permissions on the directory if it's new
    try:
        if os.name != 'nt':
            os.chmod(CONFIG_DIR, 0o700)
    except Exception:
        pass

    data = {
        "GEMINI_API_KEY": gemini_key.strip(),
        "LANGSMITH_API_KEY": langsmith_key.strip(),
        "temporary": temporary
    }
    
    # Write the config file
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    # Set config file permissions to owner-only read/write
    try:
        if os.name != 'nt':
            os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass

def load_credentials() -> dict:
    """Loads the stored credentials. Returns an empty dict if not found."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "GEMINI_API_KEY": data.get("GEMINI_API_KEY", ""),
                "LANGSMITH_API_KEY": data.get("LANGSMITH_API_KEY", ""),
                "temporary": data.get("temporary", False)
            }
    except Exception:
        return {}

def clear_credentials():
    """Removes stored keys from the configuration file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"GEMINI_API_KEY": "", "LANGSMITH_API_KEY": "", "temporary": False}, f, indent=2)
        except Exception:
            pass

def check_credentials() -> dict:
    """Checks which credentials have been configured."""
    creds = load_credentials()
    return {
        "gemini_configured": bool(creds.get("GEMINI_API_KEY")),
        "langsmith_configured": bool(creds.get("LANGSMITH_API_KEY")),
        "temporary": creds.get("temporary", False)
    }
