import React, { useState, useEffect } from 'react';
import { Save, Key, Cpu, ShieldCheck, Mail, User } from 'lucide-react';

const MODELS = [
  { id: 'gpt-4o', name: 'OpenAI GPT-4o (Recommended)', provider: 'openai' },
  { id: 'gpt-4o-mini', name: 'OpenAI GPT-4o Mini (Fast/Cheap)', provider: 'openai' },
  { id: 'gemini-flash-latest', name: 'Google Gemini Flash Latest (Truly Free)', provider: 'gemini' },
  { id: 'gemini-2.0-flash', name: 'Google Gemini 2.0 Flash', provider: 'gemini' },
  { id: 'gemini-2.5-flash', name: 'Google Gemini 2.5 Flash', provider: 'gemini' },
  { id: 'gemini-3-flash-preview', name: 'Google Gemini 3.0 Flash (Next Gen)', provider: 'gemini' },
];

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [settings, setSettings] = useState({
    openai_api_key: '',
    gemini_api_key: '',
    preferred_model: 'gpt-4o',
    name: '',
    email: '',
  });

  useEffect(() => {
    fetch('/api/user/settings', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
      .then(res => res.json())
      .then(data => {
        setSettings(data);
        setLoading(false);
      })
      .catch(err => console.error('Failed to load settings', err));
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch('/api/user/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        setMessage({ type: 'success', text: 'Settings saved successfully!' });
      } else {
        throw new Error('Failed to save');
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Error saving settings' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="loading-state">Loading settings...</div>;

  return (
    <div className="page-container fade-in">
      <header className="page-header">
        <div className="header-text">
          <h2>AI & Account Settings</h2>
          <p>Configure your personal API keys and model preferences</p>
        </div>
      </header>

      <form className="settings-form" onSubmit={handleSave}>
        <div className="settings-grid">
          {/* Account Section */}
          <section className="settings-section glass">
            <div className="section-header">
              <User size={20} className="section-icon" />
              <h3>Profile Information</h3>
            </div>
            <div className="form-group">
              <label>Full Name</label>
              <div className="input-with-icon">
                <User size={16} />
                <input
                  type="text"
                  value={settings.name || ''}
                  onChange={e => setSettings({ ...settings, name: e.target.value })}
                  placeholder="Your Name"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Email Address</label>
              <div className="input-with-icon">
                <Mail size={16} />
                <input type="email" value={settings.email || ''} readOnly disabled />
              </div>
              <small className="help-text">Email cannot be changed for OAuth accounts</small>
            </div>
          </section>

          {/* AI Model Section */}
          <section className="settings-section glass">
            <div className="section-header">
              <Cpu size={20} className="section-icon" />
              <h3>LLM Configuration</h3>
            </div>
            <div className="form-group">
              <label>Preferred AI Model</label>
              <select
                value={settings.preferred_model}
                onChange={e => setSettings({ ...settings, preferred_model: e.target.value })}
              >
                {MODELS.map(m => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>OpenAI API Key</label>
              <div className="input-with-icon">
                <Key size={16} />
                <input
                  type="password"
                  value={settings.openai_api_key || ''}
                  onChange={e => setSettings({ ...settings, openai_api_key: e.target.value })}
                  placeholder="sk-..."
                />
              </div>
            </div>
            <div className="form-group">
              <label>Google Gemini API Key</label>
              <div className="input-with-icon">
                <Key size={16} />
                <input
                  type="password"
                  value={settings.gemini_api_key || ''}
                  onChange={e => setSettings({ ...settings, gemini_api_key: e.target.value })}
                  placeholder="AIza..."
                />
              </div>
            </div>
          </section>
        </div>

        <div className="settings-footer glass">
          <div className="security-note">
            <ShieldCheck size={16} />
            <span>Your keys are encrypted and stored securely.</span>
          </div>
          
          {message && (
            <div className={`form-message ${message.type}`}>
              {message.text}
            </div>
          )}

          <button type="submit" className="save-btn" disabled={saving}>
            {saving ? 'Saving...' : (
              <>
                <Save size={18} />
                <span>Save Changes</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
