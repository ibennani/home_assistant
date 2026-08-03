class SlNearbyCard extends HTMLElement {
  static get CARD_VERSION() {
    return "20260803a";
  }

  static getStubConfig() {
    return {
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
      refresh_seconds: 15,
      location_refresh_seconds: 15,
      sites_cache_version: "20260803a",
    };
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  _ensureCaches() {
    if (!this._departureCache) {
      this._departureCache = new Map();
    }
    if (!this._modeFilters) {
      this._modeFilters = new Map();
    }
  }

  setConfig(config) {
    try {
      const base = SlNearbyCard.getStubConfig();
      const input = config && typeof config === "object" ? config : {};
      this.config = Object.assign({}, base, input);
      this._ensureCaches();
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
    this._ensureCaches();
    const prevLocationKey = this._locationKey;
    this._hass = hass;
    const nextLocationKey = this._getLocationKey();
    this._locationKey = nextLocationKey;
    if (prevLocationKey !== undefined && prevLocationKey !== nextLocationKey) {
      this._departureCache.clear();
      this._openSiteId = null;
      this._lastListKey = null;
    }
    this._ensureBusLineTerminusLabels();
    this._updateView();
    this._syncRefreshTimer();
    this._syncLocationRefreshTimer();
  }

  _ensureBusLineTerminusLabels() {
    const api = window.SlDepartureTime;
    if (!api || !api.ensureBusLineTerminus || this._busLineTerminusBound) {
      return;
    }
    this._busLineTerminusBound = true;
    const self = this;
    api.ensureBusLineTerminus("20260729x").then(function () {
      self._updateView();
    });
  }

  connectedCallback() {
    this._ensureCaches();
    if (this._cardVersion !== SlNearbyCard.CARD_VERSION) {
      this._cardVersion = SlNearbyCard.CARD_VERSION;
      this._lastListKey = null;
    }
    if (!this._cardClickBound) {
      this._cardClickBound = true;
      this.addEventListener("click", (event) => this._onCardClick(event), true);
      this.addEventListener(
        "touchend",
        (event) => {
          if (event.target.closest(".departure-block")) {
            event.preventDefault();
            this._onCardClick(event);
          }
        },
        { capture: true, passive: false },
      );
    }
    this._ensureModalStyles();
    this._ensureSitesLoaded().then(() => this._updateView());
    this._ensureVisibilityObserver();
    this._syncRefreshTimer();
  }

  disconnectedCallback() {
    if (this._locationRefreshTimer) {
      clearInterval(this._locationRefreshTimer);
      this._locationRefreshTimer = undefined;
    }
    if (this._visibilityObserver) {
      this._visibilityObserver.disconnect();
      this._visibilityObserver = undefined;
    }
    this._locationRefreshActive = false;
    this._isVisible = false;
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
    }
    if (this._departureClock) {
      this._departureClock.stop();
      this._departureClock = undefined;
    }
    if (this._departureClockTimer) {
      clearInterval(this._departureClockTimer);
      this._departureClockTimer = undefined;
    }
    this._closeLineRouteModal();
  }

  _getOpenDepartures() {
    if (!this._openSiteId) {
      return [];
    }
    const cache = this._getCache().get(String(this._openSiteId));
    if (!cache || !cache.departures) {
      return [];
    }
    return this._filterDeparturesByMode(cache.departures, this._openSiteId);
  }

  _ensureDepartureClock() {
    if (this._departureClock) {
      return this._departureClock;
    }
    const clockApi = window.SlDepartureTime && window.SlDepartureTime.createAdaptiveClock;
    if (!clockApi) {
      return null;
    }
    const self = this;
    this._departureClock = clockApi({
      getDepartures: function () {
        return self._getOpenDepartures();
      },
      onTick: function () {
        if (self._openSiteId) {
          self._updateDeparturePanel(self._openSiteId);
        }
      },
    });
    return this._departureClock;
  }

  _syncDepartureClock() {
    if (this._departureClock) {
      this._departureClock.stop();
    }
    if (this._departureClockTimer) {
      clearInterval(this._departureClockTimer);
      this._departureClockTimer = undefined;
    }
    if (!this._openSiteId) {
      return;
    }
    const clock = this._ensureDepartureClock();
    if (clock) {
      clock.start();
      return;
    }
    const self = this;
    this._departureClockTimer = window.setInterval(function () {
      if (self._openSiteId) {
        self._updateDeparturePanel(self._openSiteId);
      }
    }, 15000);
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
      this._sitesPromise = fetch("/local/sl-sites.json?v=" + (this.config.sites_cache_version || SlNearbyCard.CARD_VERSION))
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

  _resolveLoggedInPersonEntity() {
    if (!this._hass || !this._hass.user || !this._hass.user.id) {
      return null;
    }
    const userId = this._hass.user.id;
    const states = this._hass.states;
    const ids = Object.keys(states);
    for (let i = 0; i < ids.length; i++) {
      const entityId = ids[i];
      if (!entityId.startsWith("person.")) {
        continue;
      }
      const state = states[entityId];
      if (state && state.attributes && state.attributes.user_id === userId) {
        return entityId;
      }
    }
    return null;
  }

  _getLocationEntity() {
    return this._resolveLoggedInPersonEntity();
  }

  _getLocationLabel() {
    const entityId = this._getLocationEntity();
    if (!entityId || !this._hass || !this._hass.states[entityId]) {
      return entityId || "okänd användare";
    }
    return this._hass.states[entityId].attributes.friendly_name || entityId;
  }

  _getLocationKey() {
    const entityId = this._getLocationEntity();
    if (!entityId) {
      return "none";
    }
    const coords = this._readCoords(entityId);
    if (!coords) {
      return entityId + ":none";
    }
    return entityId + ":" + coords.lat.toFixed(4) + "," + coords.lon.toFixed(4);
  }

  _notifyServiceForPerson(personEntityId) {
    if (!personEntityId || !this._hass) {
      return null;
    }
    const person = this._hass.states[personEntityId];
    if (!person || !person.attributes) {
      return null;
    }
    const candidates = [];
    const source = person.attributes.source;
    if (source && String(source).indexOf("device_tracker.") === 0) {
      candidates.push(source);
    }
    const trackers = person.attributes.device_trackers || [];
    for (let i = 0; i < trackers.length; i++) {
      if (candidates.indexOf(trackers[i]) < 0) {
        candidates.push(trackers[i]);
      }
    }
    for (let j = 0; j < candidates.length; j++) {
      const suffix = String(candidates[j]).replace(/^device_tracker\./, "");
      if (suffix) {
        return "mobile_app_" + suffix;
      }
    }
    return null;
  }

  _requestLocationUpdate() {
    if (!this._hass) {
      return;
    }
    const personEntity = this._getLocationEntity();
    const service = this._notifyServiceForPerson(personEntity);
    if (!service) {
      return;
    }
    this._hass
      .callService("notify", service, {
        message: "request_location_update",
      })
      .catch(function () {
        /* telefonen kanske inte är tillgänglig */
      });
  }

  _ensureVisibilityObserver() {
    if (this._visibilityObserver || typeof IntersectionObserver === "undefined") {
      if (!this._visibilityObserver) {
        this._isVisible = true;
        this._syncLocationRefreshTimer();
      }
      return;
    }
    const self = this;
    this._visibilityObserver = new IntersectionObserver(
      function (entries) {
        const visible = entries.some(function (entry) {
          return entry.isIntersecting && entry.intersectionRatio > 0;
        });
        if (self._isVisible === visible) {
          return;
        }
        self._isVisible = visible;
        self._syncLocationRefreshTimer();
      },
      { threshold: [0, 0.01] },
    );
    this._visibilityObserver.observe(this);
  }

  _syncLocationRefreshTimer() {
    const seconds = Number((this.config && this.config.location_refresh_seconds) || 15);
    if (this._locationRefreshTimer) {
      clearInterval(this._locationRefreshTimer);
      this._locationRefreshTimer = undefined;
    }

    const shouldRun = !!(this._isVisible && this._hass);
    if (!shouldRun) {
      this._locationRefreshActive = false;
      return;
    }

    const justBecameVisible = !this._locationRefreshActive;
    this._locationRefreshActive = true;

    if (justBecameVisible) {
      this._requestLocationUpdate();
    }

    if (!seconds || seconds < 5) {
      return;
    }

    const self = this;
    this._locationRefreshTimer = window.setInterval(function () {
      self._requestLocationUpdate();
    }, seconds * 1000);
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
    const locationEntity = this._getLocationEntity();
    const personLoc = locationEntity ? this._readCoords(locationEntity) : null;
    const homeLoc = this._readCoords(this.config.home_zone_entity);
    const refLoc = this._getReferenceLocation();
    const maxDistanceM = Number(this.config.max_gps_km || 200) * 1000;

    if (!personLoc && homeLoc) {
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
        return homeLoc;
      }
      return personLoc;
    }
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
    if (result.service_response && result.service_response.content) {
      const content = result.service_response.content;
      return {
        departures: content.departures || [],
        stop_deviations: content.stop_deviations || [],
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
    if (result.departures || result.stop_deviations || result.routes || result.journeys || result.locations) {
      return result;
    }
    return {};
  }

  _escapeJsString(value) {
    return String(value || "")
      .replace(/\\/g, "\\\\")
      .replace(/'/g, "\\'")
      .replace(/\n/g, "\\n");
  }

  openDepartureModal(siteId, departureKey) {
    const numericSiteId = Number(siteId);
    const dep = this._findDepartureByKey(numericSiteId, departureKey);
    if (!dep) {
      this._showModalMessage("Avgång", "Kunde inte läsa avgången.", true);
      return;
    }
    this._openLineRouteModal(dep, numericSiteId, this._getSiteName(numericSiteId));
  }

  _unwrapServiceResponse(result) {
    if (!result) {
      return {};
    }
    if (typeof result === "string") {
      try {
        return this._unwrapServiceResponse(JSON.parse(result));
      } catch (error) {
        return {};
      }
    }
    if (result.journeys || result.locations) {
      return result;
    }
    if (result.content && (result.content.journeys || result.content.locations)) {
      return result.content;
    }
    if (result.service_response) {
      return this._unwrapServiceResponse(result.service_response);
    }
    if (result.response) {
      return this._unwrapServiceResponse(result.response);
    }
    const keys = Object.keys(result);
    if (keys.length === 1) {
      return this._unwrapServiceResponse(result[keys[0]]);
    }
    return result;
  }

  _callWithResponse(domain, service, serviceData) {
    const self = this;
    if (this._hass && this._hass.connection && this._hass.connection.sendMessagePromise) {
      return this._hass.connection
        .sendMessagePromise({
          type: "call_service",
          domain: domain,
          service: service,
          service_data: serviceData,
          return_response: true,
        })
        .then(function (msg) {
          return self._unwrapServiceResponse((msg && msg.response) || msg || {});
        });
    }
    if (this._hass && this._hass.callApi) {
      return this._hass
        .callApi(
          "POST",
          "services/" + domain + "/" + service + "?return_response",
          serviceData,
        )
        .then(function (result) {
          return self._unwrapServiceResponse(result);
        });
    }
    if (this._hass && this._hass.callService) {
      return this._hass
        .callService(domain, service, serviceData, undefined, true)
        .then(function (result) {
          return self._unwrapServiceResponse(result);
        });
    }
    return Promise.reject(new Error("Kunde inte anropa Home Assistant"));
  }

  _callDepartures(siteId) {
    const serviceData = { site_id: Number(siteId) };
    return this._callWithResponse("rest_command", "sl_site_departures", serviceData).then(
      (result) => this._extractPayload(result),
    );
  }

  _transportModeLabel(mode) {
    const labels = {
      BUS: "Buss",
      TRAIN: "Pendeltåg",
      METRO: "Tunnelbana",
      TRAM: "Spårvagn",
      SHIP: "Båt",
      FERRY: "Båt",
    };
    return labels[String(mode || "").toUpperCase()] || mode || "Övrigt";
  }

  _getTransportModes(departures) {
    const modes = [];
    const seen = new Set();
    for (let i = 0; i < (departures || []).length; i++) {
      const mode = String((departures[i].line && departures[i].line.transport_mode) || "").toUpperCase();
      if (!mode || seen.has(mode)) {
        continue;
      }
      seen.add(mode);
      modes.push(mode);
    }
    modes.sort();
    return modes;
  }

  _getActiveModeFilter(siteId) {
    return this._modeFilters.get(String(siteId)) || "ALL";
  }

  _setActiveModeFilter(siteId, mode) {
    this._modeFilters.set(String(siteId), mode || "ALL");
  }

  _filterDeparturesByMode(departures, siteId) {
    const active = this._getActiveModeFilter(siteId);
    if (active === "ALL") {
      return departures;
    }
    return departures.filter(function (dep) {
      const mode = String((dep.line && dep.line.transport_mode) || "").toUpperCase();
      return mode === active;
    });
  }

  _renderModeFilters(siteId, modes) {
    if (!modes || modes.length <= 1) {
      return "";
    }
    const self = this;
    const active = this._getActiveModeFilter(siteId);
    let html = '<div class="mode-filters" data-site-id="' + siteId + '">';
    html +=
      '<button type="button" class="mode-filter' +
      (active === "ALL" ? " active" : "") +
      '" data-site-id="' +
      siteId +
      '" data-mode="ALL">Alla</button>';
    modes.forEach(function (mode) {
      html +=
        '<button type="button" class="mode-filter' +
        (active === mode ? " active" : "") +
        '" data-site-id="' +
        siteId +
        '" data-mode="' +
        self._escapeHtml(mode) +
        '">' +
        self._escapeHtml(self._transportModeLabel(mode)) +
        "</button>";
    });
    html += "</div>";
    return html;
  }

  _renderFiltersBlock(siteId, modes) {
    const filters = this._renderModeFilters(siteId, modes);
    if (!filters) {
      return "";
    }
    return '<div class="mode-filters-wrap">' + filters + "</div>";
  }

  _syncRefreshTimer() {
    const seconds = Number((this.config && this.config.refresh_seconds) || 0);
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
    }
    if (!seconds || seconds < 10 || !this._openSiteId) {
      return;
    }
    const self = this;
    this._refreshTimer = window.setInterval(function () {
      if (self._openSiteId) {
        self._loadDepartures(self._openSiteId, true);
      }
    }, seconds * 1000);
  }

  _hasDepartureCache(entry) {
    return !!(entry && !entry.loading && (entry.fetched_at || entry.error));
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
    if (!force && this._hasDepartureCache(existing)) {
      this._updateDeparturePanel(siteId);
      return;
    }

    const showCachedWhileRefreshing = force && this._hasDepartureCache(existing);
    if (!showCachedWhileRefreshing) {
      if (!this._departureInflight) {
        this._departureInflight = {};
      }
      this._departureInflight[cacheKey] = true;
      cache.set(cacheKey, { loading: true });
      this._updateDeparturePanel(siteId);
    } else {
      if (!this._departureInflight) {
        this._departureInflight = {};
      }
      this._departureInflight[cacheKey] = true;
    }

    const self = this;
    self
      ._callDepartures(siteId)
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
        if (showCachedWhileRefreshing && existing) {
          cache.set(cacheKey, Object.assign({}, existing, { loading: false }));
        } else {
          cache.set(cacheKey, {
            loading: false,
            error: (error && error.message) || "Kunde inte hämta avgångar",
          });
        }
        self._updateDeparturePanel(siteId);
      })
      .then(function () {
        self._departureInflight[cacheKey] = false;
      });
  }

  _prefetchDepartures(stops) {
    const self = this;
    let chain = Promise.resolve();
    stops.forEach(function (stop, index) {
      chain = chain.then(function () {
        const cacheKey = String(stop.id);
        const existing = self._getCache().get(cacheKey);
        if (existing && (existing.fetched_at || existing.error)) {
          self._updateDeparturePanel(stop.id);
          return null;
        }
        return new Promise(function (resolve) {
          window.setTimeout(function () {
            self._loadDepartures(stop.id, false);
            resolve();
          }, Math.min(index, 8) * 200);
        });
      });
    });
    return chain;
  }

  _shouldHideDeparted(expectedAt, now) {
    const hideDeparted = !this.config || this.config.hide_departed !== false;
    if (window.SlDepartureTime && window.SlDepartureTime.shouldHideDeparted) {
      return window.SlDepartureTime.shouldHideDeparted(expectedAt, now, hideDeparted);
    }
    return hideDeparted && expectedAt ? this._isDeparted(expectedAt, now) : false;
  }

  _sortDeparturesByTime(departures) {
    if (window.SlDepartureTime && window.SlDepartureTime.sortDeparturesByTime) {
      return window.SlDepartureTime.sortDeparturesByTime(departures);
    }
    return (departures || []).slice().sort(function (a, b) {
      const aMs = new Date(a.expected || a.scheduled || 0).getTime();
      const bMs = new Date(b.expected || b.scheduled || 0).getTime();
      return aMs - bMs;
    });
  }

  _formatDepartureLabel(dep) {
    const api = window.SlDepartureTime;
    if (api && api.formatDepartureLabel) {
      return api.formatDepartureLabel(dep);
    }
    return String((dep && dep.destination) || (dep && dep.direction) || "").trim();
  }

  _prepareDepartures(departures) {
    const now = new Date();
    const items = [];
    const self = this;

    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const expected = dep.expected || dep.scheduled;
      const expectedAt = expected ? new Date(expected) : null;
      const expectedMs = expectedAt ? expectedAt.getTime() : Number.POSITIVE_INFINITY;
      const destination = self._formatDepartureLabel(dep);
      if (self._shouldHideDeparted(expectedAt, now)) {
        continue;
      }
      items.push(Object.assign({}, dep, { destination: destination, _expectedMs: expectedMs }));
    }

    return self._sortDeparturesByTime(items);
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

  _isDeparted(expectedAt, now) {
    if (window.SlDepartureTime && window.SlDepartureTime.isDeparted) {
      return window.SlDepartureTime.isDeparted(expectedAt, now);
    }
    return expectedAt ? this._diffMinutes(expectedAt, now) < 0 : false;
  }

  _formatDepartureDisplay(scheduledAt, expectedAt, now) {
    const self = this;
    if (window.SlDepartureTime && window.SlDepartureTime.formatHtml) {
      return window.SlDepartureTime.formatHtml(scheduledAt, expectedAt, now, function (date) {
        return self._formatClock(date);
      });
    }
    if (!expectedAt) {
      return "";
    }
    const diff = self._diffMinutes(expectedAt, now);
    if (diff <= 0) {
      return '<span class="departure-now">Nu</span>';
    }
    return self._formatClock(expectedAt);
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

  _renderDepartureMeta(detailItems) {
    if (!detailItems.length) {
      return "";
    }
    const self = this;
    return (
      '<div class="departure-meta">' +
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
      "</div>"
    );
  }

  _renderDepartureRow(dep, extraClass, key, now, siteId) {
    const self = this;
    const scheduledAt = self._parseDate(dep.scheduled);
    const expectedAt = self._parseDate(dep.expected) || scheduledAt;
    const isCancelled = self._isCancelled(dep);
    const detailItems = self._buildDepartureDetailItems(dep);

    let departureTime = "";
    if (isCancelled) {
      departureTime = '<span class="cancelled-time">Inställd</span>';
    } else if (expectedAt) {
      departureTime = self._formatDepartureDisplay(scheduledAt, expectedAt, now);
    }

    const line = dep.line || {};
    const icon = self._transportIcon(line.transport_mode);
    const lineClass = self._lineIconClass(
      line.transport_mode,
      line.designation,
      line.group_of_lines,
    );
    const detailMeta = self._renderDepartureMeta(detailItems);

    return (
      '<div class="departure-block' +
      (extraClass || "") +
      '" data-site-id="' +
      String(siteId) +
      '" data-departure-key="' +
      self._escapeHtml(key) +
      '" role="button" tabindex="0" title="Visa kvarvarande hållplatser"><div class="row departure">' +
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
      detailMeta +
      "</div>"
    );
  }

  _buildDepartureRows(departures, siteId, now) {
    const self = this;
    let activeDeps = [];
    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const expectedAt = self._parseDate(dep.expected) || self._parseDate(dep.scheduled);
      if (self._shouldHideDeparted(expectedAt, now)) {
        continue;
      }
      activeDeps.push(dep);
    }
    activeDeps = self._sortDeparturesByTime(activeDeps);

    const anim = window.SlDepartureListAnim;
    if (anim && anim.manager) {
      return anim.manager.buildRows(String(siteId), {
        activeDeps: activeDeps,
        allDeps: departures,
        now: now,
        shouldHideDeparted: function (dep, currentNow) {
          const expectedAt = self._parseDate(dep.expected) || self._parseDate(dep.scheduled);
          return self._shouldHideDeparted(expectedAt, currentNow);
        },
        renderRow: function (dep, extraClass, key) {
          return self._renderDepartureRow(dep, extraClass, key, now, siteId);
        },
      });
    }

    let rows = "";
    for (let j = 0; j < activeDeps.length; j++) {
      const key =
        anim && anim.departureKey
          ? anim.departureKey(activeDeps[j])
          : String(j);
      rows += self._renderDepartureRow(activeDeps[j], "", key, now, siteId);
    }
    return rows;
  }

  _runDepartureListAnimation(siteId, panel) {
    const anim = window.SlDepartureListAnim;
    if (!anim || !panel) {
      return;
    }
    const listEl = panel.querySelector(".departures-list");
    if (!listEl) {
      return;
    }
    const self = this;
    anim.manager.afterRender(String(siteId), listEl, function () {
      self._updateDeparturePanel(siteId);
    });
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

    const allDepartures = cache.departures || [];
    const modes = this._getTransportModes(allDepartures);
    const filtersBlock = this._renderFiltersBlock(siteId, modes);
    const departures = this._filterDeparturesByMode(allDepartures, siteId);

    if (!departures.length) {
      return (
        stopInfoBlock +
        filtersBlock +
        '<div class="departures-empty">Inga avgångar' +
        (modes.length > 1 ? " för valt trafikslag" : "") +
        " inom " +
        (this.config.forecast_minutes || 60) +
        " min.</div>"
      );
    }

    const now = new Date();
    const rows = this._buildDepartureRows(departures, siteId, now);

    return (
      stopInfoBlock +
      filtersBlock +
      '<div class="departures departures-list"><div class="row header"><div class="col icon"></div><div class="col icon"></div><div class="col main left">Linje</div><div class="col right">Avgång</div></div>' +
      rows +
      "</div>"
    );
  }

  _updateDeparturePanel(siteId) {
    const panel = this.querySelector('.stop-accordion[data-site-id="' + siteId + '"] .stop-body');
    if (!panel) {
      return;
    }
    const scopeId = String(siteId);
    const anim = window.SlDepartureListAnim;
    if (anim && anim.manager.isAnimating(scopeId)) {
      return;
    }
    panel.innerHTML = this._renderDepartures(siteId);
    this._runDepartureListAnimation(siteId, panel);
    if (this._departureClock) {
      this._departureClock.reschedule();
    }
  }

  _renderStopSummary(stop) {
    return (
      '<div class="stop-summary-content">' +
      '<div class="stop-header-row">' +
      '<h1 class="card-header"><div class="name">' +
      this._escapeHtml(stop.name) +
      '</div></h1><span class="stop-distance">' +
      this._formatDistance(stop.distance_m) +
      "</span></div></div>"
    );
  }

  _normalizeStopName(name) {
    return String(name || "")
      .trim()
      .toLowerCase()
      .replace(/^stockholm,\s*/i, "");
  }

  _resolveSiteIdByName(name) {
    const target = this._normalizeStopName(name);
    if (!target || !this._sites || !this._sites.length) {
      return null;
    }
    let bestId = null;
    let bestScore = -1;
    for (let i = 0; i < this._sites.length; i++) {
      const site = this._sites[i];
      const siteName = this._normalizeStopName(site.name);
      if (!siteName) {
        continue;
      }
      if (target === siteName) {
        return Number(site.id);
      }
      if (target.includes(siteName) || siteName.includes(target)) {
        const score = siteName.length;
        if (score > bestScore) {
          bestScore = score;
          bestId = Number(site.id);
        }
      }
    }
    return bestId;
  }

  _siteGid(siteId) {
    return "909100100000" + String(siteId);
  }

  _pickStopFinderLocation(payload, destination) {
    const locations = (payload && payload.locations) || [];
    const target = this._normalizeStopName(destination);
    let best = null;
    let bestScore = -1;
    for (let i = 0; i < locations.length; i++) {
      const location = locations[i];
      const name = this._normalizeStopName(location.name);
      if (!name || !location.id) {
        continue;
      }
      let score = 0;
      if (target && (target === name || target.includes(name) || name.includes(target))) {
        score = 100 + name.length;
      } else if (String(location.name || "").indexOf("Stockholm") >= 0) {
        score = 10;
      }
      if (score > bestScore) {
        bestScore = score;
        best = location;
      }
    }
    return best;
  }

  _dedupeStopNames(stops) {
    const result = [];
    let lastName = "";
    for (let i = 0; i < (stops || []).length; i++) {
      const name = String((stops[i] && stops[i].name) || "").trim();
      if (!name || name === lastName) {
        continue;
      }
      result.push({ name: name });
      lastName = name;
    }
    return result;
  }

  _extractDepartureStops(payload, dep, siteId, siteName) {
    const line = (dep && dep.line) || {};
    const designation = String(line.designation || "").trim();
    const journeys = (payload && payload.journeys) || [];
    let bestStops = [];

    for (let i = 0; i < journeys.length; i++) {
      const legs = journeys[i].legs || [];
      for (let j = 0; j < legs.length; j++) {
        const leg = legs[j];
        const transport = leg.transportation || {};
        const number = String(transport.number || "");
        const disassembled = String(transport.disassembledName || "");
        if (
          designation &&
          number.indexOf(designation) < 0 &&
          disassembled.indexOf(designation) < 0
        ) {
          continue;
        }
        const stops = [];
        const sequence = leg.stopSequence || [];
        for (let k = 0; k < sequence.length; k++) {
          const point = sequence[k];
          const parent = point.parent || {};
          const name = parent.disassembledName || point.disassembledName || point.name;
          if (name) {
            stops.push({ name: String(name).trim() });
          }
        }
        if (stops.length > bestStops.length) {
          bestStops = stops;
        }
      }
    }

    bestStops = this._dedupeStopNames(bestStops);
    if (!bestStops.length) {
      return [];
    }

    const stopAreaName = dep && dep.stop_area && dep.stop_area.name;
    const currentIndex = this._findCurrentStopIndex(bestStops, siteId, stopAreaName || siteName);
    if (currentIndex >= 0) {
      return bestStops.slice(currentIndex);
    }
    return bestStops;
  }

  _resolveDestinationGid(dep) {
    const destination = String((dep && dep.destination) || (dep && dep.direction) || "").trim();
    if (!destination) {
      return Promise.resolve(null);
    }
    const siteId = this._resolveSiteIdByName(destination);
    if (siteId) {
      return Promise.resolve(this._siteGid(siteId));
    }
    const self = this;
    return this._callWithResponse("rest_command", "sl_stop_finder", {
      name: destination,
    })
      .then(function (payload) {
        let location = self._pickStopFinderLocation(self._unwrapServiceResponse(payload), destination);
        if (location && location.id) {
          return String(location.id);
        }
        return self
          ._callWithResponse("rest_command", "sl_stop_finder", {
            name: destination + ", Stockholm",
          })
          .then(function (retryPayload) {
            location = self._pickStopFinderLocation(
              self._unwrapServiceResponse(retryPayload),
              destination,
            );
            return location && location.id ? String(location.id) : null;
          });
      });
  }

  _journeyMotParams(dep) {
    const mode = String((dep && dep.line && dep.line.transport_mode) || "").toUpperCase();
    const params = {
      incl_mot_0: "false",
      incl_mot_2: "false",
      incl_mot_3: "false",
      incl_mot_4: "false",
      incl_mot_5: "false",
      incl_mot_9: "false",
    };
    if (mode === "BUS") {
      params.incl_mot_5 = "true";
      return params;
    }
    if (mode === "METRO") {
      params.incl_mot_2 = "true";
      return params;
    }
    if (mode === "TRAIN") {
      params.incl_mot_0 = "true";
      return params;
    }
    if (mode === "TRAM") {
      params.incl_mot_4 = "true";
      return params;
    }
    if (mode === "SHIP" || mode === "FERRY") {
      params.incl_mot_9 = "true";
      return params;
    }
    return {
      incl_mot_0: "true",
      incl_mot_2: "true",
      incl_mot_3: "true",
      incl_mot_4: "true",
      incl_mot_5: "true",
      incl_mot_9: "true",
    };
  }

  _fetchDepartureStops(dep, siteId, siteName) {
    const self = this;
    return this._ensureSitesLoaded()
      .then(function () {
        return self._resolveDestinationGid(dep);
      })
      .then(function (destGid) {
        if (!destGid) {
          throw new Error("Kunde inte hitta destinationen " + (dep.destination || ""));
        }
        return self._callWithResponse(
          "rest_command",
          "sl_journey_stops",
          Object.assign(
            {
              origin_site: Number(siteId),
              dest_gid: destGid,
            },
            self._journeyMotParams(dep),
          ),
        );
      })
      .then(function (payload) {
        return self._extractDepartureStops(
          self._unwrapServiceResponse(payload),
          dep,
          siteId,
          siteName,
        );
      });
  }

  _findCurrentStopIndex(stops, siteId, siteName) {
    const normalizedSiteName = this._normalizeStopName(siteName);
    for (let i = 0; i < (stops || []).length; i++) {
      const stop = stops[i] || {};
      if (stop.site_id != null && Number(stop.site_id) === Number(siteId)) {
        return i;
      }
      if (normalizedSiteName && this._normalizeStopName(stop.name) === normalizedSiteName) {
        return i;
      }
    }
    return -1;
  }

  _getModalRoot() {
    this._ensureModalStyles();
    return document.body || this;
  }

  _modalStyleRules() {
    return [
      ".sl-line-route-modal{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:flex-end;justify-content:center}",
      ".sl-line-route-backdrop{position:absolute;inset:0;background:rgba(0,0,0,.55)}",
      ".sl-line-route-panel{position:relative;width:min(100%,520px);max-height:min(80vh,720px);overflow:hidden;display:flex;flex-direction:column;background:var(--card-background-color,#1c1c1c);color:var(--primary-text-color,#fff);border-radius:16px 16px 0 0;box-shadow:0 -8px 32px rgba(0,0,0,.35);margin:0 0 env(safe-area-inset-bottom,0)}",
      ".sl-line-route-header{display:flex;align-items:flex-start;gap:12px;padding:16px 16px 8px;border-bottom:1px solid var(--divider-color,rgba(255,255,255,.12))}",
      ".sl-line-route-title{flex:1;font-size:1rem;font-weight:600;line-height:1.35}",
      ".sl-line-route-close{border:0;background:transparent;color:var(--primary-text-color,#fff);font-size:1.6rem;line-height:1;cursor:pointer;padding:0 4px}",
      ".sl-line-route-meta{padding:8px 16px 12px;color:var(--secondary-text-color,#bbb);font-size:.85rem}",
      ".sl-line-route-meta.error{color:var(--error-color,#e53935)}",
      ".line-route-stops{list-style:none;margin:0;padding:8px 0 16px;overflow-y:auto}",
      ".line-route-stop{display:flex;align-items:center;gap:12px;padding:10px 16px;border-top:1px solid var(--divider-color,rgba(255,255,255,.08))}",
      ".line-route-stop.is-clickable{cursor:pointer;touch-action:manipulation}",
      ".line-route-stop.is-clickable:hover{background:rgba(255,255,255,.04)}",
      ".line-route-stop.is-current{background:rgba(250,211,112,.12)}",
      ".line-route-stop.is-current .line-route-stop-name{color:#fad370;font-weight:600}",
      ".line-route-stop.is-destination .line-route-stop-name{font-weight:600}",
      ".line-route-stop-index{width:1.5rem;color:var(--secondary-text-color,#bbb);font-size:.85rem;text-align:right;flex-shrink:0}",
      ".line-route-stop-name{flex:1;min-width:0}",
      ".sl-line-route-back-btn{border:0;background:transparent;color:var(--primary-text-color,#fff);font-size:1.25rem;line-height:1;cursor:pointer;padding:0 4px 0 0;flex-shrink:0}",
      ".modal-departures-wrap{overflow-y:auto;max-height:calc(min(80vh,720px) - 88px)}",
      ".modal-departures-wrap .departures-list{padding:0 16px 16px}",
      ".modal-departures-wrap .departure-block{margin-top:4px}",
      ".modal-departures-empty{padding:16px;color:var(--secondary-text-color)}",
    ].join("");
  }

  _ensureModalStyles() {
    const styleId = "sl-nearby-card-modal-styles";
    let styleEl = document.getElementById(styleId);
    const version = SlNearbyCard.CARD_VERSION;
    if (styleEl && styleEl.dataset.version === version) {
      return;
    }
    if (!styleEl) {
      styleEl = document.createElement("style");
      styleEl.id = styleId;
      document.head.appendChild(styleEl);
    }
    styleEl.dataset.version = version;
    styleEl.textContent = this._modalStyleRules();
  }

  _closeLineRouteModal() {
    const modal = document.querySelector(".sl-line-route-modal[data-sl-card-id='" + this._modalOwnerId + "']");
    if (modal) {
      modal.remove();
    }
    this._lineRouteModalOpen = false;
    this._modalRouteContext = null;
  }

  _ensureModalOwnerId() {
    if (!this._modalOwnerId) {
      this._modalOwnerId = "sl-nearby-" + String(Date.now()) + "-" + String(Math.random()).slice(2, 8);
    }
    return this._modalOwnerId;
  }

  _wrapModalHtml(html) {
    return html.replace(
      'class="sl-line-route-modal"',
      'class="sl-line-route-modal" data-sl-card-id="' + this._escapeHtml(this._ensureModalOwnerId()) + '"',
    );
  }

  _showModalMessage(title, message, isError) {
    const self = this;
    self._closeLineRouteModal();
    self._lineRouteModalOpen = true;
    const html =
      '<div class="sl-line-route-modal" role="dialog" aria-modal="true" data-sl-card-id="' +
      self._escapeHtml(self._ensureModalOwnerId()) +
      '">' +
      '<div class="sl-line-route-backdrop" data-action="close-line-route"></div>' +
      '<div class="sl-line-route-panel">' +
      '<div class="sl-line-route-header">' +
      '<div class="sl-line-route-title">' +
      self._escapeHtml(title) +
      "</div>" +
      '<button type="button" class="sl-line-route-close" data-action="close-line-route" aria-label="Stäng">×</button>' +
      "</div>" +
      '<div class="sl-line-route-meta' +
      (isError ? " error" : "") +
      '">' +
      self._escapeHtml(message) +
      "</div></div></div>";
    self._getModalRoot().insertAdjacentHTML("beforeend", html);
    self._bindModalClicks(
      self._getModalRoot().querySelector(
        '.sl-line-route-modal[data-sl-card-id="' + self._modalOwnerId + '"]',
      ),
    );
  }

  _findDepartureByKey(siteId, departureKey) {
    const anim = window.SlDepartureListAnim;
    if (anim && anim.manager && anim.manager._scopes) {
      const scope = anim.manager._scopes.get(String(siteId));
      if (scope && scope.lastDepsByKey && scope.lastDepsByKey.has(departureKey)) {
        return scope.lastDepsByKey.get(departureKey);
      }
    }
    const cache = this._getCache().get(String(siteId));
    if (!cache || !cache.departures) {
      return null;
    }
    const departures = cache.departures;
    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const key =
        anim && anim.departureKey ? anim.departureKey(dep) : String(i);
      if (String(key) === String(departureKey)) {
        return dep;
      }
    }
    return null;
  }

  _insertModal(html) {
    const self = this;
    const root = self._getModalRoot();
    root.insertAdjacentHTML("beforeend", self._wrapModalHtml(html));
    const modal = root.querySelector(
      '.sl-line-route-modal[data-sl-card-id="' + self._modalOwnerId + '"]',
    );
    self._bindModalClicks(modal);
    return modal;
  }

  _getActiveModal() {
    return document.querySelector('.sl-line-route-modal[data-sl-card-id="' + this._modalOwnerId + '"]');
  }

  _bindModalClicks(modal) {
    const self = this;
    if (!modal || modal.dataset.clickBound) {
      return;
    }
    modal.dataset.clickBound = "1";
    modal.addEventListener(
      "click",
      function (event) {
        self._onModalClick(event);
      },
      true,
    );
  }

  _setModalPanelInner(html) {
    const modal = this._getActiveModal();
    const panel = modal && modal.querySelector(".sl-line-route-panel");
    if (panel) {
      panel.innerHTML = html;
    }
  }

  _renderModalHeader(title, options) {
    const opts = options || {};
    const self = this;
    let backBtn = "";
    if (opts.showBack) {
      backBtn =
        '<button type="button" class="sl-line-route-back-btn" data-action="modal-route-back" aria-label="Tillbaka">←</button>';
    }
    return (
      '<div class="sl-line-route-header">' +
      backBtn +
      '<div class="sl-line-route-title">' +
      self._escapeHtml(title) +
      "</div>" +
      '<button type="button" class="sl-line-route-close" data-action="close-line-route" aria-label="Stäng">×</button>' +
      "</div>"
    );
  }

  _renderDepartureStopsPanelInner(stops, dep, siteId, siteName) {
    const self = this;
    const line = (dep && dep.line) || {};
    const designation = line.designation || "";
    const destination = self._formatDepartureLabel(dep);
    const stopItems = (stops || [])
      .map(function (stop, index) {
        let className = "line-route-stop is-clickable";
        if (index === 0) {
          className += " is-current";
        }
        if (index === stops.length - 1) {
          className += " is-destination";
        }
        return (
          '<li class="' +
          className +
          '" data-action="open-stop-departures" data-stop-name="' +
          self._escapeHtml(stop.name || "") +
          '" role="button" tabindex="0" title="Visa avgångar">' +
          '<span class="line-route-stop-index">' +
          String(index + 1) +
          '</span><span class="line-route-stop-name">' +
          self._escapeHtml(stop.name || "") +
          "</span></li>"
        );
      })
      .join("");

    return (
      self._renderModalHeader("Linje " + designation + " mot " + destination) +
      '<div class="sl-line-route-meta">' +
      stops.length +
      " hållplatser kvar" +
      (stops[0] ? " · från " + self._escapeHtml(stops[0].name || siteName || "") : "") +
      " · klicka för avgångar</div>" +
      '<ol class="line-route-stops">' +
      stopItems +
      "</ol>"
    );
  }

  _renderDepartureStopsModal(stops, dep, siteId, siteName) {
    const self = this;
    return (
      '<div class="sl-line-route-modal" role="dialog" aria-modal="true">' +
      '<div class="sl-line-route-backdrop" data-action="close-line-route"></div>' +
      '<div class="sl-line-route-panel">' +
      self._renderDepartureStopsPanelInner(stops, dep, siteId, siteName) +
      "</div></div>"
    );
  }

  _renderModalDeparturesLoading(stopName) {
    return (
      this._renderModalHeader("Avgångar · " + stopName) +
      '<div class="sl-line-route-meta">Hämtar avgångar…</div>'
    );
  }

  _renderModalDeparturesPanel(stopName, siteId, departures, stopDeviations) {
    const self = this;
    const now = new Date();
    const anim = window.SlDepartureListAnim;
    let body = "";
    const stopInfo = (stopDeviations || [])
      .map(function (dev) {
        return (
          '<div class="stop-info-item">' +
          self._escapeHtml(dev.message || dev.text || dev.title || "") +
          "</div>"
        );
      })
      .join("");
    if (stopInfo) {
      body += '<div class="stop-info">' + stopInfo + "</div>";
    }
    if (!departures || !departures.length) {
      body +=
        '<div class="modal-departures-empty">Inga avgångar inom ' +
        String((self.config && self.config.forecast_minutes) || 60) +
        " min.</div>";
    } else {
      let rows = "";
      for (let i = 0; i < departures.length; i++) {
        const dep = departures[i];
        const key =
          anim && anim.departureKey ? anim.departureKey(dep) : String(i);
        rows += self._renderDepartureRow(dep, "", key, now, siteId);
      }
      body +=
        '<div class="departures departures-list modal-departures-list">' +
        '<div class="row header"><div class="col icon"></div><div class="col icon"></div><div class="col main left">Linje</div><div class="col right">Avgång</div></div>' +
        rows +
        "</div>";
    }
    return (
      self._renderModalHeader("Avgångar · " + stopName, { showBack: true }) +
      '<div class="sl-line-route-meta">' +
      (departures ? departures.length : 0) +
      " avgångar inom " +
      String((self.config && self.config.forecast_minutes) || 60) +
      " min</div>" +
      '<div class="modal-departures-wrap">' +
      body +
      "</div>"
    );
  }

  _restoreModalRouteStops() {
    const ctx = this._modalRouteContext;
    if (!ctx || ctx.view !== "departures" || !ctx.routeBack) {
      return;
    }
    const back = ctx.routeBack;
    this._modalRouteContext = back;
    this._setModalPanelInner(
      this._renderDepartureStopsPanelInner(back.stops, back.dep, back.siteId, back.siteName),
    );
  }

  _openStopDeparturesInModal(stopName) {
    const self = this;
    const name = String(stopName || "").trim();
    if (!name) {
      return;
    }
    self._setModalPanelInner(self._renderModalDeparturesLoading(name));
    self
      ._ensureSitesLoaded()
      .then(function () {
        const siteId = self._resolveSiteIdByName(name);
        if (!siteId) {
          throw new Error("Kunde inte hitta hållplatsen " + name);
        }
        return self._callDepartures(siteId).then(function (payload) {
          return {
            siteId: siteId,
            payload: payload,
          };
        });
      })
      .then(function (result) {
        if (!self._lineRouteModalOpen) {
          return;
        }
        const departures = self._prepareDepartures(result.payload.departures || []);
        self._getCache().set(String(result.siteId), {
          loading: false,
          departures: departures,
          stop_deviations: result.payload.stop_deviations || [],
          fetched_at: Date.now(),
        });
        const routeBack = self._modalRouteContext;
        self._modalRouteContext = {
          view: "departures",
          stopName: name,
          siteId: result.siteId,
          routeBack: routeBack,
        };
        self._setModalPanelInner(
          self._renderModalDeparturesPanel(
            name,
            result.siteId,
            departures,
            result.payload.stop_deviations || [],
          ),
        );
      })
      .catch(function (error) {
        if (!self._lineRouteModalOpen) {
          return;
        }
        const routeBack = self._modalRouteContext;
        self._modalRouteContext = {
          view: "departures",
          stopName: name,
          siteId: null,
          routeBack: routeBack,
        };
        self._setModalPanelInner(
          self._renderModalHeader("Avgångar · " + name, { showBack: true }) +
            '<div class="sl-line-route-meta error">' +
            self._escapeHtml((error && error.message) || "Kunde inte hämta avgångar") +
            "</div>",
        );
      });
  }

  _onModalClick(event) {
    const closeTarget = event.target.closest("[data-action='close-line-route']");
    if (closeTarget) {
      event.preventDefault();
      event.stopPropagation();
      this._closeLineRouteModal();
      return;
    }

    const backTarget = event.target.closest("[data-action='modal-route-back']");
    if (backTarget) {
      event.preventDefault();
      event.stopPropagation();
      this._restoreModalRouteStops();
      return;
    }

    const stopTarget = event.target.closest("[data-action='open-stop-departures']");
    if (stopTarget) {
      event.preventDefault();
      event.stopPropagation();
      this._openStopDeparturesInModal(stopTarget.getAttribute("data-stop-name"));
      return;
    }

    const block = event.target.closest(".departure-block");
    if (!block || !block.closest(".sl-line-route-modal")) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const siteId = Number(block.getAttribute("data-site-id"));
    const departureKey = block.getAttribute("data-departure-key");
    if (!siteId || !departureKey) {
      this._showModalMessage("Avgång", "Kunde inte läsa avgången.", true);
      return;
    }

    this._showModalMessage("Avgång", "Hämtar hållplatser…", false);

    const dep = this._findDepartureByKey(siteId, departureKey);
    if (!dep) {
      this._showModalMessage("Avgång", "Kunde inte läsa avgången. Försök igen om en stund.", true);
      return;
    }
    this._openLineRouteModal(dep, siteId, this._getSiteName(siteId));
  }

  _openLineRouteModal(dep, siteId, siteName) {
    const self = this;
    if (!dep) {
      return;
    }
    self._closeLineRouteModal();
    self._lineRouteModalOpen = true;
    self._insertModal(
      '<div class="sl-line-route-modal" role="dialog" aria-modal="true">' +
        '<div class="sl-line-route-backdrop" data-action="close-line-route"></div>' +
        '<div class="sl-line-route-panel">' +
        '<div class="sl-line-route-header">' +
        '<div class="sl-line-route-title">Hämtar hållplatser…</div>' +
        '<button type="button" class="sl-line-route-close" data-action="close-line-route" aria-label="Stäng">×</button>' +
        "</div>" +
        '<div class="sl-line-route-meta">Slår upp kvarvarande hållplatser</div>' +
        "</div></div>",
    );

    self
      ._fetchDepartureStops(dep, siteId, siteName)
      .then(function (stops) {
        if (!self._lineRouteModalOpen) {
          return;
        }
        self._closeLineRouteModal();
        if (!stops || !stops.length) {
          self._showModalMessage(
            "Linje " + ((dep.line && dep.line.designation) || ""),
            "Inga kvarvarande hållplatser hittades för den här avgången.",
            false,
          );
          return;
        }
        self._lineRouteModalOpen = true;
        self._modalRouteContext = {
          view: "stops",
          stops: stops,
          dep: dep,
          siteId: siteId,
          siteName: siteName,
        };
        self._insertModal(self._renderDepartureStopsModal(stops, dep, siteId, siteName));
      })
      .catch(function (error) {
        if (!self._lineRouteModalOpen) {
          return;
        }
        self._showModalMessage(
          "Linje " + ((dep.line && dep.line.designation) || ""),
          (error && error.message) || "Kunde inte hämta hållplatser",
          true,
        );
      });
  }

  _getSiteName(siteId) {
    if (!this._sites || !this._sites.length) {
      return "";
    }
    for (let i = 0; i < this._sites.length; i++) {
      if (Number(this._sites[i].id) === Number(siteId)) {
        return this._sites[i].name || "";
      }
    }
    return "";
  }

  _onDepartureClick(event) {
    if (event.target.closest(".sl-line-route-modal")) {
      this._onModalClick(event);
      return;
    }

    const block = event.target.closest(".departure-block");
    if (!block) {
      return;
    }
    const card = block.closest("sl-nearby-card, ha-sl-nearby-stops-card");
    if (!card || card !== this) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const siteId = Number(block.getAttribute("data-site-id"));
    const departureKey = block.getAttribute("data-departure-key");
    if (!siteId || !departureKey) {
      this._showModalMessage("Avgång", "Kunde inte läsa avgången.", true);
      return;
    }

    this._showModalMessage("Avgång", "Hämtar hållplatser…", false);

    const dep = this._findDepartureByKey(siteId, departureKey);
    if (!dep) {
      this._showModalMessage("Avgång", "Kunde inte läsa avgången. Försök igen om en stund.", true);
      return;
    }
    this._openLineRouteModal(dep, siteId, this._getSiteName(siteId));
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
      if (window.SlDepartureListAnim) {
        window.SlDepartureListAnim.manager.resetScope(String(siteId));
      }
      this._syncRefreshTimer();
      this._syncDepartureClock();
      return;
    }
    this._openSiteId = siteId;
    this._syncRefreshTimer();
    this._syncDepartureClock();
    this._loadDepartures(siteId, true);
  }

  _onFilterInteraction(event) {
    const button = event.target.closest(".mode-filter");
    if (!button || !this.contains(button)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (event.type === "mousedown") {
      return;
    }
    const siteId = Number(button.dataset.siteId);
    const mode = button.dataset.mode || "ALL";
    this._setActiveModeFilter(siteId, mode);
    if (window.SlDepartureListAnim) {
      window.SlDepartureListAnim.manager.resetScope(String(siteId));
    }
    this._updateDeparturePanel(siteId);
  }

  _onCardClick(event) {
    if (event.target.closest(".sl-line-route-modal")) {
      this._onDepartureClick(event);
      return;
    }
    if (event.target.closest(".departure-block")) {
      this._onDepartureClick(event);
      return;
    }
    this._onFilterInteraction(event);
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
    const styleEl = this.querySelector("style.sl-nearby-card-style");
    const version = SlNearbyCard.CARD_VERSION;
    if (!root || !styleEl || styleEl.dataset.version !== version) {
      this.innerHTML =
        '<style class="sl-nearby-card-style" data-version="' +
        version +
        '">' +
        this._styles() +
        '</style><ha-card><div class="sl-card-root"></div></ha-card>';
      root = this.querySelector(".sl-card-root");
      root.addEventListener("toggle", (event) => this._onToggle(event), true);
      root.addEventListener("mousedown", (event) => this._onFilterInteraction(event), true);
      this._lastListKey = null;
    }

    const locationEntity = this._getLocationEntity();
    const location = this._getSearchLocation();
    const stops = this._getNearestStops();
    let body = "";

    if (this._sitesError) {
      body = '<div class="status-message error">' + this._escapeHtml(this._sitesError) + "</div>";
    } else if (!this._sites) {
      body = '<div class="status-message">Laddar hållplatser…</div>';
    } else if (!locationEntity) {
      body =
        '<div class="status-message">Ingen person entitet kopplad till ditt Home Assistant-konto.</div>';
    } else if (!location) {
      body =
        '<div class="status-message">Ingen GPS-position från ' +
        this._escapeHtml(this._getLocationLabel()) +
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
            '<summary class="stop-summary">' +
            self._renderStopSummary(stop) +
            "</summary>" +
            '<div class="stop-body">' +
            self._renderDepartures(stop.id) +
            "</div></details>"
          );
        })
        .join("");
      self._prefetchDepartures(stops);
    }

    const listKey = stops
      .map(function (stop) {
        return stop.id + ":" + Math.round(stop.distance_m);
      })
      .join(",");
    if (this._lastListKey === listKey && this.querySelector(".stop-accordion")) {
      const header = root.querySelector(".list-header");
      if (header) {
        header.remove();
      }
      for (let i = 0; i < stops.length; i++) {
        const distEl = root.querySelector(
          '.stop-accordion[data-site-id="' + stops[i].id + '"] .stop-distance',
        );
        if (distEl) {
          distEl.textContent = this._formatDistance(stops[i].distance_m);
        }
      }
      if (this._openSiteId) {
        this._updateDeparturePanel(this._openSiteId);
      }
      return;
    }
    this._lastListKey = listKey;
    root.innerHTML = body;
  }

  _styles() {
    return [
      ":host{display:block;width:100%}",
      "ha-card{padding:0 0 12px;width:100%;box-sizing:border-box;display:block}",
      ".sl-card-root{width:100%;box-sizing:border-box}",
      ".status-message{padding:16px;color:var(--secondary-text-color)}",
      ".status-message.error{color:var(--error-color)}",
      ".stop-accordion{width:100%;box-sizing:border-box;border-top:1px solid var(--divider-color,rgba(0,0,0,.12))}",
      ".stop-summary{list-style:none;padding:0;cursor:pointer;width:100%;box-sizing:border-box}",
      ".stop-summary::-webkit-details-marker{display:none}",
      ".stop-summary-content{padding:0;width:100%;box-sizing:border-box}",
      ".stop-header-row{display:flex;align-items:flex-start;gap:12px;padding:0 16px;width:100%;box-sizing:border-box}",
      ".stop-header-row .card-header{flex:1;min-width:0;margin:0}",
      ".card-header .name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
      ".stop-distance{color:var(--secondary-text-color);white-space:nowrap;padding-top:16px;flex-shrink:0}",
      ".mode-filters-wrap{padding:0 16px 12px;width:100%;box-sizing:border-box}",
      ".mode-filters{display:flex;flex-wrap:wrap;gap:8px}",
      ".mode-filter{border:1px solid var(--divider-color,rgba(255,255,255,.2));background:transparent;color:var(--primary-text-color);border-radius:16px;padding:4px 12px;font-size:.8rem;cursor:pointer}",
      ".mode-filter.active{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color,#fff)}",
      ".stop-body{padding:0 16px 12px;width:100%;box-sizing:border-box}",
      ".departures-empty,.departures-error{padding:8px 0 12px;color:var(--secondary-text-color)}",
      ".departures-error{color:var(--error-color)}",
      ".departures.departures-list{width:100%;box-sizing:border-box}",
      ".row{margin-top:8px;display:grid;grid-template-columns:40px 40px minmax(0,1fr) auto;align-items:center;width:100%;box-sizing:border-box}",
      ".col{display:flex;flex-direction:column;justify-content:center;position:relative;min-width:0}",
      ".row.header{height:40px;font-size:medium;font-weight:400;opacity:var(--dark-primary-opacity)}",
      ".main{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".transport-icon{width:40px;height:40px;display:inline-flex;justify-content:center;align-items:center;flex-shrink:0}",
      ".line-icon{border-radius:3px;padding:3px 3px 0 3px;color:#fff;width:36px;min-width:36px;height:22px;font-weight:500;display:inline-block;text-align:center;box-sizing:border-box;text-shadow:1px 1px 2px var(--outline-color)}",
      ".bus{border:1px solid var(--outline-color);color:var(--primary-text-color)}",
      ".bus_red,.bus.red,.red{background-color:#9e0e13;color:#fff;border:none}",
      ".blue{background-color:#0089ca}",
      ".green{background-color:#179d4d}",
      ".metro{background:#0061eb}",
      ".train{background:#ec619f}",
      ".tram{background:#985141}",
      ".warning-message{color:var(--warning-color);font-size:smaller}",
      ".departure-block{margin-top:8px;border-radius:6px;width:100%;box-sizing:border-box;cursor:pointer;touch-action:manipulation;-webkit-tap-highlight-color:rgba(255,255,255,.12)}",
      ".departure-block:hover{background:rgba(255,255,255,.04)}",
      ".departure-block .row.departure{margin-top:0}",
      ".departure-meta{display:flex;flex-direction:column;gap:2px;padding:2px 0 0 80px;margin-bottom:2px;width:100%;box-sizing:border-box}",
      ".detail-item{font-size:smaller;line-height:1.35}",
      ".stop-point-label,.line-type-label{color:#fad370!important;font-weight:500}",
      ".stop-info{margin:0 0 8px;padding:8px 12px 0;font-size:smaller;line-height:1.35;color:#fad370!important;border-top:1px solid var(--divider-color,rgba(0,0,0,.12))}",
      ".stop-info-item{color:#fad370!important}",
      ".stop-info-item+.stop-info-item{margin-top:6px}",
      ".short-train{color:#0abcfc;font-size:smaller;font-weight:600;margin-left:.35em;text-transform:lowercase}",
      ".old-time{text-decoration:line-through;opacity:.65;margin-right:.35em}",
      ".new-time{color:#0abcfc;font-weight:600}",
      ".delay-min{color:#0abcfc;font-weight:600}",
      ".departure-now{color:#fad370!important;font-weight:600}",
      ".cancelled-time{color:#e53935;font-weight:600}",
      ".leaves-in{white-space:nowrap;min-width:5.5rem;text-align:right;display:inline-block}",
      ".mr1{margin-right:8px}",
      ".left{text-align:left}",
      ".right{text-align:right}",
      ".departure-block[data-departure-key]{max-height:500px}",
      ".departure-block.departure-exit-slide{overflow:hidden;box-sizing:border-box;transition:max-height .5s ease,margin-top .5s ease,opacity .5s ease}",
      ".departure-block.departure-exit-slide.departure-exit-slide-active{max-height:0!important;margin-top:0!important;opacity:0}",
      "ha-icon{width:24px;height:24px;color:var(--paper-item-icon-color)}",
    ].join("");
  }
}

function _defineSlNearbyCard(tag) {
  if (customElements.get(tag)) {
    const proto = customElements.get(tag).prototype;
    const nextProto = SlNearbyCard.prototype;
    const names = Object.getOwnPropertyNames(nextProto);
    for (let i = 0; i < names.length; i++) {
      const name = names[i];
      if (name !== "constructor") {
        proto[name] = nextProto[name];
      }
    }
    Object.getOwnPropertyNames(SlNearbyCard).forEach(function (name) {
      if (name !== "length" && name !== "name" && name !== "prototype") {
        try {
          Object.defineProperty(
            customElements.get(tag),
            name,
            Object.getOwnPropertyDescriptor(SlNearbyCard, name),
          );
        } catch (error) {
          /* ignore read-only props */
        }
      }
    });
    return;
  }
  customElements.define(tag, SlNearbyCard);
}

_defineSlNearbyCard("sl-nearby-card");
_defineSlNearbyCard("ha-sl-nearby-stops-card");

window.SlNearbyCardActions = {
  openDeparture: function (event, siteId, departureKey) {
    if (event) {
      event.preventDefault();
      if (event.stopPropagation) {
        event.stopPropagation();
      }
    }
    let card = null;
    if (event && event.currentTarget) {
      card = event.currentTarget.closest("sl-nearby-card, ha-sl-nearby-stops-card");
    }
    if (!card) {
      card = document.querySelector("sl-nearby-card, ha-sl-nearby-stops-card");
    }
    if (card && typeof card.openDepartureModal === "function") {
      card.openDepartureModal(siteId, departureKey);
      return;
    }
    window.alert("SL-kortet är inte redo ännu. Ladda om sidan.");
  },
};

function _bindSlNearbyCardGlobalClicks(version) {
  if (
    window.__slNearbyCardGlobalClickHandler &&
    window.__slNearbyCardGlobalClickVersion === version
  ) {
    return;
  }
  if (window.__slNearbyCardGlobalClickHandler) {
    document.removeEventListener("click", window.__slNearbyCardGlobalClickHandler, true);
    document.removeEventListener("touchend", window.__slNearbyCardGlobalTouchHandler, true);
  }
  window.__slNearbyCardGlobalClickVersion = version;
  window.__slNearbyCardGlobalClickHandler = function (event) {
    const block = event.target.closest(".departure-block");
    if (block) {
      const card = block.closest("sl-nearby-card, ha-sl-nearby-stops-card");
      if (card && typeof card._onDepartureClick === "function") {
        card._onDepartureClick(event);
        return;
      }
    }
    const filter = event.target.closest(".mode-filter");
    if (!filter) {
      return;
    }
    const card = filter.closest("sl-nearby-card, ha-sl-nearby-stops-card");
    if (card && typeof card._onFilterInteraction === "function") {
      card._onFilterInteraction(event);
    }
  };
  window.__slNearbyCardGlobalTouchHandler = function (event) {
    const block = event.target.closest(".departure-block");
    if (!block) {
      return;
    }
    event.preventDefault();
    window.__slNearbyCardGlobalClickHandler(event);
  };
  document.addEventListener("click", window.__slNearbyCardGlobalClickHandler, true);
  document.addEventListener("touchend", window.__slNearbyCardGlobalTouchHandler, {
    capture: true,
    passive: false,
  });
}

_bindSlNearbyCardGlobalClicks(SlNearbyCard.CARD_VERSION);

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
