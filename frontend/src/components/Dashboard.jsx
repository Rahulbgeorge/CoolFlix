import { Play, Info, Settings, AlertCircle } from 'lucide-react';
import VideoCard from './VideoCard';
import { useFocusable } from '@noriginmedia/norigin-spatial-navigation';

export default function Dashboard({ videos, onPlay, onOpenSettings, onSwitchTab }) {
  const completedVideos = videos.filter((v) => v.status === 'completed' || v.status === 'not_required');
  const transcodingVideos = videos.filter((v) => v.status !== 'completed' && v.status !== 'not_required');

  // Featured video for Hero Section
  const featuredVideo = completedVideos.length > 0 ? completedVideos[0] : null;

  const { ref: playRef, focused: playFocused } = useFocusable({
    focusKey: 'HERO_PLAY',
    onEnterPress: () => featuredVideo && onPlay(featuredVideo)
  });

  const { ref: infoRef, focused: infoFocused } = useFocusable({
    focusKey: 'HERO_INFO',
    onEnterPress: () => onSwitchTab('queue')
  });

  const { ref: configRef, focused: configFocused } = useFocusable({
    focusKey: 'HERO_CONFIGURE',
    onEnterPress: onOpenSettings
  });

  return (
    <div style={{ paddingTop: 'var(--navbar-height)', paddingBottom: '80px' }}>
      {/* Hero Banner */}
      {featuredVideo ? (
        <div className="hero-banner">
          {featuredVideo.preview_url ? (
            <video
              src={featuredVideo.preview_url}
              className="hero-video-bg"
              autoPlay
              muted
              loop
              playsInline
            />
          ) : (
            <div 
              className="hero-video-bg" 
              style={{ 
                background: 'linear-gradient(135deg, #090909 0%, #1c1c1c 100%)',
                width: '100%',
                height: '100%',
                position: 'absolute',
                top: 0,
                left: 0
              }} 
            />
          )}
          <div className="hero-overlay" />
          <div className="hero-content">
            <h1 className="hero-title">{featuredVideo.cleaned_title || featuredVideo.title}</h1>
            
            {/* Hero metadata badges */}
            <div className="hero-meta-row" style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '12px', 
              fontSize: '14px', 
              color: '#fff', 
              marginTop: '10px',
              marginBottom: '15px',
              fontWeight: '500'
            }}>
              {featuredVideo.year && <span style={{ color: '#a3a3a3' }}>{featuredVideo.year}</span>}
              {featuredVideo.resolution && (
                <span style={{ 
                  border: '1px solid rgba(255,255,255,0.6)', 
                  padding: '1px 6px', 
                  borderRadius: '3px', 
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  fontWeight: 'bold',
                  letterSpacing: '1px'
                }}>
                  {featuredVideo.resolution}
                </span>
              )}
              {featuredVideo.size && <span style={{ color: '#a3a3a3' }}>{featuredVideo.size}</span>}
              {featuredVideo.subtitles && (
                <span style={{ 
                  border: '1px solid rgba(255,255,255,0.6)', 
                  padding: '1px 6px', 
                  borderRadius: '3px', 
                  fontSize: '11px',
                  fontWeight: 'bold',
                  backgroundColor: 'rgba(255,255,255,0.1)'
                }}>
                  SUBTITLES
                </span>
              )}
              {featuredVideo.languages && featuredVideo.languages.length > 0 && (
                <span style={{ color: 'var(--accent-red)', fontWeight: '600' }}>
                  {featuredVideo.languages.join(' • ')}
                </span>
              )}
            </div>

            <p className="hero-desc">
              Watch this video in full high-definition adaptive HLS streams. Transcoded with custom profiles,
              complete with interactive scrubber previews, multiple quality channels, and responsive playback speeds.
            </p>
            <div className="hero-btn-row">
              <button
                ref={playRef}
                className={`btn btn-primary focusable ${playFocused ? 'nav-focused' : ''}`}
                onClick={() => onPlay(featuredVideo)}
              >
                <Play size={18} fill="currentColor" />
                Play
              </button>
              <button
                ref={infoRef}
                className={`btn btn-secondary focusable ${infoFocused ? 'nav-focused' : ''}`}
                onClick={() => onSwitchTab('queue')}
              >
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
              <button
                ref={configRef}
                className={`btn btn-primary focusable ${configFocused ? 'nav-focused' : ''}`}
                onClick={onOpenSettings}
              >
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
