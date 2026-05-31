import { useState, useEffect } from 'react';
import { Settings, Film, ListOrdered, Download } from 'lucide-react';

export default function Navbar({ activeTab, onNavigate }) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 30) {
        setScrolled(true);
      } else {
        setScrolled(false);
      }
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav className={`navbar ${scrolled ? 'scrolled' : ''}`}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '40px' }}>
        <a href="#" className="navbar-brand focusable" onClick={(e) => { e.preventDefault(); onNavigate('/'); }}>
          Netflix
        </a>
        <div className="navbar-links">
          <a
            href="#"
            className={`navbar-link focusable ${activeTab === 'browse' ? 'active' : ''}`}
            onClick={(e) => {
              e.preventDefault();
              onNavigate('/');
            }}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <Film size={16} />
            Browse
          </a>
          <a
            href="#"
            className={`navbar-link focusable ${activeTab === 'queue' ? 'active' : ''}`}
            onClick={(e) => {
              e.preventDefault();
              onNavigate('/queue');
            }}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <ListOrdered size={16} />
            Transcode Queue
          </a>
          <a
            href="#"
            className={`navbar-link focusable ${activeTab === 'downloader' ? 'active' : ''}`}
            onClick={(e) => {
              e.preventDefault();
              onNavigate('/downloader');
            }}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <Download size={16} />
            Downloader
          </a>
        </div>
      </div>
      <div className="navbar-links">
        <button
          className="navbar-link focusable"
          onClick={() => onNavigate('/settings')}
          style={{ background: 'transparent', display: 'flex', alignItems: 'center', gap: '6px' }}
          title="Configure settings"
        >
          <Settings size={18} />
          Settings
        </button>
      </div>
    </nav>
  );
}
