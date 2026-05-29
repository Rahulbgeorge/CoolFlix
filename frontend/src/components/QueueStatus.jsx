import { useState } from 'react';
import { RefreshCw, AlertTriangle, FileVideo, CheckCircle2, RotateCcw } from 'lucide-react';

export default function QueueStatus({ videos, apiBaseUrl, onRetryComplete }) {
  const [retryingIds, setRetryingIds] = useState(new Set());
  const [selectedTargets, setSelectedTargets] = useState({});

  const handleRetry = async (video) => {
    const nextRetrying = new Set(retryingIds);
    nextRetrying.add(video.id);
    setRetryingIds(nextRetrying);

    const target = selectedTargets[video.id] || video.transcode_target || 'original';

    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/${video.id}/retry`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ target })
      });
      if (response.ok) {
        if (onRetryComplete) {
          onRetryComplete();
        }
      } else {
        alert('Failed to retry video processing.');
      }
    } catch (err) {
      console.error(err);
      alert('Network error occurred during retry request.');
    } finally {
      const finishRetrying = new Set(retryingIds);
      finishRetrying.delete(video.id);
      setRetryingIds(finishRetrying);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 size={20} style={{ color: '#4ade80' }} />;
      case 'processing':
        return <RefreshCw size={20} style={{ color: '#0071eb' }} className="spin" />;
      case 'failed':
        return <AlertTriangle size={20} style={{ color: 'var(--accent-red)' }} />;
      default:
        return <FileVideo size={20} style={{ color: 'var(--text-muted)' }} />;
    }
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case 'completed': return 'Transcode Complete';
      case 'processing': return 'Transcoding HLS...';
      case 'failed': return 'Transcode Failed';
      case 'pending': return 'In Queue';
      default: return status;
    }
  };

  return (
    <div className="container queue-container">
      <div className="queue-title-row">
        <h2 style={{ fontSize: '28px', color: '#fff' }}>Transcoding Jobs Queue</h2>
      </div>

      {videos.length === 0 ? (
        <div className="empty-state">
          <FileVideo size={48} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
          <h4 className="empty-state-title">No videos found</h4>
          <p className="empty-state-desc">
            The transcoding queue is empty. Click on Settings, configure your source folder, and run a scan to detect video files.
          </p>
        </div>
      ) : (
        <div className="queue-list">
          {videos.map((video) => {
            const isProcessing = video.status === 'processing';
            const isFailed = video.status === 'failed';
            const isRetrying = retryingIds.has(video.id);

            return (
              <div key={video.id} className="queue-item">
                <div className="queue-item-header">
                  <div className="queue-item-info">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {getStatusIcon(video.status)}
                      <h4 className="queue-item-title">{video.title}</h4>
                    </div>
                    <p className="queue-item-path">{video.original_path}</p>
                  </div>
                  
                  <div className="queue-item-status-col">
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: '700',
                        color: video.status === 'completed' ? '#4ade80' : video.status === 'processing' ? '#0071eb' : video.status === 'failed' ? 'var(--accent-red)' : 'var(--text-sub)',
                        textTransform: 'uppercase'
                      }}
                    >
                      {getStatusLabel(video.status)}
                    </span>
                    {(isFailed || video.status === 'completed') && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <select
                          value={selectedTargets[video.id] || video.transcode_target || 'original'}
                          onChange={(e) => setSelectedTargets({ ...selectedTargets, [video.id]: e.target.value })}
                          disabled={isRetrying}
                          style={{
                            padding: '6px 10px',
                            borderRadius: '4px',
                            backgroundColor: '#1a1a1a',
                            color: '#fff',
                            border: '1px solid #333',
                            fontSize: '11px',
                            cursor: 'pointer',
                            outline: 'none'
                          }}
                        >
                          <option value="original">Original (Streamable As Is)</option>
                          <option value="1080p">1080p Full HD</option>
                          <option value="720p">720p HD</option>
                          <option value="480p">480p SD</option>
                        </select>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '6px 12px', fontSize: '11px', gap: '4px' }}
                          onClick={() => handleRetry(video)}
                          disabled={isRetrying}
                        >
                          <RotateCcw size={12} />
                          {isRetrying ? 'Retrying...' : 'Re-transcode'}
                        </button>
                      </div>
                    )}
                    {(video.status === 'processing' || video.status === 'pending') && (
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        Target: {video.transcode_target === 'original' ? 'Original' : video.transcode_target}
                      </span>
                    )}
                  </div>
                </div>

                {/* Progress bar */}
                {(isProcessing || video.status === 'pending' || isFailed) && (
                  <div className="queue-item-progress-wrapper">
                    <div className="queue-item-progress-rail">
                      <div
                        className="queue-item-progress-fill"
                        style={{
                          width: `${video.progress}%`,
                          backgroundColor: isFailed ? 'var(--accent-red)' : '#0071eb'
                        }}
                      />
                    </div>
                    <span className="queue-item-progress-text">{video.progress}%</span>
                  </div>
                )}

                {/* Error message */}
                {isFailed && video.error_message && (
                  <div className="queue-item-error">
                    <strong>Error details:</strong> {video.error_message}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
