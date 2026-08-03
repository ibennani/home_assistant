(function () {
  const SL_PATH = "sl-nara";
  const SESSION_KEY = "sl-tab-cache-busted";
  const SL_ASSETS = [
    "/local/sl-nearby-card.js",
    "/local/sl-departure-time.js",
    "/local/sl-departure-list-animation.js",
    "/local/sl-tab-cache-bust.js",
    "/local/sl-nearby-card.version.txt",
  ];

  function isSlTab() {
    try {
      return window.location.pathname.indexOf(SL_PATH) >= 0;
    } catch (error) {
      return false;
    }
  }

  async function clearBrowserCaches() {
    if (!("caches" in window)) {
      return;
    }
    try {
      const keys = await caches.keys();
      await Promise.all(
        keys.map(function (key) {
          return caches.delete(key);
        }),
      );
    } catch (error) {
      /* ignore */
    }
  }

  async function prefetchFreshAssets() {
    const bust = Date.now();
    await Promise.all(
      SL_ASSETS.map(function (url) {
        return fetch(url + "?_=" + bust, {
          cache: "no-store",
          credentials: "same-origin",
        }).catch(function () {});
      }),
    );
  }

  let handling = false;

  async function handleSlTabEnter() {
    if (!isSlTab() || handling || sessionStorage.getItem(SESSION_KEY)) {
      return;
    }

    handling = true;
    try {
      await clearBrowserCaches();
      await prefetchFreshAssets();
      sessionStorage.setItem(SESSION_KEY, String(Date.now()));
      window.location.reload();
    } finally {
      handling = false;
    }
  }

  function handleNavigationAwayFromSlTab() {
    if (!isSlTab()) {
      sessionStorage.removeItem(SESSION_KEY);
    }
  }

  window.addEventListener("location-changed", function () {
    handleNavigationAwayFromSlTab();
    handleSlTabEnter();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", handleSlTabEnter);
  } else {
    handleSlTabEnter();
  }
})();
