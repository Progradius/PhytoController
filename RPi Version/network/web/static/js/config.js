(() => {
  "use strict";
  const setConditionalState = (container, visible) => {
    container.hidden = !visible;
    container.querySelectorAll("input, select, textarea, button").forEach((control) => { control.disabled = !visible; });
  };
  document.querySelectorAll("[data-mode-form]").forEach((form) => {
    const update = () => {
      const mode = form.querySelector('input[name="mode"]:checked')?.value;
      form.querySelectorAll("[data-mode-fields]").forEach((container) => setConditionalState(container, container.dataset.modeFields === mode));
    };
    form.querySelectorAll('input[name="mode"]').forEach((radio) => radio.addEventListener("change", update)); update();
  });
  document.querySelectorAll("[data-motor-form]").forEach((form) => {
    const update = () => {
      const mode = form.querySelector('input[name="motor_mode"]:checked')?.value;
      form.querySelectorAll("[data-motor-fields]").forEach((container) => setConditionalState(container, container.dataset.motorFields === mode));
    };
    form.querySelectorAll('input[name="motor_mode"]').forEach((radio) => radio.addEventListener("change", update)); update();
  });
  document.querySelectorAll("[data-reveal]").forEach((button) => button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.reveal); if (!input) return;
    const reveal = input.type === "password"; input.type = reveal ? "text" : "password";
    button.textContent = reveal ? "Masquer" : "Afficher";
    button.setAttribute("aria-label", reveal ? "Masquer la nouvelle valeur" : "Afficher la nouvelle valeur");
  }));
  document.querySelectorAll("[data-config-form]").forEach((form) => form.addEventListener("submit", () => {
    const button = form.querySelector("[data-save-button]"); if (button) { button.disabled = true; button.textContent = "Enregistrement…"; }
  }));
  document.getElementById("form-errors")?.focus();
})();
