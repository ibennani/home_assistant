class SlNearbyCard extends HTMLElement {
  static getStubConfig() {
    return {
      location_entity: "person.ilias_bennani",
      home_zone_entity: "zone.home",
      reference_lat: 59.331136036994,
      reference_lon: 18.0576584245687,
      reference_name: "Stockholms central",
      max_stops: 20,
      max_gps_km: 200,
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
    try {
      const base = SlNearbyCard.getStubConfig();
      const input = config && typeof config === "object" ? config : {};
      this.config = Object.assign({}, base, input);
      this._locationNote = "";
      if (!this._departureCache) {
        this._departureCache = new Map();
      }
      this._updateView();
    } catch (error) {
      this.config = SlNearbyCard.getStubConfig();
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
      this._sitesPromise = fetch("/local/sl-sites.json?v=20260727s")
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

  _getReferenceLocation() {
    const lat = Number(this.config.reference_lat);
    const lon = Number(this.config.reference_lon);
    if (isFinite(lat) && isFinite(lon)) {
      return { lat: lat, lon: lon };
    }
    return { lat: 59.331136036994, lon: 18.0576584245687 };
  }

  _getSearchLocation() {
    const personLoc = this._readCoords(this.config.location_entity);
    const homeLoc = this._readCoords(this.config.home_zone_entity);
    const refLoc = this._getReferenceLocation();
    const refName = this.config.reference_name || "Stockholms central";
    const maxDistanceM = Number(this.config.max_gps_km || 200) * 1000;

    if (!personLoc && homeLoc) {
      this._locationNote = "Använder hemzon (ingen GPS)";
      return homeLoc;
    }
    if (!personLoc) {
      return null;
    }
    const distFromRef = this._haversineMeters(
      personLoc.lat,
      personLoc.lon,
      refLoc.lat,
      refLoc.lon,
    );
    if (distFromRef > maxDistanceM) {
      if (homeLoc) {
        this._locationNote =
          "GPS långt från " + refName + " — visar hållplatser nära hemzon";
        return homeLoc;
      }
      this._locationNote = "GPS långt från " + refName;
      return personLoc;
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
    const serviceData = { site_id: Number(siteId) };
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
    const msg = String(dev.message || dev.text || dev.title || "").toLowerCase();
    return msg.includes("kort tåg") || msg.includes("kort tag") || msg.includes("short train");
  }

  _isDelayDeviation(dev) {
    const msg = String(dev.message || dev.text || dev.title || "").toLowerCase();
    return (
      msg.includes("försen") ||
      msg.includes("senare") ||
      msg.includes("delay") ||
      msg.includes("delayed")
    );
  }

  _formatStopPointLabel(dep) {
    const stopPoint = dep && dep.stop_point;
    if (!stopPoint || !stopPoint.designation) {
      return "";
    }
    const designation = String(stopPoint.designation).trim();
    if (!designation) {
      return "";
    }
    const mode = String((dep.line && dep.line.transport_mode) || "").toUpperCase();
    if (mode === "TRAIN" || mode === "METRO") {
      return "Spår " + designation;
    }
    return "Läge " + designation;
  }

  _formatLineTypeLabel(dep) {
    const lineType = dep && dep.line && dep.line.group_of_lines;
    if (!lineType) {
      return "";
    }
    const label = String(lineType).trim();
    return label || "";
  }

  _buildDepartureDetailItems(dep) {
    const self = this;
    const items = [];
    const stopPointLabel = self._formatStopPointLabel(dep);
    if (stopPointLabel) {
      items.push({ text: stopPointLabel, className: "stop-point-label" });
    }
    const lineTypeLabel = self._formatLineTypeLabel(dep);
    if (lineTypeLabel) {
      items.push({ text: lineTypeLabel, className: "line-type-label" });
    }
    const deviations = dep.deviations || [];
    const isShortTrain = deviations.some(function (dev) {
      return self._isShortTrainDeviation(dev);
    });
    const otherDeviations = deviations.filter(function (dev) {
      return !self._isShortTrainDeviation(dev) && !self._isDelayDeviation(dev);
    });
    if (isShortTrain) {
      items.push({ text: "kort tåg", className: "short-train" });
    }
    for (let i = 0; i < otherDeviations.length; i++) {
      const dev = otherDeviations[i];
      const text = dev.message || dev.text || dev.title;
      if (text) {
        items.push({ text: text, className: "warning-message" });
      }
    }
    return items;
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

  _lineIconClass(transportMode, line, groupOfLines) {
    const designation = String(line || "");
    if (transportMode === "BUS") {
      return groupOfLines === "blåbuss"
        ? "bus bus_" + designation + " blue"
        : "bus_red bus_" + designation;
    }
    if (transportMode === "METRO") {
      let cls = "metro metro_" + designation;
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
    if (transportMode === "TRAM") {
      return "tram tram_" + designation;
    }
    if (transportMode === "TRAIN") {
      return "train";
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

    const stopInfo = (cache.stop_deviations || [])
      .map(function (dev) {
        return (
          '<div class="stop-info-item">' +
          this._escapeHtml(dev.message || dev.text || dev.title || "") +
          "</div>"
        );
      }, this)
      .join("");
    const stopInfoBlock = stopInfo ? '<div class="stop-info">' + stopInfo + "</div>" : "";

    const departures = cache.departures || [];
    if (!departures.length) {
      return (
        stopInfoBlock +
        '<div class="departures-empty">Inga avgångar inom ' +
        (this.config.forecast_minutes || 60) +
        " min.</div>"
      );
    }

    const now = new Date();
    const self = this;
    let rows = "";
    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const scheduledAt = self._parseDate(dep.scheduled);
      const expectedAt = self._parseDate(dep.expected) || scheduledAt;
      const diff = expectedAt ? self._diffMinutes(expectedAt, now) : 0;
      const isAtPlatform = diff === 0;
      const isDeparted = diff < 0;
      const isCancelled = self._isCancelled(dep);
      const isDelayed = !isCancelled && self._isDelayed(scheduledAt, expectedAt);
      const detailItems = self._buildDepartureDetailItems(dep);

      let departureTime = "";
      if (isCancelled) {
        departureTime = '<span class="cancelled-time">Inställd</span>';
      } else if (isDelayed && scheduledAt && expectedAt) {
        const newTime = self.config.show_time_always
          ? self._formatClock(expectedAt)
          : isAtPlatform
            ? "Nu"
            : self._formatClock(expectedAt);
        departureTime =
          '<span class="old-time">' +
          self._formatClock(scheduledAt) +
          '</span><span class="new-time">' +
          newTime +
          "</span>";
      } else if (expectedAt) {
        departureTime = self.config.show_time_always
          ? self._formatClock(expectedAt)
          : isAtPlatform
            ? "Nu"
            : self._formatClock(expectedAt);
      }

      const line = dep.line || {};
      const icon = self._transportIcon(line.transport_mode);
      const lineClass = self._lineIconClass(
        line.transport_mode,
        line.designation,
        line.group_of_lines,
      );

      let detailRow = "";
      if (detailItems.length) {
        detailRow =
          '<div class="row detail-row"><div class="col icon"></div><div class="col icon"></div>' +
          '<div class="col main left detail-messages">' +
          detailItems
            .map(function (item) {
              return (
                '<span class="detail-item ' +
                item.className +
                '">' +
                self._escapeHtml(item.text) +
                "</span>"
              );
            })
            .join("") +
          '</div><div class="col right"></div></div>';
      }

      rows +=
        '<div class="departure-block' +
        (isDeparted ? " departed" : "") +
        '"><div class="row departure">' +
        '<div class="col icon"><ha-icon class="transport-icon" icon="' +
        icon +
        '"></ha-icon></div>' +
        '<div class="col icon"><span class="line-icon mr1 ' +
        lineClass +
        '">' +
        self._escapeHtml(line.designation || "") +
        "</span></div>" +
        '<div class="col main left">' +
        self._escapeHtml(dep.destination || "") +
        '</div><div class="col right"><span class="leaves-in">' +
        departureTime +
        "</span></div></div>" +
        detailRow +
        "</div>";
    }

    return (
      stopInfoBlock +
      '<div class="departures"><div class="row header"><div class="col icon"></div><div class="col main left">Linje</div><div class="col right">Avgång</div></div>' +
      rows +
      "</div>"
    );
  }

  _formatListHeader(count) {
    let html = '<div class="list-header"><strong>' + count + " hållplatser</strong>";
    if (this._locationNote) {
      html +=
        '<div class="location-note">' + this._escapeHtml(this._locationNote) + "</div>";
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
      const root = this.querySelector(".sl-card-root");
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
    let root = this.querySelector(".sl-card-root");
    if (!root) {
      this.innerHTML =
        '<style>' +
        this._styles() +
        '</style><ha-card><div class="sl-card-root"></div></ha-card>';
      root = this.querySelector(".sl-card-root");
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
      body = self._formatListHeader(stops.length);
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

    const listKey =
      stops.map((s) => s.id).join(",") + "|" + (this._locationNote || "");
    if (this._lastListKey === listKey && this.querySelector(".stop-accordion")) {
      const header = root.querySelector(".list-header");
      if (header) {
        header.outerHTML = this._formatListHeader(stops.length);
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
      ".location-note{color:#fad370!important;font-size:smaller;line-height:1.35;margin-top:4px}",
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
      ".departure.departed>.main,.departure-block.departed .main{text-decoration:line-through;color:var(--secondary-text-color)}",
      ".row{margin-top:8px;display:flex;justify-content:space-between}",
      ".col{display:flex;flex-direction:column;justify-content:center;position:relative}",
      ".col.icon{flex-basis:40px}",
      ".row.header{height:40px;font-size:medium;font-weight:400;opacity:var(--dark-primary-opacity)}",
      ".main{flex:2}",
      ".transport-icon{width:40px;height:40px;display:inline-flex;justify-content:center;align-items:center}",
      ".line-icon{border-radius:3px;padding:3px 3px 0 3px;color:#fff;min-width:22px;height:22px;font-weight:500;display:inline-block;text-align:center;text-shadow:1px 1px 2px var(--outline-color)}",
      ".bus{border:1px solid var(--outline-color);color:var(--primary-text-color)}",
      ".bus_red,.bus.red,.red{background-color:#9e0e13;color:#fff;border:none}",
      ".blue{background-color:#0089ca}",
      ".green{background-color:#179d4d}",
      ".metro{background:#0061eb}",
      ".train{background:#ec619f}",
      ".tram{background:#985141}",
      ".warning-message{color:var(--warning-color);font-size:smaller}",
      ".departure-block{margin-top:8px}",
      ".departure-block .row.departure{margin-top:0}",
      ".row.detail-row{margin-top:2px}",
      ".row.detail-row .detail-messages{display:flex;flex-direction:column;gap:2px}",
      ".detail-item{font-size:smaller;line-height:1.3}",
      ".stop-point-label,.line-type-label{color:#fad370!important;font-weight:500}",
      ".stop-info{margin:0 8px 8px;padding:8px 12px 0;font-size:smaller;line-height:1.35;color:#fad370!important;border-top:1px solid var(--divider-color,rgba(0,0,0,.12))}",
      ".stop-info-item{color:#fad370!important}",
      ".stop-info-item+.stop-info-item{margin-top:6px}",
      ".short-train{color:#0abcfc;font-size:smaller;font-weight:600;margin-left:.35em;text-transform:lowercase}",
      ".old-time{text-decoration:line-through;opacity:.65;margin-right:.35em}",
      ".new-time{color:#0abcfc;font-weight:600}",
      ".cancelled-time{color:#e53935;font-weight:600}",
      ".leaves-in{white-space:nowrap}",
      ".mr1{margin-right:8px}",
      ".left{text-align:left}",
      ".right{text-align:right}",
      "ha-icon{width:24px;height:24px;color:var(--paper-item-icon-color)}",
    ].join("");
  }
}

if (!customElements.get("sl-nearby-card")) {
  customElements.define("sl-nearby-card", SlNearbyCard);
}
if (!customElements.get("ha-sl-nearby-stops-card")) {
  customElements.define("ha-sl-nearby-stops-card", SlNearbyCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some(function (card) { return card.type === "sl-nearby-card"; })) {
  window.customCards.push({
    type: "sl-nearby-card",
    name: "SL närmaste hållplatser",
    preview: true,
    description: "Visar närmaste SL-hållplatser från GPS och avgångar i accordion.",
  });
}
if (!window.customCards.some(function (card) { return card.type === "ha-sl-nearby-stops-card"; })) {
  window.customCards.push({
    type: "ha-sl-nearby-stops-card",
    name: "SL närmaste hållplatser (alias)",
    preview: false,
    description: "Alias för sl-nearby-card.",
  });
}
