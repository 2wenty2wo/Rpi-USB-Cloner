/**
 * Main application entry point for RPi USB Cloner web UI.
 * Coordinates all modules and handles the application lifecycle.
 */

class RpiUsbClonerApp {
  constructor() {
    this.config = {
      DEBUG_UI: true,
      WS_URL: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`,
      RECONNECT_MAX_ATTEMPTS: 5,
      HEARTBEAT_INTERVAL: 30000
    };

    // Initialize managers
    this.theme = new ThemeManager();
    this.health = new HealthManager();
    this.devices = new DeviceManager();
    this.screen = new ScreenManager('screen', {
      onButtonPress: (button) => this.sendButton(button)
    });
    this.logs = new LogManager('debug-log', {
      maxEntries: 1000,
      autoScroll: true
    });

    // Initialize WebSocket client
    this.ws = new WebSocketClient(this.config.WS_URL, {
      maxAttempts: this.config.RECONNECT_MAX_ATTEMPTS
    });

    // Connection state
    this.heartbeatInterval = null;
    
    this._init();
  }

  _init() {
    this._setupWebSocketCallbacks();
    this._setupUIControls();
    this._setupGlobalErrorHandling();
    
    // Connect to WebSocket
    this.connect();
  }

  _setupWebSocketCallbacks() {
    this.ws.onOpen = () => {
      this._log('log', 'WebSocket connected', { url: this.config.WS_URL });
      this._updateStatus(true);
      
      // Subscribe to all channels
      this.ws.subscribe(['screen', 'logs', 'health', 'devices', 'images', 'control']);
      
      // Start heartbeat
      this._startHeartbeat();
    };

    this.ws.onClose = (event) => {
      this._log('warn', 'WebSocket disconnected', {
        code: event.code,
        wasClean: event.wasClean
      });
      this._updateStatus(false);
      this._stopHeartbeat();
    };

    this.ws.onError = (error) => {
      this._log('error', 'WebSocket error', { error });
    };

    this.ws.onMessage = (data) => this._handleMessage(data);
    this.ws.onBinaryMessage = (data) => this.screen.updateFrame(data);
  }

  _setupUIControls() {
    // Log filters
    const levelFilter = document.getElementById('log-level-filter');
    const sourceFilter = document.getElementById('log-source-filter');
    const searchInput = document.getElementById('log-search-input');
    const clearBtn = document.getElementById('clear-logs-btn');
    const autoScrollToggle = document.getElementById('auto-scroll-toggle');

    if (levelFilter) {
      levelFilter.addEventListener('change', () => {
        this.logs.setFilters({ level: levelFilter.value });
      });
    }

    if (sourceFilter) {
      sourceFilter.addEventListener('change', () => {
        this.logs.setFilters({ source: sourceFilter.value });
      });
    }

    if (searchInput) {
      searchInput.addEventListener('input', () => {
        this.logs.setFilters({ search: searchInput.value });
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        this.logs.clear();
      });
    }

    if (autoScrollToggle) {
      autoScrollToggle.addEventListener('change', () => {
        this.logs.setAutoScroll(autoScrollToggle.checked);
      });
    }

    // Log count display
    document.addEventListener('logCountChanged', (e) => {
      const display = document.getElementById('log-count-display');
      if (display) {
        const { visible, total } = e.detail;
        display.textContent = visible === total 
          ? `${total} logs` 
          : `${visible} / ${total} logs`;
      }
    });
  }

  _setupGlobalErrorHandling() {
    window.addEventListener('error', (event) => {
      this._log('error', 'JavaScript error', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno
      });
    });

    window.addEventListener('unhandledrejection', (event) => {
      this._log('error', 'Unhandled promise rejection', {
        reason: String(event.reason)
      });
    });
  }

  _handleMessage(data) {
    switch (data.type) {
      case 'subscribed':
        this._log('log', 'Subscribed to channels', { channels: data.channels });
        break;

      case 'health':
        this.health.update(data);
        break;

      case 'logs':
        if (data.update_type === 'snapshot') {
          this.logs.handleSnapshot(data.entries);
        } else if (data.update_type === 'append') {
          this.logs.handleAppend(data.entries);
        }
        break;

      case 'devices':
        this.devices.updateDevices(data.devices, data.operation_active);
        break;

      case 'images':
        this.devices.updateImages(data.images, data.repo_stats, data.operation_active);
        break;

      case 'pong':
        // Heartbeat response - connection is alive
        break;

      case 'error':
        this._log('warn', 'Server error', { message: data.message });
        break;

      default:
        if (this.config.DEBUG_UI) {
          this._log('debug', 'Unknown message type', { type: data.type });
        }
    }
  }

  _startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      if (this.ws.isConnected()) {
        this.ws.ping();
      }
    }, this.config.HEARTBEAT_INTERVAL);
  }

  _stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  _updateStatus(connected) {
    const statusEl = document.getElementById('status');
    if (!statusEl) return;

    statusEl.className = 'nav-link d-flex align-items-center small';
    if (connected) {
      statusEl.innerHTML = '<span class="status status-green"><span class="status-dot status-dot-animated"></span>Connected</span>';
    } else {
      statusEl.innerHTML = '<span class="status status-red"><span class="status-dot"></span>Disconnected</span>';
    }
  }

  _log(level, message, details = {}) {
    // Console logging
    const logger = console[level] || console.log;
    logger(message, details);

    // UI logging (only if not from websocket to avoid loops)
    if (!details.source || details.source !== 'WS') {
      this.logs.append(level, message, details, 'UI');
    }
  }

  // Public API
  connect() {
    this.ws.connect();
  }

  disconnect() {
    this.ws.disconnect();
  }

  sendButton(button) {
    if (this.ws.isConnected()) {
      this.ws.sendButton(button);
      this._log('log', 'Button pressed', { button, source: 'WS' });
    } else {
      this._log('warn', 'WebSocket not connected, button press dropped', { button });
    }
  }

  isConnected() {
    return this.ws.isConnected();
  }
}

// Initialize app when DOM is ready
let app;
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    app = new RpiUsbClonerApp();
  });
} else {
  app = new RpiUsbClonerApp();
}

// Export for debugging
if (typeof window !== 'undefined') {
  window.RpiUsbClonerApp = RpiUsbClonerApp;
  window.app = app;
}
