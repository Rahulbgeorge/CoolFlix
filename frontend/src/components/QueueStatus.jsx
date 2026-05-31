import { useState, useEffect } from 'react';
import { RefreshCw, AlertTriangle, FileVideo, CheckCircle2, RotateCcw } from 'lucide-react';

function QueueItem({
  video,
  tracker,
  selectedTargets,
  setSelectedTargets,
  isRetrying,
  handleRetry,
  updateVideoSettings,
  getStatusIcon,
  getStatusLabel
}) {
  const isProcessing = video.status === 'processing';
  const isFailed = video.status === 'failed';

  // Smooth progress interpolation
  const [smoothProgress, setSmoothProgress] = useState(video.progress);

  // Sync state with backend updates directly if not processing
  useEffect(() => {
    if (!isProcessing) {
      setSmoothProgress(video.progress);
    }
  }, [video.progress, isProcessing]);

  // Handle smooth linear interpolation during processing
  useEffect(() => {
    if (!isProcessing || !tracker) {
      return;
    }

    // Set initial progress
    setSmoothProgress((prev) => {
      // If the actual progress has jumped ahead, sync with it immediately
      if (video.progress > prev) {
        return video.progress;
      }
      return prev;
    });

    const intervalTime = 100; // ms
    const timer = setInterval(() => {
      setSmoothProgress((prev) => {
        if (prev >= 100) return 100;

        const now = Date.now();
        const elapsedTotal = (now - tracker.startTime) / 1000;
        const progressTotal = video.progress - tracker.startProgress;
        
        if (progressTotal <= 0 || elapsedTotal <= 0) {
          // Creep forward slowly to indicate active work
          return Math.min(prev + 0.01, video.progress + 0.5);
        }

        const rate = progressTotal / elapsedTotal; // % progress per second
        const increment = rate * (intervalTime / 1000);

        const nextVal = prev + increment;
        
        // Define logical ceiling based on current processing status and HLS settings
        let cap = 100;
        if (video.preview_clip_status === 'processing') {
          cap = 5.0;
        } else if (video.sprite_status === 'processing') {
          const hasPhysicalPreview = ['pending', 'processing', 'completed'].includes(video.preview_status);
          if (hasPhysicalPreview) {
            cap = video.hls_required ? 33.3 : 50.0;
          } else {
            cap = video.hls_required ? 66.7 : 100.0;
          }
        } else if (video.preview_status === 'processing') {
          cap = video.hls_required ? 66.7 : 100.0;
        } else if (video.hls_status === 'processing') {
          cap = 100.0;
        }

        // Allow smooth progress to creep slightly ahead of reported progress to feel responsive,
        // but strictly clamp to the current stage cap, and don't drift more than 4% or 2.5 seconds ahead of backend
        const maxExpectedAdvance = Math.max(4, rate * 2.5);
        const safetyCap = Math.min(cap, video.progress + maxExpectedAdvance);
        
        return Math.min(nextVal, safetyCap);
      });
    }, intervalTime);

    return () => clearInterval(timer);
  }, [video.progress, isProcessing, tracker, video.preview_clip_status, video.sprite_status, video.preview_status, video.hls_status, video.hls_required]);

  // Round smoothProgress to 1 decimal place for displaying
  const displayProgress = isProcessing ? Math.round(smoothProgress * 10) / 10 : video.progress;

  const formatETA = (seconds) => {
    if (seconds === null || seconds === undefined || isNaN(seconds) || seconds === Infinity) return '';
    if (seconds < 60) return ` (~${Math.round(seconds)}s remaining)`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return ` (~${mins}m ${secs}s remaining)`;
  };

  const getDetailedStatusSmooth = (video, progressVal) => {
    if (video.status === 'failed') return 'Transcode failed';
    if (video.status === 'pending') return 'In transcode queue...';
    if (video.status === 'completed') return 'Completed';
    
    // 1. Build the active stages list dynamically based on database state
    const activeStages = [];
    
    // Stage 1: Preview Clip (always exists)
    activeStages.push({
      key: 'preview_clip',
      label: 'Creating preview clip metadata & thumbnail',
      status: video.preview_clip_status,
      startProgress: 0,
      endProgress: 5.0
    });
    
    // Stage 2: Sprite Sheet (always exists)
    const hasPhysicalPreview = ['pending', 'processing', 'completed'].includes(video.preview_status);
    let spriteEnd = 50.0;
    if (hasPhysicalPreview) {
      spriteEnd = video.hls_required ? 33.3 : 50.0;
    } else {
      spriteEnd = video.hls_required ? 66.7 : 100.0;
    }
    activeStages.push({
      key: 'sprite',
      label: 'Generating scrubbing sprite sheet',
      status: video.sprite_status,
      startProgress: 5.0,
      endProgress: spriteEnd
    });
    
    // Stage 3: Physical Preview (optional, exists if not 'not_required')
    if (hasPhysicalPreview) {
      const previewEnd = video.hls_required ? 66.7 : 100.0;
      activeStages.push({
        key: 'preview',
        label: 'Generating physical preview clip',
        status: video.preview_status,
        startProgress: spriteEnd,
        endProgress: previewEnd
      });
    }
    
    // Stage 4: HLS Transcoding (optional, exists if required)
    if (video.hls_required) {
      const hlsStart = hasPhysicalPreview ? 66.7 : spriteEnd;
      activeStages.push({
        key: 'hls',
        label: 'Transcoding HLS segments',
        status: video.hls_status,
        startProgress: hlsStart,
        endProgress: 100.0
      });
    }
    
    const totalStages = activeStages.length;
    
    // 2. Find which stage is currently active
    let activeIndex = activeStages.findIndex(s => s.status === 'processing');
    if (activeIndex === -1) {
      activeIndex = activeStages.findIndex(s => s.status === 'pending');
    }
    if (activeIndex === -1) {
      activeIndex = totalStages - 1;
    }
    
    const currentStage = activeStages[activeIndex];
    
    // 3. Compute stage percentage
    const stageRange = currentStage.endProgress - currentStage.startProgress;
    let stagePercent = 0;
    if (stageRange > 0) {
      stagePercent = Math.min(100, Math.max(0, Math.round(((progressVal - currentStage.startProgress) / stageRange) * 100.0)));
    } else {
      stagePercent = 100;
    }
    
    return `Stage ${activeIndex + 1}/${totalStages}: ${currentStage.label}... (${stagePercent}%)`;
  };

  return (
    <div className="queue-item">
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
            {video.hls_status === 'skipped' && video.status === 'completed' ? 'Sprites & Previews Ready' : getStatusLabel(video.status)}
          </span>
          {(isFailed || video.status === 'completed') && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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
        </div>
      </div>

      {/* Movie-specific configuration settings panel */}
      <div 
        className="queue-item-settings"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '24px',
          padding: '10px 16px',
          backgroundColor: 'rgba(255, 255, 255, 0.02)',
          borderTop: '1px dashed rgba(255, 255, 255, 0.05)',
          borderBottom: '1px dashed rgba(255, 255, 255, 0.05)',
          fontSize: '12px',
          color: 'var(--text-sub)',
          flexWrap: 'wrap',
          marginBottom: '10px'
        }}
      >
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: isProcessing ? 'not-allowed' : 'pointer', userSelect: 'none' }}>
          <input
            type="checkbox"
            checked={video.hls_required}
            disabled={isProcessing}
            onChange={(e) => updateVideoSettings(video.id, { hls_required: e.target.checked })}
            style={{ cursor: isProcessing ? 'not-allowed' : 'pointer' }}
          />
          <span style={{ fontWeight: '500' }}>HLS Adaptive Transcoding Required</span>
        </label>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>Target Quality Profile:</span>
          <select
            value={video.transcode_target || 'original'}
            disabled={isProcessing}
            onChange={(e) => updateVideoSettings(video.id, { transcode_target: e.target.value })}
            style={{
              padding: '4px 8px',
              borderRadius: '4px',
              backgroundColor: '#1a1a1a',
              color: '#fff',
              border: '1px solid #333',
              fontSize: '11px',
              cursor: isProcessing ? 'not-allowed' : 'pointer',
              outline: 'none'
            }}
          >
            <option value="original">Original (Streamable As Is)</option>
            <option value="1080p">1080p Full HD</option>
            <option value="720p">720p HD</option>
            <option value="480p">480p SD</option>
          </select>
        </div>
        
        {video.hls_status === 'skipped' && (
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 'auto', fontStyle: 'italic' }}>
            HLS skipped by configuration (Direct MP4 Streaming enabled)
          </span>
        )}
      </div>

      {/* Progress bar stack (vertical layout container) */}
      {(isProcessing || video.status === 'pending' || video.hls_status === 'pending' || video.hls_status === 'processing' || isFailed) && (
        <div className="queue-item-progress-container" style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
            <span style={{ color: 'var(--text-sub)', fontWeight: '600' }}>
              {getDetailedStatusSmooth(video, displayProgress)}
            </span>
            <span style={{ color: 'var(--text-muted)' }}>
              {formatETA(tracker?.eta)}
            </span>
          </div>
          <div className="queue-item-progress-wrapper">
            <div className="queue-item-progress-rail">
              <div
                className={`queue-item-progress-fill ${isProcessing ? 'active' : ''}`}
                style={{
                  width: `${displayProgress}%`,
                  backgroundColor: isFailed ? 'var(--accent-red)' : '#0071eb'
                }}
              />
            </div>
            <span className="queue-item-progress-text">{displayProgress}%</span>
          </div>
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
}

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

  const updateVideoSettings = async (videoId, settings) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/${videoId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(settings)
      });
      if (response.ok) {
        if (onRetryComplete) {
          onRetryComplete();
        }
      } else {
        alert('Failed to update video settings.');
      }
    } catch (err) {
      console.error(err);
      alert('Network error occurred during settings update.');
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
      case 'processing': return 'Processing Stages...';
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
          {videos.map((video) => (
            <QueueItem
              key={video.id}
              video={video}
              tracker={jobTracker[video.id]}
              selectedTargets={selectedTargets}
              setSelectedTargets={setSelectedTargets}
              isRetrying={retryingIds.has(video.id)}
              handleRetry={handleRetry}
              updateVideoSettings={updateVideoSettings}
              getStatusIcon={getStatusIcon}
              getStatusLabel={getStatusLabel}
            />
          ))}
        </div>
      )}
    </div>
  );
}
