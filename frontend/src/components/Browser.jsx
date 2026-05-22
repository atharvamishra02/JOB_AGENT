import { Monitor } from 'lucide-react';

export default function Browser() {
  const vncUrl = `${window.location.protocol}//${window.location.host}/vnc/vnc.html?autoconnect=true&resize=scale`;

  return (
    <div className="card" style={{ height: 'calc(100vh - 190px)', padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div className="card-header" style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
          <Monitor size={18} style={{ color: 'var(--accent)' }} /> Live Browser View (NoVNC)
        </h3>
        <p className="hint" style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
          Interact with the autonomous Chrome browser session on the server here. Double-click the VNC screen to enable keyboard input if needed.
        </p>
      </div>
      <div className="card-body" style={{ padding: 0, flexGrow: 1, height: '100%' }}>
        <iframe
          src={vncUrl}
          title="NoVNC Chrome Viewer"
          style={{ width: '100%', height: '100%', border: 'none', background: '#111' }}
          allowFullScreen
        />
      </div>
    </div>
  );
}
