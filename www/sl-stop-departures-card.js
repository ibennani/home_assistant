class SlStopDeparturesCard extends HTMLElement {
  static get CARD_VERSION() {
    return "20260904a";
  }

  static getStubConfig() {
    return {
      title: "Huddinge centrum",
      site_id: 9527,
      forecast_minutes: 120,
      hide_departed: true,
      show_time_always: true,
      language: "sv-SE",
      refresh_seconds: 30,
      alight_train_site_id: 9180,
      alight_bus_site_id: 1923,
      transfer_site_id: 9529,
      connecting_lines: ["43", "41"],
      train_leg_huddinge_alvsjo_minutes: 7,
      transfer_alvsjo_minutes: 3,
      train_pt_fallback_minutes: 31,
      bus_pt_fallback_minutes: 20,
    };
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  setConfig(config) {
    try {
      const base = SlStopDeparturesCard.getStubConfig();
      const input = config && typeof config === "object" ? config : {};
      this.config = Object.assign({}, base, input);
      if (!this._travelCache) {
        this._travelCache = new Map();
      }
      if (!this._data) {
        this._data = { loading: true };
      }
      if (!this._modeFilter) {
        this._modeFilter = "ALL";
      }
      this._updateView();
    } catch (error) {
      this.config = SlStopDeparturesCard.getStubConfig();
      this.innerHTML =
        '<ha-card><div class="status-message error">Kortfel: ' +
        String((error && error.message) || error) +
        "</div></ha-card>";
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._ensureBusLineTerminusLabels();
    // Avgångar hämtas via REST — rita inte om vid varje global hass-uppdatering.
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
      self._updateView();
    });
  }

  connectedCallback() {
    if (this._cardVersion !== SlStopDeparturesCard.CARD_VERSION) {
      this._cardVersion = SlStopDeparturesCard.CARD_VERSION;
      this._filterClickBound = false;
    }
    this._loadData(false);
    this._syncRefreshTimer();
    this._syncDepartureClock();
  }

  disconnectedCallback() {
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
  }

  _getVisibleDepartures() {
    const allDepartures = (this._data && this._data.departures) || [];
    return this._filterDeparturesByMode(allDepartures);
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
        return self._getVisibleDepartures();
      },
      onTick: function () {
        self._updateView({ clockOnly: true });
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
    const clock = this._ensureDepartureClock();
    if (clock) {
      clock.start();
      return;
    }
    const self = this;
    this._departureClockTimer = window.setInterval(function () {
      self._updateView({ clockOnly: true });
    }, 15000);
  }

  getCardSize() {
    return 10;
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
    const self = this;
    this._refreshTimer = window.setInterval(function () {
      self._loadData(true);
    }, seconds * 1000);
  }

  _extractPayload(result) {
    if (!result) {
      return {};
    }
    if (result.content) {
      return result.content;
    }
    if (result.departures || result.journeys || result.stop_deviations) {
      return result;
    }
    if (result.service_response) {
      const extracted = this._extractPayload(result.service_response);
      if (extracted.departures || extracted.journeys || extracted.stop_deviations) {
        return extracted;
      }
    }
    if (result.response) {
      const extracted = this._extractPayload(result.response);
      if (extracted.departures || extracted.journeys || extracted.stop_deviations) {
        return extracted;
      }
    }
    const keys = Object.keys(result);
    if (keys.length === 1 && result[keys[0]] && typeof result[keys[0]] === "object") {
      const extracted = this._extractPayload(result[keys[0]]);
      if (extracted.departures || extracted.journeys || extracted.stop_deviations) {
        return extracted;
      }
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
    if (this._hass && this._hass.callService) {
      return this._hass.callService(domain, service, serviceData, undefined, true);
    }
    return Promise.reject(new Error("Kunde inte anropa Home Assistant"));
  }

  _callSiteDepartures(siteId) {
    const forecast = Number(this.config.forecast_minutes || 120);
    return this._callWithResponse("rest_command", "sl_site_departures", {
      site_id: Number(siteId),
      forecast: forecast,
    }).then((result) => this._extractPayload(result));
  }

  _matchesDeparture(dep) {
    const line = dep.line || {};
    const mode = String(line.transport_mode || "").toUpperCase();
    if (mode === "TRAIN" && String(dep.direction_code) === "2") {
      return "train";
    }
    if (
      String(line.designation || line.id) === "742" &&
      String(dep.direction_code) === "1" &&
      dep.destination === "Drevviksstrand"
    ) {
      return "bus";
    }
    return null;
  }

  _shouldHideDeparted(expectedAt, now) {
    const hideDeparted = !this.config || this.config.hide_departed !== false;
    if (window.SlDepartureTime && window.SlDepartureTime.shouldHideDeparted) {
      return window.SlDepartureTime.shouldHideDeparted(expectedAt, now, hideDeparted);
    }
    return hideDeparted && expectedAt ? this._isDeparted(expectedAt, now) : false;
  }

  _formatDepartureLabel(dep) {
    const api = window.SlDepartureTime;
    if (api && api.formatDepartureLabel) {
      return api.formatDepartureLabel(dep);
    }
    return String((dep && dep.destination) || (dep && dep.direction) || "").trim();
  }

  _prepareDepartures(departures) {
    const items = [];
    const self = this;
    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const kind = this._matchesDeparture(dep);
      if (!kind) {
        continue;
      }
      const expected = dep.expected || dep.scheduled;
      const expectedAt = expected ? new Date(expected) : null;
      const expectedMs = expectedAt ? expectedAt.getTime() : Number.POSITIVE_INFINITY;
      const destination = self._formatDepartureLabel(dep);
      items.push(
        Object.assign({}, dep, {
          destination: destination,
          _rawDestination: dep.destination,
          _rawDirection: dep.direction,
          _expectedMs: expectedMs,
          _kind: kind,
        }),
      );
    }
    return self._sortDeparturesByTime(items);
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

  _getVisibleDepartures(departures) {
    const now = new Date();
    const self = this;
    const visible = [];
    for (let i = 0; i < (departures || []).length; i++) {
      const dep = departures[i];
      if (!self._shouldHideDepartedDeparture(dep, now)) {
        visible.push(dep);
      }
    }
    return self._sortDeparturesByTime(visible);
  }

  _buildJourneyMap(departures) {
    const map = new Map();
    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const jid = dep.journey && dep.journey.id;
      if (jid) {
        map.set(String(jid), dep);
      }
    }
    return map;
  }

  _buildBusJourneyMap(departures) {
    return this._buildJourneyMap(departures);
  }

  _filterTrainDepartures(departures) {
    const items = [];
    for (let i = 0; i < (departures || []).length; i++) {
      const dep = departures[i];
      const mode = String((dep.line && dep.line.transport_mode) || "").toUpperCase();
      if (mode === "TRAIN") {
        items.push(dep);
      }
    }
    return items;
  }

  _sortDeparturesByTime(departures) {
    if (window.SlDepartureTime && window.SlDepartureTime.sortDeparturesByTime) {
      return window.SlDepartureTime.sortDeparturesByTime(departures);
    }
    return this._sortDeparturesByTimeLegacy(departures);
  }

  _sortDeparturesByTimeLegacy(departures) {
    return departures.slice().sort(function (a, b) {
      const aMs = new Date(a.expected || a.scheduled || 0).getTime();
      const bMs = new Date(b.expected || b.scheduled || 0).getTime();
      return aMs - bMs;
    });
  }

  _connectingLines() {
    const lines = this.config && this.config.connecting_lines;
    if (Array.isArray(lines) && lines.length) {
      return lines.map(function (line) {
        return String(line);
      });
    }
    return ["43", "41"];
  }

  _computeBusPtMinutes(dep, busJourneyMap) {
    const jid = dep.journey && dep.journey.id;
    if (!jid) {
      return null;
    }
    const alight = busJourneyMap.get(String(jid));
    if (!alight) {
      return null;
    }
    const start = this._parseDate(dep.expected || dep.scheduled);
    const end = this._parseDate(alight.expected || alight.scheduled);
    if (!start || !end) {
      return null;
    }
    return Math.max(1, Math.round((end.getTime() - start.getTime()) / 60000));
  }

  _computeBusTravelMinutes(dep, busJourneyMap) {
    const pt = this._computeBusPtMinutes(dep, busJourneyMap);
    if (pt === null) {
      return Number(this.config.bus_pt_fallback_minutes || 20);
    }
    return pt;
  }

  _findAlvsjoArrival(dep, alvsjoDepartures) {
    const jid = dep.journey && dep.journey.id;
    if (!jid) {
      return null;
    }
    for (let i = 0; i < alvsjoDepartures.length; i++) {
      const alvsjoDep = alvsjoDepartures[i];
      if (alvsjoDep.journey && String(alvsjoDep.journey.id) === String(jid)) {
        return this._parseDate(alvsjoDep.expected || alvsjoDep.scheduled);
      }
    }
    return null;
  }

  _isSouthboundTrain(dep) {
    return String(dep.direction_code) === "1";
  }

  _computeTrainPtMinutes(dep, alvsjoDepartures, farstaJourneyMap) {
    const start = this._parseDate(dep.expected || dep.scheduled);
    if (!start) {
      return null;
    }
    const transferMin = Number(this.config.transfer_alvsjo_minutes || 3);
    const huddingeAlvsjoFallback = Number(this.config.train_leg_huddinge_alvsjo_minutes || 7);
    let alvsjoAt = this._findAlvsjoArrival(dep, alvsjoDepartures);
    if (!alvsjoAt) {
      alvsjoAt = new Date(start.getTime() + huddingeAlvsjoFallback * 60000);
    }
    const earliestConnectMs = alvsjoAt.getTime() + transferMin * 60000;
    const connectingLines = this._connectingLines();
    let bestPt = null;
    for (let i = 0; i < alvsjoDepartures.length; i++) {
      const connectDep = alvsjoDepartures[i];
      const line = connectDep.line || {};
      if (String(line.transport_mode || "").toUpperCase() !== "TRAIN") {
        continue;
      }
      if (!this._isSouthboundTrain(connectDep)) {
        continue;
      }
      const designation = String(line.designation || line.id || "");
      if (connectingLines.indexOf(designation) === -1) {
        continue;
      }
      const connectJid = connectDep.journey && connectDep.journey.id;
      if (!connectJid || !farstaJourneyMap.has(String(connectJid))) {
        continue;
      }
      const connectAt = this._parseDate(connectDep.expected || connectDep.scheduled);
      if (!connectAt || connectAt.getTime() < earliestConnectMs) {
        continue;
      }
      const farstaDep = farstaJourneyMap.get(String(connectJid));
      const end = this._parseDate(farstaDep.expected || farstaDep.scheduled);
      if (!end || end.getTime() < connectAt.getTime()) {
        continue;
      }
      const pt = Math.max(1, Math.round((end.getTime() - start.getTime()) / 60000));
      if (bestPt === null || pt < bestPt) {
        bestPt = pt;
      }
    }
    return bestPt;
  }

  _computeTrainTravelMinutes(dep, alvsjoDepartures, farstaJourneyMap) {
    const pt = this._computeTrainPtMinutes(dep, alvsjoDepartures, farstaJourneyMap);
    if (pt === null) {
      return Number(this.config.train_pt_fallback_minutes || 31);
    }
    return pt;
  }

  _formatTravelDuration(totalMinutes, departureAt) {
    const minutes = Math.max(1, Math.round(totalMinutes));
    let text;
    if (minutes < 60) {
      text = "Restid " + minutes + " min";
    } else {
      const hours = Math.floor(minutes / 60);
      const rest = minutes % 60;
      if (rest === 0) {
        text = "Restid " + hours + " h";
      } else {
        text = "Restid " + hours + " h " + rest + " min";
      }
    }
    if (departureAt) {
      const arrival = new Date(departureAt.getTime() + minutes * 60000);
      text += ", hemma " + this._formatClock(arrival);
    }
    return text;
  }

  _travelCacheKey(dep) {
    const when = dep.expected || dep.scheduled || "";
    return dep._kind + "|" + ((dep.line && dep.line.designation) || "") + "|" + when;
  }

  _ensureTravelTimes(departures) {
    const self = this;
    const busJourneyMap = (this._data && this._data.busJourneyMap) || new Map();
    const alvsjoTrainDepartures = (this._data && this._data.alvsjoTrainDepartures) || [];
    const farstaJourneyMap = (this._data && this._data.farstaJourneyMap) || new Map();

    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const key = self._travelCacheKey(dep);
      if (self._travelCache.has(key)) {
        dep._travelMinutes = self._travelCache.get(key);
        continue;
      }
      let total;
      if (dep._kind === "bus") {
        total = self._computeBusTravelMinutes(dep, busJourneyMap);
      } else if (dep._kind === "train") {
        total = self._computeTrainTravelMinutes(dep, alvsjoTrainDepartures, farstaJourneyMap);
      } else {
        continue;
      }
      self._travelCache.set(key, total);
      dep._travelMinutes = total;
    }
    self._updateView();
    return Promise.resolve();
  }

  _loadData(force) {
    if (!this._hass) {
      return;
    }
    if (this._loading && !force) {
      return;
    }
    this._loading = true;
    if (!this._data || force) {
      this._data = { loading: true };
      this._updateView();
    }
    const self = this;
    const siteId = Number(this.config.site_id);
    const busSiteId = Number(this.config.alight_bus_site_id);
    const transferSiteId = Number(this.config.transfer_site_id || 9529);
    const trainSiteId = Number(this.config.alight_train_site_id);
    const emptySite = function () {
      return { departures: [], stop_deviations: [] };
    };
    Promise.all([
      self._callSiteDepartures(siteId),
      self._callSiteDepartures(busSiteId).catch(emptySite),
      self._callSiteDepartures(transferSiteId).catch(emptySite),
      self._callSiteDepartures(trainSiteId).catch(emptySite),
    ])
      .then(function (results) {
        const main = results[0];
        const busSite = results[1];
        const transferSite = results[2];
        const trainSite = results[3];
        const departures = self._prepareDepartures(main.departures || []);
        const alvsjoTrainDepartures = self._sortDeparturesByTime(
          self._filterTrainDepartures(transferSite.departures || []),
        );
        const farstaJourneyMap = self._buildJourneyMap(
          self._filterTrainDepartures(trainSite.departures || []),
        );
        self._data = {
          loading: false,
          departures: departures,
          stop_deviations: main.stop_deviations || [],
          busJourneyMap: self._buildBusJourneyMap(busSite.departures || []),
          alvsjoTrainDepartures: alvsjoTrainDepartures,
          farstaJourneyMap: farstaJourneyMap,
          error: null,
        };
        self._updateView();
        return self._ensureTravelTimes(departures);
      })
      .catch(function (error) {
        self._data = {
          loading: false,
          departures: [],
          stop_deviations: [],
          busJourneyMap: new Map(),
          alvsjoTrainDepartures: [],
          farstaJourneyMap: new Map(),
          error: (error && error.message) || "Kunde inte hämta avgångar",
        };
        self._updateView();
      })
      .then(function () {
        self._loading = false;
      });
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
    return expectedAt.getTime() - scheduledAt.getTime() >= 30000;
  }

  _deviationText(dev) {
    return String((dev && (dev.message || dev.text || dev.title)) || "").trim();
  }

  _isShortTrainDeviation(dev) {
    const msg = this._deviationText(dev).toLowerCase();
    return msg.includes("kort tåg") || msg.includes("kort tag") || msg.includes("short train");
  }

  _collectBannerMessages(stopDeviations, departures) {
    const seen = new Set();
    const messages = [];
    const add = (text) => {
      const value = String(text || "").trim();
      if (!value || seen.has(value)) {
        return;
      }
      seen.add(value);
      messages.push(value);
    };

    const stopList = stopDeviations || [];
    for (let i = 0; i < stopList.length; i++) {
      add(this._deviationText(stopList[i]));
    }

    const depList = departures || [];
    for (let i = 0; i < depList.length; i++) {
      const deviations = depList[i].deviations || [];
      for (let j = 0; j < deviations.length; j++) {
        const dev = deviations[j];
        if (this._isShortTrainDeviation(dev)) {
          continue;
        }
        add(this._deviationText(dev));
      }
    }

    return messages;
  }

  _renderStopInfoBlock(messages) {
    if (!messages || !messages.length) {
      return "";
    }
    const self = this;
    return (
      '<div class="stop-info">' +
      messages
        .map(function (message) {
          return (
            '<div class="stop-info-item">' + self._escapeHtml(message) + "</div>"
          );
        })
        .join("") +
      "</div>"
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
    return String(lineType).trim();
  }

  _buildDepartureDetailItems(dep) {
    const items = [];
    const stopPointLabel = this._formatStopPointLabel(dep);
    if (stopPointLabel) {
      items.push({ text: stopPointLabel, className: "stop-point-label" });
    }
    const lineTypeLabel = this._formatLineTypeLabel(dep);
    if (lineTypeLabel) {
      items.push({ text: lineTypeLabel, className: "line-type-label" });
    }
    const deviations = dep.deviations || [];
    const isShortTrain = deviations.some((dev) => this._isShortTrainDeviation(dev));
    if (isShortTrain) {
      items.push({ text: "kort tåg", className: "short-train" });
    }
    if (dep._travelMinutes) {
      const when = this._parseDate(dep.expected || dep.scheduled);
      items.push({
        text: this._formatTravelDuration(dep._travelMinutes, when),
        className: "travel-time",
      });
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

  _filterDeparturesByMode(departures) {
    const active = this._modeFilter || "ALL";
    if (active === "ALL") {
      return departures;
    }
    return departures.filter(function (dep) {
      const mode = String((dep.line && dep.line.transport_mode) || "").toUpperCase();
      return mode === active;
    });
  }

  _renderModeFilters(modes) {
    if (!modes || modes.length <= 1) {
      return "";
    }
    const self = this;
    const active = this._modeFilter || "ALL";
    let html = '<div class="mode-filters">';
    html +=
      '<button type="button" class="mode-filter' +
      (active === "ALL" ? " active" : "") +
      '" data-mode="ALL">Alla</button>';
    modes.forEach(function (mode) {
      html +=
        '<button type="button" class="mode-filter' +
        (active === mode ? " active" : "") +
        '" data-mode="' +
        self._escapeHtml(mode) +
        '">' +
        self._escapeHtml(self._transportModeLabel(mode)) +
        "</button>";
    });
    html += "</div>";
    return html;
  }

  _onFilterClick(event) {
    const button = event.target.closest(".mode-filter");
    if (!button || !this.contains(button)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    this._modeFilter = button.dataset.mode || "ALL";
    if (window.SlDepartureListAnim) {
      window.SlDepartureListAnim.manager.resetScope(this._animScopeId());
    }
    this._updateView();
  }

  _renderDepartureMeta(detailItems) {
    if (!detailItems.length) {
      return "";
    }
    const self = this;
    return detailItems
      .map(function (item) {
        return (
          '<span class="detail-item ' +
          item.className +
          '">' +
          self._escapeHtml(item.text) +
          "</span>"
        );
      })
      .join("");
  }

  _renderDepartureDeviations(detailItems) {
    const self = this;
    const devItems = detailItems.filter(function (item) {
      return item.className === "short-train" || item.className === "warning-message";
    });
    if (!devItems.length) {
      return "";
    }
    return (
      '<div class="row departure-deviations">' +
      devItems
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

  _renderDepartureMetaRow(detailItems) {
    const metaItems = detailItems.filter(function (item) {
      return item.className !== "short-train" && item.className !== "warning-message";
    });
    return this._renderDepartureMeta(metaItems);
  }

  _animScopeId() {
    return "stop-" + String((this.config && this.config.site_id) || "main");
  }

  _renderDepartureRow(dep, extraClass, key, now) {
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
    const detailMeta = self._renderDepartureMetaRow(detailItems);
    const detailDeviations = self._renderDepartureDeviations(detailItems);

    return (
      '<div class="departure-block' +
      (extraClass || "") +
      '" data-departure-key="' +
      self._escapeHtml(key) +
      '"><div class="row departure-line">' +
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
      '</div></div><div class="row departure-time"><span class="leaves-in">' +
      departureTime +
      "</span>" +
      detailMeta +
      "</div>" +
      detailDeviations +
      "</div>"
    );
  }

  _buildDepartureRows(departures, now) {
    const self = this;
    const activeDeps = self._getVisibleDepartures(departures);

    const anim = window.SlDepartureListAnim;
    if (anim && anim.manager) {
      return anim.manager.buildRows(self._animScopeId(), {
        activeDeps: activeDeps,
        allDeps: departures,
        now: now,
        shouldHideDeparted: function (dep, currentNow) {
          return self._shouldHideDepartedDeparture(dep, currentNow);
        },
        renderRow: function (dep, extraClass, key) {
          return self._renderDepartureRow(dep, extraClass, key, now);
        },
      });
    }

    let rows = "";
    for (let j = 0; j < activeDeps.length; j++) {
      const key =
        anim && anim.departureKey ? anim.departureKey(activeDeps[j]) : String(j);
      rows += self._renderDepartureRow(activeDeps[j], "", key, now);
    }
    return rows;
  }

  _runDepartureListAnimation(root) {
    const anim = window.SlDepartureListAnim;
    if (!anim || !root) {
      return;
    }
    const scopeId = this._animScopeId();
    if (!anim.manager.hasPendingExit(scopeId)) {
      return;
    }
    const listEl = root.querySelector(".departures-list");
    if (!listEl) {
      return;
    }
    const self = this;
    anim.manager.afterRender(scopeId, listEl, function () {
      self._updateView({ clockOnly: true });
    });
  }

  _renderBody() {
    const data = this._data || { loading: true };
    if (data.loading) {
      return '<div class="status-message">Hämtar avgångar…</div>';
    }
    if (data.error) {
      return '<div class="status-message error">' + this._escapeHtml(data.error) + "</div>";
    }

    const allDepartures = data.departures || [];
    const modes = this._getTransportModes(allDepartures);
    const departures = this._filterDeparturesByMode(allDepartures);
    const bannerMessages = this._collectBannerMessages(data.stop_deviations, allDepartures);
    const stopInfoBlock = this._renderStopInfoBlock(bannerMessages);

    if (!departures.length) {
      return (
        stopInfoBlock +
        '<div class="departures-empty">Inga matchande avgångar' +
        (modes.length > 1 ? " för valt trafikslag" : "") +
        ".</div>"
      );
    }

    const now = new Date();
    const rows = this._buildDepartureRows(departures, now);

    return (
      stopInfoBlock +
      '<div class="departures departures-list">' +
      rows +
      "</div>"
    );
  }

  _updateView(options) {
    if (!this.config) {
      return;
    }
    const clockOnly = options && options.clockOnly;
    const anim = window.SlDepartureListAnim;
    if (anim && anim.manager.isAnimating(this._animScopeId())) {
      return;
    }
    let root = this.querySelector(".sl-stop-card-root");
    const version = SlStopDeparturesCard.CARD_VERSION;
    const styleEl = this.querySelector("style.sl-stop-card-style");
    if (!root || !styleEl || styleEl.dataset.version !== version) {
      this.innerHTML =
        '<style class="sl-stop-card-style" data-version="' +
        version +
        '">' +
        this._styles() +
        '</style><ha-card><div class="sl-stop-card-root"></div></ha-card>';
      root = this.querySelector(".sl-stop-card-root");
    }
    if (!this._filterClickBound) {
      this.addEventListener("click", (event) => this._onFilterClick(event), true);
      this._filterClickBound = true;
    }

    if (clockOnly) {
      const content = root.querySelector(".card-content");
      if (content) {
        content.innerHTML = this._renderBody();
        this._runDepartureListAnimation(root);
      }
      if (this._departureClock) {
        this._departureClock.reschedule();
      }
      return;
    }

    const title = this.config.title || "Hållplats";
    const allDepartures = (this._data && this._data.departures) || [];
    const modes = this._getTransportModes(allDepartures);
    const filters = this._renderModeFilters(modes);
    root.innerHTML =
      '<h1 class="card-header"><div class="name">' +
      this._escapeHtml(title) +
      "</div></h1>" +
      (filters ? '<div class="mode-filters-wrap">' + filters + "</div>" : "") +
      '<div class="card-content">' +
      this._renderBody() +
      "</div>";
    this._runDepartureListAnimation(root);
    if (this._departureClock) {
      this._departureClock.reschedule();
    }
  }

  _styles() {
    return [
      "ha-card{padding:0}",
      ".card-header .name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
      ".mode-filters-wrap{padding:0 16px 12px}",
      ".mode-filters{display:flex;flex-wrap:wrap;gap:8px}",
      ".mode-filter{border:1px solid var(--divider-color,rgba(255,255,255,.2));background:transparent;color:var(--primary-text-color);border-radius:16px;padding:4px 12px;font-size:.8rem;cursor:pointer}",
      ".mode-filter.active{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color,#fff)}",
      ".departures{font-size:150%}",
      ".status-message{padding:16px;color:var(--secondary-text-color)}",
      ".status-message.error{color:var(--error-color)}",
      ".departures-empty,.departures-error{padding:8px 16px 12px;color:var(--secondary-text-color)}",
      ".row{margin-top:8px;display:flex;justify-content:space-between}",
      ".col{display:flex;flex-direction:column;justify-content:center;position:relative}",
      ".col.icon{flex-basis:40px}",
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
      ".warning-message{color:var(--warning-color)}",
      ".departure-block{margin-top:8px;padding:0 8px}",
      ".row.departure-line{display:flex;align-items:center;gap:4px;margin-top:0}",
      ".row.departure-time{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:flex-start;text-align:left;gap:.35em .75em;margin-top:2px;padding-left:80px}",
      ".row.departure-deviations{display:flex;flex-direction:column;align-items:flex-start;text-align:left;gap:2px;margin-top:2px;padding-left:80px}",
      ".row.departure-deviations .detail-item{display:block;line-height:1.35}",
      ".detail-item{line-height:1.35}",
      ".stop-point-label,.line-type-label{color:#fad370!important;font-weight:500}",
      ".travel-time{color:#4caf50!important;font-weight:600}",
      ".stop-info{margin:0 8px 10px;padding:8px 12px 4px;font-size:smaller;line-height:1.4;color:#fad370!important}",
      ".stop-info-item{color:#fad370!important}",
      ".stop-info-item+.stop-info-item{margin-top:4px}",
      ".short-train{color:#0abcfc;font-weight:600;text-transform:lowercase}",
      ".old-time{text-decoration:line-through;opacity:.65;margin-right:.35em}",
      ".new-time{color:#0abcfc;font-weight:600}",
      ".delay-min{color:#0abcfc;font-weight:600}",
      ".departure-now{color:#fad370!important;font-weight:600}",
      ".cancelled-time{color:#e53935;font-weight:600}",
      ".leaves-in{white-space:nowrap}",
      ".departure-block[data-departure-key]{max-height:500px}",
      ".departure-block.departure-exit-slide{overflow:hidden;box-sizing:border-box;transition:max-height .5s ease,margin-top .5s ease,opacity .5s ease}",
      ".departure-block.departure-exit-slide.departure-exit-slide-active{max-height:0!important;margin-top:0!important;opacity:0}",
      ".mr1{margin-right:8px}",
      ".left{text-align:left}",
      ".right{text-align:right}",
      "ha-icon{width:24px;height:24px;color:var(--paper-item-icon-color)}",
    ].join("");
  }
}

function _defineSlStopDeparturesCard(tag) {
  if (customElements.get(tag)) {
    const proto = customElements.get(tag).prototype;
    const nextProto = SlStopDeparturesCard.prototype;
    Object.getOwnPropertyNames(nextProto).forEach(function (name) {
      if (name !== "constructor") {
        proto[name] = nextProto[name];
      }
    });
    return;
  }
  customElements.define(tag, SlStopDeparturesCard);
}

_defineSlStopDeparturesCard("sl-stop-departures-card");

window.customCards = window.customCards || [];
if (!window.customCards.some(function (card) { return card.type === "sl-stop-departures-card"; })) {
  window.customCards.push({
    type: "sl-stop-departures-card",
    name: "SL hållplats med restid",
    preview: true,
    description: "Visar filtrerade avgångar med avvikelser och restid till hem.",
  });
}
