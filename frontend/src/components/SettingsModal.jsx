import { useState, useEffect, useCallback } from 'react';
import { X, FolderOpen, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';

export default function SettingsModal({ isOpen, onClose, apiBaseUrl, onScanComplete }) {
  const [sourceLoc, setSourceLoc] = useState('');
  const [outputLoc, setOutputLoc] = useState('');
  const [defaultTranscodeTarget, setDefaultTranscodeTarget] = useState('original');
  const [isOutputLocCustomized, setIsOutputLocCustomized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState(null);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/config`);
      const data = await response.json();
      setSourceLoc(data.source_loc || '');
      setOutputLoc(data.output_loc || '');
      setDefaultTranscodeTarget(data.default_transcode_target || 'original');
      if (data.output_loc && data.source_loc && data.output_loc !== `${data.source_loc}/streamable`) {
        setIsOutputLocCustomized(true);
      }
    } catch (err) {
      console.error('Error fetching config:', err);
      setMessage({ type: 'error', text: 'Failed to load configuration.' });
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchConfig();
    }
  }, [isOpen, fetchConfig]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          source_loc: sourceLoc,
          output_loc: outputLoc,
          default_transcode_target: defaultTranscodeTarget
        }),
      });
      const data = await response.json();
      if (response.ok) {
        setMessage({ type: 'success', text: 'Settings saved successfully.' });
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to save settings.' });
      }
    } catch (err) {
      console.error('Error saving settings:', err);
      setMessage({ type: 'error', text: 'Network error occurred while saving.' });
    } finally {
      setSaving(false);
    }
  };

  const handleScan = async () => {
    setScanning(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/scan`, {
        method: 'POST',
      });
      const data = await response.json();
      if (response.ok) {
        setMessage({
          type: 'success',
          text: `Scan finished! Added ${data.new_videos_added} new video(s) to the queue.`
        });
        if (onScanComplete) {
          onScanComplete();
        }
      } else {
        setMessage({ type: 'error', text: data.error || 'Failed to scan directory.' });
      }
    } catch (err) {
      console.error('Error scanning directory:', err);
      setMessage({ type: 'error', text: 'Network error occurred during scan.' });
    } finally {
      setScanning(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <button className="modal-close" onClick={onClose}>
          <X size={20} />
        </button>
        <h3 className="modal-title">Settings</h3>

        {message && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '12px 16px',
              borderRadius: '4px',
              fontSize: '14px',
              marginBottom: '20px',
              backgroundColor: message.type === 'error' ? 'rgba(225, 9, 20, 0.15)' : 'rgba(74, 222, 128, 0.15)',
              border: `1px solid ${message.type === 'error' ? 'rgba(225, 9, 20, 0.3)' : 'rgba(74, 222, 128, 0.3)'}`,
              color: message.type === 'error' ? '#ff4a53' : '#4ade80',
            }}
          >
            {message.type === 'error' ? <AlertCircle size={18} /> : <CheckCircle size={18} />}
            <span>{message.text}</span>
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-sub)' }}>
            Loading configuration...
          </div>
        ) : (
          <form onSubmit={handleSave}>
            <div className="form-group">
              <label className="form-label" htmlFor="source-loc">
                Original Videos Source Path
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="source-loc"
                  type="text"
                  className="form-input"
                  placeholder="e.g. /Users/username/Videos"
                  value={sourceLoc}
                  onChange={(e) => {
                    const newSource = e.target.value;
                    setSourceLoc(newSource);
                    if (!isOutputLocCustomized) {
                      setOutputLoc(newSource ? `${newSource}/streamable` : '');
                    }
                  }}
                  style={{ paddingLeft: '40px' }}
                  required
                />
                <FolderOpen
                  size={16}
                  style={{
                    position: 'absolute',
                    left: '14px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: 'var(--text-muted)'
                  }}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="output-loc">
                Transcoded Videos Save Path
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="output-loc"
                  type="text"
                  className="form-input"
                  placeholder="e.g. /Users/username/Videos/streamable"
                  value={outputLoc}
                  onChange={(e) => {
                    setOutputLoc(e.target.value);
                    setIsOutputLocCustomized(true);
                  }}
                  style={{ paddingLeft: '40px' }}
                  required
                />
                <FolderOpen
                  size={16}
                  style={{
                    position: 'absolute',
                    left: '14px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: 'var(--text-muted)'
                  }}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="default-quality">
                Default Transcode Quality
              </label>
              <select
                id="default-quality"
                className="form-input"
                value={defaultTranscodeTarget}
                onChange={(e) => setDefaultTranscodeTarget(e.target.value)}
                style={{
                  backgroundColor: '#1f1f1f',
                  border: '1px solid #333',
                  color: '#fff',
                  padding: '10px 14px',
                  borderRadius: '4px',
                  fontSize: '14px',
                  cursor: 'pointer',
                  width: '100%',
                  outline: 'none'
                }}
              >
                <option value="original">Original (Streamable As Is)</option>
                <option value="1080p">1080p Full HD</option>
                <option value="720p">720p HD</option>
                <option value="480p">480p SD</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={saving}>
                {saving ? 'Saving...' : 'Save Settings'}
              </button>
              
              <button
                type="button"
                className="btn btn-secondary"
                style={{ width: '100%' }}
                onClick={handleScan}
                disabled={scanning || !sourceLoc}
              >
                <RefreshCw size={16} className={scanning ? 'spin' : ''} />
                {scanning ? 'Scanning...' : 'Scan Directory'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
