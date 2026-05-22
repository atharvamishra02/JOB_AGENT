import { useEffect, useRef } from 'react';

export default function Logs({ logs, setLogs }) {
  const termRef = useRef();
  const autoScroll = useRef(true);

  useEffect(() => {
    if (autoScroll.current && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [logs]);

  const getLevel = (log) => {
    const msg = (log.message || '').toLowerCase();
    if (msg.includes('❌') || msg.includes('error') || log.level === 'error') return 'error';
    if (msg.includes('✅') || msg.includes('success') || log.level === 'success') return 'success';
    if (msg.includes('⚠') || msg.includes('warning') || log.level === 'warning') return 'warning';
    return '';
  };

  const formatTime = (ts) => {
    if (!ts) return '--:--:--';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-US', { hour12: false });
    } catch { return '--:--:--'; }
  };

  return (
    <div className="card" style={{ height: 'calc(100vh - 160px)' }}>
      <div className="card-header">
        <h3>Live Execution Logs ({logs.length})</h3>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
            <input
              type="checkbox"
              defaultChecked
              onChange={e => autoScroll.current = e.target.checked}
              style={{ accentColor: 'var(--accent)' }}
            />
            Auto-scroll
          </label>
          <button className="btn btn-ghost btn-sm" onClick={() => setLogs([])}>Clear</button>
        </div>
      </div>
      <div className="log-terminal" ref={termRef} style={{ height: 'calc(100% - 60px)', maxHeight: 'none' }}>
        {logs.length > 0 ? logs.map((log, i) => (
          <div key={log.id || i} className={`log-line ${getLevel(log)}`}>
            <span className="log-time">{formatTime(log.timestamp)}</span>
            <span className="log-msg">{log.message}</span>
          </div>
        )) : (
          <div className="log-line">
            <span className="log-time">--:--:--</span>
            <span className="log-msg" style={{ color: 'var(--text-muted)' }}>Waiting for workflow execution...</span>
          </div>
        )}
      </div>
    </div>
  );
}
