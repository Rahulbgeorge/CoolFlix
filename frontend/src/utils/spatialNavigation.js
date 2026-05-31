export const SpatialNavigationManager = {
  active: true,

  init() {
    window.addEventListener('keydown', this.handleKeyDown);
    document.addEventListener('mousemove', this.handleMouseMove);
  },

  destroy() {
    window.removeEventListener('keydown', this.handleKeyDown);
    document.removeEventListener('mousemove', this.handleMouseMove);
  },

  handleMouseMove() {
    // Temporarily deactivate glow border when using standard mouse hover
    const current = document.querySelector('.nav-focused');
    if (current) {
      current.classList.remove('nav-focused');
    }
  },

  getFocusableElements() {
    return Array.from(document.querySelectorAll('.focusable')).filter(el => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        parseFloat(style.opacity || '1') > 0
      );
    });
  },

  getCurrentFocused() {
    return document.querySelector('.nav-focused');
  },

  focusElement(el) {
    if (!el) return;
    
    const previous = this.getCurrentFocused();
    if (previous) {
      previous.classList.remove('nav-focused');
      previous.dispatchEvent(new CustomEvent('nav-blur'));
    }

    el.classList.add('nav-focused');
    
    // Ensure element is HTML focusable or has tabIndex to call focus()
    if (el.tabIndex === -1 && !['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'A'].includes(el.tagName)) {
      el.tabIndex = 0;
    }
    el.focus();
    
    el.dispatchEvent(new CustomEvent('nav-focus'));

    // Smoothly scroll the element into center/nearest viewport
    el.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'nearest'
    });
  },

  handleKeyDown(e) {
    if (!SpatialNavigationManager.active) return;

    const key = e.key;
    const isArrow = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(key);
    
    if (isArrow) {
      const current = SpatialNavigationManager.getCurrentFocused();
      
      // Special TV remote seeking: left/right arrows on scrubber seek the video instead of shifting focus
      if (current && current.classList.contains('player-timeline-wrapper') && (key === 'ArrowLeft' || key === 'ArrowRight')) {
        e.preventDefault();
        current.dispatchEvent(new CustomEvent('nav-seek', { detail: { direction: key === 'ArrowLeft' ? 'left' : 'right' } }));
        return;
      }

      e.preventDefault();
      
      const focusables = SpatialNavigationManager.getFocusableElements();
      if (focusables.length === 0) return;
      
      if (!current) {
        // Default: focus the first visible focusable element
        SpatialNavigationManager.focusElement(focusables[0]);
        return;
      }

      const direction = key.replace('Arrow', '').toLowerCase(); // 'left', 'right', 'up', 'down'
      const nextEl = SpatialNavigationManager.findClosestElement(current, focusables, direction);
      
      if (nextEl) {
        SpatialNavigationManager.focusElement(nextEl);
      }
    } else if (key === 'Enter') {
      const current = SpatialNavigationManager.getCurrentFocused();
      if (current) {
        // Trigger simulated click if not focused on raw inputs which native clicks handle
        if (document.activeElement === current) {
          e.preventDefault();
          current.click();
        }
      }
    } else if (key === 'Escape' || key === 'Backspace') {
      // Find modal close or player back button to navigate backwards
      const backBtn = document.querySelector('.player-back-btn') || document.querySelector('.modal-close');
      if (backBtn) {
        e.preventDefault();
        backBtn.click();
      }
    }
  },

  findClosestElement(current, candidates, direction) {
    const currentRect = current.getBoundingClientRect();
    const cx = currentRect.left + currentRect.width / 2;
    const cy = currentRect.top + currentRect.height / 2;

    let bestCandidate = null;
    let minDistance = Infinity;

    for (const el of candidates) {
      if (el === current) continue;

      const rect = el.getBoundingClientRect();
      const tx = rect.left + rect.width / 2;
      const ty = rect.top + rect.height / 2;

      const dx = tx - cx;
      const dy = ty - cy;

      let dPrimary = 0;
      let dSecondary = 0;
      let isValid = false;

      // Calculate directional boundaries
      if (direction === 'left') {
        dPrimary = cx - tx;
        dSecondary = Math.abs(cy - ty);
        isValid = tx < cx - 5;
      } else if (direction === 'right') {
        dPrimary = tx - cx;
        dSecondary = Math.abs(cy - ty);
        isValid = tx > cx + 5;
      } else if (direction === 'up') {
        dPrimary = cy - ty;
        dSecondary = Math.abs(cx - tx);
        isValid = ty < cy - 5;
      } else if (direction === 'down') {
        dPrimary = ty - cy;
        dSecondary = Math.abs(cx - tx);
        isValid = ty > cy + 5;
      }

      if (isValid) {
        // Secondary axis weight of 4 ensures strong row/column locking
        const distance = dPrimary + 4 * dSecondary;
        if (distance < minDistance) {
          minDistance = distance;
          bestCandidate = el;
        }
      }
    }

    return bestCandidate;
  }
};
