/**
 * Configuration and constants for the RPi USB Cloner web UI.
 */

const CONFIG = {
  DEBUG_UI: true,
  WS_URL: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`,
  MAX_LOG_ENTRIES: 1000,
  RECONNECT: {
    MAX_ATTEMPTS: 5,
    INITIAL_DELAY: 2000,
    MAX_DELAY: 30000,
    BACKOFF_MULTIPLIER: 1.5
  },
  HEARTBEAT_INTERVAL: 30000
};

// Log level badge color mappings (Loguru-compatible with Tabler classes)
const LEVEL_BADGE_CLASSES = {
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

// Button mapping for keyboard controls
const KEY_BUTTON_MAP = {
  ArrowUp: 'UP',
  ArrowDown: 'DOWN',
  ArrowLeft: 'LEFT',
  ArrowRight: 'RIGHT',
  Enter: 'OK',
  Escape: 'BACK'
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { CONFIG, LEVEL_BADGE_CLASSES, KEY_BUTTON_MAP };
}
