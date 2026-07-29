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

  function needsFastClock(departures, now, thresholdMin) {
    const nearThreshold = thresholdMin == null ? 10 : thresholdMin;
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
    const slow = slowMs == null ? 30000 : slowMs;
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
    needsFastClock: needsFastClock,
    getClockIntervalMs: getClockIntervalMs,
    createAdaptiveClock: createAdaptiveClock,
  };
})(typeof window !== "undefined" ? window : globalThis);
