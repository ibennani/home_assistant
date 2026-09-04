/**
 * Utanimationslogik när avgångar försvinner (avgångna).
 * Tona bort och rulla upp samtidigt (0,5 s).
 */
(function (root) {
  var EXIT_MS = 500;

  function departureKey(dep) {
    if (root.SlDepartureTime && root.SlDepartureTime.departureKey) {
      return root.SlDepartureTime.departureKey(dep);
    }
    if (!dep) {
      return "";
    }
    var line = dep.line || {};
    var stopPoint = dep.stop_point || {};
    return [
      dep.scheduled || "",
      line.designation || "",
      line.transport_mode || "",
      dep.destination || dep.direction || "",
      dep.direction_code != null ? String(dep.direction_code) : "",
      stopPoint.id != null ? String(stopPoint.id) : stopPoint.designation || "",
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
        completedExits: new Set(),
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
    scope.completedExits = new Set();
    scope.lastVisibleKeys = null;
    scope.lastDepsByKey.clear();
  };

  Manager.prototype.buildRenderList = function (scopeId, options) {
    var activeDeps = options.activeDeps || [];
    var allDeps = options.allDeps || activeDeps;
    var shouldHideDeparted = options.shouldHideDeparted;
    var now = options.now || new Date();
    var scope = this._getScope(scopeId);
    var keyFn = departureKey;
    var compare =
      root.SlDepartureTime && root.SlDepartureTime.compareDeparturesByTime
        ? root.SlDepartureTime.compareDeparturesByTime
        : function (a, b) {
            var aTime = new Date(a.expected || a.scheduled || 0).getTime();
            var bTime = new Date(b.expected || b.scheduled || 0).getTime();
            return aTime - bTime;
          };

    var allMap = new Map();
    for (var i = 0; i < allDeps.length; i++) {
      var allDep = allDeps[i];
      var allKey = keyFn(allDep);
      if (allKey) {
        allMap.set(allKey, allDep);
      }
    }

    var activeItems = [];
    var activeKeySet = new Set();
    for (var j = 0; j < activeDeps.length; j++) {
      var dep = activeDeps[j];
      var baseKey = keyFn(dep) || "dep-" + String(j);
      var key = baseKey;
      var suffix = 0;
      while (activeKeySet.has(key)) {
        suffix++;
        key = baseKey + "#" + suffix;
      }
      activeKeySet.add(key);
      activeItems.push({ dep: dep, key: key, isExiting: false });
      if (scope.completedExits) {
        scope.completedExits.delete(key);
      }
    }

    if (scope.lastVisibleKeys) {
      scope.lastVisibleKeys.forEach(function (prevKey) {
        if (activeKeySet.has(prevKey) || scope.exiting.has(prevKey)) {
          return;
        }
        if (scope.completedExits && scope.completedExits.has(prevKey)) {
          return;
        }
        var dep = allMap.get(prevKey) || scope.lastDepsByKey.get(prevKey);
        if (!dep || !shouldHideDeparted(dep, now)) {
          return;
        }
        scope.exiting.set(prevKey, { dep: dep, phase: "pending-exit" });
      });
    }

    var renderItems = activeItems.slice();
    scope.exiting.forEach(function (entry, key) {
      if (activeKeySet.has(key)) {
        return;
      }
      renderItems.push({ dep: entry.dep, key: key, isExiting: true });
    });

    renderItems.sort(function (a, b) {
      return compare(a.dep, b.dep);
    });

    scope.lastVisibleKeys = activeKeySet;
    scope.lastDepsByKey = new Map(allMap);
    for (var k = 0; k < activeItems.length; k++) {
      scope.lastDepsByKey.set(activeItems[k].key, activeItems[k].dep);
    }

    return renderItems;
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
        if (!scope.completedExits) {
          scope.completedExits = new Set();
        }
        scope.completedExits.add(key);
        remaining--;
        if (remaining === 0 && typeof onComplete === "function") {
          onComplete();
        }
      }, EXIT_MS);
    });
  };

  Manager.prototype.hasPendingExit = function (scopeId) {
    var scope = this._scopes.get(scopeId);
    if (!scope) {
      return false;
    }
    var pending = false;
    scope.exiting.forEach(function (entry) {
      if (entry.phase === "pending-exit") {
        pending = true;
      }
    });
    return pending;
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
