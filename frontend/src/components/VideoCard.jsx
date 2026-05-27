import { useState, useRef } from 'react';
import { Play } from 'lucide-react';

export default function VideoCard({ video, onPlay, onSelectRow }) {
  const [hovered, setHovered] = useState(false);
  const hoverTimeout = useRef(null);
  const videoRef = useRef(null);

  const handleMouseEnter = () => {
    setHovered(true);
    if (video.status === 'completed' && video.preview_url) {
      // Small delay before starting video playback to avoid jarring jumps on swipe-over
      hoverTimeout.current = setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.play().catch(() => {});
        }
      }, 400);
    }
  };

  const handleMouseLeave = () => {
    setHovered(false);
    if (hoverTimeout.current) {
      clearTimeout(hoverTimeout.current);
    }
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = 0;
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const sStr = s < 10 ? `0${s}` : s;
    if (h > 0) {
      const mStr = m < 10 ? `0${m}` : m;
      return `${h}:${mStr}:${sStr}`;
    }
    return `${m}:${sStr}`;
  };

  const isCompleted = video.status === 'completed';

  const handleClick = () => {
    if (isCompleted) {
      onPlay(video);
    } else if (onSelectRow) {
      onSelectRow();
    }
  };

  return (
    <div
      className="video-card"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      {/* Thumbnail */}
      {isCompleted ? (
        <img
          src={video.thumbnail_url}
          alt={video.title}
          className="video-card-thumb"
          loading="lazy"
        />
      ) : (
        <div
          style={{
            width: '100%',
            height: '100%',
            backgroundColor: '#262626',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-sub)',
            fontSize: '13px',
            textAlign: 'center',
            padding: '16px'
          }}
        >
          <span>{video.title}</span>
        </div>
      )}

      {/* Hover Silent Preview Video */}
      {isCompleted && video.preview_url && hovered && (
        <video
          ref={videoRef}
          src={video.preview_url}
          className="video-card-preview"
          muted
          loop
          playsInline
        />
      )}

      {/* Processing Status Badges */}
      {!isCompleted && (
        <span className={`video-card-status-badge status-${video.status}`}>
          {video.status}
        </span>
      )}

      {video.status === 'processing' && (
        <div
          className="processing-progress-bar"
          style={{ width: `${video.progress}%` }}
        />
      )}

      {/* Overlay details */}
      <div className="video-card-overlay">
        <h4 className="video-card-title">{video.title}</h4>
        <div className="video-card-meta">
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            {isCompleted && <Play size={10} fill="currentColor" />}
            {isCompleted ? 'Play' : video.status}
          </span>
          {isCompleted && <span>{formatDuration(video.duration)}</span>}
        </div>
      </div>
    </div>
  );
}
