/**
 * Utanimationslogik när avgångar försvinner (avgångna).
 * Tona bort och rulla upp samtidigt (0,5 s).
 */
(function (root) {
  var EXIT_MS = 500;

  function departureKey(dep) {
    if (!dep) {
      return "";
    }
    var line = dep.line || {};
    var stopPoint = dep.stop_point || {};
    // SL återanvänder journey.id mellan helt olika avgångar — använd aldrig bara journey-id.
    return [
      dep.scheduled || dep.expected || "",
      line.designation || "",
      line.transport_mode || "",
      dep.destination || dep.direction || "",
      dep.direction_code != null ? String(dep.direction_code) : "",
      stopPoint.designation || "",
    ].join("|");
  }

  function animationCss() {
    return [
      ".departure-block[data-departure-key]{max-height:500px}",
      ".departure-block.departure-exit-slide{overflow:hidden;box-sizing:border-box;transition:max-height " +
        EXIT_MS +
        "ms ease,margin-top " +
        EXIT_MS +
        "ms ease,opacity " +
        EXIT_MS +
        "ms ease}",
      ".departure-block.departure-exit-slide.departure-exit-slide-active{max-height:0!important;margin-top:0!important;opacity:0}",
    ].join("");
  }

  function Manager() {
    this._scopes = new Map();
  }

  Manager.prototype._getScope = function (scopeId) {
    if (!this._scopes.has(scopeId)) {
      this._scopes.set(scopeId, {
        exiting: new Map(),
        lastVisibleKeys: null,
        lastDepsByKey: new Map(),
        timers: [],
      });
    }
    return this._scopes.get(scopeId);
  };

  Manager.prototype._schedule = function (scope, fn, delay) {
    var timer = setTimeout(fn, delay);
    scope.timers.push(timer);
    return timer;
  };

  Manager.prototype.resetScope = function (scopeId) {
    var scope = this._scopes.get(scopeId);
    if (!scope) {
      return;
    }
    for (var i = 0; i < scope.timers.length; i++) {
      clearTimeout(scope.timers[i]);
    }
    scope.timers = [];
    scope.exiting.clear();
    scope.lastVisibleKeys = null;
    scope.lastDepsByKey.clear();
  };

  Manager.prototype.buildRenderList = function (scopeId, options) {
    var activeDeps = options.activeDeps || [];
    var allDeps = options.allDeps || activeDeps;
    var shouldHideDeparted = options.shouldHideDeparted;
    var now = options.now || new Date();
    var scope = this._getScope(scopeId);

    var activeMap = new Map();
    var allMap = new Map();
    for (var i = 0; i < allDeps.length; i++) {
      var allKey = departureKey(allDeps[i]);
      if (allKey) {
        allMap.set(allKey, allDeps[i]);
      }
    }
    for (var j = 0; j < activeDeps.length; j++) {
      var activeKey = departureKey(activeDeps[j]);
      if (activeKey) {
        activeMap.set(activeKey, activeDeps[j]);
      }
    }

    if (scope.lastVisibleKeys) {
      scope.lastVisibleKeys.forEach(function (key) {
        if (activeMap.has(key) || scope.exiting.has(key)) {
          return;
        }
        var dep = allMap.get(key) || scope.lastDepsByKey.get(key);
        if (!dep || !shouldHideDeparted(dep, now)) {
          return;
        }
        scope.exiting.set(key, { dep: dep, phase: "pending-exit" });
      });
    }

    var renderItems = [];
    var seen = new Set();
    var ordered = activeDeps.slice();
    scope.exiting.forEach(function (entry, key) {
      if (!activeMap.has(key)) {
        ordered.push(entry.dep);
      }
    });
    var compare =
      root.SlDepartureTime && root.SlDepartureTime.compareDeparturesByTime
        ? root.SlDepartureTime.compareDeparturesByTime
        : function (a, b) {
            var aTime = new Date(a.expected || a.scheduled || 0).getTime();
            var bTime = new Date(b.expected || b.scheduled || 0).getTime();
            return aTime - bTime;
          };
    ordered.sort(compare);

    for (var k = 0; k < ordered.length; k++) {
      var dep = ordered[k];
      var key = departureKey(dep);
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      renderItems.push(key);
    }

    scope.lastVisibleKeys = new Set(activeMap.keys());
    scope.lastDepsByKey = allMap;

    return renderItems.map(function (key) {
      var dep = activeMap.get(key) || scope.exiting.get(key).dep;
      return {
        dep: dep,
        key: key,
        isExiting: scope.exiting.has(key),
      };
    });
  };

  Manager.prototype.buildRows = function (scopeId, options) {
    var renderRow = options.renderRow;
    var items = this.buildRenderList(scopeId, options);
    var html = "";
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      html += renderRow(
        item.dep,
        item.isExiting ? " departure-exiting" : "",
        item.key,
      );
    }
    return html;
  };

  Manager.prototype.afterRender = function (scopeId, listEl, onComplete) {
    if (!listEl) {
      return;
    }
    var scope = this._getScope(scopeId);
    var self = this;
    var remaining = 0;

    scope.exiting.forEach(function (entry, key) {
      if (entry.phase !== "pending-exit") {
        return;
      }
      var el = listEl.querySelector('[data-departure-key="' + cssEscape(key) + '"]');
      if (!el) {
        scope.exiting.delete(key);
        return;
      }
      remaining++;
      entry.phase = "exit";
      el.style.maxHeight = el.offsetHeight + "px";
      el.classList.add("departure-exit-slide");
      requestAnimationFrame(function () {
        el.classList.add("departure-exit-slide-active");
      });
      self._schedule(scope, function () {
        scope.exiting.delete(key);
        remaining--;
        if (remaining === 0 && typeof onComplete === "function") {
          onComplete();
        }
      }, EXIT_MS);
    });
  };

  Manager.prototype.isAnimating = function (scopeId) {
    var scope = this._scopes.get(scopeId);
    return !!(scope && scope.exiting.size > 0);
  };

  function cssEscape(value) {
    if (typeof CSS !== "undefined" && CSS.escape) {
      return CSS.escape(value);
    }
    return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }

  root.SlDepartureListAnim = {
    EXIT_MS: EXIT_MS,
    FADE_MS: EXIT_MS,
    SLIDE_MS: EXIT_MS,
    departureKey: departureKey,
    animationCss: animationCss,
    manager: new Manager(),
  };
})(typeof window !== "undefined" ? window : globalThis);
