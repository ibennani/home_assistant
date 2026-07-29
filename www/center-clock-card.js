class HaCenterClockCard extends HTMLElement {
  static get CARD_VERSION() {
    return "20260729j";
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  setConfig(config) {
    this.config = config || {};
    this._updateClock();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateClock();
  }

  connectedCallback() {
    this._updateClock();
    if (!this._interval) {
      this._interval = window.setInterval(() => this._updateClock(), 1000);
    }
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

  getGridOptions() {
    return {
      columns: 12,
      min_columns: 6,
      rows: 2,
      min_rows: 1,
    };
  }

  _formatTime(date) {
    const pad = (value) => String(value).padStart(2, "0");
    const use12h = this.config.time_format === "12";

    if (use12h) {
      const hours12 = ((date.getHours() + 11) % 12) + 1;
      const suffix = date.getHours() >= 12 ? " PM" : " AM";
      return `${pad(hours12)}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${suffix}`;
    }

    return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  _updateClock() {
    if (!this.config) {
      return;
    }

    const fontSize = this.config.font_size || "3.5rem";
    const version = HaCenterClockCard.CARD_VERSION;
    const time = this._formatTime(new Date());
    const clock = this.querySelector(".clock");
    const styleEl = this.querySelector("style.center-clock-style");

    if (clock && styleEl && styleEl.dataset.version === version) {
      clock.textContent = time;
      return;
    }

    this.innerHTML = `
      <style class="center-clock-style" data-version="${version}">
        :host {
          display: block;
          width: 100%;
        }
        ha-card {
          display: flex;
          justify-content: center;
          align-items: center;
          width: 100%;
          box-sizing: border-box;
          padding: 12px 16px;
        }
        .clock {
          width: 100%;
          text-align: center;
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
