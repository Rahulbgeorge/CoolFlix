import { useState, useEffect, useRef, useCallback } from 'react';
import Hls from 'hls.js';
import {
  Play, Pause, RotateCcw, RotateCw, Volume2, VolumeX,
  Maximize, Minimize, ArrowLeft, Gauge, Activity,
  RefreshCw, AlertCircle, Globe, Scissors, Trash2
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
  const [showLanguageMenu, setShowLanguageMenu] = useState(false);
  
  // Audio tracks state
  const [audioTracks, setAudioTracks] = useState([]);
  const [currentAudioTrackIdx, setCurrentAudioTrackIdx] = useState(-1);
  
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

  // Edit mode and clips state
  const [isEditMode, setIsEditMode] = useState(false);
  const [clips, setClips] = useState([]);
  const [categories, setCategories] = useState([]);
  const [clipName, setClipName] = useState('');
  const [clipCategory, setClipCategory] = useState('');
  const [clipStart, setClipStart] = useState(0);
  const [clipEnd, setClipEnd] = useState(0);
  const [saveError, setSaveError] = useState('');
  const [thumbCacheBust, setThumbCacheBust] = useState(Date.now());

  const fetchClips = useCallback(async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/${videoId}/clips`);
      if (response.ok) {
        const data = await response.json();
        setClips(data.clips || []);
        setCategories(data.categories || []);
      }
    } catch (err) {
      console.error('Failed to fetch clips:', err);
    }
  }, [apiBaseUrl, videoId]);

  useEffect(() => {
    fetchClips();
  }, [fetchClips]);

  const handleSaveClip = async (e) => {
    e.preventDefault();
    setSaveError('');
    if (!clipName.trim()) {
      setSaveError('Name cannot be empty');
      return;
    }
    if (!clipCategory.trim()) {
      setSaveError('Category cannot be empty');
      return;
    }
    if (clipStart < 0) {
      setSaveError('Start position cannot be negative');
      return;
    }
    if (clipEnd <= clipStart) {
      setSaveError('End position must be greater than start position');
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/${videoId}/clips`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: clipName,
          category: clipCategory,
          start_time: clipStart,
          end_time: clipEnd
        })
      });
      const data = await response.json();
      if (response.ok && data.success) {
        setClipName('');
        setClipStart(0);
        setClipEnd(0);
        fetchClips();
        if (clipCategory.trim() === 'Preview') {
          fetchVideoData();
        }
      } else {
        setSaveError(data.error || 'Failed to save clip');
      }
    } catch (err) {
      console.error('Save clip error:', err);
      setSaveError('Network error');
    }
  };

  const handleDeleteClip = async (clipId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this clip?')) return;
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/clips/${clipId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        fetchClips();
        fetchVideoData();
      } else {
        alert('Failed to delete clip');
      }
    } catch (err) {
      console.error('Delete clip error:', err);
    }
  };

  const handleUploadThumbnail = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/${videoId}/thumbnail`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      if (response.ok && data.success) {
        fetchVideoData();
      } else {
        alert(data.error || 'Failed to upload thumbnail');
      }
    } catch (err) {
      console.error('Error uploading thumbnail:', err);
      alert('Network error while uploading thumbnail.');
    }
  };

  const handleDeleteThumbnail = async () => {
    if (!confirm('Revert to the auto-generated thumbnail from the preview clip?')) return;
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/${videoId}/thumbnail`, {
        method: 'DELETE'
      });
      const data = await response.json();
      if (response.ok && data.success) {
        fetchVideoData();
      } else {
        alert(data.error || 'Failed to delete custom thumbnail');
      }
    } catch (err) {
      console.error('Error deleting thumbnail:', err);
      alert('Network error while deleting thumbnail.');
    }
  };
  
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
      setThumbCacheBust(Date.now());
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
    if (!videoData || !videoRef.current) return;

    const videoElement = videoRef.current;

    const handleLoadedMetadata = () => {
      if (videoElement.audioTracks) {
        const tracks = [];
        for (let i = 0; i < videoElement.audioTracks.length; i++) {
          const track = videoElement.audioTracks[i];
          tracks.push({
            index: i,
            label: track.label || track.language || `Track ${i + 1}`,
            lang: track.language,
            enabled: track.enabled
          });
        }
        setAudioTracks(tracks);
        const activeIdx = tracks.findIndex(t => t.enabled);
        setCurrentAudioTrackIdx(activeIdx !== -1 ? activeIdx : 0);
      }
    };

    const useDirectMp4 = videoData.hls_status !== 'completed';

    if (useDirectMp4) {
      // Direct MP4 streaming via Nginx (original.mp4 symlink served with range request support)
      videoElement.src = videoData.original_file_url;
      videoElement.addEventListener('loadedmetadata', handleLoadedMetadata);
      videoElement.play().catch(() => {});
      
      // TODO Phase 2: When per-track audio files are available (video_eng.mp4, video_tamil.mp4),
      // populate audioTracks with their Nginx URLs and re-enable the language selector.
      // Frontend will switch audio by changing videoElement.src to the selected track's URL.
      
      // Hide qualities selection (single file stream)
      setQualities([]);
      setCurrentQualityIdx(-1);
    } else {
      // Adaptive HLS streaming
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

          // Collect audio tracks
          const tracks = hls.audioTracks.map((track, index) => ({
            index,
            label: track.name || track.lang || `Track ${index + 1}`,
            lang: track.lang
          }));
          setAudioTracks(tracks);
          setCurrentAudioTrackIdx(hls.audioTrack);
          
          // Auto play on load
          videoElement.play().catch(() => {});
        });

        hls.on(Hls.Events.AUDIO_TRACKS_UPDATED, (event, data) => {
          const tracks = data.audioTracks.map((track, index) => ({
            index,
            label: track.name || track.lang || `Track ${index + 1}`,
            lang: track.lang
          }));
          setAudioTracks(tracks);
        });

        hls.on(Hls.Events.AUDIO_TRACK_SWITCHED, (event, data) => {
          setCurrentAudioTrackIdx(data.id);
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
        videoElement.addEventListener('loadedmetadata', handleLoadedMetadata);
        videoElement.play().catch(() => {});
      }
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      videoElement.removeEventListener('loadedmetadata', handleLoadedMetadata);
    };
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
          setShowLanguageMenu(false);
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
      // Ignore keyboard controls if user is typing in any input/textarea
      const targetTag = e.target.tagName.toLowerCase();
      if (targetTag === 'input' || targetTag === 'textarea' || e.target.isContentEditable) {
        return;
      }

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

  const handleAudioTrackChange = (index) => {
    if (hlsRef.current) {
      hlsRef.current.audioTrack = index;
      setCurrentAudioTrackIdx(index);
    } else if (videoRef.current && videoRef.current.audioTracks) {
      for (let i = 0; i < videoRef.current.audioTracks.length; i++) {
        videoRef.current.audioTracks[i].enabled = (i === index);
      }
      setCurrentAudioTrackIdx(index);
    }
    // TODO Phase 2: When per-track audio files exist, switch src to the selected track's Nginx URL:
    // else if (videoData.audio_track_files && videoData.audio_track_files[index]) {
    //   videoElement.src = videoData.audio_track_files[index].url;
    //   videoElement.currentTime = savedTime;
    //   videoElement.play();
    // }
  };

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

  if (!videoData) {
    return (
      <div className="custom-player-container" style={{ display: 'flex', alignItems: 'center', justify: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <RefreshCw size={48} className="spin" style={{ color: 'var(--accent-red)', marginBottom: '16px' }} />
          <h3 style={{ color: '#fff' }}>Loading Video...</h3>
        </div>
      </div>
    );
  }

  return (
    <div className={`custom-player-container ${showControls ? 'show-controls' : ''}`} ref={containerRef} style={{ display: 'flex', flexDirection: 'row' }}>
      <div style={{ flex: 1, position: 'relative', height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
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
                      setShowLanguageMenu(false);
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
                    setShowLanguageMenu(false);
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

              {/* Language Selector — only shown with HLS (multi-track) streaming */}
              {/* TODO Phase 2: Re-enable for per-track audio files (video_eng.mp4 etc.) */}
              {audioTracks.length > 1 && hlsRef.current && (
                <div className="popover-menu-wrapper">
                  <button
                    className="player-btn"
                    onClick={() => {
                      setShowLanguageMenu(!showLanguageMenu);
                      setShowQualityMenu(false);
                      setShowSpeedMenu(false);
                    }}
                    title="Change audio language"
                    style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                  >
                    <Globe size={20} />
                    <span style={{ fontSize: '12px', fontWeight: 'bold' }}>
                      {audioTracks.find((t) => t.index === currentAudioTrackIdx)?.label || 'Audio'}
                    </span>
                  </button>
                  {showLanguageMenu && (
                    <div className="popover-menu" style={{ right: 0, minWidth: '120px' }}>
                      {audioTracks.map((t) => (
                        <button
                          key={t.index}
                          className={`popover-item ${t.index === currentAudioTrackIdx ? 'active' : ''}`}
                          onClick={() => {
                            handleAudioTrackChange(t.index);
                            setShowLanguageMenu(false);
                          }}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Edit Mode Toggle */}
              <button
                className={`player-btn ${isEditMode ? 'active' : ''}`}
                onClick={() => {
                  setIsEditMode(!isEditMode);
                  if (!isEditMode && playing) {
                    togglePlay();
                  }
                }}
                title="Toggle Edit Mode (Clips)"
                style={{ color: isEditMode ? 'var(--accent-red)' : '#fff' }}
              >
                <Scissors size={20} />
              </button>

              {/* Fullscreen */}
              <button className="player-btn" onClick={toggleFullscreen}>
                {fullscreen ? <Minimize size={20} /> : <Maximize size={20} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
      
      {isEditMode && (
        <div className="edit-sidebar">
          <h3>
            <Scissors size={20} />
            Edit Mode
          </h3>

          <form className="edit-form" onSubmit={handleSaveClip}>
            {saveError && <div className="edit-error-msg">{saveError}</div>}
            
            <div className="edit-time-row">
              <span className="edit-time-text">Start: {formatTime(clipStart)}</span>
              <button 
                type="button" 
                className="edit-sidebar-btn" 
                onClick={() => setClipStart(Math.round(currentTime * 10) / 10)}
              >
                Set Start
              </button>
            </div>

            <div className="edit-time-row">
              <span className="edit-time-text">End: {formatTime(clipEnd)}</span>
              <button 
                type="button" 
                className="edit-sidebar-btn" 
                onClick={() => setClipEnd(Math.round(currentTime * 10) / 10)}
              >
                Set End
              </button>
            </div>

            <div className="form-group" style={{ marginBottom: '12px' }}>
              <label className="form-label" style={{ marginBottom: '4px' }}>Clip Name</label>
              <input 
                type="text" 
                className="edit-input" 
                value={clipName} 
                onChange={(e) => setClipName(e.target.value)} 
                placeholder="e.g. Action Scene"
              />
            </div>

            <div className="form-group" style={{ marginBottom: '12px' }}>
              <label className="form-label" style={{ marginBottom: '4px' }}>Category</label>
              <input 
                type="text" 
                className="edit-input" 
                list="existing-categories"
                value={clipCategory} 
                onChange={(e) => setClipCategory(e.target.value)} 
                placeholder="e.g. Action"
              />
              <datalist id="existing-categories">
                {categories.map((cat, idx) => (
                  <option key={idx} value={cat} />
                ))}
              </datalist>
            </div>

            <button type="submit" className="btn btn-primary" style={{ width: '100%', fontSize: '13px', padding: '8px' }}>
              Save Clip
            </button>
          </form>

          <hr style={{ border: '0', borderTop: '1px solid #333', margin: '20px 0' }} />
          
          <div className="thumbnail-section" style={{ marginBottom: '20px' }}>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', color: '#fff' }}>Thumbnail Settings</h4>
            
            {/* Thumbnail Preview */}
            <div className="thumbnail-preview-container" style={{ position: 'relative', width: '100%', height: '110px', backgroundColor: '#1a1a1a', borderRadius: '4px', overflow: 'hidden', marginBottom: '12px', border: '1px solid #333', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {videoData?.thumbnail_url ? (
                <img 
                  src={`${videoData.thumbnail_url}${videoData.thumbnail_url.includes('?') ? '&' : '?'}t=${thumbCacheBust}`} 
                  alt="Video Thumbnail" 
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                />
              ) : (
                <span style={{ color: '#666', fontSize: '12px' }}>No Thumbnail Available</span>
              )}
            </div>
            
            <div style={{ fontSize: '11px', color: 'var(--text-sub)', marginBottom: '12px' }}>
              {videoData?.has_custom_thumbnail ? (
                <span style={{ color: '#4ade80', fontWeight: 'bold' }}>Custom Uploaded Image</span>
              ) : (
                <span>Auto-generated from start of Preview Clip</span>
              )}
            </div>

            {/* Thumbnail Actions */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label 
                className="btn btn-secondary" 
                style={{ width: '100%', fontSize: '12px', padding: '6px 10px', textAlign: 'center', cursor: 'pointer', display: 'block', boxSizing: 'border-box', backgroundColor: '#333', color: '#fff', borderRadius: '4px' }}
              >
                Upload Custom Image
                <input 
                  type="file" 
                  accept="image/png, image/jpeg, image/jpg" 
                  style={{ display: 'none' }} 
                  onChange={handleUploadThumbnail} 
                />
              </label>
              
              {videoData?.has_custom_thumbnail && (
                <button 
                  type="button" 
                  className="btn" 
                  style={{ width: '100%', fontSize: '12px', padding: '6px 10px', backgroundColor: 'var(--accent-red)', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                  onClick={handleDeleteThumbnail}
                >
                  Delete Custom Image
                </button>
              )}
            </div>
          </div>

          <div className="clips-section-title">Saved Clips ({clips.length})</div>
          <div className="clips-list">
            {clips.length === 0 ? (
              <div style={{ color: '#666', fontSize: '13px', textAlign: 'center', padding: '20px 0' }}>
                No clips saved yet.
              </div>
            ) : (
              clips.map((clip) => (
                <div 
                  key={clip.id} 
                  className="clip-item"
                  onClick={() => {
                    if (videoRef.current) {
                      videoRef.current.currentTime = clip.start_time;
                    }
                  }}
                >
                  <div className="clip-item-info">
                    <span className="clip-item-category">{clip.category}</span>
                    <span className="clip-item-title">{clip.name}</span>
                    <span className="clip-item-time">
                      {formatTime(clip.start_time)} - {formatTime(clip.end_time)}
                    </span>
                  </div>
                  <button 
                    className="clip-delete-btn" 
                    onClick={(e) => handleDeleteClip(clip.id, e)}
                    title="Delete clip"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
