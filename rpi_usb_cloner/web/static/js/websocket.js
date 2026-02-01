/**
 * Multiplexed WebSocket client for RPi USB Cloner.
 * Manages a single connection with channel subscriptions.
 */

class WebSocketClient {
  constructor(url, options = {}) {
    this.url = url;
    this.socket = null;
    this.subscribedChannels = new Set();
    this.reconnectAttempts = 0;
    this.reconnectDelay = options.initialDelay || 2000;
    this.maxReconnectAttempts = options.maxAttempts || 5;
    this.maxDelay = options.maxDelay || 30000;
    this.backoffMultiplier = options.backoffMultiplier || 1.5;
    
    // Callbacks
    this.onOpen = null;
    this.onClose = null;
    this.onError = null;
    this.onMessage = null;
    this.onBinaryMessage = null;
  }

  connect() {
    if (this.socket) {
      try {
        this.socket.close();
      } catch (e) {
        // Ignore
      }
    }

    this.socket = new WebSocket(this.url);
    this.socket.binaryType = 'arraybuffer';

    this.socket.addEventListener('open', (event) => {
      this.reconnectAttempts = 0;
      this.reconnectDelay = 2000;
      if (this.onOpen) this.onOpen(event);
    });

    this.socket.addEventListener('message', (event) => {
      if (event.data instanceof ArrayBuffer) {
        if (this.onBinaryMessage) this.onBinaryMessage(event.data);
      } else {
        try {
          const data = JSON.parse(event.data);
          if (this.onMessage) this.onMessage(data);
        } catch (error) {
          console.error('Failed to parse message:', error);
        }
      }
    });

    this.socket.addEventListener('close', (event) => {
      if (this.onClose) this.onClose(event);
      this._scheduleReconnect();
    });

    this.socket.addEventListener('error', (error) => {
      if (this.onError) this.onError(error);
    });
  }

  _scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    setTimeout(() => this.connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(
      this.reconnectDelay * this.backoffMultiplier,
      this.maxDelay
    );
  }

  subscribe(channels) {
    const newChannels = Array.isArray(channels) ? channels : [channels];
    this.send({ action: 'subscribe', channels: newChannels });
    newChannels.forEach(ch => this.subscribedChannels.add(ch));
  }

  unsubscribe(channels) {
    const channelsToRemove = Array.isArray(channels) ? channels : [channels];
    this.send({ action: 'unsubscribe', channels: channelsToRemove });
    channelsToRemove.forEach(ch => this.subscribedChannels.delete(ch));
  }

  sendButton(button) {
    this.send({ action: 'control', button });
  }

  ping() {
    this.send({ action: 'ping' });
  }

  send(data) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
      return true;
    }
    return false;
  }

  isConnected() {
    return this.socket && this.socket.readyState === WebSocket.OPEN;
  }

  getReadyState() {
    return this.socket ? this.socket.readyState : WebSocket.CLOSED;
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { WebSocketClient };
}
