import { useState, useEffect } from 'react';
import { RefreshCw, AlertTriangle, FileVideo, CheckCircle2, RotateCcw } from 'lucide-react';

export default function QueueStatus({ videos, apiBaseUrl, onRetryComplete }) {
  const [retryingIds, setRetryingIds] = useState(new Set());
  const [selectedTargets, setSelectedTargets] = useState({});
  const [jobTracker, setJobTracker] = useState({});

  useEffect(() => {
    setJobTracker((prev) => {
      const next = { ...prev };
      videos.forEach((video) => {
        if (video.status === 'processing') {
          const prevData = prev[video.id];
          const now = Date.now();
          if (!prevData) {
            next[video.id] = {
              startTime: now,
              startProgress: video.progress,
              lastTime: now,
              lastProgress: video.progress,
              eta: null
            };
          } else {
            const elapsedTotal = (now - prevData.startTime) / 1000;
            const progressTotal = video.progress - prevData.startProgress;
            
            // Re-estimate ETA if we have elapsed more than 3 seconds and made some progress
            if (progressTotal > 0.5 && elapsedTotal > 3.0) {
              const percentPerSec = progressTotal / elapsedTotal;
              const remainingPercent = 100 - video.progress;
              const etaSeconds = remainingPercent / percentPerSec;
              next[video.id] = {
                ...prevData,
                lastTime: now,
                lastProgress: video.progress,
                eta: etaSeconds
              };
            }
          }
        } else if (prev[video.id]) {
          delete next[video.id];
        }
      });
      return next;
    });
  }, [videos]);

  const formatETA = (seconds) => {
    if (seconds === null || seconds === undefined || isNaN(seconds) || seconds === Infinity) return '';
    if (seconds < 60) return `(~${Math.round(seconds)}s remaining)`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `(~${mins}m ${secs}s remaining)`;
  };

  const getDetailedStatus = (video) => {
    if (video.status === 'failed') return 'Transcode failed';
    if (video.status === 'pending') return 'In transcode queue...';
    if (video.status === 'completed') return 'Completed';
    
    if (video.hls_status === 'processing' || (video.hls_status === 'pending' && video.status === 'processing')) {
      const hlsPercent = Math.min(100, Math.round((video.progress / 80.0) * 100.0));
      return `Stage 1/3: Transcoding HLS (${hlsPercent}%)`;
    }
    if (video.sprite_status === 'processing' || (video.sprite_status === 'pending' && video.hls_status === 'completed')) {
      return 'Stage 2/3: Generating scrubbing sprite sheet...';
    }
    if (video.preview_status === 'processing' || (video.preview_status === 'pending' && video.sprite_status === 'completed')) {
      return 'Stage 3/3: Generating preview clip & thumbnail...';
    }
    return 'Processing...';
  };

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
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '11px' }}>
                      <span style={{ color: 'var(--text-sub)', fontWeight: '600' }}>
                        {getDetailedStatus(video)}
                      </span>
                      <span style={{ color: 'var(--text-muted)' }}>
                        {formatETA(jobTracker[video.id]?.eta)}
                      </span>
                    </div>
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
