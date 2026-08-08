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
  const payload = await fetchJson(
    "https://transport.integration.sl.se/v1/sites/8194/departures?forecast=60",
  );
  const departures = (payload.departures || []).map((dep) =>
    Object.assign({}, dep, {
      _rawDestination: dep.destination,
    }),
  );

  const rendered = buildRenderList(departures);
  const first830Farsta = rendered.find(
    (item) =>
      String(item.dep.line && item.dep.line.designation) === "830" &&
      String(item.dep.destination || "").toLowerCase().includes("farsta"),
  );

  if (!first830Farsta) {
    console.error("MISSLYCKAD: Ingen 830 mot Farsta centrum i render-listan");
    process.exit(1);
  }

  const firstFarsta = rendered.find((item) =>
    String(item.dep.destination || "").toLowerCase().includes("farsta"),
  );
  if (
    firstFarsta &&
    String(firstFarsta.dep.line && firstFarsta.dep.line.designation) !== "830"
  ) {
    console.error(
      "MISSLYCKAD: Första Farsta-avgången är linje",
      firstFarsta.dep.line.designation,
      "inte 830 (journey.id-kollision)",
    );
    process.exit(1);
  }

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

  console.log(
    "OK: Länna gård —",
    rendered.length,
    "avgångar, första 830 Farsta",
    first830Farsta.dep.expected || first830Farsta.dep.scheduled,
  );
}

main().catch((error) => {
  console.error("MISSLYCKAD:", error.message || error);
  process.exit(1);
});
