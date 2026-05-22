import { useEffect, useState } from 'react';
import { User, RefreshCw } from 'lucide-react';
import { fetchResumeData } from '../api';

export default function ResumeView({ toast }) {
  const [data, setData] = useState(null);

  const load = () => {
    fetchResumeData()
      .then(setData)
      .catch(() => toast?.('Failed to load resume data', 'error'));
  };

  useEffect(() => { load(); }, []);

  const resume = data?.resume_data || {};
  const profile = data?.user_profile || {};
  const hasData = resume.skills?.length || resume.experience?.length || resume.summary;

  return (
    <div className="card">
      <div className="card-header">
        <h3>Parsed Resume Data</h3>
        <button className="btn btn-ghost btn-sm" onClick={load}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      <div className="card-body">
        {hasData ? (
          <>
            {/* Profile */}
            <div className="resume-section">
              <h4>Profile</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 24px' }}>
                {profile.name && <div><span className="stat-label">Name</span><br /><strong>{profile.name}</strong></div>}
                {profile.email && <div><span className="stat-label">Email</span><br /><strong>{profile.email}</strong></div>}
                {profile.phone && <div><span className="stat-label">Phone</span><br /><strong>{profile.phone}</strong></div>}
                {profile.location && <div><span className="stat-label">Location</span><br /><strong>{profile.location}</strong></div>}
                {profile.linkedin && <div><span className="stat-label">LinkedIn</span><br /><a href={profile.linkedin} target="_blank" className="job-link">{profile.linkedin}</a></div>}
                {profile.github && <div><span className="stat-label">GitHub</span><br /><a href={profile.github} target="_blank" className="job-link">{profile.github}</a></div>}
              </div>
            </div>

            {/* Summary */}
            {resume.summary && (
              <div className="resume-section">
                <h4>Summary</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.6 }}>{resume.summary}</p>
              </div>
            )}

            {/* Skills */}
            {resume.skills?.length > 0 && (
              <div className="resume-section">
                <h4>Skills ({resume.skills.length})</h4>
                <div className="skill-tags">
                  {resume.skills.map((s, i) => <span key={i} className="skill-tag">{s}</span>)}
                </div>
              </div>
            )}

            {/* Experience */}
            {resume.experience?.length > 0 && (
              <div className="resume-section">
                <h4>Experience</h4>
                {resume.experience.map((exp, i) => (
                  <div key={i} className="exp-item">
                    <div className="exp-title">{exp.title || 'Role'}</div>
                    <div className="exp-company">{exp.company || ''} {exp.dates ? `• ${exp.dates}` : ''}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Education */}
            {resume.education?.length > 0 && (
              <div className="resume-section">
                <h4>Education</h4>
                {resume.education.map((edu, i) => (
                  <div key={i} className="exp-item">
                    <div className="exp-title">{edu.degree || edu.institution || 'Education'}</div>
                    <div className="exp-company">{edu.institution || ''} {edu.year ? `• ${edu.year}` : ''}</div>
                  </div>
                ))}
              </div>
            )}

            {/* YoE */}
            {resume.years_of_experience > 0 && (
              <div className="resume-section">
                <h4>Years of Experience</h4>
                <span className="stat-value" style={{ fontSize: 22 }}>{resume.years_of_experience}</span>
              </div>
            )}
          </>
        ) : (
          <div className="empty-state">
            <User size={40} strokeWidth={1.2} />
            <p>Resume data will appear after the parser agent runs.</p>
          </div>
        )}
      </div>
    </div>
  );
}
