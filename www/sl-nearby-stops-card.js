class SlNearbyStopsCard extends HTMLElement {
  static getStubConfig() {
    return {
      location_entity: "person.ilias_bennani",
      max_stops: 20,
      forecast_minutes: 60,
      hide_departed: true,
      show_time_always: true,
      language: "sv-SE",
      refresh_seconds: 60,
    };
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  setConfig(config) {
    const base = SlNearbyStopsCard.getStubConfig();
    const input = config && typeof config === "object" ? config : {};
    this.config = Object.assign({}, base, input);
    if (!this._departureCache) {
      this._departureCache = new Map();
    }
    this._openSiteId = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.config) {
      return;
    }
    const prev = this._locationKey;
    const next = this._getLocationKey();
    this._locationKey = next;
    if (prev !== next) {
      this._departureCache.clear();
      this._openSiteId = null;
    }
    this._ensureBusLineTerminusLabels();
    this._render();
    this._syncRefreshTimer();
  }

  _ensureBusLineTerminusLabels() {
    const api = window.SlDepartureTime;
    if (!api || !api.ensureBusLineTerminus || this._busLineTerminusBound) {
      return;
    }
    this._busLineTerminusBound = true;
    const self = this;
    api.ensureBusLineTerminus("20260729w").then(function () {
      self._render();
    });
  }

  getCardSize() {
    const maxStops = this.config && this.config.max_stops ? this.config.max_stops : 20;
    return Math.max(4, Number(maxStops));
  }

  getGridOptions() {
    return {
      columns: 12,
      min_columns: 6,
      rows: 8,
      min_rows: 4,
    };
  }

  connectedCallback() {
    this._ensureSitesLoaded().then(() => this._render());
    this._syncRefreshTimer();
  }

  disconnectedCallback() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
    }
  }

  async _ensureSitesLoaded() {
    if (this._sites) {
      return this._sites;
    }
    if (!this._sitesPromise) {
      this._sitesPromise = fetch("/local/sl-sites.json")
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Kunde inte läsa sl-sites.json (${response.status})`);
          }
          return response.json();
        })
        .then((sites) => {
          this._sites = sites;
          return sites;
        })
        .catch((error) => {
          this._sitesError = error.message || String(error);
          return [];
        });
    }
    return this._sitesPromise;
  }

  _getLocationKey() {
    const location = this._getLocation();
    if (!location) {
      return "missing";
    }
    return `${location.lat.toFixed(4)},${location.lon.toFixed(4)}`;
  }

  _getLocation() {
    if (!this._hass || !this.config || !this.config.location_entity) {
      return null;
    }
    const state = this._hass.states[this.config.location_entity];
    if (!state) {
      return null;
    }
    const lat = Number(state.attributes.latitude);
    const lon = Number(state.attributes.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      return null;
    }
    return { lat, lon };
  }

  _haversineMeters(lat1, lon1, lat2, lon2) {
    const toRad = (value) => (value * Math.PI) / 180;
    const earthRadius = 6371000;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  _getNearestStops() {
    const location = this._getLocation();
    if (!location || !this._sites || !this._sites.length) {
      return [];
    }
    const maxStops = Number(this.config.max_stops || 20);
    return this._sites
      .map((site) =>
        Object.assign({}, site, {
          distance_m: this._haversineMeters(location.lat, location.lon, site.lat, site.lon),
        }),
      )
      .sort((a, b) => a.distance_m - b.distance_m)
      .slice(0, maxStops);
  }

  _formatDistance(meters) {
    if (meters < 1000) {
      return `${Math.round(meters)} m`;
    }
    return `${(meters / 1000).toFixed(1)} km`;
  }

  _syncRefreshTimer() {
    const seconds = Number((this.config && this.config.refresh_seconds) || 0);
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
    }
    if (!seconds || seconds < 15) {
      return;
    }
    this._refreshTimer = window.setInterval(() => {
      if (!this._openSiteId) {
        return;
      }
      this._loadDepartures(this._openSiteId, true);
    }, seconds * 1000);
  }

  async _loadDepartures(siteId, force = false) {
    if (!this._hass || !this._hass.callService) {
      return;
    }
    const cacheKey = String(siteId);
    if (!force && this._departureCache.has(cacheKey) && !this._departureCache.get(cacheKey).loading) {
      return;
    }

    this._departureCache.set(cacheKey, { loading: true });
    this._render();

    try {
      const result = await this._hass.callService(
        "script",
        "turn_on",
        {
          entity_id: "script.sl_hamta_avgangar_for_hallplats",
          variables: { site_id: String(siteId) },
        },
        undefined,
        true,
      );
      const payload = (result && result.response) || result || {};
      const departures = this._prepareDepartures(payload.departures || []);
      this._departureCache.set(cacheKey, {
        loading: false,
        departures,
        stop_deviations: payload.stop_deviations || [],
        fetched_at: Date.now(),
      });
    } catch (error) {
      this._departureCache.set(cacheKey, {
        loading: false,
        error: (error && error.message) || "Kunde inte hämta avgångar",
      });
    }

    this._render();
  }

  _shouldHideDepartedDeparture(dep, now) {
    const hideDeparted = !this.config || this.config.hide_departed !== false;
    const api = window.SlDepartureTime;
    if (api && api.shouldHideDepartedDeparture) {
      return api.shouldHideDepartedDeparture(dep, now, hideDeparted);
    }
    const expectedAt = this._parseDate(dep.expected) || this._parseDate(dep.scheduled);
    return this._shouldHideDeparted(expectedAt, now);
  }

  _shouldHideDeparted(expectedAt, now) {
    const hideDeparted = !this.config || this.config.hide_departed !== false;
    if (window.SlDepartureTime && window.SlDepartureTime.shouldHideDeparted) {
      return window.SlDepartureTime.shouldHideDeparted(expectedAt, now, hideDeparted);
    }
    if (!hideDeparted || !expectedAt) {
      return false;
    }
    return this._diffMinutes(expectedAt, now) < 0;
  }

  _formatDepartureLabel(dep) {
    const api = window.SlDepartureTime;
    if (api && api.formatDepartureLabel) {
      return api.formatDepartureLabel(dep);
    }
    return String((dep && dep.destination) || (dep && dep.direction) || "").trim();
  }

  _prepareDepartures(departures) {
    const self = this;

    return departures
      .map((dep) => {
        const expected = dep.expected || dep.scheduled;
        const expectedAt = expected ? new Date(expected) : null;
        const expectedMs = expectedAt ? expectedAt.getTime() : Number.POSITIVE_INFINITY;
        const destination = self._formatDepartureLabel(dep);
        return Object.assign({}, dep, {
          destination: destination,
          _rawDestination: dep.destination,
          _rawDirection: dep.direction,
          _expectedMs: expectedMs,
          _expectedAt: expectedAt,
        });
      })
      .sort((a, b) => a._expectedMs - b._expectedMs);
  }

  _parseDate(value) {
    if (!value) {
      return null;
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  _diffMinutes(from, to) {
    return Math.ceil((from.getTime() - to.getTime()) / 1000 / 60);
  }

  _formatClock(date) {
    return date.toLocaleTimeString(this.config.language || "sv-SE", {
      hour: "numeric",
      minute: "numeric",
    });
  }

  _isCancelled(dep) {
    const state = String(dep.state || "").toUpperCase();
    const journeyState = String((dep.journey && dep.journey.state) || "").toUpperCase();
    return state === "CANCELLED" || state === "INHIBITED" || journeyState === "CANCELLED";
  }

  _isDelayed(scheduledAt, expectedAt) {
    if (!scheduledAt || !expectedAt) {
      return false;
    }
    return Math.round((expectedAt.getTime() - scheduledAt.getTime()) / 1000 / 60) >= 1;
  }

  _isShortTrainDeviation(dev) {
    const msg = `${dev.message || dev.text || dev.title || ""}`.toLowerCase();
    return msg.includes("kort tåg") || msg.includes("kort tag") || msg.includes("short train");
  }

  _isDelayDeviation(dev) {
    const msg = `${dev.message || dev.text || dev.title || ""}`.toLowerCase();
    return msg.includes("försen") || msg.includes("senare") || msg.includes("delay") || msg.includes("delayed");
  }

  _lineIconClass(transportMode, line, groupOfLines) {
    const designation = String(line || "");
    switch (transportMode) {
      case "BUS":
        return groupOfLines === "blåbuss" ? `bus bus_${designation} blue` : `bus_red bus_${designation}`;
      case "METRO": {
        let cls = `metro metro_${designation}`;
        if (designation === "10" || designation === "11") {
          cls += " blue";
        }
        if (designation === "13" || designation === "14") {
          cls += " red";
        }
        if (designation === "17" || designation === "18" || designation === "19") {
          cls += " green";
        }
        return cls;
      }
      case "TRAM":
        return `tram tram_${designation}`;
      case "TRAIN":
        return "train";
      case "SHIP":
      case "FERRY":
        return "ship";
      default:
        return "train";
    }
  }

  _transportIcon(transportMode) {
    const icons = {
      METRO: "mdi:subway",
      BUS: "mdi:bus",
      TRAM: "mdi:tram",
      TRAIN: "mdi:train",
      SHIP: "mdi:ship",
      FERRY: "mdi:ferry",
      TAXI: "mdi:taxi",
    };
    return icons[transportMode] || "mdi:train";
  }

  _escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _renderDepartures(siteId) {
    const cache = this._departureCache.get(String(siteId));
    if (!cache) {
      return `<div class="departures-empty">Öppna för att hämta avgångar…</div>`;
    }
    if (cache.loading) {
      return `<div class="departures-empty">Hämtar avgångar…</div>`;
    }
    if (cache.error) {
      return `<div class="departures-error">${this._escapeHtml(cache.error)}</div>`;
    }

    const stopInfo = (cache.stop_deviations || [])
      .map((dev) => `<div class="stop-info-item">${this._escapeHtml(dev.message || dev.text || dev.title || "")}</div>`)
      .join("");

    const stopInfoBlock = stopInfo
      ? `<div class="stop-info">${stopInfo}</div>`
      : "";

    if (!cache.departures || !cache.departures.length) {
      return `${stopInfoBlock}<div class="departures-empty">Inga avgångar inom ${this.config.forecast_minutes || 60} min.</div>`;
    }

    const now = new Date();
    const rows = cache.departures
      .filter((dep) => !this._shouldHideDepartedDeparture(dep, now))
      .map((dep) => {
        const scheduledAt = this._parseDate(dep.scheduled);
        const expectedAt = this._parseDate(dep.expected) || scheduledAt;
        const diff = expectedAt ? this._diffMinutes(expectedAt, now) : 0;
        const isAtPlatform = diff === 0;
        const isCancelled = this._isCancelled(dep);
        const isDelayed = !isCancelled && this._isDelayed(scheduledAt, expectedAt);
        const deviations = dep.deviations || [];
        const isShortTrain = deviations.some((dev) => this._isShortTrainDeviation(dev));
        const otherDeviations = deviations.filter(
          (dev) => !this._isShortTrainDeviation(dev) && !this._isDelayDeviation(dev),
        );

        const deviationItems = [];
        if (isShortTrain) {
          deviationItems.push({ text: "kort tåg", className: "short-train" });
        }
        for (const dev of otherDeviations) {
          const text = dev.message || dev.text || dev.title;
          if (text) {
            deviationItems.push({ text, className: "warning-message" });
          }
        }

        let departureTime = "";
        if (isCancelled) {
          departureTime = `<span class="cancelled-time">Inställd</span>`;
        } else if (isDelayed && scheduledAt && expectedAt) {
          const newTime = this.config.show_time_always
            ? this._formatClock(expectedAt)
            : isAtPlatform
              ? "Nu"
              : this._formatClock(expectedAt);
          departureTime = `<span class="old-time">${this._formatClock(scheduledAt)}</span><span class="new-time">${newTime}</span>`;
        } else if (expectedAt) {
          departureTime = this.config.show_time_always
            ? this._formatClock(expectedAt)
            : isAtPlatform
              ? "Nu"
              : this._formatClock(expectedAt);
        }

        const line = dep.line || {};
        const icon = this._transportIcon(line.transport_mode);
        const lineClass = this._lineIconClass(
          line.transport_mode,
          line.designation,
          line.group_of_lines,
        );

        const deviationRow = deviationItems.length
          ? `<div class="row deviation-row">
              <div class="col icon"></div>
              <div class="col icon"></div>
              <div class="col main left deviation-messages">
                ${deviationItems
                  .map((item) => `<span class="deviation-item ${item.className}">${this._escapeHtml(item.text)}</span>`)
                  .join("")}
              </div>
              <div class="col right"></div>
            </div>`
          : "";

        return `<div class="departure-block">
          <div class="row departure">
            <div class="col icon"><ha-icon class="transport-icon" icon="${icon}"></ha-icon></div>
            <div class="col icon"><span class="line-icon mr1 ${lineClass}">${this._escapeHtml(line.designation || "")}</span></div>
            <div class="col main left">${this._escapeHtml(dep.destination || "")}</div>
            <div class="col right"><span class="leaves-in">${departureTime}</span></div>
          </div>
          ${deviationRow}
        </div>`;
      })
      .join("");

    return `${stopInfoBlock}
      <div class="departures">
        <div class="row header">
          <div class="col icon"></div>
          <div class="col main left">Linje</div>
          <div class="col right">Avgång</div>
        </div>
        ${rows}
      </div>`;
  }

  _render() {
    if (!this.config) {
      return;
    }

    try {
    const location = this._getLocation();
    const stops = this._getNearestStops();
    const locationLabel = this.config.location_entity;

    let body = "";
    if (this._sitesError) {
      body = `<div class="status-message error">${this._escapeHtml(this._sitesError)}</div>`;
    } else if (!this._sites) {
      body = `<div class="status-message">Laddar hållplatser…</div>`;
    } else if (!location) {
      body = `<div class="status-message">Ingen GPS-position från ${this._escapeHtml(locationLabel)}.</div>`;
    } else if (!stops.length) {
      body = `<div class="status-message">Inga hållplatser hittades.</div>`;
    } else {
      body = stops
        .map((stop) => {
          const isOpen = this._openSiteId === stop.id;
          return `<details class="stop-accordion" data-site-id="${stop.id}" ${isOpen ? "open" : ""}>
            <summary class="stop-summary">
              <span class="stop-name">${this._escapeHtml(stop.name)}</span>
              <span class="stop-distance">${this._formatDistance(stop.distance_m)}</span>
            </summary>
            <div class="stop-body">${this._renderDepartures(stop.id)}</div>
          </details>`;
        })
        .join("");
    }

    this.innerHTML = `
      <style>
        ha-card {
          padding: 8px 0 12px;
        }
        .status-message {
          padding: 16px;
          color: var(--secondary-text-color);
        }
        .status-message.error {
          color: var(--error-color);
        }
        .stop-accordion {
          border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        }
        .stop-accordion:last-child {
          border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        }
        .stop-summary {
          list-style: none;
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: center;
          padding: 14px 16px;
          cursor: pointer;
          font-size: 1rem;
        }
        .stop-summary::-webkit-details-marker {
          display: none;
        }
        .stop-summary::after {
          content: "▾";
          color: var(--secondary-text-color);
          transition: transform 0.15s ease;
        }
        details[open] > .stop-summary::after {
          transform: rotate(180deg);
        }
        .stop-name {
          font-weight: 500;
        }
        .stop-distance {
          color: var(--secondary-text-color);
          white-space: nowrap;
        }
        .stop-body {
          padding: 0 8px 12px;
        }
        .departures-empty,
        .departures-error {
          padding: 8px 16px 12px;
          color: var(--secondary-text-color);
        }
        .departures-error {
          color: var(--error-color);
        }
        .departures > :first-child {
          margin-top: 0;
        }
        .row {
          margin-top: 8px;
          display: flex;
          justify-content: space-between;
        }
        .col {
          display: flex;
          flex-direction: column;
          justify-content: center;
          position: relative;
        }
        .col.icon {
          flex-basis: 40px;
        }
        .row.header {
          height: 40px;
          font-size: medium;
          font-weight: 400;
          opacity: var(--dark-primary-opacity);
        }
        .main {
          flex: 2;
        }
        .transport-icon {
          width: 40px;
          height: 40px;
          display: inline-flex;
          justify-content: center;
          align-items: center;
        }
        .line-icon {
          border-radius: 3px;
          padding: 3px 3px 0 3px;
          color: #fff;
          min-width: 22px;
          height: 22px;
          font-weight: 500;
          display: inline-block;
          text-align: center;
          text-shadow: 1px 1px 2px var(--outline-color);
        }
        .bus {
          border: 1px solid var(--outline-color);
          color: var(--primary-text-color);
        }
        .bus_red,
        .bus.red,
        .red {
          background-color: #9e0e13;
          color: #fff;
          border: none;
        }
        .blue {
          background-color: #0089ca;
        }
        .green {
          background-color: #179d4d;
        }
        .train {
          background-color: #ec619f;
        }
        .tram {
          background-color: #985141;
        }
        .warning-message {
          color: var(--warning-color);
          font-size: smaller;
        }
        .departure-block {
          margin-top: 8px;
        }
        .departure-block .row.departure {
          margin-top: 0;
        }
        .row.deviation-row {
          margin-top: 2px;
        }
        .row.deviation-row .deviation-messages {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .deviation-item {
          font-size: smaller;
          line-height: 1.3;
        }
        .stop-info {
          margin: 0 8px 8px;
          padding: 8px 12px 0;
          font-size: smaller;
          line-height: 1.35;
          color: #fad370 !important;
          border-top: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
        }
        .stop-info-item {
          color: #fad370 !important;
        }
        .stop-info-item + .stop-info-item {
          margin-top: 6px;
        }
        .short-train {
          color: #0abcfc;
          font-size: smaller;
          font-weight: 600;
          margin-left: 0.35em;
          text-transform: lowercase;
        }
        .old-time {
          text-decoration: line-through;
          opacity: 0.65;
          margin-right: 0.35em;
        }
        .new-time {
          color: #0abcfc;
          font-weight: 600;
        }
        .cancelled-time {
          color: #e53935;
          font-weight: 600;
        }
        .leaves-in {
          white-space: nowrap;
        }
        .mr1 {
          margin-right: 8px;
        }
        .left { text-align: left; }
        .right { text-align: right; }
        ha-icon {
          width: 24px;
          height: 24px;
          color: var(--paper-item-icon-color);
        }
      </style>
      <ha-card>
        ${body}
      </ha-card>
    `;

    this.querySelectorAll(".stop-accordion").forEach((element) => {
      element.addEventListener("toggle", (event) => {
        const details = event.currentTarget;
        const siteId = Number(details.dataset.siteId);
        if (!details.open) {
          if (this._openSiteId === siteId) {
            this._openSiteId = null;
          }
          return;
        }
        this._openSiteId = siteId;
        this._loadDepartures(siteId);
      });
    });
    } catch (error) {
      this.innerHTML = `<ha-card><div class="status-message error">${this._escapeHtml(error.message || String(error))}</div></ha-card>`;
    }
  }
}

if (!customElements.get("sl-nearby-stops-card")) {
  customElements.define("sl-nearby-stops-card", SlNearbyStopsCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "sl-nearby-stops-card",
  name: "SL närmaste hållplatser",
  preview: false,
  description: "Visar närmaste SL-hållplatser från GPS och avgångar i accordion.",
});
