import { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import Dashboard from './components/Dashboard';
import QueueStatus from './components/QueueStatus';
import SettingsModal from './components/SettingsModal';
import VideoPlayer from './components/VideoPlayer';

const API_BASE_URL = 'http://localhost:8000';

export default function App() {
  const [activeTab, setActiveTab] = useState('browse');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [activeVideoId, setActiveVideoId] = useState(null);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch videos from the backend API
  const fetchVideos = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/videos`);
      if (response.ok) {
        const data = await response.json();
        setVideos(data.videos || []);
      }
    } catch (err) {
      console.error('Failed to fetch videos from backend:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchVideos();
  }, [fetchVideos]);

  // Poll for transcoding status in the background if there are pending or processing items
  useEffect(() => {
    const hasActiveTranscodes = videos.some(
      (v) => v.status === 'processing' || v.status === 'pending'
    );

    if (!hasActiveTranscodes) return;

    const interval = setInterval(() => {
      fetchVideos();
    }, 2000); // Poll every 2 seconds for smooth UI updates

    return () => clearInterval(interval);
  }, [videos, fetchVideos]);

  const handleScanComplete = () => {
    fetchVideos();
    setActiveTab('queue'); // Redirect to queue to watch progress
  };

  return (
    <>
      {activeVideoId !== null ? (
        <VideoPlayer
          videoId={activeVideoId}
          apiBaseUrl={API_BASE_URL}
          onClose={() => {
            setActiveVideoId(null);
            fetchVideos(); // Fetch videos again to get latest state
          }}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <Navbar
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            onOpenSettings={() => setIsSettingsOpen(true)}
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
              onPlay={(v) => setActiveVideoId(v.id)}
              onOpenSettings={() => setIsSettingsOpen(true)}
              onSwitchTab={setActiveTab}
            />
          ) : (
            <QueueStatus
              videos={videos}
              apiBaseUrl={API_BASE_URL}
              onRetryComplete={fetchVideos}
            />
          )}

          <SettingsModal
            isOpen={isSettingsOpen}
            onClose={() => setIsSettingsOpen(false)}
            apiBaseUrl={API_BASE_URL}
            onScanComplete={handleScanComplete}
          />
        </div>
      )}
    </>
  );
}
