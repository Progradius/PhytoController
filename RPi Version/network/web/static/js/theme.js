(() => {
  "use strict";

  const STORAGE_KEY = "phyto.theme";
  const root = document.documentElement;
  let theme = "dark";

  try {
    if (window.localStorage.getItem(STORAGE_KEY) === "daylight") theme = "daylight";
  } catch (_error) {
    // Le stockage local est facultatif : le thème sombre reste le repli sûr.
  }

  const updateThemeColor = () => {
    const meta = document.querySelector("meta[data-theme-color]");
    if (meta) meta.content = theme === "daylight" ? meta.dataset.daylight : meta.dataset.dark;
  };

  const updateControls = () => {
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const daylight = theme === "daylight";
      button.setAttribute("aria-pressed", String(daylight));
      button.textContent = daylight ? "Mode sombre" : "Plein jour";
    });
  };

  const apply = (next, persist = false) => {
    theme = next === "daylight" ? "daylight" : "dark";
    root.dataset.theme = theme;
    updateThemeColor();
    updateControls();
    if (persist) {
      try { window.localStorage.setItem(STORAGE_KEY, theme); }
      catch (_error) { /* Le choix reste valable pour la page courante. */ }
    }
    document.dispatchEvent(new CustomEvent("phyto:themechange", {detail: {theme}}));
  };

  apply(theme);
  window.PhytoTheme = {current: () => theme, apply};
  document.addEventListener("DOMContentLoaded", () => {
    updateControls();
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => apply(theme === "daylight" ? "dark" : "daylight", true));
    });
  });
})();
