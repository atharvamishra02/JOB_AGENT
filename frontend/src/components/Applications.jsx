import { useEffect, useState } from 'react';
import { FileText, RefreshCw } from 'lucide-react';
import { fetchApplications } from '../api';

const STATUS_MAP = {
  applied: 'success', success: 'success',
  skipped: 'warning',
  failed: 'danger',
  ask_user: 'info', pending: 'info',
  duplicate: 'muted',
};

export default function Applications({ toast }) {
  const [apps, setApps] = useState([]);

  const load = () => {
    fetchApplications()
      .then(d => setApps(d.applications || []))
      .catch(() => toast?.('Failed to load applications', 'error'));
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="card">
      <div className="card-header">
        <h3>Application History ({apps.length})</h3>
        <button className="btn btn-ghost btn-sm" onClick={load}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {apps.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Company</th>
                  <th>Score</th>
                  <th>Decision</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {apps.map((a, i) => (
                  <tr key={a.id || i}>
                    <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{a.title}</td>
                    <td>{a.company}</td>
                    <td>
                      <div className="score-bar-wrap">
                        <div className="score-bar">
                          <div
                            className="score-fill"
                            style={{
                              width: `${a.match_score || 0}%`,
                              background: a.match_score >= 75 ? 'var(--success)' : a.match_score >= 50 ? 'var(--warning)' : 'var(--danger)',
                            }}
                          />
                        </div>
                        <span className="score-val">{a.match_score?.toFixed(0) || 0}</span>
                      </div>
                    </td>
                    <td><span className="badge badge-muted">{a.decision || '-'}</span></td>
                    <td><span className={`badge badge-${STATUS_MAP[a.status] || 'muted'}`}>{a.status}</span></td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {a.created_at ? new Date(a.created_at).toLocaleDateString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <FileText size={40} strokeWidth={1.2} />
            <p>No applications recorded yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}
