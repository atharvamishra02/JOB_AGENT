import { useEffect, useState } from 'react';
import { Briefcase, ExternalLink, RefreshCw } from 'lucide-react';
import { fetchJobs } from '../api';

function scoreColor(s) {
  if (s >= 75) return 'var(--success)';
  if (s >= 50) return 'var(--warning)';
  return 'var(--danger)';
}

export default function Jobs({ toast }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    fetchJobs()
      .then(d => setJobs(d.jobs || []))
      .catch(() => toast?.('Failed to load jobs', 'error'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="card">
      <div className="card-header">
        <h3>Discovered Jobs ({jobs.length})</h3>
        <button className="btn btn-ghost btn-sm" onClick={load}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      <div className="card-body" style={{ padding: 0 }}>
        {jobs.length > 0 ? jobs.map((job, i) => (
          <div key={job.job_id || i} className="job-card">
            <div className="job-title">{job.title || 'Untitled'}</div>
            <div className="job-company">{job.company || 'Unknown'}</div>
            <div className="job-meta">
              <span className={`badge ${job.source === 'linkedin' ? 'badge-info' : 'badge-success'}`}>
                {job.source || 'unknown'}
              </span>
              <span>📍 {job.location || 'N/A'}</span>
              <span>💰 {job.salary_range || 'Undisclosed'}</span>
              <span>📅 {job.posted_date || 'N/A'}</span>
              {job.url && (
                <a href={job.url} target="_blank" rel="noopener noreferrer" className="job-link">
                  <ExternalLink size={12} style={{ marginRight: 4 }} />
                  View Job
                </a>
              )}
            </div>
          </div>
        )) : (
          <div className="empty-state">
            <Briefcase size={40} strokeWidth={1.2} />
            <p>{loading ? 'Loading...' : 'No jobs discovered yet. Run the workflow to scrape listings.'}</p>
          </div>
        )}
      </div>
    </div>
  );
}
