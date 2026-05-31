import { useState, useEffect } from 'react';
import { Settings, Film, ListOrdered, Download } from 'lucide-react';
import { useFocusable } from '@noriginmedia/norigin-spatial-navigation';

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

  const { ref: brandRef, focused: brandFocused } = useFocusable({
    focusKey: 'NAV_BRAND',
    onEnterPress: () => onNavigate('/')
  });

  const { ref: browseRef, focused: browseFocused } = useFocusable({
    focusKey: 'NAV_BROWSE',
    onEnterPress: () => onNavigate('/')
  });

  const { ref: queueRef, focused: queueFocused } = useFocusable({
    focusKey: 'NAV_QUEUE',
    onEnterPress: () => onNavigate('/queue')
  });

  const { ref: downloaderRef, focused: downloaderFocused } = useFocusable({
    focusKey: 'NAV_DOWNLOADER',
    onEnterPress: () => onNavigate('/downloader')
  });

  const { ref: settingsRef, focused: settingsFocused } = useFocusable({
    focusKey: 'NAV_SETTINGS',
    onEnterPress: () => onNavigate('/settings')
  });

  return (
    <nav className={`navbar ${scrolled ? 'scrolled' : ''}`}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '40px' }}>
        <a
          ref={brandRef}
          href="#"
          className={`navbar-brand focusable ${brandFocused ? 'nav-focused' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/'); }}
        >
          Netflix
        </a>
        <div className="navbar-links">
          <a
            ref={browseRef}
            href="#"
            className={`navbar-link focusable ${activeTab === 'browse' ? 'active' : ''} ${browseFocused ? 'nav-focused' : ''}`}
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
            ref={queueRef}
            href="#"
            className={`navbar-link focusable ${activeTab === 'queue' ? 'active' : ''} ${queueFocused ? 'nav-focused' : ''}`}
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
            ref={downloaderRef}
            href="#"
            className={`navbar-link focusable ${activeTab === 'downloader' ? 'active' : ''} ${downloaderFocused ? 'nav-focused' : ''}`}
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
          ref={settingsRef}
          className={`navbar-link focusable ${settingsFocused ? 'nav-focused' : ''}`}
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
