import { Play, Info, Settings, AlertCircle } from 'lucide-react';
import VideoCard from './VideoCard';

export default function Dashboard({ videos, onPlay, onOpenSettings, onSwitchTab }) {
  const completedVideos = videos.filter((v) => v.status === 'completed');
  const transcodingVideos = videos.filter((v) => v.status !== 'completed');

  // Featured video for Hero Section
  const featuredVideo = completedVideos.length > 0 ? completedVideos[0] : null;

  return (
    <div style={{ paddingTop: 'var(--navbar-height)', paddingBottom: '80px' }}>
      {/* Hero Banner */}
      {featuredVideo ? (
        <div className="hero-banner">
          <video
            src={featuredVideo.preview_url}
            className="hero-video-bg"
            autoPlay
            muted
            loop
            playsInline
          />
          <div className="hero-overlay" />
          <div className="hero-content">
            <h1 className="hero-title">{featuredVideo.title}</h1>
            <p className="hero-desc">
              Watch this video in full high-definition adaptive HLS streams. Transcoded with custom profiles,
              complete with interactive scrubber previews, multiple quality channels, and responsive playback speeds.
            </p>
            <div className="hero-btn-row">
              <button className="btn btn-primary" onClick={() => onPlay(featuredVideo)}>
                <Play size={18} fill="currentColor" />
                Play
              </button>
              <button className="btn btn-secondary" onClick={() => onSwitchTab('queue')}>
                <Info size={18} />
                Transcode Info
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div
          className="hero-banner"
          style={{
            background: 'linear-gradient(135deg, #090909 0%, #1a1a1a 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '50vh',
            textAlign: 'center',
          }}
        >
          <div className="hero-content" style={{ alignItems: 'center', margin: '0 auto', maxWidth: '500px' }}>
            <h1 className="hero-title" style={{ fontSize: '36px', color: 'var(--accent-red)' }}>
              Netflix Clone
            </h1>
            <p className="hero-desc">
              Welcome to the HLS video streaming platform. Start by configuring your video source directory in settings,
              and scan for videos to begin transcoding.
            </p>
            <div className="hero-btn-row">
              <button className="btn btn-primary" onClick={onOpenSettings}>
                <Settings size={18} />
                Configure Source Loc
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Browse Rows */}
      <div className="container">
        {/* Currently Transcoding Row */}
        {transcodingVideos.length > 0 && (
          <div className="video-row-section">
            <h3 className="row-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              Currently Transcoding
              <span
                style={{
                  fontSize: '11px',
                  background: 'rgba(0,113,235,0.2)',
                  color: '#0071eb',
                  padding: '3px 8px',
                  borderRadius: '12px',
                  fontWeight: 600,
                }}
              >
                {transcodingVideos.length} Video(s)
              </span>
            </h3>
            <div className="video-grid">
              {transcodingVideos.map((video) => (
                <VideoCard
                  key={video.id}
                  video={video}
                  onPlay={onPlay}
                  onSelectRow={() => onSwitchTab('queue')}
                />
              ))}
            </div>
          </div>
        )}

        {/* Completed Videos Row */}
        <div className="video-row-section" style={{ marginTop: '20px' }}>
          <h3 className="row-title">Watch Videos</h3>
          {completedVideos.length > 0 ? (
            <div className="video-grid">
              {completedVideos.map((video) => (
                <VideoCard key={video.id} video={video} onPlay={onPlay} />
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <AlertCircle size={40} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
              <h4 className="empty-state-title">No transcode streams ready</h4>
              <p className="empty-state-desc">
                We couldn't find any completed HLS video streams. Check the Transcoding Queue tab or click Scan in settings
                to build them.
              </p>
              <button className="btn btn-secondary" onClick={onOpenSettings}>
                Scan Directory
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
