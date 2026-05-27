import { useState, useEffect } from 'react';
import { Settings, Film, ListOrdered } from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, onOpenSettings }) {
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
        <a href="#" className="navbar-brand" onClick={() => setActiveTab('browse')}>
          Netflix
        </a>
        <div className="navbar-links">
          <a
            href="#"
            className={`navbar-link ${activeTab === 'browse' ? 'active' : ''}`}
            onClick={(e) => {
              e.preventDefault();
              setActiveTab('browse');
            }}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <Film size={16} />
            Browse
          </a>
          <a
            href="#"
            className={`navbar-link ${activeTab === 'queue' ? 'active' : ''}`}
            onClick={(e) => {
              e.preventDefault();
              setActiveTab('queue');
            }}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <ListOrdered size={16} />
            Transcode Queue
          </a>
        </div>
      </div>
      <div className="navbar-links">
        <button
          className="navbar-link"
          onClick={onOpenSettings}
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
