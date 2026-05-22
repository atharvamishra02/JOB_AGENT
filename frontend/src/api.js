const BASE = '';

function getHeaders(extra = {}) {
  const token = localStorage.getItem('token');
  const headers = { ...extra };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export async function fetchDashboard() {
  const res = await fetch(`${BASE}/api/dashboard`, { headers: getHeaders() });
  return res.json();
}

export async function fetchJobs() {
  const res = await fetch(`${BASE}/api/jobs`, { headers: getHeaders() });
  return res.json();
}

export async function fetchApplications() {
  const res = await fetch(`${BASE}/api/applications`, { headers: getHeaders() });
  return res.json();
}

export async function fetchResumeData() {
  const res = await fetch(`${BASE}/api/resume-data`, { headers: getHeaders() });
  return res.json();
}

export async function fetchResumes() {
  const res = await fetch(`${BASE}/api/resumes`, { headers: getHeaders() });
  return res.json();
}

export async function fetchLogs() {
  const res = await fetch(`${BASE}/api/logs`, { headers: getHeaders() });
  return res.json();
}

export async function fetchWorkflowStatus() {
  const res = await fetch(`${BASE}/api/workflow-status`, { headers: getHeaders() });
  return res.json();
}

export async function startWorkflow(resumePath) {
  const res = await fetch(`${BASE}/api/start-workflow`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ resume_path: resumePath }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to start workflow');
  }
  return res.json();
}

export async function stopWorkflow() {
  const res = await fetch(`${BASE}/api/stop-workflow`, { 
    method: 'POST', 
    headers: getHeaders() 
  });
  return res.json();
}

export async function uploadResume(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/upload-resume`, { 
    method: 'POST', 
    headers: getHeaders(),
    body: form 
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Upload failed');
  }
  return res.json();
}

export function createWebSocket(onMessage, onOpen, onClose) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const token = localStorage.getItem('token');
  const wsUrl = `${protocol}//${window.location.host}/ws${token ? `?token=${token}` : ''}`;
  const ws = new WebSocket(wsUrl);
  ws.onopen = () => onOpen?.();
  ws.onclose = () => onClose?.();
  ws.onerror = () => onClose?.();
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onMessage?.(data);
    } catch { /* ignore */ }
  };
  return ws;
}
