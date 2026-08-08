/**
 * Delad avgångstidsvisning för SL-kort.
 * >=30 min: klockslag. <30 min: "X min" (avrundat nedåt).
 * Försening: (+X min) i blått, eller genomstruket+klockslag om schemalagd >=30 min bort.
 */
(function (root) {
  function ceilMinutesUntil(from, to) {
    if (!from || !to) {
      return 0;
    }
    return Math.ceil((to.getTime() - from.getTime()) / 60000);
  }

  function floorMinutesUntil(from, to) {
    if (!from || !to) {
      return 0;
    }
    return Math.max(0, Math.floor((to.getTime() - from.getTime()) / 60000));
  }

  function formatDepartureTimeHtml(scheduledAt, expectedAt, now, formatClock) {
    if (!expectedAt || !now || !formatClock) {
      return "";
    }

    const ceilToExpected = ceilMinutesUntil(now, expectedAt);
    if (ceilToExpected <= 0) {
      return '<span class="departure-now">Nu</span>';
    }

    const minToExpected = floorMinutesUntil(now, expectedAt);
    const minToScheduled = scheduledAt ? floorMinutesUntil(now, scheduledAt) : minToExpected;
    const delayMin =
      scheduledAt && expectedAt
        ? Math.max(0, Math.floor((expectedAt.getTime() - scheduledAt.getTime()) / 60000))
        : 0;
    const isDelayed = delayMin >= 1;
    const delaySuffix = isDelayed
      ? ' <span class="delay-min">(+' + delayMin + " min)</span>"
      : "";

    if (isDelayed && minToScheduled >= 30) {
      return (
        '<span class="old-time">' +
        formatClock(scheduledAt) +
        '</span><span class="new-time">' +
        formatClock(expectedAt) +
        "</span>"
      );
    }

    if (minToExpected >= 30) {
      return formatClock(expectedAt) + delaySuffix;
    }

    return minToExpected + " min" + delaySuffix;
  }

  function isDeparted(expectedAt, now) {
    return ceilMinutesUntil(now, expectedAt) < 0;
  }

  function shouldHideDeparted(expectedAt, now, hideDeparted) {
    if (hideDeparted === false) {
      return false;
    }
    return isDeparted(expectedAt, now);
  }

  function parseDepartureDate(dep) {
    if (!dep) {
      return null;
    }
    const raw = dep.expected || dep.scheduled;
    if (!raw) {
      return null;
    }
    if (raw instanceof Date) {
      return raw;
    }
    const parsed = new Date(raw);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  function getDepartureSortMs(dep) {
    const at = parseDepartureDate(dep);
    return at ? at.getTime() : Number.POSITIVE_INFINITY;
  }

  function normalizeDepartureName(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/^stockholm,\s*/i, "")
      .replace(/\bstockholms\b/g, "stockholm")
      .replace(/\s+station$/i, "")
      .replace(/\s+/g, " ");
  }

  function isGenericBusHub(name) {
    const normalized = normalizeDepartureName(name);
    return normalized === "stockholm c" || normalized === "city" || normalized === "centralen";
  }

  var busLineTerminusMap = null;
  var busLineTerminusVersion = null;
  var busLineTerminusPromise = null;

  function getBusLineTerminus(designation, directionCode) {
    if (!busLineTerminusMap || !designation) {
      return null;
    }
    let branch = null;
    if (directionCode === 2 || directionCode === "2") {
      branch = "2";
    } else if (directionCode === 1 || directionCode === "1") {
      branch = "1";
    }
    if (!branch) {
      return null;
    }
    const line = busLineTerminusMap[String(designation)];
    return line && line[branch] ? String(line[branch]) : null;
  }

  function ensureBusLineTerminus(version) {
    const cacheVersion = version || "1";
    if (busLineTerminusMap && busLineTerminusVersion === cacheVersion) {
      return Promise.resolve(busLineTerminusMap);
    }
    if (busLineTerminusPromise && busLineTerminusVersion === cacheVersion) {
      return busLineTerminusPromise;
    }
    busLineTerminusVersion = cacheVersion;
    busLineTerminusPromise = fetch(
      "/local/sl-bus-line-terminus.json?v=" + encodeURIComponent(cacheVersion),
    )
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Kunde inte ladda busslinje-data");
        }
        return response.json();
      })
      .then(function (data) {
        busLineTerminusMap = data || {};
        return busLineTerminusMap;
      })
      .catch(function () {
        busLineTerminusMap = {};
        return busLineTerminusMap;
      });
    return busLineTerminusPromise;
  }

  function formatDepartureLabel(dep) {
    if (!dep) {
      return "";
    }
    const destPattern = /(?: station(?: \([^)]+\))?| \([^)]+\))$/;
    const line = dep.line || {};
    const mode = String(line.transport_mode || "").toUpperCase();
    const destination = String(dep.destination || "").trim();
    const direction = String(dep.direction || "").trim();
    let label = destination || direction;

    if (mode === "TRAIN") {
      // Pendeltåg: destination = reseled, direction = slutstation.
      if (direction && normalizeDepartureName(direction) !== normalizeDepartureName(destination)) {
        label = direction;
      }
      label = label.replace(destPattern, "").trim();
    } else if (mode === "BUS") {
      // Buss: vid korttur skiljer sig destination (t.ex. Gullmarsplan) från linjens riktning.
      if (
        destination &&
        direction &&
        normalizeDepartureName(destination) !== normalizeDepartureName(direction)
      ) {
        label = destination;
      } else if (isGenericBusHub(destination)) {
        const terminus = getBusLineTerminus(line.designation, dep.direction_code);
        if (terminus) {
          label = terminus;
        }
      }
    }

    return label;
  }

  function compareDeparturesByTime(a, b) {
    const diff = getDepartureSortMs(a) - getDepartureSortMs(b);
    if (diff !== 0) {
      return diff;
    }
    const aLine = String((a && a.line && a.line.designation) || "");
    const bLine = String((b && b.line && b.line.designation) || "");
    if (aLine !== bLine) {
      return aLine.localeCompare(bLine);
    }
    return formatDepartureLabel(a).localeCompare(formatDepartureLabel(b));
  }

  function sortDeparturesByTime(departures) {
    return (departures || []).slice().sort(compareDeparturesByTime);
  }

  function needsFastClock(departures, now, thresholdMin) {
    const nearThreshold = thresholdMin == null ? 30 : thresholdMin;
    const current = now || new Date();
    if (!departures || !departures.length) {
      return false;
    }
    for (let i = 0; i < departures.length; i++) {
      const expectedAt = parseDepartureDate(departures[i]);
      if (!expectedAt) {
        continue;
      }
      const mins = (expectedAt.getTime() - current.getTime()) / 60000;
      if (mins < nearThreshold && mins >= -1) {
        return true;
      }
    }
    return false;
  }

  function getClockIntervalMs(departures, now, fastMs, slowMs, thresholdMin) {
    const fast = fastMs == null ? 5000 : fastMs;
    const slow = slowMs == null ? 15000 : slowMs;
    return needsFastClock(departures, now, thresholdMin) ? fast : slow;
  }

  function createAdaptiveClock(options) {
    let timer = null;
    let stopped = true;
    const opts = options || {};

    function clearTimer() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    function schedule() {
      clearTimer();
      if (stopped) {
        return;
      }
      const now = new Date();
      const departures = typeof opts.getDepartures === "function" ? opts.getDepartures() : [];
      const interval = getClockIntervalMs(
        departures,
        now,
        opts.fastMs,
        opts.slowMs,
        opts.nearThresholdMin,
      );
      timer = setTimeout(function () {
        if (stopped) {
          return;
        }
        if (typeof opts.onTick === "function") {
          opts.onTick();
        }
        schedule();
      }, interval);
    }

    return {
      start: function () {
        stopped = false;
        schedule();
      },
      stop: function () {
        stopped = true;
        clearTimer();
      },
      reschedule: function () {
        if (!stopped) {
          schedule();
        }
      },
    };
  }

  root.SlDepartureTime = {
    ceilMinutesUntil: ceilMinutesUntil,
    floorMinutesUntil: floorMinutesUntil,
    formatHtml: formatDepartureTimeHtml,
    isDeparted: isDeparted,
    shouldHideDeparted: shouldHideDeparted,
    parseDepartureDate: parseDepartureDate,
    getDepartureSortMs: getDepartureSortMs,
    formatDepartureLabel: formatDepartureLabel,
    ensureBusLineTerminus: ensureBusLineTerminus,
    getBusLineTerminus: getBusLineTerminus,
    compareDeparturesByTime: compareDeparturesByTime,
    sortDeparturesByTime: sortDeparturesByTime,
    needsFastClock: needsFastClock,
    getClockIntervalMs: getClockIntervalMs,
    createAdaptiveClock: createAdaptiveClock,
  };
})(typeof window !== "undefined" ? window : globalThis);
