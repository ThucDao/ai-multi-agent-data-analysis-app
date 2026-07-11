import os
import json
import textwrap
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from google import genai
from google.genai import types
from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from langsmith import traceable
import pandas as pd
import markdown2

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from mdit_py_plugins.footnote import footnote_plugin

# Configuration globals
client = None
MODEL = "gemini-3.5-flash"
ARTIFACTS_DIR = Path("artifacts")

# Callback to report progress to the backend web server
_status_callback: Callable[[str, str, str | None], None] = None

def register_status_callback(cb: Callable[[str, str, str | None], None]):
    """Registers a status callback function."""
    global _status_callback
    _status_callback = cb

def update_status(agent: str, message: str, error: str | None = None):
    """Sends status updates back to the registered callback."""
    if _status_callback:
        _status_callback(agent, message, error)

def set_client_and_model(api_key: str, tier: str):
    """Initializes the Gemini API client and selects the model based on tier."""
    global client, MODEL
    client = genai.Client(api_key=api_key)
    if tier.lower() == "paid":
        MODEL = "gemini-3.1-pro-preview"
    else:
        MODEL = "gemini-3.5-flash"

# Define LangGraph shared State
class State(BaseModel):
    dataset_path: str
    profile: dict | None = None
    plan: dict | None = None
    code: str | None = None
    exec_result: dict | None = None
    charts_meta: list | None = None
    insights: str | None = None
    report_md: str | None = None
    report_pdf: str | None = None
    retry_count: int = 0
    last_error: str | None = None

MAX_RETRIES = 2

# Traceable Wrapper around Gemini generate content
@traceable(name="gemini_generate_content", run_type="llm")
def gemini_call(prompt: str, thinking_level: str = "high"):
    """
    Wrapper for google-genai to generate content.
    Automatically traced by LangSmith.
    """
    if client is None:
        raise ValueError("Gemini Client has not been initialized. Please configure API keys first.")
        
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level)
        ),
    )

    usage = getattr(resp, "usage_metadata", None)
    token_usage = None
    if usage:
        token_usage = {
            "prompt_tokens": usage.prompt_token_count,
            "completion_tokens": usage.candidates_token_count,
            "total_tokens": usage.total_token_count,
            "thoughts_tokens": getattr(usage, "thoughts_token_count", None),
        }

    return {
        "generations": [{"text": resp.text}],
        "llm_output": {
            "model_name": MODEL,
            "token_usage": token_usage,
        },
        "raw_response": resp,
    }

# ----------------- Tools -----------------

def load_dataset(path: str):
    """Loads a CSV file and profiles its basic structure."""
    df = pd.read_csv(path)
    summary = {
        "shape": df.shape,
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing_pct": df.isna().mean().to_dict(),
        "head": df.head(5).to_dict(orient="records"),
        "describe": df.describe(include="all").fillna("").to_dict()
    }
    return summary

def run_python(code: str):
    """Runs generated python code inside a restricted execution sandbox."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    local_env = {"ARTIFACTS_DIR": ARTIFACTS_DIR}
    try:
        exec(textwrap.dedent(code), {}, local_env)
        return {
            "ok": True,
            "stdout": local_env.get("_stdout", ""),
            "artifacts": local_env.get("_artifacts", []),
            "charts_meta": local_env.get("_charts_meta", []),
        }
    except Exception:
        return {"ok": False, "traceback": traceback.format_exc()}

# Setup markdown parser for HTML/PDF rendering
md = (
    MarkdownIt("commonmark", {"breaks": True, "html": True})
    .enable(["table", "strikethrough"])
    .use(tasklists_plugin)
    .use(footnote_plugin)
)

def render_pdf_xhtml2pdf(markdown_text: str, pdf_path: Path):
    """Renders PDF using xhtml2pdf (pure Python, zero native OS dependencies)."""
    from xhtml2pdf import pisa
    import os
    
    html_body = md.render(markdown_text)
    
    html_template = f"""
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        @page {{
          size: letter;
          margin: 0.8in;
        }}
        body {{
          font-family: Helvetica, Arial, sans-serif;
          font-size: 10pt;
          line-height: 1.4;
          color: #111111;
        }}
        h1 {{ font-size: 18pt; margin-bottom: 8pt; color: #111111; }}
        h2 {{ font-size: 14pt; margin-top: 14pt; margin-bottom: 6pt; color: #222222; }}
        h3 {{ font-size: 11pt; margin-top: 10pt; margin-bottom: 4pt; color: #333333; }}
        p {{ margin-bottom: 6pt; }}
        ul, ol {{ margin-bottom: 8pt; margin-left: 15pt; }}
        li {{ margin-bottom: 2pt; }}
        table {{
          width: 100%;
          border-collapse: collapse;
          margin: 10pt 0;
          font-size: 9pt;
        }}
        th, td {{
          border: 1px solid #cccccc;
          padding: 5pt;
          text-align: left;
        }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        img {{
          display: block;
          margin: 10pt auto;
          max-width: 320px;
        }}
        .chart-block {{
          page-break-inside: avoid;
          margin-bottom: 12pt;
        }}
        code {{
          background-color: #f6f6f6;
          font-family: Courier, monospace;
          font-size: 9pt;
        }}
      </style>
    </head>
    <body>
      {html_body}
    </body>
    </html>
    """
    
    # Callback to resolve relative image path references from html (e.g. "artifacts/chart...")
    def link_callback(uri, rel):
        if uri.startswith("artifacts/"):
            return os.path.abspath(uri)
        return uri

    with open(pdf_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(
            src=html_template,
            dest=pdf_file,
            link_callback=link_callback
        )
        
    if pisa_status.err:
        raise RuntimeError("xhtml2pdf failed to render PDF document.")

def render_pdf_weasyprint(markdown_text: str, pdf_path: Path):
    """Renders PDF using WeasyPrint (high-fidelity printer rendering, requires GTK+)."""
    import weasyprint
    html_body = md.render(markdown_text)

    html_template = f"""
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{
          font-family: Arial, sans-serif;
          font-size: 12px;
          line-height: 1.5;
          color: #111;
        }}
        h1 {{ font-size: 20px; margin-bottom: 6px; }}
        h2 {{ font-size: 16px; margin-top: 18px; margin-bottom: 6px; }}
        h3 {{ font-size: 13px; margin-top: 12px; margin-bottom: 4px; }}
        p {{ margin: 6px 0; }}
        ul, ol {{
          margin: 6px 0 6px 18px;
        }}
        li {{ margin: 2px 0; }}
        table {{
          width: 100%;
          border-collapse: collapse;
          margin: 8px 0 12px 0;
          font-size: 11px;
        }}
        th, td {{
          border: 1px solid #ccc;
          padding: 6px;
          text-align: left;
        }}
        th {{ background: #f2f2f2; }}
        img {{
          display: block;
          margin: 8px auto 8px auto;
          max-width: 70%;
          height: auto;
          page-break-inside: avoid;
        }}
        .chart-block {{
          page-break-inside: avoid;
          margin-bottom: 12px;
        }}
        code {{
          background: #f6f6f6;
          padding: 2px 4px;
          border-radius: 4px;
          font-size: 11px;
        }}
        pre code {{
          display: block;
          padding: 8px;
          overflow-x: auto;
        }}
      </style>
    </head>
    <body>
      {html_body}
    </body>
    </html>
    """

    weasyprint.HTML(
        string=html_template,
        base_url=str(ARTIFACTS_DIR.parent.resolve())
    ).write_pdf(str(pdf_path))

def render_pdf(markdown_text: str, engine: str = "xhtml2pdf"):
    """Compiles Markdown report to PDF using the chosen rendering engine."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    pdf_path = ARTIFACTS_DIR / f"report_{timestamp}.pdf"

    if engine.lower() == "weasyprint":
        render_pdf_weasyprint(markdown_text, pdf_path)
    else:
        render_pdf_xhtml2pdf(markdown_text, pdf_path)

    return str(pdf_path)

# ----------------- Agents -----------------

@traceable(name="profiler_agent")
def profiler_agent(state: State):
    update_status("profiler", "Reading the CSV dataset and profiling columns...")
    profile = load_dataset(state.dataset_path)

    update_status("profiler", "Formulating an analysis and visualization plan...")
    prompt = f"""
    You are the Data Profiler Agent.
    Produce a JSON analysis plan with:
      - task_type: "classification"|"regression"|"eda_only"
      - target_column (if any)
      - eda_steps (list)
      - charts_to_make (list)  # 5-10 max, most informative
      - baseline_model_steps (list if modeling)
      - risks_or_data_issues (list)

    Dataset profile:
    {json.dumps(profile, indent=2)}
    """

    resp = gemini_call(prompt, thinking_level="high")
    text = resp["generations"][0]["text"]

    try:
        # Strip markdown tags if any
        stripped = text.strip()
        if stripped.startswith("```json"):
            stripped = stripped[7:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        plan = json.loads(stripped.strip())
    except Exception:
        plan = {"raw_plan": text}

    state.profile = profile
    state.plan = plan
    return state

@traceable(name="code_writer_agent")
def code_writer_agent(state: State):
    retry_msg = f" (Attempt {state.retry_count + 1})" if state.retry_count > 0 else ""
    update_status("code_writer", f"Generating Python data analysis code{retry_msg}...")
    
    prompt = f"""
    You are the Code Writer Agent.
    Write Python code ONLY (no markdown formatting, do not wrap code in ```python ... ```).

    Previous error to fix (if any):
    {state.last_error}

    HARD REQUIREMENTS:
    1. Load dataset from: {state.dataset_path}
    2. Follow the plan exactly.
    3. Create ALL charts in charts_to_make.
    4. Save every chart in ARTIFACTS_DIR with filenames like:
         ARTIFACTS_DIR / "chart_01_<short_name>.png"
    5. Track saved plot paths in _artifacts (list[str]).
    6. Track chart metadata in _charts_meta (list[dict]) with:
         {{
           "title": "<human readable chart title>",
           "filename": "artifacts/chart_01_x.png",
           "description": "<what this plot shows (1-2 sentences)>",
           "one_liner": "<ONE line insight from the chart>"
         }}
       The one_liner MUST be a single sentence, max ~20 words.

    7. Store useful console output in _stdout.

    IMPORTANT:
    - import matplotlib.pyplot as plt
    - plt.close() after saving each plot
    - ensure _artifacts and _charts_meta exist even if empty
    - if modeling, add baseline metrics to _stdout

    Dataset profile:
    {json.dumps(state.profile, indent=2)}

    Analysis plan:
    {json.dumps(state.plan, indent=2)}

    Return ONLY executable python code.
    """

    resp = gemini_call(prompt, thinking_level="high")
    code = resp["generations"][0]["text"]
    
    # Strip markdown block ticks if returned by LLM
    stripped = code.strip()
    if stripped.startswith("```python"):
        stripped = stripped[9:]
    elif stripped.startswith("```"):
        stripped = stripped[3:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
        
    state.code = stripped.strip()
    return state

@traceable(name="executor_agent")
def executor_agent(state: State):
    update_status("executor", "Running data analysis code inside sandbox environment...")
    result = run_python(state.code)
    state.exec_result = result
    state.charts_meta = result.get("charts_meta", [])

    if not result["ok"]:
        state.retry_count += 1
        state.last_error = result.get("traceback", "Unknown error")
        update_status("executor", "Code execution failed. Attempting self-correction...")
    else:
        update_status("executor", "Code executed successfully! Outputs saved.")

    return state

@traceable(name="insights_agent")
def insights_agent(state: State):
    update_status("insights", "Synthesizing visual graphs and raw metrics into analytical insights...")
    prompt = f"""
    You are the Insights Agent.

    HARD REQUIREMENTS:
    - No empty bullets.
    - No repeated bullets.
    - Be specific to this dataset and these charts.
    - Output format:

      ### Chart Insights
      For each chart in charts_meta:
      - **<title>**
        - Takeaway 1 (one sentence)
        - Takeaway 2 (one sentence)
        - Caveat/Risk (one sentence)

      ### Overall Insights
      - 3-5 bullets max, each one sentence.

    Inputs:
    Profile:
    {json.dumps(state.profile, indent=2)}

    Execution result:
    {json.dumps(state.exec_result, indent=2)}

    Charts meta:
    {json.dumps(state.charts_meta, indent=2)}
    """

    resp = gemini_call(prompt, thinking_level="high")
    state.insights = resp["generations"][0]["text"]
    return state

@traceable(name="report_agent")
def report_agent(state: State):
    update_status("report", "Compiling Markdown report and rendering PDF document...")
    prompt = f"""
    You are the Report Agent.
    Create a neat Markdown report (HTML allowed).

    HARD REQUIREMENTS:
    - Do NOT repeat section titles or chart titles.
    - Do NOT output empty bullet points. If a bullet would be empty, skip it.
    - Keep spacing consistent: one blank line between sections.
    - Use charts_meta as the ONLY source of charts.
    - Include EVERY chart, exactly once, in the same order as charts_meta.
    - For each chart output EXACTLY this block:

      <div class="chart-block">
        <h3>Chart {{i}}: {{title}}</h3>
        <img src="{{filename}}" alt="{{title}}">
        <p><b>What it shows:</b> {{one_liner}}</p>
      </div>

      Where:
      - title, filename, one_liner come from charts_meta
      - one_liner must be ONE sentence, max ~20 words.

    Sections:
    1. Dataset Overview (short)
    2. Data Quality Notes (bullets)
    3. Exploratory Analysis (chart-by-chart blocks only, no extra chart titles)
    4. Modeling Results (if any; use a markdown table)
    5. Key Insights (use insights text)
    6. Recommendations / Next Steps (bullets)

    Inputs:
    Profile: {json.dumps(state.profile, indent=2)}
    Exec stdout: {state.exec_result.get("stdout","")}
    Exec ok: {state.exec_result.get("ok")}
    Traceback (if any): {state.exec_result.get("traceback","")}
    Charts meta:
    {json.dumps(state.charts_meta, indent=2)}
    Insights:
    {state.insights}

    Return ONLY the Markdown report.
    """

    resp = gemini_call(prompt, thinking_level="low")
    state.report_md = resp["generations"][0]["text"]
    state.report_pdf = None
    return state

# ----------------- Compile Graph -----------------

g = StateGraph(State)
g.add_node("profiler", profiler_agent)
g.add_node("code_writer", code_writer_agent)
g.add_node("executor", executor_agent)
g.add_node("insights", insights_agent)
g.add_node("report", report_agent)

g.set_entry_point("profiler")
g.add_edge("profiler", "code_writer")
g.add_edge("code_writer", "executor")

def retry_or_continue(state: State):
    # Success path
    if state.exec_result and state.exec_result.get("ok"):
        return "insights"
    # Stop retrying after MAX_RETRIES
    if state.retry_count >= MAX_RETRIES:
        return "report"
    return "code_writer"

g.add_conditional_edges(
    "executor",
    retry_or_continue,
    {"code_writer": "code_writer", "insights": "insights", "report": "report"}
)

g.add_edge("insights", "report")
g.add_edge("report", END)

graph = g.compile()

def run_agent_workflow(dataset_path: str) -> dict:
    """Invokes the compiled agent graph and returns the final state outputs."""
    initial_state = State(dataset_path=dataset_path)
    final_state = graph.invoke(initial_state)
    return {
        "report_md": final_state.get("report_md"),
        "report_pdf": final_state.get("report_pdf"),
        "ok": final_state.get("exec_result", {}).get("ok", False) if final_state.get("exec_result") else False,
        "last_error": final_state.get("last_error")
    }
