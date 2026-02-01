/**
 * Log management: rendering, filtering, and display.
 */

class LogManager {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.options = {
      maxEntries: options.maxEntries || 1000,
      autoScroll: options.autoScroll !== false,
      ...options
    };
    
    this.entries = [];
    this.autoScrollEnabled = this.options.autoScroll;
    this.activeTagFilters = new Set();
    this.levelFilter = 'all';
    this.sourceFilter = 'all';
    this.searchQuery = '';
    
    // Badge color mapping
    this.levelBadgeClasses = {
      trace: 'bg-secondary-lt text-secondary',
      debug: 'bg-primary-lt text-primary',
      info: 'bg-info text-white',
      success: 'bg-success text-white',
      warning: 'bg-warning text-dark',
      error: 'bg-danger text-white',
      critical: 'bg-red-darken text-white',
      warn: 'bg-warning text-dark',
      log: 'bg-secondary-lt text-secondary'
    };
  }

  setFilters({ level, source, search } = {}) {
    if (level !== undefined) this.levelFilter = level.toLowerCase();
    if (source !== undefined) this.sourceFilter = source.toLowerCase();
    if (search !== undefined) this.searchQuery = search.toLowerCase();
    this._applyFilters();
  }

  toggleTagFilter(tag) {
    if (this.activeTagFilters.has(tag)) {
      this.activeTagFilters.delete(tag);
    } else {
      this.activeTagFilters.add(tag);
    }
    this._applyFilters();
    return this.activeTagFilters.has(tag);
  }

  clearTagFilters() {
    this.activeTagFilters.clear();
    this._applyFilters();
  }

  setAutoScroll(enabled) {
    this.autoScrollEnabled = enabled;
    if (enabled) this._scrollToBottom();
  }

  clear() {
    if (this.container) {
      this.container.innerHTML = '';
    }
    this.entries = [];
    this._updateCount();
  }

  append(level, message, details = {}, source = 'UI', timestamp = null, tags = null) {
    if (!this.container) return;

    const entry = {
      id: Date.now() + Math.random(),
      level: level.toLowerCase(),
      message,
      details,
      source,
      timestamp: timestamp || new Date().toISOString(),
      tags: this._collectTags(message, details, tags)
    };

    this.entries.push(entry);
    
    // Trim if exceeding max
    if (this.entries.length > this.options.maxEntries) {
      this.entries.shift();
      if (this.container.firstChild) {
        this.container.removeChild(this.container.firstChild);
      }
    }

    const element = this._createEntryElement(entry);
    this.container.appendChild(element);
    
    // Apply filters to new entry
    this._applyFilterToElement(element, entry);
    this._updateCount();
    
    if (this.autoScrollEnabled) {
      this._scrollToBottom();
    }

    return entry;
  }

  handleSnapshot(entries) {
    this.clear();
    entries.forEach(entry => {
      if (typeof entry === 'string') {
        const trimmed = entry.trim();
        if (trimmed) this.append('log', trimmed, {}, 'APP');
      } else if (entry && typeof entry === 'object') {
        this.append(
          entry.level || 'log',
          entry.message || JSON.stringify(entry),
          entry.details || {},
          entry.source || 'APP',
          entry.timestamp,
          entry.tags
        );
      }
    });
  }

  handleAppend(entries) {
    entries.forEach(entry => {
      if (typeof entry === 'string') {
        const trimmed = entry.trim();
        if (trimmed) this.append('log', trimmed, {}, 'APP');
      } else if (entry && typeof entry === 'object') {
        this.append(
          entry.level || 'log',
          entry.message || JSON.stringify(entry),
          entry.details || {},
          entry.source || 'APP',
          entry.timestamp,
          entry.tags
        );
      }
    });
  }

  getVisibleCount() {
    if (!this.container) return 0;
    return this.container.querySelectorAll('.list-group-item:not(.d-none)').length;
  }

  getTotalCount() {
    return this.entries.length;
  }

  _collectTags(message, details, explicitTags) {
    const tags = new Set();
    
    // Parse message for implicit tags
    if (message.includes('WebSocket')) tags.add('WEBSOCKET');
    if (message.includes('Screen changed')) tags.add('NAVIGATION');
    if (message.includes('socket not connected')) tags.add('WARNING');
    
    // Add explicit tags
    if (Array.isArray(explicitTags)) {
      explicitTags.forEach(t => tags.add(t));
    }
    
    return Array.from(tags);
  }

  _createEntryElement(entry) {
    const formatted = this._formatMessage(entry.message, entry.details);
    
    const div = document.createElement('div');
    div.className = 'list-group-item d-flex align-items-start gap-2 py-2';
    div.dataset.level = entry.level;
    div.dataset.source = entry.source.toLowerCase();
    div.dataset.tags = entry.tags.join(',');
    div.dataset.id = entry.id;

    // Level badge
    const badgeClass = this.levelBadgeClasses[entry.level] || 'bg-secondary';
    
    div.innerHTML = `
      <span class="badge badge-sm ${badgeClass} text-uppercase fw-bold text-center px-2">${entry.level.toUpperCase()}</span>
      <div class="flex-grow-1">
        <div class="d-flex align-items-center flex-wrap gap-1">
          <span class="text-secondary fs-7 lh-sm me-2" title="${new Date(entry.timestamp).toLocaleString()}">${this._formatRelativeTime(entry.timestamp)}</span>
          <span class="badge badge-sm bg-secondary-lt text-secondary me-2">${entry.source}</span>
          <span class="fs-6">${this._escapeHtml(formatted.text)}</span>
        </div>
        ${entry.tags.length ? `
          <div class="mt-1 d-flex gap-1">
            ${entry.tags.map(t => `<span class="badge badge-sm bg-azure-lt text-azure" style="cursor:pointer" data-tag="${this._escapeHtml(t)}">${this._escapeHtml(t)}</span>`).join('')}
          </div>
        ` : ''}
        ${formatted.details ? `
          <div class="mt-1 text-secondary fs-7 lh-sm font-monospace">${this._escapeHtml(formatted.details)}</div>
        ` : ''}
      </div>
    `;

    // Add tag click handlers
    div.querySelectorAll('[data-tag]').forEach(tagEl => {
      tagEl.addEventListener('click', () => {
        const tag = tagEl.dataset.tag;
        this.toggleTagFilter(tag);
        // Visual feedback
        tagEl.classList.toggle('bg-azure');
        tagEl.classList.toggle('bg-azure-lt');
      });
    });

    return div;
  }

  _formatMessage(message, details) {
    // Button press messages
    const buttonMatch = message.match(/Button pressed[:\s]*({.*}|\w+)/);
    if (buttonMatch || (details && details.button)) {
      const button = details?.button || buttonMatch?.[1]?.replace(/[{}]/g, '').match(/button["']?\s*:\s*["']?(\w+)/)?.[1] || 'unknown';
      const icons = { UP: '⬆️', DOWN: '⬇️', LEFT: '⬅️', RIGHT: '➡️', OK: '✓', SELECT: '✓', BACK: '◀️' };
      return { text: `${icons[button] || '🔘'} Button: ${button}`, details: null };
    }

    // Screen change
    const screenMatch = message.match(/Screen changed:\s*(\w+)\s*->\s*(\w+)/);
    if (screenMatch) {
      return { text: `Screen: ${screenMatch[1]} → ${screenMatch[2]}`, details: null, tags: ['NAVIGATION'] };
    }

    // WebSocket messages
    const wsMatch = message.match(/(Log|Screen|Control|Health)\s+WebSocket\s+(connected|disconnected|error)/i);
    if (wsMatch) {
      const icons = { connected: '🟢', disconnected: '🔴', error: '⚠️' };
      return { text: `${icons[wsMatch[2]]} ${wsMatch[1]} WebSocket ${wsMatch[2]}`, details: null, tags: ['WEBSOCKET'] };
    }

    // Default
    const detailParts = [];
    if (details && typeof details === 'object') {
      for (const [key, value] of Object.entries(details)) {
        if (['url', 'readyState', 'reconnectAttempts'].includes(key)) continue;
        detailParts.push(`${key}: ${JSON.stringify(value)}`);
      }
    }

    return { text: message, details: detailParts.length ? detailParts.join(', ') : null };
  }

  _formatRelativeTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 5) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`;
    
    return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  _applyFilters() {
    if (!this.container) return;
    
    const elements = this.container.querySelectorAll('.list-group-item');
    elements.forEach(el => {
      const entry = this.entries.find(e => e.id === Number(el.dataset.id));
      if (entry) {
        this._applyFilterToElement(el, entry);
      }
    });
    
    this._updateCount();
  }

  _applyFilterToElement(element, entry) {
    const levelMatch = this.levelFilter === 'all' || entry.level === this.levelFilter;
    const sourceMatch = this.sourceFilter === 'all' || entry.source.toLowerCase() === this.sourceFilter;
    const tagMatch = this.activeTagFilters.size === 0 || entry.tags.some(t => this.activeTagFilters.has(t));
    const searchMatch = !this.searchQuery || 
      entry.message.toLowerCase().includes(this.searchQuery) ||
      entry.source.toLowerCase().includes(this.searchQuery);

    if (levelMatch && sourceMatch && tagMatch && searchMatch) {
      element.classList.remove('d-none');
    } else {
      element.classList.add('d-none');
    }
  }

  _updateCount() {
    const event = new CustomEvent('logCountChanged', {
      detail: { visible: this.getVisibleCount(), total: this.getTotalCount() }
    });
    document.dispatchEvent(event);
  }

  _scrollToBottom() {
    if (this.container) {
      this.container.scrollTop = this.container.scrollHeight;
    }
  }

  _escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LogManager };
}
