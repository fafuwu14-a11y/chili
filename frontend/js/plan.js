import { api } from "./api.js";
import { escapeHtml as esc, formatNumber as nf, percent, toast, unitWord } from "./ui.js";
import { mountUserMenu, bindNavMore } from "./session.js";

const TIER_HINTS = {
  冲: "分数略高于你的预测线，放在志愿表最前面，用来博一次更好的结果。",
  稳: "与你位次最匹配的一段，是真正决定去向的部分，重点核对专业与城市。",
  保: "用来兜底，确保不滑档；建议全部勾选「服从专业调剂」。",
};

const MODE_HINTS = {
  auto: "同一所学校适量重复，兼顾覆盖面与被录取可能。",
  school: "同一所学校只占一个志愿，把整张表铺到尽可能多的学校上，适合「先保学校」。",
  major: "允许同一所学校的多个专业同时进表，适合「就盯着这几个方向填」。",
};

const state = { meta: null, plan: null, mode: "auto" };

const els = {
  form: document.getElementById("plan-form"),
  province: document.getElementById("province"),
  track: document.getElementById("track"),
  score: document.getElementById("score"),
  rank: document.getElementById("rank"),
  chong: document.getElementById("chong"),
  wen: document.getElementById("wen"),
  bao: document.getElementById("bao"),
  slotTotal: document.getElementById("slot-total"),
  modeSwitch: document.getElementById("plan-mode"),
  modeHint: document.getElementById("plan-mode-hint"),
  generate: document.getElementById("generate-btn"),
  result: document.getElementById("plan-result"),
  meta: document.getElementById("plan-meta"),
  note: document.getElementById("plan-note"),
  table: document.getElementById("plan-table"),
  advice: document.getElementById("plan-advice"),
  copy: document.getElementById("copy-plan"),
  print: document.getElementById("print-plan"),
  printMeta: document.getElementById("print-meta"),
  loading: document.getElementById("loading"),
};

async function init() {
  bind();
  updateSlotTotal();
  try {
    state.meta = await api.meta();
    applyMeta();
    fillProvinces();
    syncTracks();
    await applyFromUrl();
  } catch (error) {
    toast(error.message);
  }
}

function bind() {
  els.province.addEventListener("change", syncTracks);
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    generate();
  });
  [els.chong, els.wen, els.bao].forEach((input) => input.addEventListener("input", updateSlotTotal));
  const fill = document.getElementById("fill-all");
  if (fill) fill.addEventListener("click", fillAll);
  if (els.modeSwitch) {
    els.modeSwitch.addEventListener("click", (event) => {
      const button = event.target.closest(".mode-btn");
      if (!button) return;
      setMode(button.dataset.mode);
      if (state.plan) generate();
    });
  }
  els.copy.addEventListener("click", copyPlan);
  els.print.addEventListener("click", () => window.print());
}

function setMode(mode, quiet) {
  state.mode = MODE_HINTS[mode] ? mode : "auto";
  if (els.modeSwitch) {
    els.modeSwitch.querySelectorAll(".mode-btn").forEach((button) => {
      const active = button.dataset.mode === state.mode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-checked", String(active));
    });
  }
  if (els.modeHint) els.modeHint.textContent = MODE_HINTS[state.mode];
  if (!quiet) syncUrl(state.plan ? state.plan.input : null);
}

function applyMeta() {
  const meta = state.meta;
  if (!meta || meta.mode !== "real") return;
  const pill = document.querySelector(".data-pill");
  if (pill) {
    const year = meta.years[meta.years.length - 1];
    pill.innerHTML = `<span class="dot"></span>数据更新至 ${year}-07`;
  }
}

/** 当前省份的投档单位（专业组 / 专业），切换省份时要跟着变。 */
function currentUnit() {
  if (!state.meta) return "group";
  const province = (els.province && els.province.value) || Object.keys(state.meta.provinces)[0];
  const info = state.meta.provinces[province];
  return (info && info.unit) || "group";
}

/** 当前省份本科批能填多少个志愿（江苏 40 个专业组、辽宁 112 个专业…）。 */
function currentSlotsMax() {
  if (!state.meta) return 45;
  const province = (els.province && els.province.value) || Object.keys(state.meta.provinces)[0];
  const info = state.meta.provinces[province];
  return (info && info.slots_max) || 45;
}

function syncSlotUnit() {
  const el = document.getElementById("slot-unit");
  if (el) el.textContent = `个${unitWord(currentUnit())}`;
  const max = currentSlotsMax();
  const label = document.getElementById("slots-max");
  if (label) label.textContent = String(max);
  for (const key of ["chong", "wen", "bao"]) {
    els[key].max = String(max);
    if (clampSlot(els[key].value) > max) els[key].value = String(max);
  }
  updateSlotTotal();
}

/** 一键按 2:4:4 把整张表填满（冲 20% / 稳 40% / 保 40%）。 */
function fillAll() {
  const max = currentSlotsMax();
  const chong = Math.max(1, Math.round(max * 0.2));
  const wen = Math.round(max * 0.4);
  const bao = Math.max(1, max - chong - wen);
  els.chong.value = String(chong);
  els.wen.value = String(wen);
  els.bao.value = String(bao);
  updateSlotTotal();
}

function updateSlotTotal() {
  const total = ["chong", "wen", "bao"].reduce((sum, key) => sum + clampSlot(els[key].value), 0);
  els.slotTotal.textContent = String(total);
  const max = currentSlotsMax();
  const bar = document.getElementById("slot-ratio");
  if (bar) {
    bar.hidden = total !== max;
    bar.textContent = `正好填满 ${max} 个`;
  }
}

function clampSlot(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(currentSlotsMax(), Math.round(number)));
}

function fillProvinces() {
  els.province.innerHTML = Object.entries(state.meta.provinces)
    .map(([name]) => {
      return `<option value="${esc(name)}">${esc(name)}</option>`;
    })
    .join("");
}

function syncTracks() {
  if (!state.meta) return;
  const info = state.meta.provinces[els.province.value];
  const tracks = info.tracks || [];
  if (!tracks.length) {
    els.track.innerHTML = `<option value="">暂无数据</option>`;
    els.track.disabled = true;
    els.generate.disabled = true;
    syncSlotUnit();
    return;
  }
  els.track.innerHTML = tracks.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
  els.track.disabled = false;
  els.generate.disabled = false;
  syncSlotUnit();
}

async function applyFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const province = params.get("province");
  const track = params.get("track");
  if (province && state.meta.provinces[province]) {
    els.province.value = province;
    syncTracks();
    if (track && state.meta.provinces[province].tracks.includes(track)) els.track.value = track;
  }
  els.score.value = params.get("score") || "";
  els.rank.value = params.get("rank") || "";
  for (const key of ["chong", "wen", "bao"]) {
    if (params.get(key) !== null) els[key].value = params.get(key);
  }
  if (params.get("mode")) setMode(params.get("mode"), true);
  updateSlotTotal();

  if (els.score.value.trim() || els.rank.value.trim()) await generate({ scroll: false });
}

async function generate({ scroll = true } = {}) {
  if (!state.meta) return;
  const scoreRaw = els.score.value.trim();
  const rankRaw = els.rank.value.trim();

  if (!scoreRaw && !rankRaw) {
    toast("请填写高考分数，或至少填写位次");
    els.score.focus();
    return;
  }

  const score = scoreRaw === "" ? null : Number(scoreRaw);
  const rank = rankRaw === "" ? null : Number(rankRaw);
  if (score !== null && (!Number.isFinite(score) || score < 0 || score > 750)) {
    toast("分数需要在 0 ~ 750 之间");
    els.score.focus();
    return;
  }
  if (rank !== null && (!Number.isFinite(rank) || rank < 1)) {
    toast("位次需要大于 0");
    els.rank.focus();
    return;
  }

  const payload = {
    province: els.province.value,
    track: els.track.value,
    score,
    rank,
    chong: clampSlot(els.chong.value),
    wen: clampSlot(els.wen.value),
    bao: clampSlot(els.bao.value),
    mode: state.mode,
  };

  setLoading(true);
  try {
    const plan = await api.plan(payload);
    state.plan = plan;
    render(plan);
    syncUrl(plan.input);
    if (scroll) {
      const top = els.result.getBoundingClientRect().top + window.scrollY - 80;
      window.scrollTo({ top, behavior: "smooth" });
    }
  } catch (error) {
    toast(error.message);
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  els.loading.hidden = !isLoading;
  els.generate.disabled = isLoading;
  els.generate.firstElementChild.textContent = isLoading ? "生成中…" : "生成方案";
}

function syncUrl(input) {
  const params = new URLSearchParams({
    province: input.province,
    track: input.track,
    score: String(input.score),
    rank: String(input.rank),
  });
  const { requested } = state.plan.summary;
  params.set("chong", String(requested.chong));
  params.set("wen", String(requested.wen));
  params.set("bao", String(requested.bao));
  if (state.mode !== "auto") params.set("mode", state.mode);
  window.history.replaceState(null, "", `?${params}`);
}

function render(plan) {
  const input = plan.input;
  const summary = plan.summary;
  const word = unitWord(input.unit || currentUnit());
  const unitCount = `个${word}`;

  els.result.hidden = false;
  const modeChip = summary.mode && summary.mode !== "auto"
    ? `<span class="mode-chip">${esc(summary.mode_label || "")}</span>`
    : "";
  els.meta.innerHTML = `${esc(input.province)} · ${esc(input.track)} · <b>${input.score}</b> 分 · 位次约 <b>${nf(input.rank)}</b> · 全省前 <b>${input.percentile}</b>%
    <span class="dot-sep">·</span> 冲 <b>${summary.chong}</b> / 稳 <b>${summary.wen}</b> / 保 <b>${summary.bao}</b>，共 <b>${summary.total}</b> ${unitCount}${
      summary.college_count ? ` · 覆盖 <b>${summary.college_count}</b> 所学校` : ""
    }${modeChip}`;
  els.note.textContent = summary.note;
  els.note.classList.toggle("is-warn", summary.total < 1);
  els.advice.textContent = plan.advice;
  els.printMeta.textContent = `${input.province} · ${input.track} · ${input.score} 分 · 位次约 ${nf(input.rank)} · ${
    summary.mode_label || "智能排"
  } · 生成于 ${plan.generated_at}`;

  els.table.innerHTML = ["冲", "稳", "保"]
    .map((tier) => tierBlock(tier, plan.slots.filter((slot) => slot.tier === tier), summary))
    .join("");
}

function tierBlock(tier, slots, summary) {
  if (!slots.length) {
    const wanted = summary.requested[tierKey(tier)];
    if (!wanted) return "";
    return `
      <section class="tier-block" data-tier="${tier}">
        <header class="tier-head">
          <span class="tier-tag">${tier}</span>
          <h3>${tierLabel(tier)}</h3>
          <p>${TIER_HINTS[tier]}</p>
        </header>
        <p class="tier-empty">这个档位暂时没有可选的${unitWord(currentUnit())}，可以调高分数或调整各档数量后重新生成。</p>
      </section>`;
  }

  return `
    <section class="tier-block" data-tier="${tier}">
      <header class="tier-head">
        <span class="tier-tag">${tier}</span>
        <h3>${tierLabel(tier)}</h3>
        <span class="tier-count">${slots.length} 个</span>
        <p>${TIER_HINTS[tier]}</p>
      </header>
      <ol class="slots">
        ${slots.map(slotRow).join("")}
      </ol>
    </section>`;
}

function slotRow(slot) {
  const p = percent(slot.probability);
  return `
    <li class="slot">
      <span class="slot-index">${String(slot.index).padStart(2, "0")}</span>
      <div class="slot-main">
        <h4>${esc(slot.college.name)}<em>${esc(slot.program)}</em></h4>
        <p>${slot.requirement ? `${esc(slot.requirement)} · ` : ""}预测 <b>${slot.predicted_score}</b> 分 / 位次 <b>${nf(slot.predicted_rank)}</b>${slot.plan ? ` · 计划 ${slot.plan} 人` : ""}</p>
      </div>
      <div class="slot-prob" data-tier="${esc(slot.tier)}">
        <b>${p}<i>%</i></b>
        <span>录取概率</span>
      </div>
      <p class="slot-advice">${esc(slot.advice)}</p>
    </li>`;
}

function tierKey(tier) {
  return { 冲: "chong", 稳: "wen", 保: "bao" }[tier];
}

function tierLabel(tier) {
  return { 冲: "冲刺", 稳: "稳妥", 保: "保底" }[tier];
}

async function copyPlan() {
  if (!state.plan) return;
  const plan = state.plan;
  const input = plan.input;
  const lines = [
    "赤鲤 · 冲稳保志愿方案",
    `${input.province} ${input.track} · ${input.score} 分 · 位次约 ${nf(input.rank)}`,
    `排法：${plan.summary.mode_label || "智能排"} · 共 ${plan.summary.total} 个 · 覆盖 ${plan.summary.college_count} 所学校`,
    "",
  ];
  for (const slot of plan.slots) {
    lines.push(
      `${String(slot.index).padStart(2, "0")}. [${slot.tier}] ${slot.college.name} ${slot.program}${slot.requirement ? `（${slot.requirement}）` : ""} 预测 ${slot.predicted_score} 分 · 概率 ${percent(slot.probability)}%`,
    );
  }
  lines.push("", plan.advice, "", "数据来源：省级招生考试机构公开投档线 · 结果由统计模型估算，仅供参考。");

  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    toast("方案已复制到剪贴板");
  } catch {
    toast("浏览器不允许复制，请手动选中表格");
  }
}

mountUserMenu();
bindNavMore();
init();
