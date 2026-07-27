class HaSlNearbyStopsCard extends HTMLElement {
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
    this.config = Object.assign({}, HaSlNearbyStopsCard.getStubConfig(), config || {});
    this._updateView();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateView();
    this._syncRefreshTimer();
  }

  connectedCallback() {
    this._ensureSitesLoaded().then(() => this._updateView());
    this._syncRefreshTimer();
  }

  disconnectedCallback() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
    }
  }

  getCardSize() {
    return 8;
  }

  _getCache() {
    if (!this._departureCache) {
      this._departureCache = new Map();
    }
    return this._departureCache;
  }

  _ensureSitesLoaded() {
    if (this._sites) {
      return Promise.resolve(this._sites);
    }
    if (!this._sitesPromise) {
      this._sitesPromise = fetch("/local/sl-sites.json")
        .then((response) => {
          if (!response.ok) {
            throw new Error("Kunde inte läsa sl-sites.json (" + response.status + ")");
          }
          return response.json();
        })
        .then((sites) => {
          this._sites = sites;
          return sites;
        })
        .catch((error) => {
          this._sitesError = error.message || String(error);
          this._sites = [];
          return [];
        });
    }
    return this._sitesPromise;
  }

  _getLocation() {
    if (!this._hass || !this.config || !this.config.location_entity) {
      return null;
    }
    const state = this._hass.states[this.config.location_entity];
    if (!state || !state.attributes) {
      return null;
    }
    const lat = Number(state.attributes.latitude);
    const lon = Number(state.attributes.longitude);
    if (!isFinite(lat) || !isFinite(lon)) {
      return null;
    }
    return { lat: lat, lon: lon };
  }

  _haversineMeters(lat1, lon1, lat2, lon2) {
    const toRad = function (value) {
      return (value * Math.PI) / 180;
    };
    const earthRadius = 6371000;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.pow(Math.sin(dLat / 2), 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.pow(Math.sin(dLon / 2), 2);
    return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  _getNearestStops() {
    const location = this._getLocation();
    if (!location || !this._sites || !this._sites.length) {
      return [];
    }
    const maxStops = Number(this.config.max_stops || 20);
    const self = this;
    return this._sites
      .map(function (site) {
        return Object.assign({}, site, {
          distance_m: self._haversineMeters(location.lat, location.lon, site.lat, site.lon),
        });
      })
      .sort(function (a, b) {
        return a.distance_m - b.distance_m;
      })
      .slice(0, maxStops);
  }

  _formatDistance(meters) {
    if (meters < 1000) {
      return Math.round(meters) + " m";
    }
    return (meters / 1000).toFixed(1) + " km";
  }

  _syncRefreshTimer() {
    const seconds = Number((this.config && this.config.refresh_seconds) || 0);
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
    }
    if (!seconds || seconds < 15 || !this._openSiteId) {
      return;
    }
    const self = this;
    this._refreshTimer = window.setInterval(function () {
      if (self._openSiteId) {
        self._loadDepartures(self._openSiteId, true);
      }
    }, seconds * 1000);
  }

  _loadDepartures(siteId, force) {
    if (!this._hass || !this._hass.callService) {
      return;
    }
    const cache = this._getCache();
    const cacheKey = String(siteId);
    if (!force && cache.has(cacheKey) && !cache.get(cacheKey).loading) {
      return;
    }

    cache.set(cacheKey, { loading: true });
    this._updateView();

    const self = this;
    this._hass
      .callService(
        "script",
        "turn_on",
        {
          entity_id: "script.sl_hamta_avgangar_for_hallplats",
          variables: { site_id: String(siteId) },
        },
        undefined,
        true,
      )
      .then(function (result) {
        const payload = (result && result.response) || result || {};
        cache.set(cacheKey, {
          loading: false,
          departures: self._prepareDepartures(payload.departures || []),
          stop_deviations: payload.stop_deviations || [],
          fetched_at: Date.now(),
        });
        self._updateView();
      })
      .catch(function (error) {
        cache.set(cacheKey, {
          loading: false,
          error: (error && error.message) || "Kunde inte hämta avgångar",
        });
        self._updateView();
      });
  }

  _prepareDepartures(departures) {
    const now = Date.now();
    const hideDeparted = !this.config || this.config.hide_departed !== false;
    const destPattern = /(?: station(?: \([^)]+\))?| \([^)]+\))$/;
    const items = [];

    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const expected = dep.expected || dep.scheduled;
      const expectedMs = expected ? new Date(expected).getTime() : Number.POSITIVE_INFINITY;
      let destination = dep.destination || "";
      if (dep.line && dep.line.transport_mode === "TRAIN") {
        destination = destination.replace(destPattern, "").trim();
      }
      if (hideDeparted && isFinite(expectedMs) && expectedMs + 5 * 60 * 1000 < now) {
        continue;
      }
      items.push(Object.assign({}, dep, { destination: destination, _expectedMs: expectedMs }));
    }

    items.sort(function (a, b) {
      return a._expectedMs - b._expectedMs;
    });
    return items;
  }

  _escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _formatClock(date) {
    return date.toLocaleTimeString(this.config.language || "sv-SE", {
      hour: "numeric",
      minute: "numeric",
    });
  }

  _lineIconClass(transportMode, line, groupOfLines) {
    const designation = String(line || "");
    if (transportMode === "BUS") {
      return groupOfLines === "blåbuss" ? "bus bus_" + designation + " blue" : "bus_red bus_" + designation;
    }
    if (transportMode === "TRAIN") {
      return "train";
    }
    if (transportMode === "TRAM") {
      return "tram tram_" + designation;
    }
    return "train";
  }

  _transportIcon(transportMode) {
    const icons = {
      METRO: "mdi:subway",
      BUS: "mdi:bus",
      TRAM: "mdi:tram",
      TRAIN: "mdi:train",
      SHIP: "mdi:ship",
      FERRY: "mdi:ferry",
    };
    return icons[transportMode] || "mdi:train";
  }

  _renderDepartures(siteId) {
    const cache = this._getCache().get(String(siteId));
    if (!cache) {
      return '<div class="departures-empty">Öppna för att hämta avgångar…</div>';
    }
    if (cache.loading) {
      return '<div class="departures-empty">Hämtar avgångar…</div>';
    }
    if (cache.error) {
      return '<div class="departures-error">' + this._escapeHtml(cache.error) + "</div>";
    }

    let html = "";
    const deviations = cache.stop_deviations || [];
    if (deviations.length) {
      html += '<div class="stop-info">';
      for (let i = 0; i < deviations.length; i++) {
        const dev = deviations[i];
        html +=
          '<div class="stop-info-item">' +
          this._escapeHtml(dev.message || dev.text || dev.title || "") +
          "</div>";
      }
      html += "</div>";
    }

    const departures = cache.departures || [];
    if (!departures.length) {
      return html + '<div class="departures-empty">Inga avgångar inom ' + (this.config.forecast_minutes || 60) + " min.</div>";
    }

    html += '<div class="departures"><div class="row header"><div class="col icon"></div><div class="col main left">Linje</div><div class="col right">Avgång</div></div>';
    const now = new Date();
    const self = this;

    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const line = dep.line || {};
      const scheduledAt = dep.scheduled ? new Date(dep.scheduled) : null;
      const expectedAt = dep.expected ? new Date(dep.expected) : scheduledAt;
      const diff = expectedAt ? Math.ceil((expectedAt.getTime() - now.getTime()) / 60000) : 0;
      const isCancelled =
        String(dep.state || "").toUpperCase() === "CANCELLED" ||
        String(dep.state || "").toUpperCase() === "INHIBITED";
      let departureTime = "";
      if (isCancelled) {
        departureTime = '<span class="cancelled-time">Inställd</span>';
      } else if (expectedAt) {
        departureTime = self._formatClock(expectedAt);
      }

      html +=
        '<div class="departure-block"><div class="row departure">' +
        '<div class="col icon"><ha-icon class="transport-icon" icon="' +
        self._transportIcon(line.transport_mode) +
        '"></ha-icon></div>' +
        '<div class="col icon"><span class="line-icon mr1 ' +
        self._lineIconClass(line.transport_mode, line.designation, line.group_of_lines) +
        '">' +
        self._escapeHtml(line.designation || "") +
        "</span></div>" +
        '<div class="col main left">' +
        self._escapeHtml(dep.destination || "") +
        '</div><div class="col right"><span class="leaves-in">' +
        departureTime +
        "</span></div></div></div>";
    }

    html += "</div>";
    return html;
  }

  _updateView() {
    if (!this.config) {
      return;
    }

    const root = this.querySelector(".sl-nearby-root");
    if (!root) {
      this.innerHTML =
        '<style>' +
        this._styles() +
        "</style><ha-card><div class=\"sl-nearby-root\"></div></ha-card>";
    }

    const container = this.querySelector(".sl-nearby-root");
    if (!container) {
      return;
    }

    const location = this._getLocation();
    const stops = this._getNearestStops();
    const locationLabel = this.config.location_entity;
    let body = "";

    if (this._sitesError) {
      body = '<div class="status-message error">' + this._escapeHtml(this._sitesError) + "</div>";
    } else if (!this._sites) {
      body = '<div class="status-message">Laddar hållplatser…</div>';
    } else if (!location) {
      body =
        '<div class="status-message">Ingen GPS-position från ' +
        this._escapeHtml(locationLabel) +
        ".</div>";
    } else if (!stops.length) {
      body = '<div class="status-message">Inga hållplatser hittades.</div>';
    } else {
      const self = this;
      body = stops
        .map(function (stop) {
          const openAttr = self._openSiteId === stop.id ? " open" : "";
          return (
            '<details class="stop-accordion" data-site-id="' +
            stop.id +
            '"' +
            openAttr +
            ">" +
            '<summary class="stop-summary"><span class="stop-name">' +
            self._escapeHtml(stop.name) +
            '</span><span class="stop-distance">' +
            self._formatDistance(stop.distance_m) +
            "</span></summary>" +
            '<div class="stop-body">' +
            self._renderDepartures(stop.id) +
            "</div></details>"
          );
        })
        .join("");
    }

    container.innerHTML = body;

    const self = this;
    container.querySelectorAll(".stop-accordion").forEach(function (element) {
      element.addEventListener("toggle", function (event) {
        const details = event.currentTarget;
        const siteId = Number(details.dataset.siteId);
        if (!details.open) {
          if (self._openSiteId === siteId) {
            self._openSiteId = null;
          }
          self._syncRefreshTimer();
          return;
        }
        self._openSiteId = siteId;
        self._syncRefreshTimer();
        self._loadDepartures(siteId, false);
      });
    });
  }

  _styles() {
    return [
      "ha-card{padding:8px 0 12px}",
      ".status-message{padding:16px;color:var(--secondary-text-color)}",
      ".status-message.error{color:var(--error-color)}",
      ".stop-accordion{border-top:1px solid var(--divider-color,rgba(0,0,0,.12))}",
      ".stop-summary{list-style:none;display:flex;justify-content:space-between;gap:12px;align-items:center;padding:14px 16px;cursor:pointer}",
      ".stop-summary::-webkit-details-marker{display:none}",
      ".stop-name{font-weight:500}",
      ".stop-distance{color:var(--secondary-text-color);white-space:nowrap}",
      ".stop-body{padding:0 8px 12px}",
      ".departures-empty,.departures-error{padding:8px 16px 12px;color:var(--secondary-text-color)}",
      ".departures-error{color:var(--error-color)}",
      ".row{margin-top:8px;display:flex;justify-content:space-between}",
      ".col{display:flex;flex-direction:column;justify-content:center}",
      ".col.icon{flex-basis:40px}",
      ".main{flex:2}",
      ".line-icon{border-radius:3px;padding:3px;min-width:22px;height:22px;font-weight:500;display:inline-block;text-align:center;color:#fff}",
      ".bus_red,.train{background-color:#9e0e13}",
      ".train{background-color:#ec619f}",
      ".tram{background-color:#985141}",
      ".stop-info{margin:0 8px 8px;padding:8px 12px 0;font-size:smaller;color:#fad370!important}",
      ".cancelled-time{color:#e53935;font-weight:600}",
      ".left{text-align:left}",
      ".right{text-align:right}",
    ].join("");
  }
}

if (!customElements.get("ha-sl-nearby-stops-card")) {
  customElements.define("ha-sl-nearby-stops-card", HaSlNearbyStopsCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ha-sl-nearby-stops-card",
  name: "SL närmaste hållplatser",
  preview: true,
  description: "Visar närmaste SL-hållplatser från GPS och avgångar i accordion.",
});
