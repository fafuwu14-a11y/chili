/**
 * 专业对比页：搜索选 2–4 个专业，画一张六维雷达图，再逐项列表。
 *
 * 图表全部手写 SVG，不引第三方库——这是参赛项目的硬约束，
 * 也顺便避免 CDN 在比赛现场挂掉。
 */

import { api } from "./api.js";
import { escapeHtml, toast } from "./ui.js";
import { mountUserMenu, bindNavMore } from "./session.js";

const MAX_PICK = 4;
const MIN_PICK = 2;

/** 六个维度，顺序与后端 major_profile.SCORE_LABELS 一致 */
const AXES = [
  { key: "course_load", label: "课业强度" },
  { key: "job_width", label: "就业面" },
  { key: "salary", label: "起薪" },
  { key: "exam_need", label: "考研必要" },
  { key: "civil_fit", label: "考公适配" },
  { key: "startup_fit", label: "创业友好" },
];

const DEFAULTS = ["计算机科学与技术", "临床医学", "社会工作"];

const els = {
  q: document.getElementById("compare-q"),
  suggest: document.getElementById("compare-suggest"),
  chosen: document.getElementById("compare-chosen"),
  radar: document.getElementById("compare-radar"),
  legend: document.getElementById("compare-legend"),
  table: document.getElementById("compare-table"),
  toast: document.getElementById("toast"),
};

const state = {
  picked: [],
  compare: null,
  timer: 0,
};

/* ---------- 选专业 ---------- */

function renderChosen() {
  els.chosen.innerHTML = state.picked
    .map(
      (name, index) => `
      <span class="compare-chip compare-chip--${index + 1}">
        <i aria-hidden="true"></i>${escapeHtml(name)}
        <button type="button" data-remove="${escapeHtml(name)}" aria-label="移除 ${escapeHtml(name)}">×</button>
      </span>`
    )
    .join("");
  els.chosen.hidden = state.picked.length === 0;
}

function renderSuggest(items) {
  if (!items.length) {
    els.suggest.hidden = true;
    els.suggest.innerHTML = "";
    return;
  }
  els.suggest.innerHTML = items
    .map(
      (item) => `
      <li>
        <button type="button" data-add="${escapeHtml(item.name)}">
          <b>${escapeHtml(item.name)}</b>
          <span>${escapeHtml(item.group)} · ${item.count} 个招生单元</span>
        </button>
      </li>`
    )
    .join("");
  els.suggest.hidden = false;
}

function addMajor(name) {
  const clean = (name || "").trim();
  if (!clean) return;
  if (state.picked.includes(clean)) {
    toast("这个专业已经在对比里了");
    return;
  }
  if (state.picked.length >= MAX_PICK) {
    toast(`最多对比 ${MAX_PICK} 个专业，先删一个`);
    return;
  }
  state.picked.push(clean);
  els.q.value = "";
  renderSuggest([]);
  refresh();
}

function removeMajor(name) {
  state.picked = state.picked.filter((item) => item !== name);
  refresh();
}

/* ---------- 雷达图 ---------- */

/** 把一个 1–5 的价值转成画布上的坐标 */
function pointAt(index, value, center, radius) {
  const angle = (-90 + index * 60) * (Math.PI / 180);
  const r = (value / 5) * radius;
  return [center + r * Math.cos(angle), center + r * Math.sin(angle)];
}

function gridPolygon(level, center, radius) {
  return AXES.map((_, index) => pointAt(index, level, center, radius).join(",")).join(" ");
}

function radarSvg(items) {
  const size = 400;
  const center = size / 2;
  const radius = 118;
  const labelRadius = 152;

  const rings = [1, 2, 3, 4, 5]
    .map(
      (level) =>
        `<polygon class="radar-ring${level === 5 ? " radar-ring--outer" : ""}" points="${gridPolygon(level, center, radius)}" />`
    )
    .join("");

  const spokes = AXES.map((_, index) => {
    const [x, y] = pointAt(index, 5, center, radius);
    return `<line class="radar-spoke" x1="${center}" y1="${center}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" />`;
  }).join("");

  const labels = AXES.map((axis, index) => {
    const angle = (-90 + index * 60) * (Math.PI / 180);
    const x = center + labelRadius * Math.cos(angle);
    const y = center + labelRadius * Math.sin(angle);
    const anchor = Math.abs(Math.cos(angle)) < 0.2 ? "middle" : Math.cos(angle) > 0 ? "start" : "end";
    // 标签上下留一点空，避免压到顶点
    const dy = Math.sin(angle) > 0.5 ? 12 : Math.sin(angle) < -0.5 ? -4 : 4;
    return `<text class="radar-label" x="${x.toFixed(1)}" y="${(y + dy).toFixed(1)}" text-anchor="${anchor}">${escapeHtml(axis.label)}</text>`;
  }).join("");

  const series = items
    .map((item, index) => {
      const points = AXES.map((axis, axisIndex) =>
        pointAt(axisIndex, item.scores[axis.key], center, radius).join(",")
      ).join(" ");
      const dots = AXES.map((axis, axisIndex) => {
        const [x, y] = pointAt(axisIndex, item.scores[axis.key], center, radius);
        return `<circle class="radar-dot radar-dot--${index + 1}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" />`;
      }).join("");
      return `<g class="radar-series radar-series--${index + 1}">
        <polygon class="radar-area" points="${points}" />
        <polygon class="radar-line" points="${points}" />
        ${dots}
      </g>`;
    })
    .join("");

  return `<svg class="compare-svg" viewBox="0 0 ${size} ${size}" role="img" aria-label="专业六维对比雷达图">
    ${rings}${spokes}${series}${labels}
  </svg>`;
}

function renderLegend(items) {
  els.legend.innerHTML = items
    .map((item, index) => {
      const top = AXES.reduce((best, axis) =>
        item.scores[axis.key] > item.scores[best.key] ? axis : best
      );
      return `
      <li class="compare-legend-item compare-legend-item--${index + 1}">
        <i aria-hidden="true"></i>
        <div>
          <b>${escapeHtml(item.name)}</b>
          <span>${escapeHtml(item.degree)} · ${item.years} 年 · 最强项：${escapeHtml(top.label)} ${item.scores[top.key]}</span>
        </div>
      </li>`;
    })
    .join("");
}

/* ---------- 对比表 ---------- */

function rangeText(block, unit) {
  if (!block) return "—";
  return `${block.low}–${block.high}${unit}`;
}

function renderTable(items) {
  const rows = [
    ["学制学位", (item) => `${item.years} 年 · ${escapeHtml(item.degree)}`],
    ["就业率区间", (item) => rangeText(item.employment, "%")],
    ["升学率区间", (item) => rangeText(item.postgrad, "%")],
    ["起薪区间", (item) => `${item.salary.low}–${item.salary.high} 元/月`],
    ["考公类别", (item) => escapeHtml((item.civil.categories || []).join("、") || "—")],
    ["对口职业", (item) => escapeHtml(item.jobs.slice(0, 3).join("、"))],
    ["核心课程", (item) => escapeHtml(item.courses.slice(0, 4).join("、"))],
  ];

  const head = `<tr><th scope="col">维度</th>${items
    .map((item) => `<th scope="col">${escapeHtml(item.name)}</th>`)
    .join("")}</tr>`;

  const body = rows
    .map(
      ([label, render]) =>
        `<tr><th scope="row">${label}</th>${items.map((item) => `<td>${render(item)}</td>`).join("")}</tr>`
    )
    .join("");

  els.table.innerHTML = `<table class="compare-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

/* ---------- 主流程 ---------- */

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const names = params.getAll("name").filter(Boolean);
  // 从专业详情页点进来通常只带一个名字，这时保留它、提示再选一个，
  // 比直接跳回三个默认专业更符合预期。
  if (names.length >= 1) return names.slice(0, MAX_PICK);
  return DEFAULTS.slice();
}

function syncUrl() {
  const params = new URLSearchParams();
  state.picked.forEach((name) => params.append("name", name));
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", next);
}

async function refresh() {
  renderChosen();
  syncUrl();

  if (state.picked.length < MIN_PICK) {
    els.radar.innerHTML = `<p class="compare-empty">至少选 ${MIN_PICK} 个专业才能对比。</p>`;
    els.legend.innerHTML = "";
    els.table.innerHTML = "";
    return;
  }

  try {
    const data = await api.majorCompare(state.picked);
    state.compare = data;
    els.radar.innerHTML = radarSvg(data.items);
    renderLegend(data.items);
    renderTable(data.items);
  } catch (error) {
    els.radar.innerHTML = `<p class="compare-empty">${escapeHtml(error.message || "对比算不出来")}</p>`;
    els.legend.innerHTML = "";
    els.table.innerHTML = "";
  }
}

/* ---------- 搜索 ---------- */

async function search(keyword) {
  const q = keyword.trim();
  if (!q) {
    renderSuggest([]);
    return;
  }
  try {
    const data = await api.majors({ q, limit: 8 });
    const items = data.items.filter((item) => !state.picked.includes(item.name));
    renderSuggest(items);
  } catch (error) {
    renderSuggest([]);
  }
}

function bind() {
  els.q.addEventListener("input", () => {
    window.clearTimeout(state.timer);
    state.timer = window.setTimeout(() => search(els.q.value), 220);
  });

  els.q.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const first = els.suggest.querySelector("[data-add]");
      if (first) addMajor(first.dataset.add);
    } else if (event.key === "Escape") {
      renderSuggest([]);
    }
  });

  els.suggest.addEventListener("click", (event) => {
    const button = event.target.closest("[data-add]");
    if (button) addMajor(button.dataset.add);
  });

  els.chosen.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove]");
    if (button) removeMajor(button.dataset.remove);
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".compare-picker")) renderSuggest([]);
  });
}

function init() {
  state.picked = readUrl();
  bind();
  refresh();
}

mountUserMenu();
bindNavMore();
init();
