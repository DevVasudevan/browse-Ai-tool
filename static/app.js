async function postJSON(url, body, opts = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  return res.json();
}

function escapeHTML(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderToolCard(tool) {
  const href = `/tools/${encodeURIComponent(tool.slug)}`;
  const visit = tool.url;

  return `
    <div class="glass-card group flex h-full flex-col overflow-hidden">
      <div class="flex items-start gap-4 p-5">
        <div class="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-white/10 ring-1 ring-white/15">
          <span class="text-sm font-semibold text-white/90">${escapeHTML(tool.icon || "AI")}</span>
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between gap-3">
            <a href="${href}" class="truncate text-base font-semibold tracking-tight text-white hover:text-white/90">${escapeHTML(tool.name)}</a>
            <span class="badge">${escapeHTML(tool.pricing_type || "")}</span>
          </div>
          <p class="mt-1 line-clamp-2 text-sm text-white/70">${escapeHTML(tool.description || "")}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <span class="pill">${escapeHTML(tool.category || "")}</span>
            ${(tool.use_cases || []).slice(0, 3).map((t) => `<span class="pill pill-muted">${escapeHTML(t)}</span>`).join("")}
          </div>
        </div>
      </div>
      <div class="mt-auto border-t border-white/10 p-5">
        <div class="flex items-center justify-between gap-3">
          <a href="${visit}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center justify-center rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-white/90">Visit Tool</a>
          <a href="${href}" class="text-sm font-semibold text-white/70 hover:text-white">Details</a>
        </div>
      </div>
    </div>
  `;
}

(function initHeroRecommendations() {
  const form = document.getElementById("hero-search");
  const input = document.getElementById("hero-q");
  const recs = document.getElementById("hero-recs");
  const grid = document.getElementById("hero-recs-grid");

  if (!form || !input || !recs || !grid) return;

  let lastController = null;
  let debounce = null;

  async function run() {
    const task = (input.value || "").trim();
    if (task.length < 3) {
      recs.classList.add("hidden");
      grid.innerHTML = "";
      return;
    }

    if (lastController) lastController.abort();
    lastController = new AbortController();

    try {
      const data = await postJSON("/api/recommend", { task }, { signal: lastController.signal });
      const tools = data.tools || [];

      if (!tools.length) {
        recs.classList.add("hidden");
        grid.innerHTML = "";
        return;
      }

      grid.innerHTML = tools.slice(0, 5).map(renderToolCard).join("");
      recs.classList.remove("hidden");
    } catch (e) {
      recs.classList.add("hidden");
      grid.innerHTML = "";
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(run, 450);
  });
})();
