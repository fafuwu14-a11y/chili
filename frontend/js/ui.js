/** Small rendering helpers: numbers, probability ring, sparkline, toast. */

const nf = new Intl.NumberFormat("zh-CN");

export function formatNumber(value) {
  return nf.format(Math.round(Number(value) || 0));
}

export function percent(probability) {
  return Math.round((Number(probability) || 0) * 100);
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

/** 「专业组」还是「专业」，取决于当前省份的投档单位。 */
export function unitWord(kind) {
  return kind === "major" ? "专业" : "专业组";
}

/** conic-gradient ring; pass the integer percentage. */
export function ringHtml(value, label = "录取概率") {
  const p = Math.max(0, Math.min(100, Math.round(value)));
  return `
    <div class="ring-wrap">
      <div class="ring" style="--p:${p}">
        <b>${p}<i>%</i></b>
      </div>
      <span class="ring-label">${label}</span>
    </div>`;
}

/** Tiny three-point sparkline of admitted rank (smaller rank sits higher). */
export function sparkline(history) {
  const ranks = (history || []).map((row) => Number(row.min_rank) || 0);
  if (ranks.length < 2) return "";

  const width = 64;
  const height = 26;
  const pad = 3;
  const min = Math.min(...ranks);
  const max = Math.max(...ranks);
  const span = Math.max(max - min, 1);
  const step = (width - pad * 2) / (ranks.length - 1);

  const points = ranks.map((rank, index) => [
    pad + index * step,
    pad + ((rank - min) / span) * (height - pad * 2),
  ]);
  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} ${(width - pad).toFixed(1)},${height - pad} ${pad},${height - pad}`;
  const last = points[points.length - 1];

  return `
    <svg class="spark" viewBox="0 0 ${width} ${height}" aria-hidden="true" focusable="false">
      <polygon points="${area}" fill="currentColor" opacity=".08" style="color:var(--tier, #E60012)"></polygon>
      <polyline points="${line}" fill="none" stroke="currentColor" stroke-width="1.6"
        stroke-linecap="round" stroke-linejoin="round" style="color:var(--tier, #E60012)"></polyline>
      <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.2" fill="currentColor" style="color:var(--tier, #E60012)"></circle>
    </svg>`;
}

let toastTimer = 0;
let hideTimer = 0;

export function toast(message) {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = message;
  node.hidden = false;
  requestAnimationFrame(() => node.classList.add("is-show"));
  // 两个定时器都要清，否则上一条 toast 的淡出收尾会把新的一条提前藏掉
  clearTimeout(toastTimer);
  clearTimeout(hideTimer);
  toastTimer = window.setTimeout(() => {
    node.classList.remove("is-show");
    hideTimer = window.setTimeout(() => {
      node.hidden = true;
    }, 240);
  }, 2600);
}
