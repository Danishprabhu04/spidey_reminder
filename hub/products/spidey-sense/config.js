// Spidey's page settings, taken from the hub catalog (hub/assets/catalog.js).
window.SPIDEY = (() => {
  const p = window.HUB.product("spidey-sense");
  return {
    VERSION: p.version,
    RELEASE_BASE: p.releaseBase,
    RELEASES_PAGE: p.releasesPage,
    FILES: p.downloads,
    GITHUB: window.HUB.github,
    LINKEDIN: window.HUB.linkedin,
    DASHBOARD_URL: p.dashboardUrl,
  };
})();
