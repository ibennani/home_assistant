class HaSlNearbyStopsCard extends HTMLElement {
  static getStubConfig() {
    return {
      location_entity: "person.ilias_bennani",
      home_zone_entity: "zone.home",
      max_stops: 20,
      max_gps_km: 80,
      forecast_minutes: 60,
      hide_departed: true,
      language: "sv-SE",
      refresh_seconds: 60,
    };
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  setConfig(config) {
    try {
      const base = HaSlNearbyStopsCard.getStubConfig();
      const input = config && typeof config === "object" ? config : {};
      this.config = Object.assign({}, base, input);
      this._locationNote = "";
      if (!this._departureCache) {
        this._departureCache = new Map();
      }
      this._updateView();
    } catch (error) {
      this.config = HaSlNearbyStopsCard.getStubConfig();
      this.innerHTML =
        '<ha-card><div class="status-message error">Kortfel: ' +
        String((error && error.message) || error) +
        "</div></ha-card>";
    }
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
    return 20;
  }

  getGridOptions() {
    const maxStops = Number((this.config && this.config.max_stops) || 20);
    return {
      columns: 12,
      min_columns: 6,
      rows: Math.max(8, maxStops),
      min_rows: 4,
    };
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
      this._sitesPromise = fetch("/local/sl-sites.json?v=20260727k")
        .then((response) => {
          if (!response.ok) {
            throw new Error("Kunde inte läsa sl-sites.json (" + response.status + ")");
          }
          return response.json();
        })
        .then((sites) => {
          if (!Array.isArray(sites)) {
            throw new Error("sl-sites.json har oväntat format");
          }
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

  _readCoords(entityId) {
    if (!this._hass || !entityId) {
      return null;
    }
    const state = this._hass.states[entityId];
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

  _getSearchLocation() {
    const personLoc = this._readCoords(this.config.location_entity);
    const homeLoc = this._readCoords(this.config.home_zone_entity);
    const maxDistanceM = Number(this.config.max_gps_km || 80) * 1000;

    if (!personLoc && homeLoc) {
      this._locationNote = "Använder hemzon (ingen GPS)";
      return homeLoc;
    }
    if (!personLoc) {
      return null;
    }
    if (homeLoc) {
      const distFromHome = this._haversineMeters(
        personLoc.lat,
        personLoc.lon,
        homeLoc.lat,
        homeLoc.lon,
      );
      if (distFromHome > maxDistanceM) {
        this._locationNote = "GPS långt från hem — visar hållplatser nära hemzon";
        return homeLoc;
      }
    }
    this._locationNote = "Position från " + this.config.location_entity;
    return personLoc;
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
    const location = this._getSearchLocation();
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

  _extractPayload(result) {
    if (!result) {
      return {};
    }
    if (result.content && (result.content.departures || result.content.stop_deviations)) {
      return {
        departures: result.content.departures || [],
        stop_deviations: result.content.stop_deviations || [],
      };
    }
    if (result.service_response) {
      const sr = result.service_response;
      if (sr["script.sl_hamta_avgangar_for_hallplats"]) {
        return sr["script.sl_hamta_avgangar_for_hallplats"];
      }
      const keys = Object.keys(sr);
      if (keys.length === 1) {
        return sr[keys[0]];
      }
    }
    if (result.response) {
      return result.response;
    }
    if (result.departures || result.stop_deviations) {
      return result;
    }
    return {};
  }

  _callWithResponse(domain, service, serviceData) {
    if (this._hass && this._hass.connection && this._hass.connection.sendMessagePromise) {
      return this._hass.connection
        .sendMessagePromise({
          type: "call_service",
          domain: domain,
          service: service,
          service_data: serviceData,
          return_response: true,
        })
        .then((msg) => (msg && msg.response) || msg || {});
    }
    if (this._hass && this._hass.callApi) {
      return this._hass.callApi(
        "POST",
        "services/" + domain + "/" + service + "?return_response",
        serviceData,
      );
    }
    if (this._hass && this._hass.callService) {
      return this._hass.callService(domain, service, serviceData, undefined, true);
    }
    return Promise.reject(new Error("Kunde inte anropa Home Assistant"));
  }

  _callDepartures(siteId) {
    const forecast = Number((this.config && this.config.forecast_minutes) || 60);
    const serviceData = {
      site_id: Number(siteId),
      forecast: forecast,
    };
    return this._callWithResponse("rest_command", "sl_site_departures", serviceData).then(
      (result) => this._extractPayload(result),
    );
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
    if (!this._hass) {
      return;
    }
    const cache = this._getCache();
    const cacheKey = String(siteId);
    if (this._departureInflight && this._departureInflight[cacheKey]) {
      return;
    }
    const existing = cache.get(cacheKey);
    if (!force && existing && !existing.loading && (existing.fetched_at || existing.error)) {
      this._updateDeparturePanel(siteId);
      return;
    }

    if (!this._departureInflight) {
      this._departureInflight = {};
    }
    this._departureInflight[cacheKey] = true;
    cache.set(cacheKey, { loading: true });
    this._updateDeparturePanel(siteId);

    const self = this;
    this._callDepartures(siteId)
      .then(function (payload) {
        cache.set(cacheKey, {
          loading: false,
          departures: self._prepareDepartures(payload.departures || []),
          stop_deviations: payload.stop_deviations || [],
          fetched_at: Date.now(),
        });
        self._updateDeparturePanel(siteId);
      })
      .catch(function (error) {
        cache.set(cacheKey, {
          loading: false,
          error: (error && error.message) || "Kunde inte hämta avgångar",
        });
        self._updateDeparturePanel(siteId);
      })
      .then(function () {
        self._departureInflight[cacheKey] = false;
      });
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
    const expectedMs = expectedAt.getTime();
    return expectedMs < now.getTime();
  }

  _prepareDepartures(departures) {
    const destPattern = /(?: station(?: \([^)]+\))?| \([^)]+\))$/;
    const items = [];
    const self = this;

    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const expected = dep.expected || dep.scheduled;
      const expectedAt = expected ? new Date(expected) : null;
      const expectedMs = expectedAt ? expectedAt.getTime() : Number.POSITIVE_INFINITY;
      let destination = dep.destination || "";
      if (dep.line && dep.line.transport_mode === "TRAIN") {
        destination = destination.replace(destPattern, "").trim();
      }
      items.push(
        Object.assign({}, dep, {
          destination: destination,
          _rawDestination: dep.destination,
          _expectedMs: expectedMs,
        }),
      );
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
    if (transportMode === "METRO") {
      return "metro";
    }
    if (transportMode === "TRAIN") {
      return "train";
    }
    if (transportMode === "TRAM") {
      return "tram tram_" + designation;
    }
    return "train";
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
      return (
        html +
        '<div class="departures-empty">Inga avgångar inom ' +
        (this.config.forecast_minutes || 60) +
        " min.</div>"
      );
    }

    html +=
      '<div class="departures"><div class="row header"><div class="col icon"></div><div class="col main left">Linje</div><div class="col right">Avgång</div></div>';
    const now = new Date();
    const self = this;

    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      if (self._shouldHideDepartedDeparture(dep, now)) {
        continue;
      }
      const line = dep.line || {};
      const expectedAt = dep.expected ? new Date(dep.expected) : dep.scheduled ? new Date(dep.scheduled) : null;
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

  _updateDeparturePanel(siteId) {
    const panel = this.querySelector('.stop-accordion[data-site-id="' + siteId + '"] .stop-body');
    if (panel) {
      panel.innerHTML = this._renderDepartures(siteId);
    }
  }

  _onToggle(event) {
    const details = event.target.closest(".stop-accordion");
    if (!details || !this.contains(details)) {
      return;
    }
    const siteId = Number(details.dataset.siteId);
    if (!details.open) {
      if (this._openSiteId === siteId) {
        this._openSiteId = null;
      }
      this._syncRefreshTimer();
      return;
    }
    this._openSiteId = siteId;
    this._syncRefreshTimer();
    this._loadDepartures(siteId, false);
  }

  _updateView() {
    if (!this.config) {
      return;
    }

    try {
      this._renderView();
    } catch (error) {
      const root = this.querySelector(".sl-nearby-root");
      const message =
        '<div class="status-message error">Visningsfel: ' +
        this._escapeHtml((error && error.message) || String(error)) +
        "</div>";
      if (root) {
        root.innerHTML = message;
      } else {
        this.innerHTML = "<ha-card>" + message + "</ha-card>";
      }
    }
  }

  _renderView() {
    let root = this.querySelector(".sl-nearby-root");
    if (!root) {
      this.innerHTML =
        '<style>' +
        this._styles() +
        '</style><ha-card><div class="sl-nearby-root"></div></ha-card>';
      root = this.querySelector(".sl-nearby-root");
      root.addEventListener("toggle", (event) => this._onToggle(event), true);
    }

    const location = this._getSearchLocation();
    const stops = this._getNearestStops();
    let body = "";

    if (this._sitesError) {
      body = '<div class="status-message error">' + this._escapeHtml(this._sitesError) + "</div>";
    } else if (!this._sites) {
      body = '<div class="status-message">Laddar hållplatser…</div>';
    } else if (!location) {
      body =
        '<div class="status-message">Ingen GPS-position från ' +
        this._escapeHtml(this.config.location_entity) +
        ".</div>";
    } else if (!stops.length) {
      body = '<div class="status-message">Inga hållplatser hittades.</div>';
    } else {
      const self = this;
      body =
        '<div class="list-header"><strong>' +
        stops.length +
        " hållplatser</strong> — " +
        this._escapeHtml(this._locationNote || "") +
        "</div>";
      body += stops
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

    const listKey = stops.map((s) => s.id).join(",");
    if (this._lastListKey === listKey && this.querySelector(".stop-accordion")) {
      const header = root.querySelector(".list-header");
      if (header) {
        header.innerHTML =
          "<strong>" + stops.length + " hållplatser</strong> — " + this._escapeHtml(this._locationNote || "");
      }
      for (let i = 0; i < stops.length; i++) {
        const distEl = root.querySelector('.stop-accordion[data-site-id="' + stops[i].id + '"] .stop-distance');
        if (distEl) {
          distEl.textContent = this._formatDistance(stops[i].distance_m);
        }
      }
      return;
    }
    this._lastListKey = listKey;
    root.innerHTML = body;
  }

  _styles() {
    return [
      "ha-card{padding:0 0 12px}",
      ".list-header{padding:14px 16px 8px;font-size:.9rem;color:var(--secondary-text-color);border-bottom:1px solid var(--divider-color,rgba(0,0,0,.12))}",
      ".list-header strong{color:var(--primary-text-color)}",
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
      ".bus_red{background:#9e0e13}",
      ".metro{background:#0061eb}",
      ".train{background:#ec619f}",
      ".tram{background:#985141}",
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
if (!window.customCards.some(function (card) { return card.type === "ha-sl-nearby-stops-card"; })) {
  window.customCards.push({
    type: "ha-sl-nearby-stops-card",
    name: "SL närmaste hållplatser",
    preview: true,
    description: "Visar närmaste SL-hållplatser från GPS och avgångar i accordion.",
  });
}
