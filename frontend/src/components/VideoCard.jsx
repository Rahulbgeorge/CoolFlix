import { useState, useRef } from 'react';
import { Play } from 'lucide-react';

export default function VideoCard({ video, onPlay, onSelectRow }) {
  const [hovered, setHovered] = useState(false);
  const hoverTimeout = useRef(null);
  const videoRef = useRef(null);

  const isPlayable = true;

  const handleMouseEnter = () => {
    setHovered(true);
    if (isPlayable && video.preview_url) {
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

  const handleClick = () => {
    if (isPlayable) {
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
      {video.thumbnail_url ? (
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
          <span>{video.cleaned_title || video.title}</span>
        </div>
      )}

      {/* Hover Silent Preview Video */}
      {isPlayable && video.preview_url && hovered && (
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
      {!isPlayable && (
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
        <h4 className="video-card-title">{video.cleaned_title || video.title}</h4>
        
        {/* Parsed Metadata Badges */}
        <div className="video-card-info" style={{ 
          fontSize: '11px', 
          color: '#e5e5e5', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '8px', 
          flexWrap: 'wrap', 
          marginTop: '4px',
          fontWeight: '500'
        }}>
          {video.year && <span>{video.year}</span>}
          {video.resolution && (
            <span style={{ 
              border: '1px solid rgba(255,255,255,0.4)', 
              padding: '0 4px', 
              borderRadius: '2px', 
              fontSize: '9px',
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}>
              {video.resolution}
            </span>
          )}
          {video.size && <span>{video.size}</span>}
          {video.subtitles && (
            <span style={{ 
              border: '1px solid rgba(255,255,255,0.4)', 
              padding: '0 4px', 
              borderRadius: '2px', 
              fontSize: '9px',
              backgroundColor: 'rgba(255,255,255,0.1)'
            }}>
              SUB
            </span>
          )}
        </div>

        {/* Language tags */}
        {video.languages && video.languages.length > 0 && (
          <div className="video-card-languages" style={{ 
            fontSize: '10.5px', 
            color: 'var(--accent-red)', 
            marginTop: '4px', 
            whiteSpace: 'nowrap', 
            overflow: 'hidden', 
            textOverflow: 'ellipsis' 
          }}>
            {video.languages.join(' • ')}
          </div>
        )}

        <div className="video-card-meta" style={{ marginTop: '6px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            {isPlayable && <Play size={10} fill="currentColor" />}
            {isPlayable ? 'Play' : video.status}
          </span>
          {isPlayable && video.duration > 0 && <span>{formatDuration(video.duration)}</span>}
        </div>
      </div>
    </div>
  );
}
