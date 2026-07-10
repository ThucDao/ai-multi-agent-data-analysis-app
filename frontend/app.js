// Local State Variables
let selectedTier = 'free';
let pdfReportPath = null;
let pollInterval = null;
let lastLogMessage = '';
let isAnalyzing = false;

// Agent node order to resolve progress states sequentially
const agentNodes = ['profiler', 'code_writer', 'executor', 'insights', 'report'];

// Page elements caching
const tierFreeBtn = document.getElementById('tier-free');
const tierPaidBtn = document.getElementById('tier-paid');
const geminiInput = document.getElementById('gemini-key');
const langsmithInput = document.getElementById('langsmith-key');
const geminiStatus = document.getElementById('gemini-status');
const langsmithStatus = document.getElementById('langsmith-status');
const fileInputText = document.getElementById('csv-file-name');
const startBtn = document.getElementById('start-analysis-btn');
const progressCard = document.getElementById('progress-card');
const resultsCard = document.getElementById('results-card');
const consoleBody = document.getElementById('console-body');
const errorAlert = document.getElementById('error-alert');
const errorText = document.getElementById('error-text');
const workflowSpinner = document.getElementById('workflow-spinner');
const markdownContainer = document.getElementById('markdown-viewer-container');
const toggleMdBtn = document.getElementById('toggle-md-btn');

// Initial Load Handler
window.addEventListener('DOMContentLoaded', () => {
  checkCredentials();
});

// Segment Control Toggle
function selectTier(tier) {
  if (isAnalyzing) return;
  selectedTier = tier;
  if (tier === 'free') {
    tierFreeBtn.classList.add('active');
    tierPaidBtn.classList.remove('active');
  } else {
    tierPaidBtn.classList.add('active');
    tierFreeBtn.classList.remove('active');
  }
}

// Check saved API keys status on backend
async function checkCredentials() {
  try {
    const res = await fetch('/api/credentials');
    const status = await res.json();
    updateCredentialsBadges(status);
  } catch (err) {
    console.error('Failed to retrieve credential setup state:', err);
  }
}

// Update credential badges in UI
function updateCredentialsBadges(status) {
  if (status.gemini_configured) {
    geminiStatus.textContent = 'Saved';
    geminiStatus.classList.add('configured');
    geminiInput.placeholder = '•••••••••••••••• (Saved)';
  } else {
    geminiStatus.textContent = 'Not Saved';
    geminiStatus.classList.remove('configured');
    geminiInput.placeholder = 'Enter Gemini API key...';
  }

  if (status.langsmith_configured) {
    langsmithStatus.textContent = 'Saved';
    langsmithStatus.classList.add('configured');
    langsmithInput.placeholder = '•••••••••••••••• (Saved)';
  } else {
    langsmithStatus.textContent = 'Not Saved';
    langsmithStatus.classList.remove('configured');
    langsmithInput.placeholder = 'Enter LangSmith API key...';
  }
}

// Save pasted API credentials
async function saveCreds() {
  const geminiKey = geminiInput.value.trim();
  const langsmithKey = langsmithInput.value.trim();

  // If fields are empty and we already have them saved, do nothing
  if (!geminiKey && !langsmithKey && 
      geminiStatus.classList.contains('configured') && 
      langsmithStatus.classList.contains('configured')) {
    alert('API keys are already saved.');
    return;
  }

  if (!geminiKey || !langsmithKey) {
    alert('Please enter values for both Gemini and LangSmith API keys.');
    return;
  }

  try {
    const res = await fetch('/api/credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gemini_api_key: geminiKey,
        langsmith_api_key: langsmithKey
      })
    });
    
    if (res.ok) {
      alert('Credentials saved successfully. The API keys have been hidden for security.');
      geminiInput.value = '';
      langsmithInput.value = '';
      checkCredentials();
    } else {
      const errData = await res.json();
      alert(`Error saving credentials: ${errData.detail || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Failed to connect to the backend: ${err.message}`);
  }
}

// Browse Button Trigger
function triggerFilePicker() {
  if (isAnalyzing) return;
  document.getElementById('csv-file-input').click();
}

// File Dialog Handler - uploads CSV
async function handleFileChange(event) {
  const file = event.target.files[0];
  if (!file) return;

  fileInputText.value = 'Uploading file...';
  startBtn.disabled = true;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/upload-csv', {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      const data = await res.json();
      fileInputText.value = data.filename;
      startBtn.disabled = false; // Enable Start button after successful upload
      addLogLine('system-msg', `Dataset "${data.filename}" uploaded successfully and ready for analysis.`);
    } else {
      const errData = await res.json();
      fileInputText.value = '';
      alert(`Upload failed: ${errData.detail || 'Please select a valid CSV.'}`);
    }
  } catch (err) {
    fileInputText.value = '';
    alert(`Error uploading file: ${err.message}`);
  }
}

// Start Multi-Agent workflow
async function startAnalysis() {
  if (isAnalyzing) return;

  // Toggle flags
  isAnalyzing = true;
  startBtn.disabled = true;
  document.getElementById('save-creds-btn').disabled = true;
  
  // UI setups
  progressCard.style.display = 'block';
  resultsCard.style.display = 'none';
  errorAlert.style.display = 'none';
  markdownContainer.style.display = 'none';
  toggleMdBtn.textContent = 'Show Markdown Report';
  
  // Reset agents nodes classes
  agentNodes.forEach(node => {
    const el = document.getElementById(`node-${node}`);
    if (el) el.className = 'agent-node';
  });

  // Clear and configure terminal log
  consoleBody.innerHTML = '';
  addLogLine('system-msg', 'Initializing analysis workflow...');
  lastLogMessage = '';

  const formData = new FormData();
  formData.append('tier', selectedTier);

  try {
    const res = await fetch('/api/run-analysis', {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      // Begin polling
      workflowSpinner.classList.add('progress-spinner');
      pollInterval = setInterval(pollStatus, 1000);
    } else {
      const errData = await res.json();
      handleHaltState(errData.detail || 'Failed to start analysis.');
    }
  } catch (err) {
    handleHaltState(`Connection failed: ${err.message}`);
  }
}

// Poll status endpoint
async function pollStatus() {
  try {
    const res = await fetch('/api/run-status');
    const status = await res.json();

    updateAgentNodesUI(status);
    updateConsoleLogs(status);

    if (!status.is_running) {
      clearInterval(pollInterval);
      pollInterval = null;
      isAnalyzing = false;
      startBtn.disabled = false;
      document.getElementById('save-creds-btn').disabled = false;
      workflowSpinner.classList.remove('progress-spinner');

      if (status.completed) {
        // Run completed successfully or with tolerable errors
        pdfReportPath = status.report_pdf;
        document.getElementById('markdown-body').innerHTML = status.report_html || '<p>No report body generated.</p>';
        resultsCard.style.display = 'block';
        addLogLine('system-msg', 'Workflow execution completed.');
      }
      
      if (status.error && !status.completed) {
        // Fatal workflow failure
        handleHaltState(status.error);
      }
    }
  } catch (err) {
    console.error('Error polling run status:', err);
  }
}

// Update the agent node cards based on current active state
function updateAgentNodesUI(status) {
  const activeNode = status.active_agent;
  
  if (status.is_running && activeNode) {
    const activeIndex = agentNodes.indexOf(activeNode);
    
    agentNodes.forEach((node, idx) => {
      const el = document.getElementById(`node-${node}`);
      if (!el) return;
      
      if (idx < activeIndex) {
        el.className = 'agent-node completed';
      } else if (idx === activeIndex) {
        el.className = 'agent-node active';
      } else {
        el.className = 'agent-node';
      }
    });
  } else if (status.completed && !status.error) {
    // If fully complete, mark all as completed
    agentNodes.forEach(node => {
      const el = document.getElementById(`node-${node}`);
      if (el) el.className = 'agent-node completed';
    });
  }
}

// Append new messages to the mock terminal console
function updateConsoleLogs(status) {
  const msg = status.message;
  const activeNode = status.active_agent;
  
  if (msg && msg !== lastLogMessage) {
    lastLogMessage = msg;
    const timestamp = new Date().toLocaleTimeString();
    
    let lineClass = 'info-msg';
    let prefix = '[SYSTEM]';
    
    if (activeNode) {
      lineClass = 'agent-msg';
      prefix = `[${activeNode.toUpperCase()} AGENT]`;
    }
    
    addLogLine(lineClass, `${prefix} (${timestamp}): ${msg}`);
  }

  // Display nested python code compiler issues (if any)
  if (status.error && status.completed) {
    addLogLine('error-msg', `[WARNING]: ${status.error}`);
  }
}

// Helper to push text nodes to scrollbox
function addLogLine(cssClass, text) {
  const div = document.createElement('div');
  div.className = `log-line ${cssClass}`;
  div.textContent = text;
  consoleBody.appendChild(div);
  consoleBody.scrollTop = consoleBody.scrollHeight;
}

// Halt flow and display error banner
function handleHaltState(friendlyError) {
  clearInterval(pollInterval);
  pollInterval = null;
  isAnalyzing = false;
  startBtn.disabled = false;
  document.getElementById('save-creds-btn').disabled = false;
  workflowSpinner.classList.remove('progress-spinner');

  // Mark currently active node as idle/failed
  agentNodes.forEach(node => {
    const el = document.getElementById(`node-${node}`);
    if (el && el.classList.contains('active')) {
      el.classList.remove('active');
    }
  });

  addLogLine('error-msg', `[FATAL ERROR]: ${friendlyError}`);
  errorText.textContent = friendlyError;
  errorAlert.style.display = 'flex';
}

// Toggle markdown findings viewer
function toggleMarkdownReport() {
  if (markdownContainer.style.display === 'none') {
    markdownContainer.style.display = 'block';
    toggleMdBtn.textContent = 'Hide Markdown Report';
    markdownContainer.scrollIntoView({ behavior: 'smooth' });
  } else {
    markdownContainer.style.display = 'none';
    toggleMdBtn.textContent = 'Show Markdown Report';
  }
}

// Desktop launcher action - open PDF report
async function openPDF() {
  if (!pdfReportPath) {
    alert('No report PDF path found.');
    return;
  }

  try {
    const res = await fetch('/api/open-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pdf_path: pdfReportPath })
    });

    if (!res.ok) {
      const errData = await res.json();
      alert(`Could not open PDF: ${errData.detail || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Failed to send open-pdf command: ${err.message}`);
  }
}

// LangSmith dashboard trigger
function openLangSmith() {
  window.open('https://smith.langchain.com/', '_blank');
}
