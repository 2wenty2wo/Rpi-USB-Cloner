/**
 * Device and image repository management.
 */

class DeviceManager {
  constructor(options = {}) {
    this.containers = {
      devices: document.getElementById(options.devicesContainerId || 'usb-devices-container'),
      images: document.getElementById(options.imagesContainerId || 'image-repo-container'),
      chart: document.getElementById(options.chartId || 'image-repo-chart'),
      chartLegend: document.getElementById(options.chartLegendId || 'image-repo-chart-legend'),
      chartDivider: document.getElementById(options.chartDividerId || 'image-repo-divider')
    };
    
    this.badges = {
      deviceCount: document.getElementById(options.deviceCountId || 'device-count'),
      imageCount: document.getElementById(options.imageCountId || 'image-count')
    };
  }

  updateDevices(devices, operationActive = false) {
    const container = this.containers.devices;
    const countBadge = this.badges.deviceCount;
    
    if (!container || !countBadge) return;

    if (!devices || devices.length === 0) {
      container.innerHTML = this._getEmptyDeviceState();
      countBadge.textContent = '0 devices';
      countBadge.className = 'badge bg-secondary text-white';
      return;
    }

    const deviceText = devices.length === 1 ? 'device' : 'devices';
    countBadge.textContent = `${devices.length} ${deviceText}`;
    countBadge.className = 'badge bg-primary text-white';

    const items = devices.map(device => this._renderDeviceItem(device)).join('');
    container.innerHTML = `<div class="list-group list-group-flush">${items}</div>`;
  }

  updateImages(images, repoStats, operationActive = false) {
    const container = this.containers.images;
    const countBadge = this.badges.imageCount;
    const chart = this.containers.chart;
    const chartLegend = this.containers.chartLegend;
    const chartDivider = this.containers.chartDivider;
    
    if (!container || !countBadge) return;

    const repoEntries = repoStats ? Object.values(repoStats) : [];
    const imageCount = images ? images.length : 0;
    const hasRepos = repoEntries.length > 0 || imageCount > 0;

    if (!hasRepos) {
      this._hideChart();
      container.innerHTML = this._getEmptyImageState();
      countBadge.textContent = '0 images';
      countBadge.className = 'badge bg-secondary text-white';
      return;
    }

    const imageText = imageCount === 1 ? 'image' : 'images';
    countBadge.textContent = `${imageCount} ${imageText}`;
    countBadge.className = 'badge bg-primary text-white';

    // Update chart
    this._updateChart(repoEntries);

    // Update image list
    const items = (images || []).map(image => this._renderImageItem(image)).join('');
    container.innerHTML = `<div class="list-group list-group-flush">${items}</div>`;
  }

  _renderDeviceItem(device) {
    const statusConfig = this._getDeviceStatusConfig(device.status);
    const mountpoints = (device.mountpoints || [])
      .map(mp => `<code class="text-secondary">${this._escapeHtml(mp)}</code>`)
      .join(', ');
    
    const mountHtml = mountpoints ? `<div class="text-secondary small mt-1">Mounted: ${mountpoints}</div>` : '';

    return `
      <div class="list-group-item">
        <div class="row align-items-center">
          <div class="col-auto">
            <span class="lucide-icon lucide-icon-hard-drive text-primary" style="font-size: 1.5rem;"></span>
          </div>
          <div class="col">
            <div class="fw-semibold">${this._escapeHtml(device.label)}</div>
            <div class="text-secondary small">
              ${this._escapeHtml(device.path)} • ${this._escapeHtml(device.size_formatted)}
              ${device.fstype ? `• ${this._escapeHtml(device.fstype)}` : ''}
            </div>
            ${mountHtml}
          </div>
          <div class="col-auto">
            <span class="badge bg-${statusConfig.color} ${statusConfig.textClass} d-flex align-items-center gap-1">
              <span class="lucide-icon lucide-icon-${statusConfig.icon}"></span>
              ${statusConfig.label}
            </span>
          </div>
        </div>
      </div>
    `;
  }

  _renderImageItem(image) {
    const isIso = image.type === 'iso';
    const typeColor = isIso ? 'info' : 'primary';
    const typeIcon = isIso ? 'disc' : 'folder';
    const typeLabel = isIso ? 'ISO' : 'Clonezilla';
    const sizeFormatted = image.size_bytes ? this._formatBytes(image.size_bytes) : '—';

    return `
      <div class="list-group-item">
        <div class="row align-items-center">
          <div class="col-auto">
            <span class="lucide-icon lucide-icon-${typeIcon} text-primary" style="font-size: 1.5rem;"></span>
          </div>
          <div class="col">
            <div class="fw-semibold">${this._escapeHtml(image.name)}</div>
            <div class="text-secondary small">${sizeFormatted}</div>
            <div class="text-secondary small mt-1">Repo: <code class="text-secondary">${this._escapeHtml(image.repo_label)}</code></div>
          </div>
          <div class="col-auto">
            <span class="badge bg-${typeColor} text-white d-flex align-items-center gap-1">
              <span class="lucide-icon lucide-icon-${typeIcon}"></span>
              ${typeLabel}
            </span>
          </div>
        </div>
      </div>
    `;
  }

  _updateChart(repoEntries) {
    const chart = this.containers.chart;
    const chartLegend = this.containers.chartLegend;
    const chartDivider = this.containers.chartDivider;
    
    if (!chart || !chartLegend || !chartDivider) return;

    // Calculate totals
    const totals = repoEntries.reduce(
      (acc, entry) => {
        const typeBytes = entry.type_bytes || {};
        acc.clonezilla += typeBytes.clonezilla || 0;
        acc.iso += typeBytes.iso || 0;
        acc.imageusb += typeBytes.imageusb || 0;
        acc.other += typeBytes.other || 0;
        acc.total += entry.total_bytes || 0;
        acc.free += entry.free_bytes || 0;
        return acc;
      },
      { clonezilla: 0, iso: 0, imageusb: 0, other: 0, total: 0, free: 0 }
    );

    if (totals.total === 0) {
      this._hideChart();
      return;
    }

    // Show chart
    chart.classList.remove('d-none');
    chartDivider.classList.remove('d-none');

    // Update segments
    const segments = [
      { key: 'clonezilla', bytes: totals.clonezilla, color: 'primary' },
      { key: 'iso', bytes: totals.iso, color: 'info' },
      { key: 'imageusb', bytes: totals.imageusb, color: 'warning' },
      { key: 'other', bytes: totals.other, color: 'secondary' },
      { key: 'free', bytes: totals.free, color: 'secondary-lt' }
    ];

    segments.forEach(seg => {
      const el = chart.querySelector(`[data-repo-segment="${seg.key}"]`);
      if (el) {
        const percent = totals.total > 0 ? (seg.bytes / totals.total) * 100 : 0;
        el.style.width = `${percent.toFixed(1)}%`;
      }
    });

    // Update legend
    const labels = {
      clonezilla: 'Clonezilla',
      iso: 'ISO',
      imageusb: 'BIN',
      other: 'Other',
      free: 'Free'
    };

    chartLegend.innerHTML = segments
      .filter(seg => seg.bytes > 0 || seg.key === 'free')
      .map(seg => `
        <span class="badge bg-${seg.color} ${seg.color === 'warning' ? 'text-dark' : 'text-white'}">
          ${labels[seg.key]}: ${this._formatBytes(seg.bytes)}
        </span>
      `).join('');
  }

  _hideChart() {
    if (this.containers.chart) this.containers.chart.classList.add('d-none');
    if (this.containers.chartDivider) this.containers.chartDivider.classList.add('d-none');
    if (this.containers.chartLegend) this.containers.chartLegend.innerHTML = '';
    
    // Reset segment widths
    if (this.containers.chart) {
      this.containers.chart.querySelectorAll('[data-repo-segment]').forEach(el => {
        el.style.width = '0%';
      });
    }
  }

  _getDeviceStatusConfig(status) {
    const configs = {
      ready: { color: 'success', icon: 'check-circle', label: 'Ready', textClass: 'text-white' },
      mounted: { color: 'info', icon: 'disc', label: 'Mounted', textClass: 'text-white' },
      unformatted: { color: 'warning', icon: 'alert-circle', label: 'Unformatted', textClass: 'text-dark' }
    };
    return configs[status] || { color: 'secondary', icon: 'disc', label: status || 'Unknown', textClass: 'text-white' };
  }

  _getEmptyDeviceState() {
    return `
      <div class="text-center text-muted py-4">
        <span class="lucide-icon lucide-icon-usb" style="font-size: 2rem;" aria-hidden="true"></span>
        <p class="mt-2">No USB devices detected</p>
        <p class="text-secondary small">Connect a USB drive to get started</p>
      </div>
    `;
  }

  _getEmptyImageState() {
    return `
      <div class="text-center text-muted py-4">
        <span class="lucide-icon lucide-icon-folder" style="font-size: 2rem;" aria-hidden="true"></span>
        <p class="mt-2">No image repos detected</p>
        <p class="text-secondary small">Connect a repo drive to browse available images</p>
      </div>
    `;
  }

  _formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / Math.pow(1024, exponent);
    const formatted = value >= 10 ? value.toFixed(1) : value.toFixed(2);
    return `${formatted} ${units[exponent]}`;
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
  module.exports = { DeviceManager };
}
