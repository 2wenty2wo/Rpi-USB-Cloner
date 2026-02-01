/**
 * OLED screen preview and controls.
 */

class ScreenManager {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) {
      console.error(`Canvas element '${canvasId}' not found`);
      return;
    }
    
    this.ctx = this.canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;
    
    this.options = {
      onButtonPress: options.onButtonPress || (() => {}),
      ...options
    };
    
    this.pendingFrame = null;
    
    this._initControls();
  }

  async updateFrame(arrayBuffer) {
    if (!this.ctx) return;
    
    // Prevent frame queuing - skip if still rendering
    if (this.pendingFrame) return;
    
    this.pendingFrame = requestAnimationFrame(async () => {
      try {
        const blob = new Blob([arrayBuffer], { type: 'image/png' });
        const bitmap = await createImageBitmap(blob);
        
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.drawImage(bitmap, 0, 0, this.canvas.width, this.canvas.height);
        
        if (typeof bitmap.close === 'function') {
          bitmap.close();
        }
      } catch (error) {
        console.error('Failed to render frame:', error);
      } finally {
        this.pendingFrame = null;
      }
    });
  }

  _initControls() {
    // D-pad and action buttons
    document.querySelectorAll('[data-button]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const button = btn.getAttribute('data-button');
        this.options.onButtonPress(button);
      });

      // Prevent text selection on touch devices
      btn.addEventListener('touchstart', (e) => {
        e.preventDefault();
        const button = btn.getAttribute('data-button');
        this.options.onButtonPress(button);
      });
    });

    // Keyboard controls
    document.addEventListener('keydown', (event) => {
      const target = event.target;
      if (target) {
        const tagName = target.tagName;
        if (target.isContentEditable || tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT') {
          return;
        }
      }

      const keyMap = {
        ArrowUp: 'UP',
        ArrowDown: 'DOWN',
        ArrowLeft: 'LEFT',
        ArrowRight: 'RIGHT',
        Enter: 'OK',
        Escape: 'BACK'
      };

      const button = keyMap[event.key];
      if (!button) return;

      event.preventDefault();
      this.options.onButtonPress(button);
    });
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ScreenManager };
}
