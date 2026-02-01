/**
 * System health metrics display.
 */

class HealthManager {
  constructor(options = {}) {
    this.elements = {
      cpu: {
        percent: document.getElementById(options.cpuPercentId || 'cpu-percent'),
        bar: document.getElementById(options.cpuBarId || 'cpu-bar')
      },
      memory: {
        percent: document.getElementById(options.memoryPercentId || 'memory-percent'),
        bar: document.getElementById(options.memoryBarId || 'memory-bar'),
        detail: document.getElementById(options.memoryDetailId || 'memory-detail')
      },
      disk: {
        percent: document.getElementById(options.diskPercentId || 'disk-percent'),
        bar: document.getElementById(options.diskBarId || 'disk-bar'),
        detail: document.getElementById(options.diskDetailId || 'disk-detail')
      },
      temperature: {
        value: document.getElementById(options.tempValueId || 'temp-value'),
        bar: document.getElementById(options.tempBarId || 'temp-bar'),
        detail: document.getElementById(options.tempDetailId || 'temp-detail')
      }
    };
  }

  update(health) {
    if (!health) return;

    // CPU
    if (health.cpu && this.elements.cpu.percent && this.elements.cpu.bar) {
      this.elements.cpu.percent.textContent = `${health.cpu.percent}%`;
      this.elements.cpu.bar.style.width = `${health.cpu.percent}%`;
      this.elements.cpu.bar.className = `progress-bar bg-${health.cpu.status}`;
      this.elements.cpu.bar.setAttribute('aria-valuenow', health.cpu.percent);
    }

    // Memory
    if (health.memory && this.elements.memory.percent && this.elements.memory.bar) {
      this.elements.memory.percent.textContent = `${health.memory.percent}%`;
      this.elements.memory.bar.style.width = `${health.memory.percent}%`;
      this.elements.memory.bar.className = `progress-bar bg-${health.memory.status}`;
      this.elements.memory.bar.setAttribute('aria-valuenow', health.memory.percent);
      
      if (this.elements.memory.detail) {
        this.elements.memory.detail.textContent = `${health.memory.used_mb} / ${health.memory.total_mb} MB`;
      }
    }

    // Disk
    if (health.disk && this.elements.disk.percent && this.elements.disk.bar) {
      this.elements.disk.percent.textContent = `${health.disk.percent}%`;
      this.elements.disk.bar.style.width = `${health.disk.percent}%`;
      this.elements.disk.bar.className = `progress-bar bg-${health.disk.status}`;
      this.elements.disk.bar.setAttribute('aria-valuenow', health.disk.percent);
      
      if (this.elements.disk.detail) {
        this.elements.disk.detail.textContent = `${health.disk.used_gb} / ${health.disk.total_gb} GB`;
      }
    }

    // Temperature
    if (this.elements.temperature.value && this.elements.temperature.bar) {
      if (health.temperature && health.temperature.celsius !== null) {
        this.elements.temperature.value.textContent = `${health.temperature.celsius}°C`;
        
        // Scale: 0°C = 0%, 100°C = 100%
        const tempPercent = Math.min(100, Math.max(0, health.temperature.celsius));
        this.elements.temperature.bar.style.width = `${tempPercent}%`;
        this.elements.temperature.bar.className = `progress-bar bg-${health.temperature.status}`;
        this.elements.temperature.bar.setAttribute('aria-valuenow', tempPercent);
        
        if (this.elements.temperature.detail) {
          this.elements.temperature.detail.textContent = 'Raspberry Pi';
        }
      } else {
        this.elements.temperature.value.textContent = 'N/A';
        this.elements.temperature.bar.style.width = '0%';
        
        if (this.elements.temperature.detail) {
          this.elements.temperature.detail.textContent = 'Not available';
        }
      }
    }
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { HealthManager };
}
