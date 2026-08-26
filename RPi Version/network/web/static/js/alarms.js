(() => {
  "use strict";
  const duration = (seconds) => {
    if (seconds < 60) return `${Math.round(seconds)} s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} h`;
    return `${(seconds / 86400).toFixed(1)} j`;
  };
  document.querySelectorAll("time[data-timestamp]").forEach((node) => {
    node.textContent = new Date(Number(node.dataset.timestamp) * 1000).toLocaleString("fr-FR");
  });
  document.querySelectorAll("[data-duration]").forEach((node) => {
    node.textContent = duration(Number(node.dataset.duration));
  });
  const storageKey = "phyto-operator-alias";
  let remembered = "";
  try { remembered = window.localStorage.getItem(storageKey) || ""; } catch (_error) { remembered = ""; }
  document.querySelectorAll(".alarm-ack-form").forEach((form) => {
    const input = form.querySelector('input[name="alias"]');
    if (input && remembered) input.value = remembered;
    form.addEventListener("submit", () => {
      if (!input) return;
      try { window.localStorage.setItem(storageKey, input.value); } catch (_error) { /* stockage facultatif */ }
    });
  });
})();
