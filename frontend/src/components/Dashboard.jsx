import { useEffect, useState } from 'react';
import { Briefcase, CheckCircle, XCircle, TrendingUp, Target } from 'lucide-react';
import { fetchDashboard } from '../api';

const PIPELINE_STEPS = [
  { key: 'resume_parser', label: 'Resume Parser' },
  { key: 'job_discovery', label: 'Job Discovery' },
  { key: 'matcher', label: 'Matcher' },
  { key: 'decision', label: 'Decision' },
  { key: 'ats_optimizer', label: 'ATS Optimizer' },
  { key: 'apply_agent', label: 'Deep Apply' },
  { key: 'tracker', label: 'Tracker' },
];

const STEP_ORDER = PIPELINE_STEPS.map(s => s.key);

function getStepState(stepKey, currentStep, completed) {
  if (completed) return 'done';
  const ci = STEP_ORDER.indexOf(currentStep);
  const si = STEP_ORDER.indexOf(stepKey);
  if (ci < 0) return 'idle';
  if (si < ci) return 'done';
  if (si === ci) return 'active';
  return 'idle';
}

export default function Dashboard({ wfStatus, toast }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetchDashboard().then(setData).catch(() => toast?.('Failed to load dashboard', 'error'));
    const iv = setInterval(() => fetchDashboard().then(setData).catch(() => {}), 8000);
    return () => clearInterval(iv);
  }, []);

  const d = data || {};
  const step = wfStatus?.current_step || '';
  const done = wfStatus?.completed || false;

  return (
    <>
      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-icon"><Briefcase size={22} /></div>
          <div><span className="stat-value">{d.total_jobs || 0}</span><span className="stat-label">Total Jobs</span></div>
        </div>
        <div className="stat-card success">
          <div className="stat-icon"><CheckCircle size={22} /></div>
          <div><span className="stat-value">{d.applied || 0}</span><span className="stat-label">Applied</span></div>
        </div>
        <div className="stat-card warning">
          <div className="stat-icon"><XCircle size={22} /></div>
          <div><span className="stat-value">{d.skipped || 0}</span><span className="stat-label">Skipped</span></div>
        </div>
        <div className="stat-card info">
          <div className="stat-icon"><Target size={22} /></div>
          <div><span className="stat-value">{d.avg_match_score || 0}</span><span className="stat-label">Avg Score</span></div>
        </div>
        <div className="stat-card danger">
          <div className="stat-icon"><TrendingUp size={22} /></div>
          <div><span className="stat-value">{d.success_rate || 0}%</span><span className="stat-label">Success Rate</span></div>
        </div>
      </div>

      {/* Pipeline */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <h3>Workflow Pipeline</h3>
          <span className={`badge ${wfStatus?.is_running ? 'badge-success' : done ? 'badge-info' : 'badge-muted'}`}>
            {wfStatus?.is_running ? 'Running' : done ? 'Completed' : 'Idle'}
          </span>
        </div>
        <div className="card-body">
          <div className="pipeline">
            {PIPELINE_STEPS.map((s, i) => {
              const state = getStepState(s.key, step, done);
              return (
                <div className="pipe-step" key={s.key}>
                  <div className="pipe-node">
                    <div className={`pipe-dot ${state}`} />
                    <span className={`pipe-label ${state}`}>{s.label}</span>
                  </div>
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div className={`pipe-connector ${state === 'done' ? 'done' : ''}`} />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom grid */}
      <div className="dash-grid">
        {/* Recent Activity */}
        <div className="card">
          <div className="card-header"><h3>Recent Activity</h3></div>
          <div className="card-body">
            {(d.recent_activity?.length > 0) ? d.recent_activity.map((r, i) => (
              <div key={i} className="job-card">
                <div className="job-title">{r.title}</div>
                <div className="job-company">{r.company}</div>
                <div className="job-meta">
                  <span className={`badge badge-${r.status === 'applied' || r.status === 'success' ? 'success' : r.status === 'skipped' ? 'warning' : r.status === 'failed' ? 'danger' : 'muted'}`}>
                    {r.status}
                  </span>
                  <span>Score: {r.match_score?.toFixed(0) || 0}</span>
                </div>
              </div>
            )) : (
              <div className="empty-state">
                <Briefcase size={40} strokeWidth={1.2} />
                <p>No activity yet. Start a workflow to begin.</p>
              </div>
            )}
          </div>
        </div>

        {/* Sources */}
        <div className="card">
          <div className="card-header"><h3>Source Distribution</h3></div>
          <div className="card-body">
            {d.sources && Object.keys(d.sources).length > 0 ? (
              Object.entries(d.sources).map(([name, count]) => {
                const total = Object.values(d.sources).reduce((a, b) => a + b, 0);
                const pct = total ? (count / total * 100) : 0;
                return (
                  <div className="source-item" key={name}>
                    <span className="source-name">{name}</span>
                    <div className="source-bar">
                      <div
                        className={`source-fill ${name.toLowerCase()}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="source-count">{count}</span>
                  </div>
                );
              })
            ) : (
              <div className="empty-state">
                <Target size={40} strokeWidth={1.2} />
                <p>Source data appears after running the workflow.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
