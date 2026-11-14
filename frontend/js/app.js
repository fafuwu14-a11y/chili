import { api } from "./api.js";
import { escapeHtml as esc, formatNumber as nf, percent, ringHtml, sparkline, toast, unitWord } from "./ui.js";
import { mountUserMenu, bindNavMore } from "./session.js";

const PAGE_SIZE = 9;

const state = {
  meta: null,
  result: null,
  tier: "all",
  sort: "match",
  shown: PAGE_SIZE,
  route: { province: "江苏", track: "物理类" },
  detail: null,
  school: null, // { id, name } —— 只查这一所学校时用
};

const els = {
  form: document.getElementById("predict-form"),
  province: document.getElementById("province"),
  track: document.getElementById("track"),
  score: document.getElementById("score"),
  rank: document.getElementById("rank"),
  submit: document.getElementById("submit-btn"),
  hint: document.getElementById("form-hint"),
  examples: document.getElementById("examples"),
  results: document.getElementById("results"),
  resultMeta: document.getElementById("result-meta"),
  chips: document.getElementById("result-chips"),
  tierFilter: document.getElementById("tier-filter"),
  sort: document.getElementById("sort"),
  cards: document.getElementById("cards"),
  loadMore: document.getElementById("load-more"),
  empty: document.getElementById("empty"),
  loading: document.getElementById("loading"),
  statColleges: document.getElementById("stat-colleges"),
  statPrograms: document.getElementById("stat-programs"),
  statUnit: document.getElementById("stat-unit"),
  statYears: document.getElementById("stat-years"),
  statModel: document.getElementById("stat-model"),
  heroSub: document.getElementById("hero-sub"),
  dataPill: document.querySelector(".data-pill"),
  drawer: document.getElementById("drawer"),
  scrim: document.getElementById("scrim"),
  nextStep: document.getElementById("next-step"),
  toPlan: document.getElementById("to-plan"),
  toMooc: document.getElementById("to-mooc"),
  schoolBox: document.getElementById("school-search"),
  schoolInput: document.getElementById("school-input"),
  schoolClear: document.getElementById("school-clear"),
  schoolHint: document.getElementById("school-hint"),
  schoolPanel: document.getElementById("school-panel"),
};

/* ------------------------------------------------------------------ boot */

async function init() {
  bindStaticEvents();
  try {
    state.meta = await api.meta();
    renderMeta();
    await maybeRunFromUrl();
  } catch (error) {
    toast(error.message);
  }
}

/** Deep links: /?province=江苏&track=物理类&score=620&open=1 */
async function maybeRunFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const province = params.get("province");
  const track = params.get("track");
  const info = state.meta.provinces[province];
  if (!province || !info) return;

  const tracks = info.tracks || [];
  if (track && tracks.length && !tracks.includes(track)) return;

  const score = params.get("score");
  const rank = params.get("rank");
  if (!score && !rank) return;

  els.province.value = province;
  syncTracks();
  if (track && tracks.includes(track)) els.track.value = track;
  els.score.value = score || "";
  els.rank.value = rank || "";
  updateHint();

  // 没有科类就没法查，先把选择器停在这。
  if (!tracks.length) return;

  // ?school=<college_id> —— 分享「只看某校」的结果，也让截图能验证这条路径。
  const schoolId = params.get("school");
  if (schoolId) {
    try {
      const detail = await api.college(schoolId, province, els.track.value);
      const name = (detail.college && detail.college.name) || "这所学校";
      state.school = { id: schoolId, name };
      els.schoolInput.value = name;
      els.schoolClear.hidden = false;
      els.schoolHint.textContent = `只看 ${name}；换省份或点「清除」恢复完整结果。`;
    } catch (error) {
      // 学校 id 失效就静默退回全量，不能让一个参数把整页搞挂
      state.school = null;
    }
  }

  const wantDrawer = params.get("open") === "1";
  await runPrediction(province, els.track.value, score ? Number(score) : null, rank ? Number(rank) : null, {
    scroll: !wantDrawer,
  });
  if (wantDrawer) openDrawerByIndex(0);
}

function renderMeta() {
  const meta = state.meta;
  const real = meta.mode === "real";
  const latestYear = meta.years[meta.years.length - 1];
  els.statColleges.textContent = meta.college_count.toLocaleString("zh-CN");
  els.statPrograms.textContent = meta.program_count.toLocaleString("zh-CN");
  if (els.statUnit) els.statUnit.textContent = `个${unitWord(currentUnit())}`;
  if (els.statYears) els.statYears.textContent = meta.years.length;
  if (els.statModel) els.statModel.textContent = real ? 1 : 2;

  if (real) {
    if (els.heroSub) {
      els.heroSub.innerHTML =
        `位次等值法：拿 <b>${latestYear}</b> 年各招生单位的真实录取位次，按考生规模换算，` +
        `估出它们在 <b>${meta.target_year}</b> 年的录取概率，并自动分成` +
        `<strong>冲</strong>、<strong>稳</strong>、<strong>保</strong>三档。`;
    }
    if (els.dataPill) {
      els.dataPill.innerHTML = `<span class="dot"></span>数据更新至 ${latestYear}-07`;
    }
    renderHowReal(latestYear, meta.target_year);
  }

  els.province.innerHTML = Object.entries(meta.provinces)
    .map(([name]) => {
      return `<option value="${esc(name)}">${esc(name)}</option>`;
    })
    .join("");

  syncTracks();
}

/** 真实数据模式下改写「预测是怎么算出来的」三张卡片。 */
function renderHowReal(latestYear, targetYear) {
  const grid = document.getElementById("how-grid");
  if (!grid) return;
  grid.innerHTML = `
    <li>
      <span class="step">01</span>
      <h3>位次打底</h3>
      <p>取该招生单位 ${latestYear} 年的真实最低录取位次，作为基准点。</p>
    </li>
    <li>
      <span class="step">02</span>
      <h3>位次等值 + 误差</h3>
      <p>拿你的位次与它比，差值按 min(录取位次×7.5%, 1,200) 折算成标准差，再用 logistic 换成概率。</p>
    </li>
    <li>
      <span class="step">03</span>
      <h3>冲稳保分档</h3>
      <p>概率 ≥85% 为保、45%–85% 为稳、低于 45% 为冲。目标年 ${targetYear}，未叠加扩招趋势，宁保守不高估。</p>
    </li>`;
}

function syncTracks() {
  if (!state.meta) return;
  const province = els.province.value;
  const tracks = state.meta.provinces[province].tracks || [];
  if (!tracks.length) {
    els.track.innerHTML = `<option value="">暂无数据</option>`;
    els.track.disabled = true;
  } else {
    els.track.innerHTML = tracks.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    els.track.disabled = false;
  }
  updateHint();
  renderExamples();
  if (els.statUnit) els.statUnit.textContent = `个${unitWord(currentUnit())}`;
}

/** 当前省份的投档单位：专业组还是专业。 */
function currentUnit() {
  if (!state.meta) return "group";
  const province = (els.province && els.province.value) || Object.keys(state.meta.provinces)[0];
  const info = state.meta.provinces[province];
  return (info && info.unit) || "group";
}

function updateHint() {
  if (!state.meta) return;
  const province = els.province.value;
  const info = state.meta.provinces[province];
  const track = els.track.value;
  const line = (info.line || {})[track];
  const candidates = (info.candidates || {})[track];
  if (!line || !candidates) {
    // 只收录分数齐全的省份，正常不会走到这里；真缺了就说清楚缺什么。
    els.hint.textContent = `${province} 暂时没有${track}的数据，换个科类或省份试试。`;
    els.submit.disabled = true;
    return;
  }
  els.submit.disabled = false;
  const wan = (candidates / 10000).toFixed(1);
  const year = state.meta.years[state.meta.years.length - 1];
  els.hint.textContent = `${province} · ${track} · ${year} 本科线 ${line} 分 · 考生约 ${wan} 万人，两者都填时以位次为准。`;
}

// 示例按钮按「当前省份的本科线」现算，换省后不会还挂着江苏的例子。
const EXAMPLE_OFFSETS = [96, 40, 8];

function exampleCases() {
  const provinces = state.meta.provinces;
  const current = els.province.value || Object.keys(provinces)[0];
  const order = [current, ...Object.keys(provinces).filter((name) => name !== current)];

  const cases = [];
  for (const name of order) {
    const info = provinces[name];
    if (!info || !info.available) continue;
    const lines = info.line || {};
    for (const track of info.tracks || []) {
      const line = lines[track];
      if (typeof line !== "number") continue;
      // 当前省份给三条（冲高 / 中段 / 压线），其他省只放一条做对比
      for (const offset of name === current ? EXAMPLE_OFFSETS : [72]) {
        cases.push({ province: name, track, score: line + offset });
      }
    }
  }
  return cases.slice(0, 5);
}

function renderExamples() {
  if (!state.meta) return;
  const cases = exampleCases();
  els.examples.innerHTML = cases
    .map(
      (item) =>
        `<button type="button" class="example" data-province="${esc(item.province)}" data-track="${esc(item.track)}" data-score="${item.score}">
          ${esc(item.province)} ${esc(item.track)} <b>${item.score}</b>
        </button>`,
    )
    .join("");
}

/* ------------------------------------------------------------ 查找学校 */

let schoolTimer = 0;

function bindSchoolSearch() {
  if (!els.schoolInput) return;

  els.schoolInput.addEventListener("input", () => {
    const q = els.schoolInput.value.trim();
    window.clearTimeout(schoolTimer);
    if (state.school && q !== state.school.name) {
      state.school = null;
      els.schoolClear.hidden = true;
    }
    if (!q) {
      hideSchoolPanel();
      return;
    }
    schoolTimer = window.setTimeout(() => searchSchools(q), 220);
  });

  els.schoolInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideSchoolPanel();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveSchoolFocus(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter") {
      const focused = els.schoolPanel.querySelector(".school-item.is-focus");
      if (focused) {
        event.preventDefault();
        selectSchool({ id: focused.dataset.id, name: focused.dataset.name });
      }
    }
  });

  els.schoolPanel.addEventListener("click", (event) => {
    const item = event.target.closest(".school-item");
    if (!item || !item.dataset.id) return;
    selectSchool({ id: item.dataset.id, name: item.dataset.name });
  });

  els.schoolClear.addEventListener("click", () => clearSchool());

  document.addEventListener("click", (event) => {
    if (!els.schoolBox.contains(event.target)) hideSchoolPanel();
  });
}

async function searchSchools(q) {
  const province = els.province.value;
  const track = els.track.value;
  if (!province || !track) return;
  try {
    const rows = await api.colleges({ q, province, track, limit: 8 });
    if (els.schoolInput.value.trim() !== q) return; // 打得快时丢掉过期结果
    renderSchoolPanel(rows, q);
  } catch (error) {
    toast(error.message);
  }
}

function renderSchoolPanel(rows, q) {
  if (!rows || !rows.length) {
    els.schoolPanel.innerHTML =
      `<li class="school-empty">没找到「${esc(q)}」。换个校名试试，目前覆盖江苏、广东、湖北、山西、辽宁、浙江、山东、河北八省。</li>`;
    els.schoolPanel.hidden = false;
    return;
  }
  els.schoolPanel.innerHTML = rows
    .map(
      (row, index) => `
      <li class="school-item${index === 0 ? " is-focus" : ""}" role="option" tabindex="-1"
          data-id="${esc(row.id)}" data-name="${esc(row.name)}">
        <span class="school-name">${esc(row.name)}</span>
        <span class="school-meta">${esc(row.city || "")}${row.city ? " · " : ""}${row.program_count} 个招生单位</span>
      </li>`,
    )
    .join("");
  els.schoolPanel.hidden = false;
}

function hideSchoolPanel() {
  if (!els.schoolPanel) return;
  els.schoolPanel.hidden = true;
}

function moveSchoolFocus(step) {
  const items = [...els.schoolPanel.querySelectorAll(".school-item")];
  if (!items.length) return;
  const current = items.findIndex((item) => item.classList.contains("is-focus"));
  items.forEach((item) => item.classList.remove("is-focus"));
  const next = (current + step + items.length) % items.length;
  items[next].classList.add("is-focus");
}

function selectSchool(school) {
  state.school = { id: school.id, name: school.name };
  els.schoolInput.value = school.name;
  els.schoolClear.hidden = false;
  hideSchoolPanel();
  els.schoolHint.textContent = `只看 ${school.name}；换省份或点「清除」恢复完整结果。`;

  const score = els.score.value.trim();
  const rank = els.rank.value.trim();
  if (!score && !rank) {
    toast("填上分数或位次，就能看这所学校的录取概率");
    els.score.focus();
    return;
  }
  runPrediction(els.province.value, els.track.value, score ? Number(score) : null, rank ? Number(rank) : null);
}

function clearSchool(quiet = false) {
  const had = Boolean(state.school) || Boolean(els.schoolInput.value);
  state.school = null;
  els.schoolInput.value = "";
  els.schoolClear.hidden = true;
  els.schoolHint.textContent = "想只看某一所？输校名，直接看它对你来说的录取概率。";
  hideSchoolPanel();
  if (quiet || !had || !state.result) return;

  const score = els.score.value.trim();
  const rank = els.rank.value.trim();
  if (!score && !rank) return;
  runPrediction(els.province.value, els.track.value, score ? Number(score) : null, rank ? Number(rank) : null);
}

/* ---------------------------------------------------------------- events */

function bindStaticEvents() {
  els.province.addEventListener("change", () => {
    syncTracks();
    renderExamples();
    clearSchool(true); // 院校 id 带科类，换省/科类后原选择必然失效
  });
  els.track.addEventListener("change", updateHint);

  bindSchoolSearch();

  els.form.addEventListener("submit", handleSubmit);

  els.examples.addEventListener("click", (event) => {
    const button = event.target.closest(".example");
    if (!button) return;
    els.province.value = button.dataset.province;
    syncTracks();
    els.track.value = button.dataset.track;
    els.score.value = button.dataset.score;
    els.rank.value = "";
    updateHint();
    els.form.requestSubmit();
  });

  els.tierFilter.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tier]");
    if (!button) return;
    state.tier = button.dataset.tier;
    state.shown = PAGE_SIZE;
    [...els.tierFilter.children].forEach((node) => {
      const active = node === button;
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-selected", String(active));
    });
    renderCards();
  });

  els.sort.addEventListener("change", () => {
    state.sort = els.sort.value;
    state.shown = PAGE_SIZE;
    renderCards();
  });

  els.loadMore.addEventListener("click", () => {
    state.shown += PAGE_SIZE;
    renderCards();
  });

  els.cards.addEventListener("click", (event) => {
    const card = event.target.closest(".card");
    if (!card) return;
    openDrawerByIndex(Number(card.dataset.index));
  });

  els.cards.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest(".card");
    if (!card) return;
    event.preventDefault();
    openDrawerByIndex(Number(card.dataset.index));
  });

  els.scrim.addEventListener("click", closeDrawer);
  els.drawer.addEventListener("click", (event) => {
    if (event.target.closest(".drawer-close")) closeDrawer();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.drawer.hidden) closeDrawer();
  });
}

/* ------------------------------------------------------------- prediction */

async function handleSubmit(event) {
  event.preventDefault();
  if (!state.meta) {
    toast("数据还没加载好，请稍候");
    return;
  }

  const province = els.province.value;
  const track = els.track.value;
  const scoreRaw = els.score.value.trim();
  const rankRaw = els.rank.value.trim();

  els.form.classList.remove("is-invalid");
  if (!scoreRaw && !rankRaw) {
    els.form.classList.add("is-invalid");
    els.score.focus();
    toast("请填写高考分数，或至少填写位次");
    return;
  }

  const score = scoreRaw === "" ? null : Number(scoreRaw);
  const rank = rankRaw === "" ? null : Number(rankRaw);

  if (score !== null && (!Number.isFinite(score) || score < 0 || score > 750)) {
    toast("分数需要在 0 ~ 750 之间");
    return;
  }
  if (rank !== null && (!Number.isFinite(rank) || rank < 1)) {
    toast("位次需要大于 0");
    return;
  }

  await runPrediction(province, track, score, rank);
}

async function runPrediction(province, track, score, rank, { scroll = true } = {}) {
  setLoading(true);
  try {
    const data = await api.predict({
      province,
      track,
      score,
      rank,
      college: state.school ? state.school.id : null,
    });
    state.result = data;
    state.route = { province, track };
    state.tier = "all";
    state.sort = "match";
    state.shown = PAGE_SIZE;

    els.sort.value = "match";
    [...els.tierFilter.children].forEach((node) => {
      const active = node.dataset.tier === "all";
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-selected", String(active));
    });

    renderResults();
    if (scroll) scrollToResults();
    return data;
  } catch (error) {
    toast(error.message);
    return null;
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  els.loading.hidden = !isLoading;
  els.submit.disabled = isLoading;
  els.submit.firstElementChild.textContent = isLoading ? "预测中…" : "开始预测";
  if (isLoading) {
    els.results.hidden = true;
    els.nextStep.hidden = true;
  }
}

function renderResults() {
  const result = state.result;
  if (!result) return;

  const input = result.input;
  const summary = result.summary;
  const listed = summary.listed ?? result.items.length;
  const more = summary.total > listed ? `（已列出最匹配的 ${listed} 个）` : "";
  // 分数正好压在某批专业组的投档线上时，位次差是 0、概率都是 50%，
  // 不解释一句会被当成「没算」。只统计已列出的这批。
  const word = unitWord(currentUnit());
  const latestYear = (state.meta.years || [])[state.meta.years.length - 1] || 2026;
  // 只看一所学校时，后端固定按「往年录取线从高到低」排，客户端的排序下拉不起作用，
  // 与其留着让人点不动，不如直接锁掉并说明。
  els.sort.disabled = Boolean(state.school);
  els.sort.title = state.school ? `只看一所学校时按往年录取线排序（${latestYear} 年最低分从高到低）` : "";
  const tied = result.items.filter((item) => !item.rank_gap).length;
  const tieNote = tied
    ? `<span class="result-tie">其中 <b>${tied}</b> 个${word}的 ${latestYear} 投档线正好是 ${input.score} 分（同分同位次），概率都显示 50%，属于最需要谨慎判断的一批。</span>`
    : "";
  els.results.hidden = false;
  const scope = state.school
    ? ` · <span class="result-scope">只看 <b>${esc(state.school.name)}</b></span>`
    : "";
  const order = state.school ? `（按 ${latestYear} 年最低分从高到低）` : "";
  els.resultMeta.innerHTML =
    `${esc(input.province)} · ${esc(input.track)} · <b>${input.score}</b> 分 · 位次约 <b>${nf(input.rank)}</b>` +
    ` · 全省前 <b>${input.percentile}</b>%${scope}　共 <b>${summary.total}</b> 个${word}${order}${more}${tieNote}`;

  els.chips.innerHTML = `
    <span class="chip chip--chong"><b>${summary.chong}</b>冲</span>
    <span class="chip chip--wen"><b>${summary.wen}</b>稳</span>
    <span class="chip chip--bao"><b>${summary.bao}</b>保</span>`;

  renderCards();
  syncNextSteps(input);
}

/** 把当前输入带到「冲稳保方案」与「专业先导课」两个页面。 */
function syncNextSteps(input) {
  const params = new URLSearchParams({
    province: input.province,
    track: input.track,
    score: String(input.score),
    rank: String(input.rank),
  });
  els.toPlan.href = `./plan.html?${params}`;

  const suggested = state.result.items[0];
  els.toMooc.href = suggested
    ? `./mooc.html?major=${encodeURIComponent(suggested.name)}`
    : "./mooc.html";

  els.nextStep.hidden = false;
}

function visibleItems() {
  if (!state.result) return [];
  let items = state.result.items.slice();
  if (state.tier !== "all") items = items.filter((item) => item.tier === state.tier);

    const sorters = {
      match: (a, b) => Math.abs(a.rank_gap) - Math.abs(b.rank_gap),
      prob: (a, b) => b.probability - a.probability,
      "prob-asc": (a, b) => a.probability - b.probability,
      rank: (a, b) => a.predicted_rank - b.predicted_rank,
      score: (a, b) => b.predicted_score - a.predicted_score,
    };
  items.sort(sorters[state.sort] || sorters.prob);
  return items;
}

function renderCards() {
  const items = visibleItems();
  const shown = items.slice(0, state.shown);

  els.cards.innerHTML = shown.map(cardHtml).join("");
  els.empty.hidden = items.length !== 0;
  els.loadMore.hidden = items.length <= state.shown;
  if (!els.loadMore.hidden) {
    els.loadMore.textContent = `加载更多（还有 ${items.length - state.shown} 个）`;
  }
}

/** 位次差文案：持平时写「持平」，避免一屏「+0」看着像没算。 */
function gapLabel(gap) {
  if (!gap) return "持平";
  return `${gap > 0 ? "+" : "−"}${nf(Math.abs(gap))}`;
}

function cardHtml(item, index) {
  const p = percent(item.probability);
  const ahead = item.rank_gap >= 0;
  const gapText = gapLabel(item.rank_gap);

  return `
    <article class="card" data-tier="${esc(item.tier)}" data-index="${index}" tabindex="0" role="button"
      aria-label="${esc(item.college.name)} ${esc(item.name)}，录取概率 ${p}%，${esc(item.tier)}档">
      <div class="card-head">
        <div class="card-title">
          <h3>${esc(item.college.name)}</h3>
          <p class="card-program">${esc(item.name)}${item.requirement ? ` <span>· ${esc(item.requirement)}</span>` : ""}</p>
        </div>
        <span class="tier-tag">${esc(item.tier)}</span>
      </div>

      <div class="card-body">
        ${ringHtml(p)}
        <dl class="facts">
          <div><dt>预测最低分</dt><dd>${item.predicted_score}</dd></div>
          <div><dt>预测最低位次</dt><dd>${nf(item.predicted_rank)}</dd></div>
          <div><dt>位次差</dt><dd class="${ahead ? "is-good" : "is-warn"}">${gapText}</dd></div>
          <div><dt>招生计划</dt><dd>${item.plan ? `${item.plan} 人` : "—"}</dd></div>
        </dl>
      </div>

      <div class="card-foot">
        <div class="tags">${item.college.tags.map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</div>
        <span class="confidence"><i></i>可信度${esc(item.confidence.level)}</span>
        ${sparkline(item.history)}
      </div>
    </article>`;
}

function scrollToResults() {
  const top = els.results.getBoundingClientRect().top + window.scrollY - 74;
  window.scrollTo({ top, behavior: "smooth" });
}

/* ---------------------------------------------------------------- drawer */

function openDrawerByIndex(index) {
  const item = visibleItems().slice(0, state.shown)[index];
  if (item) openDrawer(item);
}

async function openDrawer(item) {
  state.current = item;
  els.drawer.hidden = false;
  els.scrim.hidden = false;
  document.body.style.overflow = "hidden";
  els.drawer.innerHTML = drawerSkeleton(item);
  requestAnimationFrame(() => els.drawer.classList.add("is-open"));

  els.drawer.querySelector(".drawer-close")?.focus();

  try {
    const detail = await api.college(item.college.id, state.route.province, state.route.track);
    if (state.current === item) renderDrawer(item, detail);
  } catch {
    /* the item panel is already usable without the extra detail */
  }
}

function drawerSkeleton(item) {
  return `
    <div class="drawer-inner">
      <button type="button" class="drawer-close" aria-label="关闭">
        <svg viewBox="0 0 24 24" width="16" height="16"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
      </button>
      <p class="drawer-eyebrow">院校详情 · ${esc(dataLabel())}</p>
      <h2 id="drawer-title">${esc(item.college.name)}</h2>
      <p class="drawer-sub">${subline(item.college)}</p>
      ${drawerHero(item)}
      <h3 class="section-title">${esc(historyTitle(item.history))}</h3>
      ${historyTable(item.history)}
      ${adviceBlock(item)}
    </div>`;
}

function drawerHero(item) {
  const p = percent(item.probability);
  return `
    <div class="drawer-hero" data-tier="${esc(item.tier)}">
      ${ringHtml(p)}
      <div class="drawer-hero-text">
        <h3>${esc(item.name)}</h3>
        <p>${item.requirement ? `${esc(item.requirement)} · ` : ""}预测最低 ${item.predicted_score} 分 / 位次 ${nf(item.predicted_rank)}</p>
        <span class="tier-tag">${esc(item.tier)}档</span>
      </div>
    </div>`;
}

function renderDrawer(item, detail) {
  const programs = detail.programs || [];
  // 一所院校的真实专业组可能几十个，超过 12 个就折叠，避免淹没下面的表格。
  const LIMIT = 12;
  const isMajor = (item.kind || "group") === "major";
  const activeIndex = programs.findIndex((program) => program.program_id === item.program_id);
  let visible = programs;
  if (programs.length > LIMIT) {
    visible = programs.slice(0, LIMIT);
    if (activeIndex >= LIMIT) visible[LIMIT - 1] = programs[activeIndex];
  }
  const hidden = programs.length - visible.length;

  const pills = visible
    .map(
      (program) => `
      <button type="button" class="program-pill${program.program_id === item.program_id ? " is-active" : ""}"
        data-program="${esc(program.program_id)}">${esc(program.name)}</button>`,
    )
    .join("");

  const more = hidden > 0
    ? `<button type="button" class="program-pill program-more" data-more="1">还有 ${hidden} 个专业组</button>`
    : "";

  // 专业模式下，一所学校可能有 30–60 个专业，横排 pill 会铺满两屏，改成可筛选列表。
  const unitArea = isMajor
    ? unitPickerHtml(programs, item)
    : `<div class="program-pills">${pills}${more}</div>`;

  els.drawer.innerHTML = `
    <div class="drawer-inner">
      <button type="button" class="drawer-close" aria-label="关闭">
        <svg viewBox="0 0 24 24" width="16" height="16"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
      </button>

      <p class="drawer-eyebrow">院校详情 · ${esc(dataLabel())}</p>
      <h2 id="drawer-title">${esc(item.college.name)}</h2>
      <p class="drawer-sub">${subline(item.college, `${detail.province} ${detail.track}`)}</p>

      ${drawerHero(item)}

      <h3 class="section-title">${esc(historyTitle(item.history))}</h3>
      ${unitArea}
      <div id="drawer-table">${historyTable(item.history)}</div>

      <h3 class="section-title">志愿建议</h3>
      ${adviceBlock(item)}

      ${drawerLink(item)}
    </div>`;

  const table = els.drawer.querySelector("#drawer-table");
  const pillArea = els.drawer.querySelector(".program-pills");

  const bindPills = () => {
    els.drawer.querySelectorAll(".program-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        const program = programs.find((row) => row.program_id === pill.dataset.program);
        if (!program) return;
        els.drawer.querySelectorAll(".program-pill").forEach((node) => node.classList.toggle("is-active", node === pill));
        table.innerHTML = historyTable(program.history);
      });
    });
  };
  bindPills();

  const picker = els.drawer.querySelector(".unit-picker");
  if (picker) bindUnitPicker(picker, programs, table);

  const moreBtn = els.drawer.querySelector(".program-more");
  if (moreBtn) {
    moreBtn.addEventListener("click", () => {
      pillArea.innerHTML = programs
        .map(
          (program) => `
          <button type="button" class="program-pill${program.program_id === item.program_id ? " is-active" : ""}"
            data-program="${esc(program.program_id)}">${esc(program.name)}</button>`,
        )
        .join("");
      bindPills();
    });
  }
}

/** 专业模式下的抽屉切换器：搜索框 + 可滚动列表（一所学校可能有几十个专业）。 */
function unitPickerHtml(programs, item) {
  const rows = programs
    .map((program) => {
      const latest = program.history[program.history.length - 1] || {};
      const active = program.program_id === item.program_id;
      return `<li><button type="button" class="unit-item${active ? " is-active" : ""}"
          data-program="${esc(program.program_id)}">
          <span class="unit-name">${esc(program.name)}</span>
          <span class="unit-score">${latest.min_score ?? "—"}</span>
        </button></li>`;
    })
    .join("");
  return `
    <div class="unit-picker">
      <input class="unit-search" type="search" placeholder="筛选这所学校的 ${programs.length} 个专业"
        aria-label="筛选专业" />
      <ul class="unit-list">${rows}</ul>
    </div>`;
}

function bindUnitPicker(picker, programs, table) {
  const search = picker.querySelector(".unit-search");
  const list = picker.querySelector(".unit-list");
  const items = [...list.querySelectorAll(".unit-item")];

  // 一所学校几十个专业，默认滚动到当前选中那个，否则用户以为没选中。
  const active = list.querySelector(".unit-item.is-active");
  if (active) active.scrollIntoView({ block: "nearest" });

  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    items.forEach((button) => {
      const name = button.querySelector(".unit-name").textContent.toLowerCase();
      button.parentElement.hidden = query !== "" && !name.includes(query);
    });
    list.scrollTop = 0;
  });

  list.addEventListener("click", (event) => {
    const button = event.target.closest(".unit-item");
    if (!button) return;
    const program = programs.find((row) => row.program_id === button.dataset.program);
    if (!program) return;
    items.forEach((node) => node.classList.toggle("is-active", node === button));
    table.innerHTML = historyTable(program.history);
  });
}

/** 真实数据的专业组是「25专业组」这类编号，不是专业名，不给先导课链接。 */
function drawerLink(item) {
  if (state.meta && state.meta.mode === "real") {
    return `
      <a class="drawer-link" href="./quiz.html">
        还不确定具体专业？先做一份专业匹配测一测
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </a>`;
  }
  return `
    <a class="drawer-link" href="./mooc.html?major=${encodeURIComponent(item.name)}">
      看看「${esc(item.name)}」有哪些先导课可以提前学
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </a>`;
}

/** 数据来源标签：真实数据 / 演示数据。 */
function dataLabel() {
  return state.meta && state.meta.mode === "real" ? "真实录取数据" : "演示数据";
}

/** 院校副标题：城市、标签、科类，空的自动跳过。 */
function subline(college, extra) {
  const parts = [college.city, (college.tags || []).join(" / "), extra];
  return parts.filter((part) => part && String(part).trim()).map(esc).join(" · ");
}

/** 「近 N 年录取数据」。 */
function historyTitle(history) {
  const years = (history || []).length;
  return years >= 2 ? `近 ${years} 年录取数据` : "历年录取数据";
}

function historyTable(history) {
  const rows = history || [];
  const latest = rows.length ? rows[rows.length - 1].year : null;
  const body = rows
    .map(
      (row) => `
      <tr${row.year === latest ? ' class="is-latest"' : ""}>
        <td>${row.year}</td>
        <td>${row.min_score}</td>
        <td>${nf(row.min_rank)}</td>
        <td>${row.plan ? row.plan : "—"}</td>
        <td>${row.line}</td>
      </tr>`,
    )
    .join("");

  return `
    <table class="data">
      <thead>
        <tr><th>年份</th><th>最低分</th><th>最低位次</th><th>计划</th><th>批次线</th></tr>
      </thead>
      <tbody>${body}</tbody>
    </table>`;
}

function adviceBlock(item) {
  return `
    <div class="advice">${esc(item.advice)}</div>
    <dl class="kv">
      <div><dt>预测可信度</dt><dd>${esc(item.confidence.level)} · ${item.confidence.score}</dd></div>
      <div><dt>你的位次</dt><dd>${nf(state.result.input.rank)}</dd></div>
      <div><dt>位次差</dt><dd>${gapLabel(item.rank_gap)}</dd></div>
    </dl>`;
}

function closeDrawer() {
  els.drawer.classList.remove("is-open");
  document.body.style.overflow = "";
  window.setTimeout(() => {
    if (!els.drawer.classList.contains("is-open")) {
      els.drawer.hidden = true;
      els.scrim.hidden = true;
      state.current = null;
    }
  }, 320);
}

mountUserMenu();
bindNavMore();
init();
