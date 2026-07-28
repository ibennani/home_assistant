class SlStopsMapCard extends HTMLElement {
  static get CARD_VERSION() {
    return "20260728m";
  }

  static getStubConfig() {
    return {
      location_entity: "person.ilias_bennani",
      home_zone_entity: "zone.home",
      max_stops: 10,
      height: 280,
      focus_site_ids: [9527, 9180, 1923],
      sites_cache_version: "20260728m",
    };
  }

  static getConfigElement() {
    return document.createElement("div");
  }

  setConfig(config) {
    const base = SlStopsMapCard.getStubConfig();
    this.config = Object.assign({}, base, config && typeof config === "object" ? config : {});
    this._scheduleRender();
  }

  set hass(hass) {
    this._hass = hass;
    this._scheduleRender();
  }

  connectedCallback() {
    if (this._cardVersion !== SlStopsMapCard.CARD_VERSION) {
      this._cardVersion = SlStopsMapCard.CARD_VERSION;
      this._map = null;
      this._markers = [];
    }
    this._ensureLeaflet()
      .then(() => this._ensureSitesLoaded())
      .then(() => this._scheduleRender());
  }

  disconnectedCallback() {
    if (this._map) {
      this._map.remove();
      this._map = null;
    }
  }

  getCardSize() {
    return 6;
  }

  _scheduleRender() {
    if (this._renderTimer) {
      return;
    }
    const self = this;
    this._renderTimer = window.requestAnimationFrame(function () {
      self._renderTimer = null;
      self._render();
    });
  }

  _ensureLeaflet() {
    if (window.L) {
      return Promise.resolve();
    }
    if (this._leafletPromise) {
      return this._leafletPromise;
    }
    this._leafletPromise = new Promise(function (resolve, reject) {
      if (!document.querySelector('link[data-sl-leaflet-css]')) {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
        link.setAttribute("data-sl-leaflet-css", "1");
        document.head.appendChild(link);
      }
      const script = document.createElement("script");
      script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      script.onload = function () {
        resolve();
      };
      script.onerror = function () {
        reject(new Error("Kunde inte ladda Leaflet"));
      };
      document.head.appendChild(script);
    });
    return this._leafletPromise;
  }

  _ensureSitesLoaded() {
    if (this._sites) {
      return Promise.resolve(this._sites);
    }
    if (!this._sitesPromise) {
      const version = this.config.sites_cache_version || SlStopsMapCard.CARD_VERSION;
      this._sitesPromise = fetch("/local/sl-sites.json?v=" + version)
        .then((response) => {
          if (!response.ok) {
            throw new Error("Kunde inte läsa sl-sites.json");
          }
          return response.json();
        })
        .then((sites) => {
          this._sites = Array.isArray(sites) ? sites : [];
          return this._sites;
        })
        .catch((error) => {
          this._sitesError = (error && error.message) || String(error);
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

  _getUserLocation() {
    return (
      this._readCoords(this.config.location_entity) ||
      this._readCoords(this.config.home_zone_entity)
    );
  }

  _haversineMeters(lat1, lon1, lat2, lon2) {
    const toRad = (value) => (value * Math.PI) / 180;
    const earthRadius = 6371000;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  _getStops(location) {
    if (!location || !this._sites || !this._sites.length) {
      return [];
    }
    const maxStops = Number(this.config.max_stops || 10);
    const focusIds = new Set(
      (this.config.focus_site_ids || []).map(function (id) {
        return Number(id);
      }),
    );
    const ranked = this._sites
      .map((site) =>
        Object.assign({}, site, {
          distance_m: this._haversineMeters(location.lat, location.lon, site.lat, site.lon),
          focused: focusIds.has(Number(site.id)),
        }),
      )
      .sort((a, b) => {
        if (a.focused !== b.focused) {
          return a.focused ? -1 : 1;
        }
        return a.distance_m - b.distance_m;
      });
    const chosen = [];
    const seen = new Set();
    for (let i = 0; i < ranked.length && chosen.length < maxStops; i++) {
      const site = ranked[i];
      if (seen.has(site.id)) {
        continue;
      }
      seen.add(site.id);
      chosen.push(site);
    }
    return chosen;
  }

  _escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  _setMapStatus(root, html) {
    if (this._map) {
      this._map.remove();
      this._map = null;
    }
    this._markers = [];
    root.innerHTML = html;
  }

  _render() {
    if (!this.config) {
      return;
    }
    const height = Number(this.config.height || 280);
    let root = this.querySelector(".sl-map-root");
    if (!root) {
      this.innerHTML =
        '<ha-card><div class="sl-map-root"></div></ha-card>' +
        "<style>" +
        ".sl-map-root{padding:0}.sl-map-canvas{width:100%;border-radius:0}.sl-map-status{padding:16px;color:var(--secondary-text-color)}" +
        ".sl-map-status.error{color:var(--error-color)}</style>";
      root = this.querySelector(".sl-map-root");
    }
    root.style.height = height + "px";

    if (this._sitesError) {
      this._setMapStatus(
        root,
        '<div class="sl-map-status error">' + this._escapeHtml(this._sitesError) + "</div>",
      );
      return;
    }
    if (!this._sites || !window.L) {
      this._setMapStatus(root, '<div class="sl-map-status">Laddar karta…</div>');
      return;
    }

    const location = this._getUserLocation();
    if (!location) {
      this._setMapStatus(root, '<div class="sl-map-status">Ingen position tillgänglig.</div>');
      return;
    }

    let canvas = root.querySelector(".sl-map-canvas");
    if (!canvas) {
      root.innerHTML = '<div class="sl-map-canvas"></div>';
      canvas = root.querySelector(".sl-map-canvas");
    }
    canvas.style.height = height + "px";

    if (!this._map) {
      this._map = window.L.map(canvas, {
        zoomControl: true,
        attributionControl: true,
      });
      window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(this._map);
    }

    const stops = this._getStops(location);
    this._markers.forEach((marker) => marker.remove());
    this._markers = [];

    const userMarker = window.L.circleMarker([location.lat, location.lon], {
      radius: 8,
      color: "#1e88e5",
      fillColor: "#42a5f5",
      fillOpacity: 0.95,
      weight: 2,
    })
      .addTo(this._map)
      .bindPopup("Din position");
    this._markers.push(userMarker);

    stops.forEach((stop) => {
      const marker = window.L.circleMarker([stop.lat, stop.lon], {
        radius: stop.focused ? 7 : 5,
        color: stop.focused ? "#ec619f" : "#666",
        fillColor: stop.focused ? "#ec619f" : "#999",
        fillOpacity: 0.9,
        weight: 2,
      })
        .addTo(this._map)
        .bindPopup(
          this._escapeHtml(stop.name) +
            "<br>" +
            Math.round(stop.distance_m) +
            " m" +
            (stop.focused ? "<br><em>Favorit</em>" : ""),
        );
      this._markers.push(marker);
    });

    const bounds = window.L.latLngBounds([[location.lat, location.lon]]);
    stops.forEach((stop) => bounds.extend([stop.lat, stop.lon]));
    this._map.fitBounds(bounds.pad(0.2));
    window.setTimeout(() => {
      if (this._map) {
        this._map.invalidateSize();
      }
    }, 100);
  }
}

if (!customElements.get("sl-stops-map-card")) {
  customElements.define("sl-stops-map-card", SlStopsMapCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "sl-stops-map-card")) {
  window.customCards.push({
    type: "sl-stops-map-card",
    name: "SL hållplatskarta",
    preview: true,
    description: "Karta med din position och närmaste SL-hållplatser.",
  });
}
