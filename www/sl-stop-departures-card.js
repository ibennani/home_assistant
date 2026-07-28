class SlStopDeparturesCard extends HTMLElement {
  static get CARD_VERSION() {
    return "20260728g";
  }

  static getStubConfig() {
    return {
      title: "Huddinge centrum",
      site_id: 9527,
      forecast_minutes: 120,
      hide_departed: true,
      show_time_always: true,
      language: "sv-SE",
      refresh_seconds: 60,
      alight_train_site_id: 9180,
      alight_bus_site_id: 1923,
      walk_train_minutes: 14,
      walk_bus_minutes: 9,
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
    this._updateView();
    this._syncRefreshTimer();
  }

  connectedCallback() {
    if (this._cardVersion !== SlStopDeparturesCard.CARD_VERSION) {
      this._cardVersion = SlStopDeparturesCard.CARD_VERSION;
    }
    this._loadData(false);
    this._syncRefreshTimer();
  }

  disconnectedCallback() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = undefined;
    }
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

  _formatItdParams(when) {
    const date = when.toLocaleDateString("sv-SE", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    const parts = date.split("-");
    return {
      itd_date: parts[0] + parts[1] + parts[2],
      itd_time:
        String(when.getHours()).padStart(2, "0") + String(when.getMinutes()).padStart(2, "0"),
    };
  }

  _callJourneyPlanner(originSite, destSite, when) {
    const itd = this._formatItdParams(when);
    return this._callWithResponse("rest_command", "sl_journey_to_site", {
      origin_site: Number(originSite),
      dest_site: Number(destSite),
      itd_date: itd.itd_date,
      itd_time: itd.itd_time,
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

  _prepareDepartures(departures) {
    const now = Date.now();
    const hideDeparted = !this.config || this.config.hide_departed !== false;
    const destPattern = /(?: station(?: \([^)]+\))?| \([^)]+\))$/;
    const items = [];
    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const kind = this._matchesDeparture(dep);
      if (!kind) {
        continue;
      }
      const expected = dep.expected || dep.scheduled;
      const expectedMs = expected ? new Date(expected).getTime() : Number.POSITIVE_INFINITY;
      let destination = dep.destination || "";
      if (dep.line && dep.line.transport_mode === "TRAIN") {
        destination = destination.replace(destPattern, "").trim();
      }
      if (hideDeparted && isFinite(expectedMs) && expectedMs + 5 * 60 * 1000 < now) {
        continue;
      }
      items.push(
        Object.assign({}, dep, {
          destination: destination,
          _expectedMs: expectedMs,
          _kind: kind,
        }),
      );
    }
    items.sort(function (a, b) {
      return a._expectedMs - b._expectedMs;
    });
    return items;
  }

  _buildBusJourneyMap(departures) {
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

  _walkMinutes(kind) {
    if (kind === "train") {
      return Number(this.config.walk_train_minutes || 14);
    }
    return Number(this.config.walk_bus_minutes || 9);
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
    const walk = this._walkMinutes("bus");
    if (pt === null) {
      return Number(this.config.bus_pt_fallback_minutes || 20) + walk;
    }
    return pt + walk;
  }

  _computeTrainPtMinutes(journeyPayload) {
    const journeys = journeyPayload.journeys || [];
    const first = journeys[0];
    if (!first) {
      return Number(this.config.train_pt_fallback_minutes || 31);
    }
    const seconds = first.tripRtDuration || first.tripDuration;
    if (!seconds) {
      return Number(this.config.train_pt_fallback_minutes || 31);
    }
    return Math.max(1, Math.round(seconds / 60));
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
    const pending = [];

    for (let i = 0; i < departures.length; i++) {
      const dep = departures[i];
      const key = self._travelCacheKey(dep);
      if (self._travelCache.has(key)) {
        dep._travelMinutes = self._travelCache.get(key);
        continue;
      }
      if (dep._kind === "bus") {
        const total = self._computeBusTravelMinutes(dep, busJourneyMap);
        self._travelCache.set(key, total);
        dep._travelMinutes = total;
        continue;
      }
      pending.push(dep);
    }

    if (!pending.length) {
      self._updateView();
      return Promise.resolve();
    }

    let chain = Promise.resolve();
    pending.forEach(function (dep) {
      chain = chain.then(function () {
        const when = self._parseDate(dep.expected || dep.scheduled) || new Date();
        return self
          ._callJourneyPlanner(
            self.config.site_id,
            self.config.alight_train_site_id,
            when,
          )
          .then(function (payload) {
            const total =
              self._computeTrainPtMinutes(payload) + self._walkMinutes("train");
            const key = self._travelCacheKey(dep);
            self._travelCache.set(key, total);
            dep._travelMinutes = total;
          })
          .catch(function () {
            const total =
              Number(self.config.train_pt_fallback_minutes || 31) +
              self._walkMinutes("train");
            const key = self._travelCacheKey(dep);
            self._travelCache.set(key, total);
            dep._travelMinutes = total;
          });
      });
    });
    return chain.then(function () {
      self._updateView();
    });
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
    Promise.all([
      self._callSiteDepartures(siteId),
      self._callSiteDepartures(busSiteId).catch(function () {
        return { departures: [], stop_deviations: [] };
      }),
    ])
      .then(function (results) {
        const main = results[0];
        const busSite = results[1];
        const departures = self._prepareDepartures(main.departures || []);
        self._data = {
          loading: false,
          departures: departures,
          stop_deviations: main.stop_deviations || [],
          busJourneyMap: self._buildBusJourneyMap(busSite.departures || []),
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

  _renderBody() {
    const data = this._data || { loading: true };
    if (data.loading) {
      return '<div class="status-message">Hämtar avgångar…</div>';
    }
    if (data.error) {
      return '<div class="status-message error">' + this._escapeHtml(data.error) + "</div>";
    }

    const departures = data.departures || [];
    const bannerMessages = this._collectBannerMessages(data.stop_deviations, departures);
    const stopInfoBlock = this._renderStopInfoBlock(bannerMessages);

    if (!departures.length) {
      return stopInfoBlock + '<div class="departures-empty">Inga matchande avgångar.</div>';
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
      const detailMeta = self._renderDepartureMeta(detailItems);

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
        detailMeta +
        "</div>";
    }

    return (
      stopInfoBlock +
      '<div class="departures"><div class="row header"><div class="col icon"></div><div class="col main left">Linje</div><div class="col right">Avgång</div></div>' +
      rows +
      "</div>"
    );
  }

  _updateView() {
    if (!this.config) {
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
    const title = this.config.title || "Hållplats";
    root.innerHTML =
      '<div class="list-header"><strong>' +
      this._escapeHtml(title) +
      "</strong></div>" +
      this._renderBody();
  }

  _styles() {
    return [
      "ha-card{padding:0 0 12px}",
      ".list-header{padding:14px 16px 8px;font-size:.9rem;color:var(--secondary-text-color);border-bottom:1px solid var(--divider-color,rgba(0,0,0,.12))}",
      ".list-header strong{color:var(--primary-text-color);font-size:1rem}",
      ".status-message{padding:16px;color:var(--secondary-text-color)}",
      ".status-message.error{color:var(--error-color)}",
      ".departures-empty,.departures-error{padding:8px 16px 12px;color:var(--secondary-text-color)}",
      ".departure-block.departed .main{text-decoration:line-through;color:var(--secondary-text-color)}",
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
      ".departure-block{margin-top:8px;padding:0 8px}",
      ".departure-block .row.departure{margin-top:0}",
      ".departure-meta{display:flex;flex-direction:column;gap:2px;padding:2px 0 0 80px;margin-bottom:2px}",
      ".detail-item{font-size:smaller;line-height:1.35}",
      ".stop-point-label,.line-type-label{color:#fad370!important;font-weight:500}",
      ".travel-time{color:#4caf50!important;font-weight:600}",
      ".stop-info{margin:0 8px 10px;padding:8px 12px 4px;font-size:smaller;line-height:1.4;color:#fad370!important}",
      ".stop-info-item{color:#fad370!important}",
      ".stop-info-item+.stop-info-item{margin-top:4px}",
      ".short-train{color:#0abcfc;font-size:smaller;font-weight:600;text-transform:lowercase}",
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
