/* Optional decorative motion is independent of chat and merchant state. */
(() => {
  const button = document.querySelector("[data-decoration-toggle]");
  if (!button) return;
  const storageKey = "nightfind-decoration-motion";
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = false;
  try {
    paused = localStorage.getItem(storageKey) === "paused";
  } catch {
    /* Decoration still works when browser storage is unavailable. */
  }

  function render() {
    document.body.classList.toggle(
      "decorations-paused",
      paused || document.hidden,
    );
    button.disabled = reducedMotion.matches;
    button.textContent = reducedMotion.matches
      ? "装饰动效已随系统关闭"
      : paused
        ? "开启装饰动效"
        : "暂停装饰动效";
  }

  button.addEventListener("click", () => {
    paused = !paused;
    try {
      localStorage.setItem(storageKey, paused ? "paused" : "running");
    } catch {
      /* Keep this tab's preference even without persistent storage. */
    }
    render();
  });
  reducedMotion.addEventListener("change", render);
  document.addEventListener("visibilitychange", render);
  render();
})();
