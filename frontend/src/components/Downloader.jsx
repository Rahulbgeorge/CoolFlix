import { useState, useEffect } from 'react';
import { Search, Loader2, AlertCircle, CheckCircle, Magnet, Link2, DownloadCloud, Clock, ArrowUp, ArrowDown } from 'lucide-react';

export default function Downloader({ apiBaseUrl }) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // Scraped page results
  const [pageTitle, setPageTitle] = useState('');
  const [magnets, setMagnets] = useState([]);
  
  // Client-side list filter
  const [filterText, setFilterText] = useState('');
  
  // Tracking downloads in progress (mapping magnet_link -> status state)
  // status: 'idle' | 'loading' | 'success' | 'error'
  const [downloadStates, setDownloadStates] = useState({});
  const [downloadErrors, setDownloadErrors] = useState({});
  
  // Active downloads from backend
  const [activeDownloads, setActiveDownloads] = useState([]);
  const [activeDownloadsError, setActiveDownloadsError] = useState('');
  const [deletingStates, setDeletingStates] = useState({});

  useEffect(() => {
    let active = true;
    
    const fetchStatus = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/api/download-status`);
        const data = await response.json();
        if (active) {
          if (response.ok && data.success) {
            setActiveDownloads(data.downloads || []);
            setActiveDownloadsError('');
          } else {
            setActiveDownloadsError(data.error || 'Failed to query active downloads.');
          }
        }
      } catch (err) {
        console.error(err);
        if (active) {
          setActiveDownloadsError('Connection to Transmission daemon failed.');
        }
      }
    };
    
    fetchStatus(); // initial fetch
    const interval = setInterval(fetchStatus, 3000);
    
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [apiBaseUrl]);

  const handleScan = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError('');
    setSuccess('');
    setPageTitle('');
    setMagnets([]);
    setDownloadStates({});
    setDownloadErrors({});

    try {
      const response = await fetch(`${apiBaseUrl}/api/parse-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setPageTitle(data.page_title);
        setMagnets(data.magnets || []);
        if (data.magnets.length === 0) {
          setError('No magnet links found on this page.');
        } else {
          setSuccess(`Successfully parsed ${data.magnets.length} magnet links!`);
        }
      } else {
        setError(data.error || 'Failed to parse the webpage.');
      }
    } catch (err) {
      console.error(err);
      setError('A network error occurred. Please make sure the backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (magnetLink) => {
    // Update state to loading for this specific magnet
    setDownloadStates(prev => ({ ...prev, [magnetLink]: 'loading' }));
    setDownloadErrors(prev => ({ ...prev, [magnetLink]: '' }));

    try {
      const response = await fetch(`${apiBaseUrl}/api/download-magnet`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ magnet_link: magnetLink })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setDownloadStates(prev => ({ ...prev, [magnetLink]: 'success' }));
      } else {
        setDownloadStates(prev => ({ ...prev, [magnetLink]: 'error' }));
        setDownloadErrors(prev => ({ ...prev, [magnetLink]: data.error || 'Failed to trigger download.' }));
      }
    } catch (err) {
      console.error(err);
      setDownloadStates(prev => ({ ...prev, [magnetLink]: 'error' }));
      setDownloadErrors(prev => ({ ...prev, [magnetLink]: 'Network error. Transmission-remote call failed.' }));
    }
  };

  const handleDelete = async (torrentId, deleteFiles) => {
    const actionKey = deleteFiles ? 'deleting' : 'removing';
    setDeletingStates(prev => ({ ...prev, [torrentId]: actionKey }));
    try {
      const response = await fetch(`${apiBaseUrl}/api/delete-torrent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ torrent_id: torrentId, delete_files: deleteFiles })
      });
      const data = await response.json();
      if (response.ok && data.success) {
        setActiveDownloads(prev => prev.filter(dl => dl.id !== torrentId));
      } else {
        alert(data.error || 'Failed to remove torrent.');
      }
    } catch (err) {
      console.error(err);
      alert('Network error. Failed to remove torrent.');
    } finally {
      setDeletingStates(prev => ({ ...prev, [torrentId]: null }));
    }
  };

  // Filter links on the fly
  const filteredMagnets = magnets.filter(m => {
    const searchString = `${m.title} ${m.resolution || ''} ${m.size || ''} ${m.languages.join(' ')}`.toLowerCase();
    return searchString.includes(filterText.toLowerCase());
  });

  return (
    <div className="container" style={{ paddingTop: 'var(--navbar-height)', paddingBottom: '80px', maxWidth: '1000px' }}>
      <div style={{ marginTop: '40px', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '32px', color: '#fff', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Magnet size={32} style={{ color: 'var(--accent-red)' }} />
          Media Torrent Downloader
        </h2>
        <p style={{ color: 'var(--text-sub)', marginTop: '8px', fontSize: '15px', lineHeight: '1.6' }}>
          Input a movie/show details page URL (e.g. from MovieRulz) to extract available torrent links, view metadata, and automatically trigger background downloads directly into your streaming library.
        </p>
      </div>

      {/* URL Input Form */}
      <form onSubmit={handleScan} style={{ 
        background: 'rgba(255,255,255,0.02)', 
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '8px',
        padding: '24px',
        marginBottom: '24px'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <label style={{ fontSize: '13px', fontWeight: 600, color: '#e5e5e5', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Webpage URL to Scrape
          </label>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flexGrow: 1 }}>
              <Link2 size={18} style={{ position: 'absolute', left: '14px', top: '15px', color: 'rgba(255,255,255,0.4)' }} />
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.5movierulz.church/veerabhadrudu-2026-telugu/movie-watch-online-free-6937.html"
                required
                style={{
                  width: '100%',
                  padding: '14px 14px 14px 44px',
                  backgroundColor: 'rgba(0,0,0,0.5)',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '4px',
                  color: '#fff',
                  fontSize: '14px',
                  outline: 'none',
                  transition: 'border-color 0.2s'
                }}
                onFocus={(e) => e.target.style.borderColor = 'var(--accent-red)'}
                onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.15)'}
              />
            </div>
            <button 
              type="submit" 
              className="btn btn-primary"
              disabled={loading}
              style={{ padding: '0 32px', minHeight: '48px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '15px', fontWeight: 600 }}
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="spin" />
                  Parsing page...
                </>
              ) : (
                'Extract Magnets'
              )}
            </button>
          </div>
        </div>
      </form>

      {/* Active Downloads Section */}
      <div style={{ marginBottom: '32px' }}>
        <h3 style={{ fontSize: '20px', color: '#fff', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
          <DownloadCloud size={22} style={{ color: 'var(--accent-red)' }} />
          Active Downloads ({activeDownloads.length})
        </h3>

        {activeDownloadsError ? (
          <div style={{
            background: 'rgba(229, 9, 20, 0.05)',
            border: '1px solid rgba(229, 9, 20, 0.2)',
            borderRadius: '6px',
            padding: '16px',
            color: '#ffa3a3',
            fontSize: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
          }}>
            <AlertCircle size={18} style={{ flexShrink: 0, color: 'var(--accent-red)' }} />
            <div>
              <strong>Transmission Service: </strong> 
              {activeDownloadsError.includes('command not found') ? 
                'Transmission CLI client is not installed on the server (brew install transmission-cli).' : 
                'Cannot connect to Transmission daemon. Ensure transmission-daemon is running.'}
            </div>
          </div>
        ) : activeDownloads.length === 0 ? (
          <div style={{
            background: 'rgba(255,255,255,0.01)',
            border: '1px dotted rgba(255,255,255,0.1)',
            borderRadius: '8px',
            padding: '32px',
            textAlign: 'center',
            color: 'var(--text-sub)'
          }}>
            <p style={{ fontSize: '14px' }}>No active downloads in Transmission.</p>
            <p style={{ fontSize: '12px', marginTop: '4px' }}>Extract magnets below and click Download to start.</p>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: '16px'
          }}>
            {activeDownloads.map((dl) => {
              const donePercent = parseInt(dl.done) || 0;
              const isSeeding = dl.status.toLowerCase().includes('seed');
              const isDownloading = dl.status.toLowerCase().includes('download');
              const isStopped = dl.status.toLowerCase().includes('stop');
              
              let statusColor = '#94a3b8'; // grey
              let statusBg = 'rgba(148, 163, 184, 0.1)';
              if (isDownloading) {
                statusColor = '#38bdf8'; // blue
                statusBg = 'rgba(56, 189, 248, 0.15)';
              } else if (isSeeding) {
                statusColor = '#34d399'; // green
                statusBg = 'rgba(52, 211, 153, 0.15)';
              } else if (isStopped) {
                statusColor = '#fb923c'; // orange
                statusBg = 'rgba(251, 146, 60, 0.15)';
              }

              return (
                <div key={dl.id} style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '8px',
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  cursor: 'default',
                  position: 'relative',
                  overflow: 'hidden'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.3)';
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'none';
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)';
                }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                    <span 
                      style={{ 
                        fontSize: '14px', 
                        color: '#fff', 
                        fontWeight: 600, 
                        whiteSpace: 'nowrap', 
                        overflow: 'hidden', 
                        textOverflow: 'ellipsis',
                        maxWidth: '200px'
                      }}
                      title={dl.name}
                    >
                      {dl.name}
                    </span>
                    <span style={{ 
                      fontSize: '10px', 
                      fontWeight: 700, 
                      color: statusColor, 
                      backgroundColor: statusBg, 
                      padding: '2px 8px', 
                      borderRadius: '4px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px'
                    }}>
                      {dl.status}
                    </span>
                  </div>

                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-sub)' }}>
                      <span>Progress</span>
                      <span style={{ fontWeight: 600, color: '#fff' }}>{dl.done} ({dl.have})</span>
                    </div>
                    
                    {/* Progress Bar */}
                    <div style={{
                      width: '100%',
                      height: '6px',
                      backgroundColor: 'rgba(255,255,255,0.08)',
                      borderRadius: '3px',
                      overflow: 'hidden',
                      marginTop: '6px'
                    }}>
                      <div style={{
                        width: `${donePercent}%`,
                        height: '100%',
                        background: isSeeding ? 
                          'linear-gradient(90deg, #34d399 0%, #059669 100%)' : 
                          'linear-gradient(90deg, #e50914 0%, #ff4d4d 100%)',
                        borderRadius: '3px',
                        transition: 'width 0.4s ease-out'
                      }} />
                    </div>
                  </div>

                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    fontSize: '11px', 
                    color: 'rgba(255,255,255,0.5)',
                    borderTop: '1px solid rgba(255,255,255,0.04)',
                    paddingTop: '8px',
                    marginTop: '4px'
                  }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={12} />
                      {dl.eta}
                    </span>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      {parseFloat(dl.down) > 0 && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#60a5fa' }}>
                          <ArrowDown size={10} />
                          {dl.down}
                        </span>
                      )}
                      {parseFloat(dl.up) > 0 && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#34d399' }}>
                          <ArrowUp size={10} />
                          {dl.up}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Delete Actions Row */}
                  <div style={{
                    display: 'flex',
                    gap: '8px',
                    borderTop: '1px solid rgba(255,255,255,0.06)',
                    paddingTop: '10px',
                    marginTop: '4px'
                  }}>
                    <button
                      onClick={() => handleDelete(dl.id, false)}
                      disabled={deletingStates[dl.id] != null}
                      style={{
                        flex: 1,
                        padding: '6px 0',
                        fontSize: '11px',
                        fontWeight: 600,
                        backgroundColor: 'rgba(255,255,255,0.05)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '4px',
                        color: '#e5e5e5',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '4px',
                        transition: 'background-color 0.2s'
                      }}
                      onMouseEnter={(e) => {
                        if (deletingStates[dl.id] == null) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)';
                      }}
                      onMouseLeave={(e) => {
                        if (deletingStates[dl.id] == null) e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)';
                      }}
                    >
                      {deletingStates[dl.id] === 'removing' ? (
                        <>
                          <Loader2 size={12} className="spin" />
                          Removing...
                        </>
                      ) : (
                        'Remove'
                      )}
                    </button>
                    
                    <button
                      onClick={() => {
                        if (window.confirm(`Are you sure you want to delete this torrent and delete its downloaded data?`)) {
                          handleDelete(dl.id, true);
                        }
                      }}
                      disabled={deletingStates[dl.id] != null}
                      style={{
                        flex: 1,
                        padding: '6px 0',
                        fontSize: '11px',
                        fontWeight: 600,
                        backgroundColor: 'rgba(229, 9, 20, 0.1)',
                        border: '1px solid rgba(229, 9, 20, 0.2)',
                        borderRadius: '4px',
                        color: '#ff8a8a',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '4px',
                        transition: 'background-color 0.2s, border-color 0.2s'
                      }}
                      onMouseEnter={(e) => {
                        if (deletingStates[dl.id] == null) {
                          e.currentTarget.style.backgroundColor = 'rgba(229, 9, 20, 0.25)';
                          e.currentTarget.style.borderColor = 'rgba(229, 9, 20, 0.4)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (deletingStates[dl.id] == null) {
                          e.currentTarget.style.backgroundColor = 'rgba(229, 9, 20, 0.1)';
                          e.currentTarget.style.borderColor = 'rgba(229, 9, 20, 0.2)';
                        }
                      }}
                    >
                      {deletingStates[dl.id] === 'deleting' ? (
                        <>
                          <Loader2 size={12} className="spin" />
                          Deleting...
                        </>
                      ) : (
                        'Delete Data'
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Feedback Messages */}
      {error && (
        <div style={{ 
          background: 'rgba(229, 9, 20, 0.1)', 
          border: '1px solid rgba(229, 9, 20, 0.3)', 
          borderRadius: '4px', 
          padding: '16px', 
          color: '#ff8a8a', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '12px',
          marginBottom: '24px'
        }}>
          <AlertCircle size={20} style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      {success && !error && (
        <div style={{ 
          background: 'rgba(74, 222, 128, 0.1)', 
          border: '1px solid rgba(74, 222, 128, 0.3)', 
          borderRadius: '4px', 
          padding: '16px', 
          color: '#a7f3d0', 
          display: 'flex', 
          alignItems: 'center', 
          gap: '12px',
          marginBottom: '24px'
        }}>
          <CheckCircle size={20} style={{ flexShrink: 0 }} />
          <span>{success}</span>
        </div>
      )}

      {/* Loading Spinner for full page parse */}
      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 0', color: 'var(--text-sub)' }}>
          <Loader2 size={48} className="spin" style={{ color: 'var(--accent-red)', marginBottom: '16px' }} />
          <h4>Fetching webpage and extracting details...</h4>
          <p style={{ fontSize: '13px', marginTop: '6px' }}>This may take a few seconds depending on page load speed.</p>
        </div>
      )}

      {/* Parser Results */}
      {magnets.length > 0 && (
        <div style={{ 
          background: 'rgba(20,20,20,0.4)', 
          border: '1px solid rgba(255,255,255,0.05)',
          borderRadius: '8px',
          padding: '24px'
        }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center', 
            flexWrap: 'wrap', 
            gap: '16px',
            borderBottom: '1px solid rgba(255,255,255,0.1)',
            paddingBottom: '16px',
            marginBottom: '20px'
          }}>
            <div>
              <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '1px', color: 'var(--accent-red)', fontWeight: 700 }}>Scraped Page Title</span>
              <h3 style={{ fontSize: '20px', color: '#fff', fontWeight: 600, marginTop: '4px' }}>{pageTitle}</h3>
            </div>
            
            {/* Search filter input */}
            <div style={{ position: 'relative', width: '100%', maxWidth: '300px' }}>
              <Search size={16} style={{ position: 'absolute', left: '10px', top: '10px', color: 'rgba(255,255,255,0.4)' }} />
              <input
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Filter links (e.g. 1080p, 5.4GB)..."
                style={{
                  width: '100%',
                  padding: '8px 12px 8px 34px',
                  backgroundColor: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '4px',
                  color: '#fff',
                  fontSize: '13px',
                  outline: 'none'
                }}
              />
            </div>
          </div>

          {/* Links list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {filteredMagnets.length === 0 ? (
              <div style={{ padding: '30px 0', textalign: 'center', color: 'var(--text-sub)', textAlign: 'center' }}>
                No magnet links matched your search filter.
              </div>
            ) : (
              filteredMagnets.map((mag, idx) => {
                const state = downloadStates[mag.magnet_link] || 'idle';
                const dlError = downloadErrors[mag.magnet_link] || '';

                return (
                  <div key={idx} style={{ 
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid rgba(255,255,255,0.05)',
                    borderRadius: '6px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '20px', flexWrap: 'wrap' }}>
                      <div style={{ flexGrow: 1, minWidth: '250px' }}>
                        {/* Title & Metadata Badges */}
                        <h5 style={{ fontSize: '15px', color: '#fff', fontWeight: 600 }}>{mag.title}</h5>
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '6px' }}>
                          {mag.resolution && (
                            <span style={{ 
                              border: '1px solid rgba(255,255,255,0.4)', 
                              padding: '0 6px', 
                              borderRadius: '2px', 
                              fontSize: '9px',
                              fontWeight: 700,
                              color: '#fff'
                            }}>{mag.resolution.toUpperCase()}</span>
                          )}
                          {mag.quality && (
                            <span style={{ 
                              border: '1px solid rgba(255,255,255,0.2)', 
                              padding: '0 6px', 
                              borderRadius: '2px', 
                              fontSize: '9px',
                              backgroundColor: 'rgba(255,255,255,0.05)',
                              color: '#fff'
                            }}>{mag.quality}</span>
                          )}
                          {mag.size && (
                            <span style={{ 
                              padding: '0 6px', 
                              borderRadius: '2px', 
                              fontSize: '9px',
                              backgroundColor: 'rgba(255,255,255,0.1)',
                              color: '#e5e5e5',
                              fontWeight: 600
                            }}>{mag.size}</span>
                          )}
                          {mag.codec && (
                            <span style={{ 
                              padding: '0 6px', 
                              borderRadius: '2px', 
                              fontSize: '9px',
                              backgroundColor: 'rgba(0,113,235,0.2)',
                              color: '#60a5fa'
                            }}>{mag.codec}</span>
                          )}
                          {mag.languages && mag.languages.length > 0 && (
                            <span style={{ 
                              padding: '0 6px', 
                              borderRadius: '2px', 
                              fontSize: '9px',
                              backgroundColor: 'rgba(229,9,20,0.15)',
                              color: 'var(--accent-red)',
                              fontWeight: 600
                            }}>{mag.languages.join(' / ')}</span>
                          )}
                        </div>
                      </div>

                      {/* Download Action Button */}
                      <div>
                        {state === 'idle' && (
                          <button
                            onClick={() => handleDownload(mag.magnet_link)}
                            className="btn btn-secondary"
                            style={{ 
                              padding: '8px 16px', 
                              fontSize: '12px', 
                              fontWeight: 600, 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: '6px',
                              backgroundColor: '#2f2f2f'
                            }}
                            title="Start downloading with Transmission"
                          >
                            <Magnet size={14} style={{ color: 'var(--accent-red)' }} />
                            Download
                          </button>
                        )}
                        {state === 'loading' && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#60a5fa', fontSize: '12px', fontWeight: 600 }}>
                            <Loader2 size={16} className="spin" />
                            Queuing...
                          </div>
                        )}
                        {state === 'success' && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#4ade80', fontSize: '12px', fontWeight: 600 }}>
                            <CheckCircle size={16} />
                            Downloading
                          </div>
                        )}
                        {state === 'error' && (
                          <button
                            onClick={() => handleDownload(mag.magnet_link)}
                            className="btn btn-secondary"
                            style={{ 
                              padding: '8px 16px', 
                              fontSize: '12px', 
                              fontWeight: 600, 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: '6px',
                              backgroundColor: 'rgba(229, 9, 20, 0.15)',
                              border: '1px solid var(--accent-red)',
                              color: '#ff8a8a'
                            }}
                            title="Retry download connection"
                          >
                            <AlertCircle size={14} />
                            Retry
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Show error explanation card if it fails */}
                    {state === 'error' && dlError && (
                      <div style={{ 
                        backgroundColor: 'rgba(229, 9, 20, 0.08)',
                        borderLeft: '3px solid var(--accent-red)',
                        padding: '10px 14px',
                        fontSize: '12px',
                        color: '#ffcbcb',
                        borderRadius: '0 4px 4px 0'
                      }}>
                        <strong>Error:</strong> {dlError}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
