import { useState, useEffect, useRef, useCallback } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import AuthPage from './components/AuthPage';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import Workflow from './components/Workflow';
import Jobs from './components/Jobs';
import Applications from './components/Applications';
import Logs from './components/Logs';
import ResumeView from './components/ResumeView';
import SettingsPage from './pages/SettingsPage';
import { createWebSocket, fetchWorkflowStatus } from './api';

const PAGES = {
  dashboard: { title: 'Dashboard', sub: 'Real-time autonomous job application overview' },
  workflow: { title: 'Workflow', sub: 'Launch and monitor the AI pipeline' },
  jobs: { title: 'Discovered Jobs', sub: 'Jobs scraped from LinkedIn & Naukri' },
  applications: { title: 'Applications', sub: 'Full application history & tracking' },
  resume: { title: 'Resume', sub: 'Parsed resume data & profile' },
  logs: { title: 'Live Logs', sub: 'Real-time execution terminal' },
  settings: { title: 'Settings', sub: 'Manage your API keys and profile' },
};

function AppContent() {
  const { isAuthenticated, loading, user, logout } = useAuth();
  const [page, setPage] = useState('dashboard');
  const [wsConnected, setWsConnected] = useState(false);
  const [wfStatus, setWfStatus] = useState({});
  const [logs, setLogs] = useState([]);
  const [toasts, setToasts] = useState([]);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  const toast = useCallback((msg, type = 'info') => {
    const id = Date.now();
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4000);
  }, []);

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    wsRef.current = createWebSocket(
      (data) => {
        if (data.type === 'init') {
          setWfStatus(data.data || {});
          if (data.logs) setLogs(data.logs);
        } else if (data.type === 'log') {
          setLogs(prev => [...prev, data.data]);
          setWfStatus(s => ({
            ...s,
            progress: data.progress ?? s.progress,
            current_step: data.current_step ?? s.current_step,
            is_running: data.is_running ?? s.is_running,
          }));
        } else if (data.type === 'status') {
          setWfStatus(data.data || {});
        }
      },
      () => {
        setWsConnected(true);
        clearTimeout(reconnectRef.current);
      },
      () => {
        setWsConnected(false);
        reconnectRef.current = setTimeout(connectWs, 3000);
      }
    );
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    connectWs();
    fetchWorkflowStatus().then(setWfStatus).catch(() => {});
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connectWs, isAuthenticated]);

  // Poll status while workflow is running
  useEffect(() => {
    if (!wfStatus.is_running) return;
    const iv = setInterval(() => {
      fetchWorkflowStatus().then(setWfStatus).catch(() => {});
    }, 3000);
    return () => clearInterval(iv);
  }, [wfStatus.is_running]);

  // Show loading spinner
  if (loading) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner-lg" />
        <p>Loading...</p>
      </div>
    );
  }

  // Show auth page if not logged in
  if (!isAuthenticated) {
    return <AuthPage />;
  }

  const info = PAGES[page] || PAGES.dashboard;

  const renderPage = () => {
    switch (page) {
      case 'dashboard': return <Dashboard wfStatus={wfStatus} toast={toast} />;
      case 'workflow': return <Workflow wfStatus={wfStatus} setWfStatus={setWfStatus} toast={toast} />;
      case 'jobs': return <Jobs toast={toast} />;
      case 'applications': return <Applications toast={toast} />;
      case 'resume': return <ResumeView toast={toast} />;
      case 'logs': return <Logs logs={logs} setLogs={setLogs} />;
      case 'settings': return <SettingsPage />;
      default: return <Dashboard wfStatus={wfStatus} toast={toast} />;
    }
  };

  return (
    <div className="app-layout">
      <div className="ambient">
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />
      </div>

      <Sidebar
        page={page}
        setPage={setPage}
        connected={wsConnected}
        wfStatus={wfStatus}
        user={user}
        onLogout={logout}
      />

      <div className="main-content">
        <header className="top-bar">
          <div>
            <h2>{info.title}</h2>
            <p className="top-bar-sub">{info.sub}</p>
          </div>
          <div className="top-bar-actions">
            {user && (
              <div className="user-badge">
                {user.picture ? (
                  <img src={user.picture} alt="" className="user-avatar" />
                ) : (
                  <div className="user-avatar-fallback">
                    {(user.name || user.email || '?')[0].toUpperCase()}
                  </div>
                )}
                <span className="user-name">{user.name || user.email}</span>
              </div>
            )}
            {!wfStatus.is_running && (
              <button className="btn btn-primary" onClick={() => setPage('workflow')}>
                ▶ Start Workflow
              </button>
            )}
            {wfStatus.is_running && (
              <span className="badge badge-success" style={{ fontSize: 13, padding: '6px 14px' }}>
                ● Running
              </span>
            )}
          </div>
        </header>

        <div className="page-content">
          {renderPage()}
        </div>
      </div>

      <div className="toast-box">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>{t.msg}</div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
