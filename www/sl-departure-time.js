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

  root.SlDepartureTime = {
    ceilMinutesUntil: ceilMinutesUntil,
    floorMinutesUntil: floorMinutesUntil,
    formatHtml: formatDepartureTimeHtml,
    isDeparted: isDeparted,
    shouldHideDeparted: shouldHideDeparted,
  };
})(typeof window !== "undefined" ? window : globalThis);
