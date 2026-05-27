import { useState, useEffect, useRef, useCallback } from 'react';
import Hls from 'hls.js';
import {
  Play, Pause, RotateCcw, RotateCw, Volume2, VolumeX,
  Maximize, Minimize, ArrowLeft, Gauge, Activity,
  RefreshCw, AlertCircle
} from 'lucide-react';

export default function VideoPlayer({ videoId, apiBaseUrl, onClose }) {
  const [videoData, setVideoData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [bufferProgress, setBufferProgress] = useState(0);
  const [showControls, setShowControls] = useState(true);

  // Popover menus state
  const [showQualityMenu, setShowQualityMenu] = useState(false);
  const [showSpeedMenu, setShowSpeedMenu] = useState(false);
  
  // Custom video quality and speed tracking
  const [qualities, setQualities] = useState([]); // [{ index: number, label: string }]
  const [currentQualityIdx, setCurrentQualityIdx] = useState(-1); // -1 = Auto
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);

  // Hover Scrub Tooltip State
  const [scrubTooltip, setScrubTooltip] = useState({
    visible: false,
    x: 0,
    timeText: '',
    spriteStyle: {}
  });

  // Center Play/Pause Flash state
  const [flashIcon, setFlashIcon] = useState(null); // 'play' | 'pause'
  
  const videoRef = useRef(null);
  const containerRef = useRef(null);
  const hlsRef = useRef(null);
  const controlsTimeoutRef = useRef(null);
  const timelineRef = useRef(null);

  const fetchVideoData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/${videoId}`);
      const data = await response.json();
      setVideoData(data);
    } catch (err) {
      console.error('Failed to load video detail', err);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, videoId]);

  // Fetch detailed video metadata
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchVideoData();
    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
      }
      if (controlsTimeoutRef.current) {
        clearTimeout(controlsTimeoutRef.current);
      }
    };
  }, [fetchVideoData]);

  // Initialize HLS
  useEffect(() => {
    if (!videoData || !videoRef.current || videoData.status !== 'completed') return;

    const videoElement = videoRef.current;

    if (Hls.isSupported()) {
      const hls = new Hls({
        maxBufferLength: 30,
        enableWorker: true
      });
      hls.loadSource(videoData.master_playlist_url);
      hls.attachMedia(videoElement);
      hlsRef.current = hls;

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        // Collect HLS streams/resolutions
        const levels = hls.levels.map((level, index) => {
          const height = level.height || (level.attrs && level.attrs.RESOLUTION ? level.attrs.RESOLUTION.split('x')[1] : null);
          return {
            index,
            label: height ? `${height}p` : `Stream ${index + 1}`
          };
        });
        setQualities([{ index: -1, label: 'Auto' }, ...levels]);
        setCurrentQualityIdx(hls.currentLevel);
        
        // Auto play on load
        videoElement.play().catch(() => {});
      });

      hls.on(Hls.Events.LEVEL_SWITCHED, (event, data) => {
        // Keep active level highlight in sync
        if (hls.autoLevelEnabled) {
          setCurrentQualityIdx(-1);
        } else {
          setCurrentQualityIdx(data.level);
        }
      });

      hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              break;
          }
        }
      });
    } else if (videoElement.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari Native Playback
      videoElement.src = videoData.master_playlist_url;
      videoElement.play().catch(() => {});
    }
  }, [videoData]);

  // Controls Visibility Auto-Hide Loop
  useEffect(() => {
    const handleActivity = () => {
      setShowControls(true);
      if (controlsTimeoutRef.current) clearTimeout(controlsTimeoutRef.current);
      
      if (playing) {
        controlsTimeoutRef.current = setTimeout(() => {
          setShowControls(false);
          setShowQualityMenu(false);
          setShowSpeedMenu(false);
        }, 3000);
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener('mousemove', handleActivity);
      container.addEventListener('click', handleActivity);
    }

    return () => {
      if (container) {
        container.removeEventListener('mousemove', handleActivity);
        container.removeEventListener('click', handleActivity);
      }
    };
  }, [playing]);

  // Keyboard controls listener
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!videoRef.current) return;
      
      switch (e.code) {
        case 'Space':
          e.preventDefault();
          togglePlay();
          break;
        case 'ArrowRight':
          e.preventDefault();
          skipTime(10);
          break;
        case 'ArrowLeft':
          e.preventDefault();
          skipTime(-10);
          break;
        case 'ArrowUp':
          e.preventDefault();
          adjustVolume(0.1);
          break;
        case 'ArrowDown':
          e.preventDefault();
          adjustVolume(-0.1);
          break;
        case 'KeyF':
          e.preventDefault();
          toggleFullscreen();
          break;
        case 'Escape':
          if (!fullscreen) {
            onClose();
          }
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullscreen, playing]);

  // Play Pause Toggle
  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused) {
      video.play().catch(() => {});
      setPlaying(true);
      triggerFlash('play');
    } else {
      video.pause();
      setPlaying(false);
      triggerFlash('pause');
    }
  }

  function triggerFlash(action) {
    setFlashIcon(action);
    // Auto reset flash state
    setTimeout(() => setFlashIcon(null), 600);
  }

  function skipTime(amount) {
    if (!videoRef.current) return;
    videoRef.current.currentTime = Math.max(0, Math.min(duration, videoRef.current.currentTime + amount));
  }

  function adjustVolume(amount) {
    const newVolume = Math.max(0, Math.min(1, volume + amount));
    setVolume(newVolume);
    if (videoRef.current) {
      videoRef.current.volume = newVolume;
      videoRef.current.muted = newVolume === 0;
      setMuted(newVolume === 0);
    }
  }

  function handleVolumeChange(e) {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (videoRef.current) {
      videoRef.current.volume = val;
      videoRef.current.muted = val === 0;
      setMuted(val === 0);
    }
  }

  function toggleMute() {
    if (!videoRef.current) return;
    const nextMute = !muted;
    videoRef.current.muted = nextMute;
    setMuted(nextMute);
    if (!nextMute && volume === 0) {
      setVolume(0.5);
      videoRef.current.volume = 0.5;
    }
  }

  function toggleFullscreen() {
    const container = containerRef.current;
    if (!container) return;

    if (!document.fullscreenElement) {
      container.requestFullscreen().then(() => setFullscreen(true)).catch(err => console.error(err));
    } else {
      document.exitFullscreen().then(() => setFullscreen(false));
    }
  }

  // Sync state with HTML5 video element events
  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;
    setCurrentTime(video.currentTime);
    
    // Calculate buffered percentage
    if (video.buffered.length > 0) {
      const bufferedEnd = video.buffered.end(video.buffered.length - 1);
      if (duration > 0) {
        setBufferProgress((bufferedEnd / duration) * 100);
      }
    }
  };

  const handleDurationChange = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  const handleVideoPlay = () => setPlaying(true);
  const handleVideoPause = () => setPlaying(false);

  // Timeline Scrub clicks/drags
  const handleTimelineAction = (e) => {
    const rect = timelineRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const width = rect.width;
    const pct = Math.max(0, Math.min(1, clickX / width));
    
    if (videoRef.current) {
      videoRef.current.currentTime = pct * duration;
      setCurrentTime(pct * duration);
    }
  };

  // Scrubber Hover sprite computation
  const handleTimelineMouseMove = (e) => {
    if (!videoData || !timelineRef.current || duration === 0) return;

    const rect = timelineRef.current.getBoundingClientRect();
    const hoverX = e.clientX - rect.left;
    const width = rect.width;
    const pct = Math.max(0, Math.min(1, hoverX / width));
    const hoverTime = pct * duration;

    // Sprite calculations
    let spriteStyle = {};
    if (videoData.sprite_info && videoData.sprite_url_template) {
      const { interval, columns, rows, width: frameW, height: frameH } = videoData.sprite_info;
      
      const frameIdx = Math.floor(hoverTime / interval);
      const totalFramesPerSheet = columns * rows;
      
      const sheetNumber = Math.floor(frameIdx / totalFramesPerSheet) + 1;
      const offsetIdx = frameIdx % totalFramesPerSheet;
      
      const col = offsetIdx % columns;
      const row = Math.floor(offsetIdx / columns);
      
      // Inject correct sheet number into template
      const paddedSheetNum = String(sheetNumber).padStart(3, '0');
      const spriteUrl = videoData.sprite_url_template.replace('%03d', paddedSheetNum);

      spriteStyle = {
        backgroundImage: `url(${spriteUrl})`,
        backgroundPosition: `-${col * frameW}px -${row * frameH}px`,
        backgroundSize: `${columns * frameW}px ${rows * frameH}px`,
        width: `${frameW}px`,
        height: `${frameH}px`
      };
    }

    setScrubTooltip({
      visible: true,
      x: hoverX,
      timeText: formatTime(hoverTime),
      spriteStyle
    });
  };

  const handleTimelineMouseLeave = () => {
    setScrubTooltip(prev => ({ ...prev, visible: false }));
  };

  const formatTime = (secs) => {
    if (isNaN(secs)) return '00:00';
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    
    const mStr = m < 10 ? `0${m}` : m;
    const sStr = s < 10 ? `0${s}` : s;
    
    if (h > 0) {
      return `${h}:${mStr}:${sStr}`;
    }
    return `${mStr}:${sStr}`;
  };

  // Qualities Switching
  const selectQuality = (index) => {
    if (hlsRef.current) {
      hlsRef.current.currentLevel = index;
      setCurrentQualityIdx(index);
    }
    setShowQualityMenu(false);
  };

  // Speed Switching
  const selectSpeed = (speed) => {
    setPlaybackSpeed(speed);
    if (videoRef.current) {
      videoRef.current.playbackRate = speed;
    }
    setShowSpeedMenu(false);
  };

  if (loading) {
    return (
      <div className="custom-player-container" style={{ display: 'flex', alignItems: 'center', justify: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <RefreshCw size={48} className="spin" style={{ color: 'var(--accent-red)', marginBottom: '16px' }} />
          <h3 style={{ color: '#fff' }}>Loading HLS Engine...</h3>
        </div>
      </div>
    );
  }

  if (!videoData || videoData.status !== 'completed') {
    return (
      <div className="custom-player-container" style={{ display: 'flex', alignItems: 'center', justify: 'center', padding: '40px' }}>
        <div style={{ textAlign: 'center', maxWidth: '400px' }}>
          <AlertCircle size={48} style={{ color: 'var(--accent-red)', marginBottom: '16px' }} />
          <h3 style={{ color: '#fff', marginBottom: '16px' }}>HLS Streams Not Ready</h3>
          <p style={{ color: 'var(--text-sub)', marginBottom: '24px' }}>
            This video is not processed yet or failed to transcode. Please return to the catalog and complete transcoding.
          </p>
          <button className="btn btn-primary" onClick={onClose}>
            Go Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`custom-player-container ${showControls ? 'show-controls' : ''}`} ref={containerRef}>
      {/* HTML5 Video Element */}
      <video
        ref={videoRef}
        className="video-element"
        onClick={togglePlay}
        onTimeUpdate={handleTimeUpdate}
        onDurationChange={handleDurationChange}
        onPlay={handleVideoPlay}
        onPause={handleVideoPause}
      />

      {/* Center Flashing Play/Pause Icons */}
      {flashIcon && (
        <div className={`player-flash-overlay flash`}>
          {flashIcon === 'play' ? <Play size={64} fill="#fff" /> : <Pause size={64} fill="#fff" />}
        </div>
      )}

      {/* Control Overlays */}
      <div className="player-overlay">
        
        {/* Top Header */}
        <div className="player-top-bar">
          <button className="player-back-btn" onClick={onClose}>
            <ArrowLeft size={24} />
          </button>
          <span className="player-video-title">{videoData.title}</span>
        </div>

        {/* Center play controls for quick triggers */}
        <div className="player-center-controls">
          <button className="center-btn" onClick={() => skipTime(-10)} title="Rewind 10s">
            <RotateCcw size={32} />
          </button>
          
          <button className="center-btn center-play-btn" onClick={togglePlay}>
            {playing ? <Pause size={38} fill="#fff" /> : <Play size={38} fill="#fff" style={{ marginLeft: '4px' }} />}
          </button>
          
          <button className="center-btn" onClick={() => skipTime(10)} title="Forward 10s">
            <RotateCw size={32} />
          </button>
        </div>

        {/* Bottom Bar */}
        <div className="player-bottom-bar">
          
          {/* Timeline Scrubber */}
          <div
            className="player-timeline-wrapper"
            ref={timelineRef}
            onClick={handleTimelineAction}
            onMouseMove={handleTimelineMouseMove}
            onMouseLeave={handleTimelineMouseLeave}
          >
            <div className="player-timeline-rail">
              <div className="player-timeline-buffer" style={{ width: `${bufferProgress}%` }} />
              <div className="player-timeline-progress" style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }} />
              <div className="player-timeline-handle" style={{ left: `${duration ? (currentTime / duration) * 100 : 0}%` }} />
            </div>

            {/* Hover Scrub Preview Card */}
            {scrubTooltip.visible && (
              <div className="player-scrub-tooltip" style={{ left: `${scrubTooltip.x}px` }}>
                {scrubTooltip.spriteStyle.backgroundImage && (
                  <div className="tooltip-thumbnail" style={scrubTooltip.spriteStyle} />
                )}
                <span className="tooltip-time">{scrubTooltip.timeText}</span>
              </div>
            )}
          </div>

          {/* Controls Row */}
          <div className="player-controls-row">
            <div className="controls-left">
              {/* Play Pause */}
              <button className="player-btn" onClick={togglePlay}>
                {playing ? <Pause size={20} /> : <Play size={20} />}
              </button>

              {/* Rewind/Forward */}
              <button className="player-btn" onClick={() => skipTime(-10)} title="Rewind 10s">
                <RotateCcw size={20} />
              </button>
              <button className="player-btn" onClick={() => skipTime(10)} title="Forward 10s">
                <RotateCw size={20} />
              </button>

              {/* Volume Slider */}
              <div className="volume-wrapper">
                <button className="player-btn" onClick={toggleMute}>
                  {muted || volume === 0 ? <VolumeX size={20} /> : <Volume2 size={20} />}
                </button>
                <div className={`volume-slider-container ${volume > 0 && !muted ? 'active' : ''}`}>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={muted ? 0 : volume}
                    onChange={handleVolumeChange}
                    className="volume-slider"
                  />
                </div>
              </div>

              {/* Time display */}
              <span className="player-time-display">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>

            <div className="controls-right">
              {/* Quality Selector */}
              {qualities.length > 0 && (
                <div className="popover-menu-wrapper">
                  <button
                    className="player-btn"
                    onClick={() => {
                      setShowQualityMenu(!showQualityMenu);
                      setShowSpeedMenu(false);
                    }}
                    title="Change resolution quality"
                    style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                  >
                    <Activity size={20} />
                    <span style={{ fontSize: '12px', fontWeight: 'bold' }}>
                      {currentQualityIdx === -1
                        ? 'Auto'
                        : qualities.find((q) => q.index === currentQualityIdx)?.label || 'Auto'}
                    </span>
                  </button>
                  {showQualityMenu && (
                    <div className="popover-menu">
                      {qualities.map((q) => (
                        <button
                          key={q.index}
                          className={`popover-item ${
                            q.index === currentQualityIdx ? 'active' : ''
                          }`}
                          onClick={() => selectQuality(q.index)}
                        >
                          {q.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Playback Speed */}
              <div className="popover-menu-wrapper">
                <button
                  className="player-btn"
                  onClick={() => {
                    setShowSpeedMenu(!showSpeedMenu);
                    setShowQualityMenu(false);
                  }}
                  title="Playback speed multiplier"
                  style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                  <Gauge size={20} />
                  <span style={{ fontSize: '12px', fontWeight: 'bold' }}>{playbackSpeed}x</span>
                </button>
                {showSpeedMenu && (
                  <div className="popover-menu" style={{ right: 0, minWidth: '80px' }}>
                    {[0.5, 0.75, 1.0, 1.25, 1.5, 2.0].map((speed) => (
                      <button
                        key={speed}
                        className={`popover-item ${playbackSpeed === speed ? 'active' : ''}`}
                        onClick={() => selectSpeed(speed)}
                      >
                        {speed}x
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Fullscreen */}
              <button className="player-btn" onClick={toggleFullscreen}>
                {fullscreen ? <Minimize size={20} /> : <Maximize size={20} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
