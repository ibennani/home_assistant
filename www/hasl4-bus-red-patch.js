/**
 * SL-röd linjeplatta för bussar i hasl4-departure-card.
 * Patchar klassen vid registrering och stylar shadow-DOM direkt.
 */
(function () {
  const STYLE_ID = "hasl-sl-bus-red-style";
  const BUS_RED = "#9e0e13";
  const STYLE_TEXT = `
    .line-icon.bus_red,
    .line-icon.bus.red,
    .line-icon.bus:not(.blue),
    .line-icon[class*="bus_"]:not(.blue):not(.train):not(.metro):not(.tram) {
      background-color: ${BUS_RED} !important;
      color: #fff !important;
      border: none !important;
      text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.35);
    }
  `;

  function isBusIcon(el) {
    const cls = el.className || "";
    if (/\bblue\b/.test(cls) || /\b(train|metro|tram)\b/.test(cls)) return false;
    return /\bbus\b/.test(cls) || /\bbus_\d/.test(cls);
  }

  function styleBusIcons(root) {
    if (!root) return;
    root.querySelectorAll(".line-icon").forEach((el) => {
      if (!isBusIcon(el)) return;
      el.style.setProperty("background-color", BUS_RED, "important");
      el.style.setProperty("color", "#fff", "important");
      el.style.setProperty("border", "none", "important");
      el.style.setProperty("text-shadow", "1px 1px 2px rgba(0, 0, 0, 0.35)", "important");
    });
  }

  function injectStyle(shadowRoot) {
    if (!shadowRoot) return;
    let style = shadowRoot.getElementById(STYLE_ID);
    if (!style) {
      style = document.createElement("style");
      style.id = STYLE_ID;
      style.textContent = STYLE_TEXT;
      shadowRoot.appendChild(style);
    }
    styleBusIcons(shadowRoot);
  }

  function patchLineIconClass(CardClass) {
    if (!CardClass?.prototype || CardClass.prototype.__haslBusRedPatched) return;
    const original = CardClass.prototype.lineIconClass;
    if (typeof original !== "function") return;

    CardClass.prototype.lineIconClass = function (type, line, group) {
      let cls = original.call(this, type, line, group);
      if (typeof cls !== "string") return cls;

      const isBusType = type === "BUS" || cls.startsWith("bus ") || cls.startsWith("bus_") || cls.includes(" bus_");
      const isBlueBus = cls.includes(" blue") || group === "blåbuss";

      if (isBusType && !isBlueBus) {
        cls = cls.replace(/\s?red\b/g, "").replace(/^bus\b/, "bus_red");
        if (!cls.includes("bus_red")) cls = `bus_red ${cls}`.trim();
      }

      return cls;
    };

    CardClass.prototype.__haslBusRedPatched = true;
  }

  function observeCard(card) {
    if (!card || card.__haslBusRedObserved) return;
    card.__haslBusRedObserved = true;

    const run = () => {
      if (card.shadowRoot) injectStyle(card.shadowRoot);
    };

    run();

    const rootObserver = new MutationObserver(run);
    const attachRootObserver = () => {
      if (!card.shadowRoot) return;
      rootObserver.observe(card.shadowRoot, { childList: true, subtree: true });
      run();
    };

    attachRootObserver();

    const cardObserver = new MutationObserver(() => {
      attachRootObserver();
      run();
    });
    cardObserver.observe(card, { childList: true, subtree: true });
  }

  function patchCards() {
    const CardClass = customElements.get("hasl4-departure-card");
    if (CardClass) patchLineIconClass(CardClass);
    document.querySelectorAll("hasl4-departure-card").forEach(observeCard);
  }

  const originalDefine = customElements.define.bind(customElements);
  customElements.define = function (name, cls, options) {
    if (name === "hasl4-departure-card") patchLineIconClass(cls);
    return originalDefine(name, cls, options);
  };

  patchCards();

  const domObserver = new MutationObserver(patchCards);
  domObserver.observe(document.documentElement, { childList: true, subtree: true });

  window.addEventListener("load", patchCards);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) patchCards();
  });

  [250, 1000, 3000, 8000].forEach((ms) => setTimeout(patchCards, ms));
})();
