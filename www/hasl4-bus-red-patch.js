/**
 * SL-röd linjeplatta för bussar i hasl4-departure-card.
 * Fungerar även när HACS-versionen registrerats före den lokala patchen.
 */
(function () {
  const STYLE_ID = "hasl-bus-red-patch-style";
  const STYLE_TEXT = `
    .line-icon.bus_red,
    .line-icon.bus.red {
      background-color: #d71d24 !important;
      color: #fff !important;
      border: none !important;
      text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.35);
    }
  `;

  function injectStyle(shadowRoot) {
    if (!shadowRoot || shadowRoot.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = STYLE_TEXT;
    shadowRoot.appendChild(style);
  }

  function patchLineIconClass(CardClass) {
    if (!CardClass?.prototype || CardClass.prototype.__haslBusRedPatched) return;
    const original = CardClass.prototype.lineIconClass;
    if (typeof original !== "function") return;

    CardClass.prototype.lineIconClass = function (type, line, group) {
      let cls = original.call(this, type, line, group);
      if (typeof cls !== "string") return cls;

      const isBus =
        cls.startsWith("bus ") ||
        cls.startsWith("bus_") ||
        cls.includes(" bus_");
      const isBlueBus = cls.includes(" blue") || group === "blåbuss";

      if (isBus && !isBlueBus) {
        cls = cls.replace(/\s?red\b/g, "").replace(/^bus\b/, "bus_red");
        if (!cls.includes("bus_red")) cls = `bus_red ${cls}`.trim();
      }

      return cls;
    };

    CardClass.prototype.__haslBusRedPatched = true;
  }

  function patchCards() {
    const CardClass = customElements.get("hasl4-departure-card");
    if (CardClass) patchLineIconClass(CardClass);

    document.querySelectorAll("hasl4-departure-card").forEach((card) => {
      if (card.shadowRoot) injectStyle(card.shadowRoot);
    });
  }

  patchCards();

  const observer = new MutationObserver(patchCards);
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.addEventListener("load", patchCards);
  setTimeout(patchCards, 500);
  setTimeout(patchCards, 2000);
})();
