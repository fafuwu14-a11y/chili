/** 功能 01：专业匹配问卷 —— 选规格 → 逐题作答 → 看匹配结果 */

import { api } from "./api.js";
import { mountUserMenu, bindNavMore } from "./session.js";

const GROUP_LABELS = {
  interest: "兴趣 · 这些说法像不像你",
  ability: "学科能力 · 现在手里有什么牌",
  pref: "工作偏好 · 你想要什么样的生活",
  style: "性格倾向 · 你习惯怎么做事",
  fit: "硬条件 · 有些现实要提前确认",
};

/** MBTI 式五级量表：1 完全不认同 … 5 非常认同 */
const SCALE_LABELS = ["完全不认同", "不太认同", "说不好", "比较认同", "非常认同"];

const els = {
  choose: document.getElementById("quiz-choose"),
  specGrid: document.getElementById("spec-grid"),
  stage: document.getElementById("quiz-stage"),
  back: document.getElementById("quiz-back"),
  specName: document.getElementById("quiz-spec-name"),
  count: document.getElementById("quiz-count"),
  progressbar: document.getElementById("quiz-progressbar"),
  progress: document.getElementById("quiz-progress"),
  group: document.getElementById("quiz-group"),
  question: document.getElementById("quiz-question"),
  options: document.getElementById("quiz-options"),
  prev: document.getElementById("quiz-prev"),
  next: document.getElementById("quiz-next"),
  submit: document.getElementById("quiz-submit"),
  result: document.getElementById("quiz-result"),
  resultTitle: document.getElementById("result-title"),
  resultMeta: document.getElementById("result-meta"),
  resultBadges: document.getElementById("result-badges"),
  interestBars: document.getElementById("interest-bars"),
  interestNote: document.getElementById("interest-note"),
  majorPick: document.getElementById("major-pick"),
  majorPickNote: document.getElementById("major-pick-note"),
  majorPickAxes: document.getElementById("major-pick-axes"),
  majorPickList: document.getElementById("major-pick-list"),
  matchList: document.getElementById("match-list"),
  advice: document.getElementById("result-advice"),
  plan: document.getElementById("result-plan"),
  again: document.getElementById("quiz-again"),
  toast: document.getElementById("toast"),
};

const state = {
  specs: [],
  spec: null,
  index: 0,
  answers: {},
};

/** 自动翻页的定时器，翻页/换规格/手动跳题时都要取消，否则会连跳两题 */
let advanceTimer = 0;

const SCORE_BANDS = [
  { min: 80, label: "高度契合", className: "is-high" },
  { min: 60, label: "方向合适", className: "is-mid" },
  { min: 0, label: "可以看看", className: "is-low" },
];

/** ------------------------------------------------------------------ */
/** 启动                                                                */
/** ------------------------------------------------------------------ */
async function boot() {
  try {
    state.specs = await api.quiz();
  } catch (error) {
    els.specGrid.innerHTML = `<p class="empty-note">${escapeHtml(error.message)}</p>`;
    return;
  }
  renderSpecs();

  const wanted = new URLSearchParams(location.search).get("spec");
  if (wanted && state.specs.some((item) => item.key === wanted)) {
    startSpec(wanted);
  }
}

function renderSpecs() {
  els.specGrid.innerHTML = "";
  for (const spec of state.specs) {
    const card = document.createElement("article");
    card.className = "spec-card";
    card.dataset.key = spec.key;
    card.innerHTML = `
      <div class="spec-top">
        <h3>${escapeHtml(spec.name)}</h3>
        <span class="spec-level">${escapeHtml(spec.level)}</span>
      </div>
      <p class="spec-num"><strong>${spec.count}</strong> 题 · 约 ${spec.minutes} 分钟</p>
      <p class="spec-desc">${escapeHtml(spec.desc)}</p>
      <div class="spec-covers">${spec.covers
        .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
        .join("")}</div>
      <button class="btn-primary spec-start" type="button">用这套开始</button>
    `;
    card.addEventListener("click", () => startSpec(spec.key));
    els.specGrid.appendChild(card);
  }
}

async function startSpec(key) {
  try {
    state.spec = await api.quizSpec(key);
  } catch (error) {
    showToast(error.message);
    return;
  }
  state.index = 0;
  state.answers = {};
  window.clearTimeout(advanceTimer);
  els.choose.hidden = true;
  els.result.hidden = true;
  els.stage.hidden = false;
  els.specName.textContent = `${state.spec.name} · ${state.spec.count} 题`;
  syncUrl(key);
  renderQuestion();
}

function syncUrl(key) {
  const url = new URL(location.href);
  if (key) url.searchParams.set("spec", key);
  else url.searchParams.delete("spec");
  history.replaceState(null, "", url);
}

/** ------------------------------------------------------------------ */
/** 答题                                                                */
/** ------------------------------------------------------------------ */
function renderQuestion() {
  const questions = state.spec.questions;
  const index = Math.min(state.index, questions.length - 1);
  const question = questions[index];
  const answered = Object.keys(state.answers).length;
  const chosen = state.answers[question.id];

  els.count.textContent = `第 ${index + 1} / ${questions.length} 题`;
  els.group.textContent = GROUP_LABELS[question.group] || "";
  els.question.textContent = question.text;
  els.progress.style.width = `${((index + 1) / questions.length) * 100}%`;
  els.progressbar.setAttribute("aria-valuenow", String(Math.round(((index + 1) / questions.length) * 100)));

  els.options.className = "likert";
  els.options.innerHTML = `
    <div class="likert-row" role="radiogroup" aria-labelledby="quiz-question">
      ${SCALE_LABELS.map((label, offset) => {
        const level = offset + 1;
        const active = chosen === level;
        return `<button class="likert-btn${active ? " is-chosen" : ""}" type="button"
            role="radio" aria-checked="${active}" data-value="${level}">
            <span class="likert-dot">${level}</span>
            <span class="likert-text">${label}</span>
          </button>`;
      }).join("")}
    </div>`;

  for (const button of els.options.querySelectorAll(".likert-btn")) {
    button.addEventListener("click", () => pick(question, Number(button.dataset.value)));
  }

  els.prev.disabled = index === 0;
  els.next.hidden = index === questions.length - 1;
  els.submit.hidden = index !== questions.length - 1;
  els.submit.textContent = answered ? `看匹配结果 →（已答 ${answered} 题）` : "看匹配结果 →";
}

function pick(question, level) {
  state.answers[question.id] = level;
  renderQuestion();

  const index = state.index;
  const isLast = index >= state.spec.questions.length - 1;
  window.clearTimeout(advanceTimer);
  if (isLast) return;

  advanceTimer = window.setTimeout(() => {
    // 用户已经手动翻页或改了答案，就别再自作主张往前跳
    if (state.index !== index) return;
    if (state.answers[question.id] !== level) return;
    state.index = index + 1;
    renderQuestion();
  }, 240);
}

function go(delta) {
  const next = state.index + delta;
  if (next < 0 || next >= state.spec.questions.length) return;
  window.clearTimeout(advanceTimer);
  state.index = next;
  renderQuestion();
}

/** ------------------------------------------------------------------ */
/** 结果                                                                */
/** ------------------------------------------------------------------ */
async function submit() {
  if (!state.spec) return;
  els.submit.disabled = true;
  els.submit.textContent = "正在打分…";
  try {
    const data = await api.match({
      spec: state.spec.key,
      answers: state.answers,
      limit: 6,
    });
    renderResult(data);
  } catch (error) {
    showToast(error.message);
  } finally {
    els.submit.disabled = false;
    renderQuestion();
  }
}

function renderResult(data) {
  els.stage.hidden = true;
  els.result.hidden = false;
  els.result.scrollIntoView({ behavior: "smooth", block: "start" });

  els.resultTitle.textContent = `${data.spec.name}结果 · 最贴合你的专业`;
  els.resultMeta.textContent = `已答 ${data.answered} / ${data.spec.count} 题；${data.confidence.note}`;

  els.resultBadges.innerHTML = `
    <span class="badge badge--red">置信度 ${data.confidence.level} · ${data.confidence.percent}%</span>
    ${data.prefs
      .slice(0, 3)
      .map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`)
      .join("")}
  `;

  els.interestBars.innerHTML = data.interest
    .map(
      (row) => `
      <div class="interest-row">
        <span class="interest-label">${escapeHtml(row.label)}</span>
        <span class="interest-track"><span class="interest-fill" style="width:${Math.round(row.value * 100)}%"></span></span>
        <span class="interest-value">${Math.round(row.value * 100)}</span>
      </div>`
    )
    .join("");

  els.interestNote.textContent = data.ability.length
    ? `兴趣之外，你的学科自评是 ${data.ability
        .map((row) => `${row.label} ${Math.round(row.value * 100)}`)
        .join(" / ")}。`
    : "分数越高，说明这类倾向越明显。";

  els.matchList.innerHTML = data.items
    .map((item, index) => renderMatchItem(item, index))
    .join("");

  renderMajorPick(data);

  els.advice.textContent = data.advice;
  els.plan.href = "./predict.html";

  for (const link of els.matchList.querySelectorAll("[data-mooc]")) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      location.href = `./mooc.html?major=${encodeURIComponent(link.dataset.mooc)}`;
    });
  }
}

function renderMatchItem(item, index) {
  const band = SCORE_BANDS.find((entry) => item.match >= entry.min);
  const colleges = (item.colleges || [])
    .map((college) => `<span class="chip chip--soft">${escapeHtml(college.name)}</span>`)
    .join("");
  const tags = item.tags
    .map((tag) => `<span class="tag ${item.matched_tags.includes(tag) ? "tag--hit" : ""}">${escapeHtml(tag)}</span>`)
    .join("");

  return `
    <li class="match-item">
      <span class="match-rank">${String(index + 1).padStart(2, "0")}</span>
      <div class="match-main">
        <div class="match-head">
          <h3>${escapeHtml(item.major)}</h3>
          ${tags}
        </div>
        <p class="match-blurb">${escapeHtml(item.blurb)}</p>
        <p class="match-reason">${escapeHtml(item.reason)}</p>
        ${renderDirections(item)}
        <div class="match-colleges"${colleges ? "" : " hidden"}>${colleges}</div>
        <div class="match-links">
          <a class="text-link" data-mooc="${escapeHtml(item.major)}" href="./mooc.html?major=${encodeURIComponent(item.major)}">看这个专业的先导课 ↗</a>
        </div>
      </div>
      <div class="match-score ${band.className}">
        <strong>${item.match}</strong><i>%</i>
        <span>${band.label}</span>
      </div>
    </li>`;
}

/** 大类下面的「具体到」三个专业，点进去是专业详情页 */
function renderDirections(item) {
  const rows = item.directions || [];
  if (!rows.length) return "";
  const links = rows
    .map(
      (row) =>
        `<a href="./major.html?major=${encodeURIComponent(row.major)}">${escapeHtml(row.major)}</a>`
    )
    .join("、");
  return `<p class="match-directions">具体到：${links}</p>`;
}

/** 结果页的「落到具体专业」卡片 */
function renderMajorPick(data) {
  const direction = data.direction || {};
  const picks = data.majors || [];
  els.majorPickNote.textContent =
    direction.note || "按上面的方向，从匹配到的大类里挑出来的具体专业。";

  const axes = (direction.axes || []).filter((row) => row.value > 0.1).slice(0, 3);
  els.majorPickAxes.innerHTML = axes
    .map(
      (row) =>
        `<span class="chip chip--soft">${escapeHtml(row.label)} · ${Math.round(row.value * 100)}</span>`
    )
    .join("");
  els.majorPickAxes.hidden = axes.length === 0;

  if (!picks.length) {
    els.majorPickList.innerHTML = `<li class="major-pick-empty">这次没算出具体专业，换标准或深度问卷再试一次。</li>`;
    return;
  }
  els.majorPickList.innerHTML = picks.map(renderMajorPickItem).join("");
}

function renderMajorPickItem(row, index) {
  const hint = row.note || row.diff || "";
  return `
    <li class="major-pick-item">
      <span class="major-pick-rank">${String(index + 1).padStart(2, "0")}</span>
      <div class="major-pick-body">
        <div class="major-pick-head">
          <a class="major-pick-name" href="./major.html?major=${encodeURIComponent(row.major)}">${escapeHtml(row.major)}</a>
          <span class="major-pick-group">${escapeHtml(row.group || "")}</span>
        </div>
        ${hint ? `<p class="major-pick-hint">${escapeHtml(hint)}</p>` : ""}
      </div>
      <span class="major-pick-score"><strong>${row.match}</strong><i>%</i></span>
    </li>`;
}

/** ------------------------------------------------------------------ */
/** 事件                                                                */
/** ------------------------------------------------------------------ */
els.back.addEventListener("click", () => {
  state.spec = null;
  els.stage.hidden = true;
  els.result.hidden = true;
  els.choose.hidden = false;
  syncUrl("");
  els.choose.scrollIntoView({ behavior: "smooth", block: "start" });
});
els.prev.addEventListener("click", () => go(-1));
els.next.addEventListener("click", () => go(1));
els.submit.addEventListener("click", submit);
els.again.addEventListener("click", () => {
  els.result.hidden = true;
  els.choose.hidden = false;
  state.spec = null;
  syncUrl("");
  els.choose.scrollIntoView({ behavior: "smooth", block: "start" });
});

document.addEventListener("keydown", (event) => {
  if (els.stage.hidden) return;
  if (event.key === "ArrowLeft") go(-1);
  if (event.key === "ArrowRight") go(1);
  const digit = Number(event.key);
  if (digit >= 1 && digit <= 5) {
    const question = state.spec?.questions[state.index];
    if (question) pick(question, digit);
  }
});

/** ------------------------------------------------------------------ */
/** 小工具                                                              */
/** ------------------------------------------------------------------ */
function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

let toastTimer = 0;
function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 2600);
}

mountUserMenu();
bindNavMore();
boot();
