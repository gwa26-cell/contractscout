(() => {
  let seconds = 0;
  const clicks = {};
  let lastPos = null;

  function trackClick(event) {
    const el = event.target.closest("button, a, select, input[type=submit]");
    if (!el) return;
    const label = (el.textContent || el.name || el.id || el.tagName).trim().slice(0, 80);
    if (!label) return;
    clicks[label] = (clicks[label] || 0) + 1;
  }

  function trackMove(event) {
    lastPos = { x: event.clientX, y: event.clientY };
  }

  async function sendTick() {
    seconds += 1;
    const payload = {
      application_id: 0,
      time_on_page: seconds,
      buttons_clicked: JSON.stringify(clicks),
      cursor_positions: JSON.stringify(lastPos ? [lastPos] : []),
      return_frequency: 0,
    };
    try {
      await fetch("/api/behavior-metrics/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (_) {
      /* ignore network blips */
    }
  }

  document.addEventListener("click", trackClick, true);
  document.addEventListener("mousemove", trackMove);
  window.setInterval(sendTick, 1000);
})();
