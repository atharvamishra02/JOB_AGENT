import { useState, useEffect, useRef } from 'react';
import { Play, Square, Upload, FileText } from 'lucide-react';
import { startWorkflow, stopWorkflow, uploadResume, fetchResumes } from '../api';

export default function Workflow({ wfStatus, setWfStatus, toast }) {
  const [resumes, setResumes] = useState([]);
  const [selected, setSelected] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef();

  useEffect(() => {
    fetchResumes().then(d => {
      setResumes(d.resumes || []);
      if (d.resumes?.length && !selected) setSelected(d.resumes[0].path);
    }).catch(() => {});
  }, []);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const r = await uploadResume(file);
      toast(r.message, 'success');
      const d = await fetchResumes();
      setResumes(d.resumes || []);
      setSelected(r.path);
    } catch (err) {
      toast(err.message, 'error');
    }
    setUploading(false);
  };

  const handleStart = async () => {
    try {
      const r = await startWorkflow(selected);
      toast('Workflow started!', 'success');
      setWfStatus(s => ({ ...s, is_running: true }));
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const handleStop = async () => {
    try {
      await stopWorkflow();
      toast('Stop requested', 'warning');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const running = wfStatus?.is_running;
  const progress = wfStatus?.progress || 0;
  const done = wfStatus?.completed;

  return (
    <>
      {/* Hero */}
      <div className="wf-hero">
        <div className="wf-icon-wrap">
          <div className={`wf-pulse ${running ? 'active' : ''}`} />
          <div className="wf-icon">
            {running ? <Activity size={26} /> : done ? <CheckIcon /> : <Play size={26} />}
          </div>
        </div>
        <div className="wf-info">
          <h3>{running ? 'Workflow Running...' : done ? 'Workflow Complete' : 'Ready to Launch'}</h3>
          <p>{running ? `Step: ${wfStatus.current_step || '...'}` : done ? 'All jobs processed successfully' : 'Select a resume and launch the autonomous pipeline'}</p>
        </div>
        <div className="wf-progress">
          <div className="progress-bar"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
          <span className="progress-text">{progress}%</span>
        </div>
      </div>

      {/* Upload */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><h3>Resume Selection</h3></div>
        <div className="card-body">
          <div className="upload-zone" onClick={() => fileRef.current?.click()}>
            <input ref={fileRef} type="file" accept=".pdf" hidden onChange={handleUpload} />
            <Upload size={36} strokeWidth={1.5} style={{ opacity: 0.4 }} />
            <p>{uploading ? 'Uploading...' : 'Drag & drop your PDF or click to browse'}</p>
            <span className="hint">Supports PDF up to 10MB</span>
          </div>

          {resumes.length > 0 && (
            <div className="resume-list">
              {resumes.map(r => (
                <div
                  key={r.path}
                  className={`resume-item ${selected === r.path ? 'selected' : ''}`}
                  onClick={() => setSelected(r.path)}
                >
                  <FileText size={18} style={{ color: 'var(--accent)' }} />
                  <span className="resume-name">{r.filename}</span>
                  <span className="resume-size">{(r.size / 1024).toFixed(0)} KB</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="card">
        <div className="card-header"><h3>Controls</h3></div>
        <div className="card-body">
          <div className="controls">
            <button className="btn btn-primary btn-lg" onClick={handleStart} disabled={running || !selected}>
              <Play size={18} /> Launch Workflow
            </button>
            <button className="btn btn-danger btn-lg" onClick={handleStop} disabled={!running}>
              <Square size={18} /> Stop
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function CheckIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function Activity({ size }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}
