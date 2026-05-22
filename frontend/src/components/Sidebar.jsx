import { LayoutDashboard, Activity, Briefcase, FileText, User, Terminal, LogOut, Cpu, Monitor } from 'lucide-react';

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'workflow', label: 'Workflow', icon: Activity },
  { id: 'jobs', label: 'Jobs', icon: Briefcase },
  { id: 'applications', label: 'Applications', icon: FileText },
  { id: 'resume', label: 'Resume', icon: User },
  { id: 'logs', label: 'Live Logs', icon: Terminal },
  { id: 'browser', label: 'Live Browser', icon: Monitor },
  { id: 'settings', label: 'Settings', icon: Cpu },
];

export default function Sidebar({ page, setPage, connected, wfStatus, user, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        <div className="brand-text">
          <h1>JobAgent</h1>
          <span className="brand-badge">AI Powered</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`nav-item ${page === id ? 'active' : ''}`}
            onClick={() => setPage(id)}
          >
            <Icon size={18} />
            <span>{label}</span>
            {id === 'workflow' && wfStatus?.is_running && (
              <span className="nav-badge">LIVE</span>
            )}
            {id === 'jobs' && wfStatus?.job_count > 0 && (
              <span className="nav-count">{wfStatus.job_count}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        {user && (
          <div className="sidebar-user">
            {user.picture ? (
              <img src={user.picture} alt="" className="sidebar-user-avatar" />
            ) : (
              <div className="sidebar-user-avatar-fallback">
                {(user.name || user.email || '?')[0].toUpperCase()}
              </div>
            )}
            <div className="sidebar-user-info">
              <span className="sidebar-user-name">{user.name || 'User'}</span>
              <span className="sidebar-user-email">{user.email}</span>
            </div>
            <button className="sidebar-logout-btn" onClick={onLogout} title="Sign Out">
              <LogOut size={16} />
            </button>
          </div>
        )}
        <div className="conn-status">
          <div className={`conn-dot ${connected ? 'connected' : ''}`} />
          <span>{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>
    </aside>
  );
}
