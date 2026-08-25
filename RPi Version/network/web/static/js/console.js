(() => {
  "use strict";
  const output = document.getElementById("console-output"); const state = document.getElementById("connection-state");
  if (!output || !state) return;
  const stream = new EventSource("/console/stream");
  stream.onopen = () => { state.textContent = "Connectée"; state.className = "connection-state is-online"; };
  stream.onmessage = (event) => { const follow = output.scrollHeight - output.scrollTop - output.clientHeight < 80; output.textContent += `${event.data}\n`; if (follow) output.scrollTop = output.scrollHeight; };
  stream.onerror = () => { state.textContent = "Reconnexion…"; state.className = "connection-state is-offline"; };
})();
