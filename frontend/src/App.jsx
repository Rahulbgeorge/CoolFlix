import { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import Dashboard from './components/Dashboard';
import QueueStatus from './components/QueueStatus';
import SettingsModal from './components/SettingsModal';
import VideoPlayer from './components/VideoPlayer';
import Downloader from './components/Downloader';
import { ConnectionManager } from './utils/connectionManager';
import { ApiInterceptor } from './utils/apiInterceptor';
import { SpatialNavigationManager } from './utils/spatialNavigation';

export default function App() {
  const [currentPath, setCurrentPath] = useState(window.location.pathname);
  const [previousPath, setPreviousPath] = useState('/');
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);

  const [apiBaseUrl, setApiBaseUrl] = useState(
    window.location.port === '5173'
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : window.location.origin
  );

  // Initialize generic HTTP / fetch API interceptor
  useEffect(() => {
    ApiInterceptor.initialize();
  }, []);

  // Initialize Spatial Navigation for Smart TV remote control
  useEffect(() => {
    SpatialNavigationManager.init();
    return () => SpatialNavigationManager.destroy();
  }, []);

  // Auto-focus default element on path/page transition to maintain clean TV focus flow
  useEffect(() => {
    const timeout = setTimeout(() => {
      const focusables = SpatialNavigationManager.getFocusableElements();
      if (focusables.length > 0) {
        const settingsOpen = currentPath === '/settings';
        const playerOpen = currentPath.startsWith('/video/');

        if (settingsOpen) {
          const closeBtn = document.querySelector('.modal-close');
          if (closeBtn) {
            SpatialNavigationManager.focusElement(closeBtn);
            return;
          }
        }
        if (playerOpen) {
          const backBtn = document.querySelector('.player-back-btn');
          if (backBtn) {
            SpatialNavigationManager.focusElement(backBtn);
            return;
          }
        }
        SpatialNavigationManager.focusElement(focusables[0]);
      }
    }, 200);

    return () => clearTimeout(timeout);
  }, [currentPath]);

  // Setup ConnectionManager for local network detection and auto-failover
  useEffect(() => {
    const defaultDomain = window.location.port === '5173'
      ? `${window.location.protocol}//${window.location.hostname}:8000`
      : window.location.origin;

    const manager = new ConnectionManager(defaultDomain, (newUrl) => {
      setApiBaseUrl(newUrl);
    });

    manager.start();
    return () => manager.stop();
  }, []);

  // Sync state with browser popstate events
  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(window.location.pathname);
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = (path) => {
    window.history.pushState({}, '', path);
    setCurrentPath(path);
  };

  // Derive active tab, modal, and video player states dynamically
  let activeTab = 'browse';
  let isSettingsOpen = false;
  let activeVideoId = null;

  if (currentPath === '/queue') {
    activeTab = 'queue';
  } else if (currentPath === '/downloader') {
    activeTab = 'downloader';
  } else if (currentPath === '/settings') {
    isSettingsOpen = true;
  } else if (currentPath.startsWith('/video/')) {
    const match = currentPath.match(/^\/video\/([^\/]+)$/);
    if (match) {
      const slug = match[1];
      const video = videos.find((v) => v.slug === slug);
      if (video) {
        activeVideoId = video.id;
      }
    }
  }

  // Fetch videos from the backend API
  const fetchVideos = useCallback(async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos`);
      if (response.ok) {
        const data = await response.json();
        setVideos(data.videos || []);
      }
    } catch (err) {
      console.error('Failed to fetch videos from backend:', err);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchVideos();
  }, [fetchVideos, activeTab]);

  // Redirect to browse if video path is visited but slug is invalid after load
  useEffect(() => {
    if (!loading && currentPath.startsWith('/video/')) {
      const match = currentPath.match(/^\/video\/([^\/]+)$/);
      if (match) {
        const slug = match[1];
        const video = videos.find((v) => v.slug === slug);
        if (!video) {
          navigate('/');
        }
      }
    }
  }, [loading, currentPath, videos]);

  // Poll for transcoding status in the background if there are pending or processing items and the transcoding page is active
  useEffect(() => {
    if (activeTab !== 'queue') return;

    const hasActiveTranscodes = videos.some(
      (v) => v.status === 'processing' || v.status === 'pending' || v.hls_status === 'processing' || v.hls_status === 'pending'
    );

    if (!hasActiveTranscodes) return;

    const interval = setInterval(() => {
      fetchVideos();
    }, 2000); // Poll every 2 seconds for smooth UI updates

    return () => clearInterval(interval);
  }, [videos, fetchVideos, activeTab]);

  const handleScanComplete = () => {
    fetchVideos();
    navigate('/queue'); // Redirect to queue to watch progress
  };

  return (
    <>
      {activeVideoId !== null ? (
        <VideoPlayer
          videoId={activeVideoId}
          apiBaseUrl={apiBaseUrl}
          onClose={() => {
            navigate(previousPath === '/settings' ? '/' : previousPath);
            fetchVideos(); // Fetch videos again to get latest state
          }}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <Navbar
            activeTab={activeTab}
            onNavigate={(path) => {
              if (path === '/settings') {
                setPreviousPath(window.location.pathname);
              }
              navigate(path);
            }}
          />

          {loading ? (
            <div
              style={{
                flexGrow: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-sub)'
              }}
            >
              Loading content library...
            </div>
          ) : activeTab === 'browse' ? (
            <Dashboard
              videos={videos}
              onPlay={(v) => {
                setPreviousPath(window.location.pathname);
                navigate(`/video/${v.slug}`);
              }}
              onOpenSettings={() => {
                setPreviousPath(window.location.pathname);
                navigate('/settings');
              }}
              onSwitchTab={(tab) => navigate(tab === 'browse' ? '/' : `/${tab}`)}
            />
          ) : activeTab === 'queue' ? (
            <QueueStatus
              videos={videos}
              apiBaseUrl={apiBaseUrl}
              onRetryComplete={fetchVideos}
            />
          ) : (
            <Downloader
              apiBaseUrl={apiBaseUrl}
            />
          )}

          <SettingsModal
            isOpen={isSettingsOpen}
            onClose={() => navigate(previousPath === '/settings' ? '/' : previousPath)}
            apiBaseUrl={apiBaseUrl}
            onScanComplete={handleScanComplete}
          />
        </div>
      )}
    </>
  );
}
