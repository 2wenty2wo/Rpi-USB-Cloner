/**
 * Theme management (dark/light mode).
 */

class ThemeManager {
  constructor(options = {}) {
    this.toggleButton = document.getElementById(options.toggleId || 'theme-toggle');
    this.iconElement = document.getElementById(options.iconId || 'theme-icon');
    this.htmlElement = document.documentElement;
    this.storageKey = options.storageKey || 'theme';
    
    this._init();
  }

  _init() {
    // Load saved theme or default to light
    const savedTheme = this._getStoredTheme();
    this.applyTheme(savedTheme);
    
    // Add click handler
    if (this.toggleButton) {
      this.toggleButton.addEventListener('click', () => this.toggle());
    }
  }

  getTheme() {
    return this.htmlElement.getAttribute('data-bs-theme') || 'light';
  }

  applyTheme(theme) {
    this.htmlElement.setAttribute('data-bs-theme', theme);
    this._updateIcon(theme);
    this._storeTheme(theme);
  }

  toggle() {
    const currentTheme = this.getTheme();
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    this.applyTheme(newTheme);
    return newTheme;
  }

  _updateIcon(theme) {
    if (!this.iconElement) return;
    
    // Remove existing icon classes
    this.iconElement.classList.remove('lucide-icon-sun', 'lucide-icon-moon');
    
    // Add appropriate icon class
    if (theme === 'dark') {
      this.iconElement.classList.add('lucide-icon-moon');
    } else {
      this.iconElement.classList.add('lucide-icon-sun');
    }
  }

  _getStoredTheme() {
    try {
      return localStorage.getItem(this.storageKey) || 'light';
    } catch (e) {
      return 'light';
    }
  }

  _storeTheme(theme) {
    try {
      localStorage.setItem(this.storageKey, theme);
    } catch (e) {
      // Ignore storage errors
    }
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ThemeManager };
}
