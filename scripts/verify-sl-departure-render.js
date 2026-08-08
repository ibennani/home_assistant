#!/usr/bin/env node
/**
 * Verifierar att SL-avgångar renderas korrekt (t.ex. 830 Farsta vid Länna gård)
 * även när SL återanvänder journey.id mellan linjer.
 */
const https = require("https");

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    https
      .get(url, (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          try {
            resolve(JSON.parse(data));
          } catch (error) {
            reject(error);
          }
        });
      })
      .on("error", reject);
  });
}

function departureKey(dep) {
  const line = dep.line || {};
  const stopPoint = dep.stop_point || {};
  return [
    dep.scheduled || "",
    line.designation || "",
    line.transport_mode || "",
    dep._rawDestination || dep.destination || dep.direction || "",
    dep.direction_code != null ? String(dep.direction_code) : "",
    stopPoint.id != null ? String(stopPoint.id) : stopPoint.designation || "",
  ].join("|");
}

function shouldHideDepartedDeparture(dep, now) {
  if (!dep) {
    return false;
  }
  let expectedAt = dep.expected ? new Date(dep.expected) : null;
  if (!expectedAt || isNaN(expectedAt.getTime())) {
    expectedAt = dep.scheduled ? new Date(dep.scheduled) : null;
  }
  if (!expectedAt || isNaN(expectedAt.getTime())) {
    return false;
  }
  return now.getTime() > expectedAt.getTime();
}

function buildRenderList(activeDeps) {
  const activeItems = [];
  const activeKeySet = new Set();
  for (let j = 0; j < activeDeps.length; j++) {
    const dep = activeDeps[j];
    const baseKey = departureKey(dep) || "dep-" + String(j);
    let key = baseKey;
    let suffix = 0;
    while (activeKeySet.has(key)) {
      suffix++;
      key = baseKey + "#" + suffix;
    }
    activeKeySet.add(key);
    activeItems.push({ dep, key });
  }
  activeItems.sort(
    (a, b) =>
      new Date(a.dep.expected || a.dep.scheduled) - new Date(b.dep.expected || b.dep.scheduled),
  );
  return activeItems;
}

async function main() {
  const delayedDep = {
    scheduled: "2026-08-08T13:20:00+02:00",
    expected: "2026-08-08T13:25:00+02:00",
    line: { designation: "830", transport_mode: "BUS" },
    destination: "Farsta centrum",
    direction_code: 2,
    stop_point: { id: 80792 },
  };
  const nowBetween = new Date("2026-08-08T13:22:00+02:00");
  if (shouldHideDepartedDeparture(delayedDep, nowBetween)) {
    console.error(
      "MISSLYCKAD: Försenad avgång dold trots att prognostiserad tid inte passerat",
    );
    process.exit(1);
  }
  const nowAfter = new Date("2026-08-08T13:26:00+02:00");
  if (!shouldHideDepartedDeparture(delayedDep, nowAfter)) {
    console.error("MISSLYCKAD: Avgång ska döljas efter prognostiserad tid");
    process.exit(1);
  }
  console.log("OK: Försenad avgång synlig tills expected passerat");

  const payload = await fetchJson(
    "https://transport.integration.sl.se/v1/sites/8194/departures?forecast=60",
  );
  const departures = (payload.departures || []).map((dep) =>
    Object.assign({}, dep, {
      _rawDestination: dep.destination,
    }),
  );

  const rendered = buildRenderList(departures);
  if (rendered.length !== departures.length) {
    console.error(
      "MISSLYCKAD: Renderade",
      rendered.length,
      "av",
      departures.length,
      "avgångar",
    );
    process.exit(1);
  }

  const first830Farsta = rendered.find(
    (item) =>
      String(item.dep.line && item.dep.line.designation) === "830" &&
      String(item.dep.destination || "").toLowerCase().includes("farsta"),
  );

  if (first830Farsta) {
    console.log(
      "OK: Länna gård —",
      rendered.length,
      "avgångar, 830 Farsta finns:",
      first830Farsta.dep.expected || first830Farsta.dep.scheduled,
    );
  } else {
    console.log(
      "OK: Länna gård —",
      rendered.length,
      "avgångar (ingen 830 Farsta i API just nu)",
    );
  }
}

main().catch((error) => {
  console.error("MISSLYCKAD:", error.message || error);
  process.exit(1);
});
