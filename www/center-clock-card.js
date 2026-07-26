class HaCenterClockCard extends HTMLElement {
  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  setConfig(config) {
    this.config = config || {};
    this._render();
  }

  connectedCallback() {
    this._render();
    this._interval = window.setInterval(() => this._render(), 1000);
  }

  disconnectedCallback() {
    if (this._interval) {
      clearInterval(this._interval);
      this._interval = undefined;
    }
  }

  getCardSize() {
    return 2;
  }

  _formatTime(date) {
    const pad = (value) => String(value).padStart(2, "0");
    const use12h = this.config.time_format === "12";

    if (use12h) {
      const hours12 = (date.getHours() + 11) % 12 + 1;
      const suffix = date.getHours() >= 12 ? " PM" : " AM";
      return `${pad(hours12)}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${suffix}`;
    }

    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  _render() {
    const fontSize = this.config.font_size || "3.5rem";
    const time = this._formatTime(new Date());

    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
    }

    this._root.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 12px 16px;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, none);
        }
        .clock {
          font-family: var(--ha-font-family-body, Roboto, sans-serif);
          font-size: ${fontSize};
          font-weight: var(--ha-font-weight-normal, 300);
          line-height: 1.1;
          color: var(--primary-text-color);
          font-variant-numeric: tabular-nums;
          letter-spacing: 0.04em;
          white-space: nowrap;
        }
      </style>
      <ha-card>
        <div class="clock" aria-live="polite" aria-label="Klocka">${time}</div>
      </ha-card>
    `;
  }
}

if (!customElements.get("ha-center-clock-card")) {
  customElements.define("ha-center-clock-card", HaCenterClockCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ha-center-clock-card",
  name: "Center Clock",
  preview: true,
  description: "Digital klocka med sekunder i samma storlek (HH:MM:SS).",
});
