// Local State Variables
let selectedTier = 'free';
let selectedEngine = 'xhtml2pdf';
let pdfReportPath = null;
let generatedMarkdown = null;
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
const exportLocationInput = document.getElementById('export-location');
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

// PDF Engine Toggle
function selectEngine(engine) {
  if (isAnalyzing) return;
  selectedEngine = engine;
  
  const xhtmlBtn = document.getElementById('engine-xhtml2pdf');
  const weasyBtn = document.getElementById('engine-weasyprint');
  const descEl = document.getElementById('engine-desc');
  
  if (engine === 'xhtml2pdf') {
    xhtmlBtn.classList.add('active');
    weasyBtn.classList.remove('active');
    descEl.innerHTML = '<strong>xhtml2pdf</strong>: Runs completely in Python. Zero native OS setup required. Works instantly on any machine.';
  } else {
    weasyBtn.classList.add('active');
    xhtmlBtn.classList.remove('active');
    descEl.innerHTML = '<strong>WeasyPrint</strong>: High-fidelity CSS3/HTML5 printer engine. Requires GTK+ and Pango installed on your operating system.';
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
  const isTemp = status.temporary;
  const badgeText = isTemp ? 'Temporary' : 'Saved';
  const placeholderSuffix = isTemp ? ' (Temporary)' : ' (Saved)';

  if (status.gemini_configured) {
    geminiStatus.textContent = badgeText;
    geminiStatus.classList.add('configured');
    geminiInput.placeholder = `••••••••••••••••${placeholderSuffix}`;
  } else {
    geminiStatus.textContent = 'Not Saved';
    geminiStatus.classList.remove('configured');
    geminiInput.placeholder = 'Enter Gemini API key...';
  }

  if (status.langsmith_configured) {
    langsmithStatus.textContent = badgeText;
    langsmithStatus.classList.add('configured');
    langsmithInput.placeholder = `••••••••••••••••${placeholderSuffix}`;
  } else {
    langsmithStatus.textContent = 'Not Saved';
    langsmithStatus.classList.remove('configured');
    langsmithInput.placeholder = 'Enter LangSmith API key...';
  }

  // Toggle "Clear Saved Keys" button based on configuration status
  const clearBtn = document.getElementById('clear-creds-btn');
  if (status.gemini_configured || status.langsmith_configured) {
    clearBtn.style.display = 'block';
  } else {
    clearBtn.style.display = 'none';
  }
}

// Save pasted API credentials
async function saveCreds(isTemporary = false) {
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
        langsmith_api_key: langsmithKey,
        temporary: isTemporary
      })
    });
    
    if (res.ok) {
      const mode = isTemporary ? 'temporarily for this session' : 'permanently';
      alert(`Credentials saved successfully ${mode}. The API keys have been hidden for security.`);
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

// Clear stored credentials on backend
async function clearCreds() {
  if (isAnalyzing) return;
  if (!confirm('Are you sure you want to delete all stored API keys from this machine?')) {
    return;
  }

  try {
    const res = await fetch('/api/credentials/clear', {
      method: 'POST'
    });
    
    if (res.ok) {
      alert('Stored credentials cleared successfully.');
      geminiInput.value = '';
      langsmithInput.value = '';
      checkCredentials();
    } else {
      const errData = await res.json();
      alert(`Error clearing credentials: ${errData.detail || 'Unknown error'}`);
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

// Browse Folder Picker for Export Location
async function browseExportLocation() {
  if (isAnalyzing) return;
  try {
    const res = await fetch('/api/select-export-directory', {
      method: 'POST'
    });
    if (res.ok) {
      const data = await res.json();
      if (data.status === 'success') {
        exportLocationInput.value = data.directory;
      }
    } else {
      const errData = await res.json();
      alert(`Folder picker failed: ${errData.detail || 'You can type the path manually.'}`);
    }
  } catch (err) {
    alert(`Could not connect to directory picker: ${err.message}. You can type the path manually.`);
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
  
  const exportPath = exportLocationInput.value.trim();
  if (exportPath) {
    formData.append('export_path', exportPath);
  }

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
        // Run completed successfully
        pdfReportPath = null; // resets local path since PDF isn't compiled yet
        generatedMarkdown = status.report_md;
        
        // Reset PDF action button state
        document.getElementById('pdf-action-title').textContent = 'Export to PDF';
        document.getElementById('pdf-action-desc').textContent = `Compile and render the report using ${selectedEngine}.`;
        
        document.getElementById('markdown-body').innerHTML = status.report_html || '<p>No report body generated.</p>';
        resultsCard.style.display = 'block';
        addLogLine('system-msg', 'Workflow execution completed. You can now toggle the report or click "Export to PDF".');
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

// On-demand PDF Generation
async function generatePDF() {
  if (isAnalyzing) return;
  if (!generatedMarkdown) {
    alert('Please run the data analysis workflow first to generate a report.');
    return;
  }

  const titleEl = document.getElementById('pdf-action-title');
  const descEl = document.getElementById('pdf-action-desc');

  // If already compiled, clicking the banner will open the PDF
  if (pdfReportPath) {
    openPDF();
    return;
  }

  // Update button state to compiling
  titleEl.textContent = 'Generating PDF...';
  descEl.textContent = 'Running HTML to PDF layout compiler engine. Please wait...';

  try {
    const res = await fetch('/api/generate-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_md: generatedMarkdown,
        engine: selectedEngine,
        export_path: exportLocationInput.value.trim() || null
      })
    });

    if (res.ok) {
      const data = await res.json();
      pdfReportPath = data.pdf_path;
      
      titleEl.textContent = 'Open PDF Report';
      
      let msg = `PDF generated successfully using ${selectedEngine}! Click to view.`;
      if (data.exported_path) {
        msg += ' Copied to export directory.';
      }
      descEl.textContent = msg;
      
      // Auto open PDF
      openPDF();
    } else {
      const errData = await res.json();
      titleEl.textContent = 'Failed to Generate PDF';
      descEl.textContent = errData.detail || 'Rendering engine returned an error.';
      alert(`PDF Compilation Error: ${errData.detail || 'Unknown error'}`);
    }
  } catch (err) {
    titleEl.textContent = 'Failed to Generate PDF';
    descEl.textContent = `Network error: ${err.message}`;
    alert(`Failed to connect to backend: ${err.message}`);
  }
}

// Desktop launcher action - open PDF report
async function openPDF() {
  if (!pdfReportPath) {
    alert('Please generate the PDF first.');
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
