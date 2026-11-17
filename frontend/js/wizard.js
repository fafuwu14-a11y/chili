/**
 * 五步选科向导。
 *
 * 设计取舍：
 * - 一次只显示一步，刷新后靠 URL 的 #step-N 和 ?q= 恢复，避免长页面里迷路；
 * - 报告写入 sessionStorage，答题中途刷新不用重新跑 23 题；
 * - 所有 AI Key 只放 localStorage，页面任何位置都不回显完整 Key；
 * - 第三方接口（院校、课程）都可能 401/404，页面必须自己降级，不能把人踢走。
 */
import { api } from "./api.js";
import { escapeHtml, formatNumber, toast } from "./ui.js";
import { mountLoginButton, openLoginModal } from "./login-modal.js";

const AI_KEY = "chili.ai.config";
const SKEY = {
  province: "chili.wizard.province.v1",
  answers: "chili.wizard.answers.v1",
  report: "chili.wizard.report.v1",
  interest: "chili.wizard.interest.v1",
  retest: "chili.wizard.retest.v1",
};

const MODE_ORDER = ["3+1+2", "3+3", "old"];
const GROUP_LABELS = {
  interest: "兴趣倾向",
  ability: "能力自评",
  value: "价值取向",
  cluster: "方向偏好",
};
const DEFAULT_SCALE = ["完全不像我", "不太像我", "说不好", "比较像我", "非常像我"];
// 后端量表文案是通用的「符合/不符合」；兴趣问卷让 15 岁学生读「像不像我」更自然
function scaleWords(labels) {
  const source = Array.isArray(labels) && labels.length ? labels : DEFAULT_SCALE;
  return source.map((label) => String(label).replace("符合", "像我"));
}
const RETEST_QUESTIONS = [
  "如果要在周末抽出 4 个小时，把这个专业的一门先导课学完，你愿意吗？",
  "如果前两年学得很吃力，你愿意继续补基础，而不是马上换方向吗？",
  "如果这个专业毕业后起薪普通、要熬几年，你还会选它吗？",
];

const nf1 = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const state = {
  step: 1,
  province: "",
  meta: null,
  metaReady: false,
  provinces: [],
  modeLabels: {},
  modeDesc: {},
  groupsById: new Map(),
  quiz: [],
  quizReady: false,
  quizLoading: false,
  quizPromise: null,
  quizIndex: 0,
  pendingQuizIndex: null,
  scaleLabels: DEFAULT_SCALE,
  answers: {},
  report: null,
  reportTop: 3,
  reportSignature: "",
  comboWindow: 0,
  comboLoading: false,
  majors: [],
  user: null,
  authChecked: false,
  interestMajor: "",
  mooc: { status: "idle", items: [], note: "", total: 0, major: "", error: "", req: 0 },
  retestByMajor: {},
  aiResult: null,
  aiBusy: false,
  providers: [],
  providersPromise: null,
  aiTrigger: null,
  aiDraft: null,
  provinceComboReq: 0,
  drawer: {
    open: false,
    major: "",
    province: "",
    track: "",
    data: null,
    error: null,
    loading: false,
    req: 0,
    trigger: null,
    closeTimer: 0,
  },
};

const ui = {};
let loginCtl = null;
let pageLock = 0;

function byId(id) {
  return document.getElementById(id);
}

function cacheUI() {
  [
    "wz-header", "wz-burger", "wz-nav", "wz-ai-open",
    "wz-step-1", "wz-step-2", "wz-step-3", "wz-step-4", "wz-step-5",
    "wz-province-search", "wz-province-groups", "wz-province-count", "wz-province-empty",
    "wz-province-summary", "wz-province-mode", "wz-province-desc", "wz-province-combos",
    "wz-start", "wz-start-note",
    "wz-quiz-loading", "wz-quiz-body", "wz-quiz-error", "wz-quiz-retry",
    "wz-progress", "wz-progress-bar", "wz-quiz-count", "wz-quiz-topic",
    "wz-question", "wz-quiz-prev", "wz-quiz-next", "wz-quiz-save",
    "wz-report-meta", "wz-combo-status", "wz-combo-grid", "wz-combo-more", "wz-to-majors",
    "wz-major-meta", "wz-major-count", "wz-major-grid", "wz-major-eligible", "wz-major-status",
    "wz-interest-select", "wz-interest-detail", "wz-mooc-list", "wz-mooc-note", "wz-mooc-all",
    "wz-ai-generate", "wz-ai-body", "wz-ai-note",
    "wz-retest-list", "wz-verdict",
    "wz-drawer", "wz-drawer-title", "wz-drawer-sub", "wz-drawer-province",
    "wz-drawer-track", "wz-drawer-note", "wz-drawer-body", "wz-drawer-close",
    "wz-ai-modal", "wz-ai-provider", "wz-ai-provider-hint", "wz-ai-key",
    "wz-ai-masked", "wz-ai-model", "wz-ai-test", "wz-ai-save", "wz-ai-status",
    "wz-ai-clear", "wz-ai-close", "wz-ai-help",
  ].forEach((id) => {
    ui[id.replace(/^wz-/, "").replace(/-([a-z])/g, (_, ch) => ch.toUpperCase())] = byId(id);
  });
  ui.toast = byId("toast");
  ui.sections = Array.from(document.querySelectorAll(".wz-section"));
  ui.stepLinks = Array.from(document.querySelectorAll(".wz-step-link"));
}

function isLoginRequired(error) {
  // 厂商 Key 失效时后端也会回 401，只有明确带 login_required 才是登录态问题
  return Boolean(error && (error.code === "login_required" || (error.status === 401 && !error.code)));
}

/* ---------- 存储：隐私模式 / 配额报错时不要让页面崩 ---------------------- */
function readSession(key, fallback) {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeSession(key, value) {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

function removeSession(key) {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function readAIConfig() {
  try {
    const raw = window.localStorage.getItem(AI_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const config = {
      provider: String(parsed.provider || "").trim(),
      key: String(parsed.key || "").trim(),
      model: String(parsed.model || "").trim(),
    };
    return config.provider && config.key ? config : null;
  } catch {
    return null;
  }
}

function maskKey(key) {
  const tail = String(key || "").slice(-4);
  return tail ? `sk-****${tail}` : "未配置";
}

/* ---------- 小工具 ------------------------------------------------------ */
function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function provinceMeta(name) {
  return (state.provinces || []).find((item) => item.name === name) || null;
}

function clusterLabel(key) {
  const list = state.meta?.quiz?.clusters || [];
  const hit = list.find((item) => item.key === key);
  return hit ? hit.name : key || "";
}

function modeLabel(mode) {
  const hit = state.provinces.find((item) => item.mode === mode);
  return state.modeLabels?.[mode] || hit?.mode_label || mode || "选科模式";
}

function answerSignature() {
  const keys = Object.keys(state.answers).sort();
  return JSON.stringify({ province: state.province, answers: keys.map((key) => [key, state.answers[key]]) });
}

function currentQuiz() {
  return state.quiz[state.quizIndex] || null;
}

function missingQuestions() {
  return state.quiz.filter((question) => state.answers[question.id] === undefined);
}

function quizCount() {
  return Number(state.meta?.quiz?.count) || state.quiz.length || 23;
}

function quizMinutes() {
  return Number(state.meta?.quiz?.minutes) || 6;
}

function scaleLabel(index) {
  return state.scaleLabels[index - 1] || DEFAULT_SCALE[index - 1] || "";
}

function activeOptionInput() {
  return ui.question.querySelector("input[type=radio]:checked") || ui.question.querySelector("input[type=radio]");
}

/* ---------- 初始化 ------------------------------------------------------ */
async function init() {
  cacheUI();
  loadStoredState();
  bindEvents();
  mountLogin();
  syncAuth();

  const requested = requestedStep();
  await loadMeta();
  if (state.province) await selectProvince(state.province, { initial: true });
  await goToStep(requested, { initial: true });
}

function loadStoredState() {
  const savedProvince = readSession(SKEY.province, "");
  state.province = typeof savedProvince === "string" ? savedProvince : "";

  const savedAnswers = readSession(SKEY.answers, {});
  state.answers = savedAnswers && typeof savedAnswers === "object" && !Array.isArray(savedAnswers)
    ? savedAnswers
    : {};

  const savedRetest = readSession(SKEY.retest, {});
  state.retestByMajor = savedRetest && typeof savedRetest === "object" && !Array.isArray(savedRetest)
    ? savedRetest
    : {};

  const savedInterest = readSession(SKEY.interest, "");
  state.interestMajor = typeof savedInterest === "string" ? savedInterest : "";

  const savedReport = readSession(SKEY.report, null);
  if (
    savedReport
    && savedReport.report
    && savedReport.province === state.province
    && savedReport.signature === answerSignature()
  ) {
    state.report = savedReport.report;
    state.reportTop = Number(savedReport.top) || 3;
    state.comboWindow = Number(savedReport.window) || 0;
    state.reportSignature = savedReport.signature;
    state.majors = Array.isArray(savedReport.report.majors) ? savedReport.report.majors : [];
  }

  const params = new URLSearchParams(window.location.search);
  const q = Number(params.get("q"));
  if (Number.isFinite(q) && q >= 1) state.pendingQuizIndex = q - 1;
}

function requestedStep() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = Number(params.get("step"));
  if (fromQuery >= 1 && fromQuery <= 5) return fromQuery;
  const match = /^#step-([1-5])$/.exec(window.location.hash || "");
  if (match) return Number(match[1]);
  if (state.pendingQuizIndex !== null) return 2;
  return 1;
}

function mountLogin() {
  const slot = document.querySelector("[data-login-slot]");
  if (!slot) return;
  loginCtl = mountLoginButton({
    slot,
    onSuccess: (user) => setUser(user),
    onLogout: () => setUser(null),
  });
}

function setUser(user) {
  state.user = user || null;
  state.authChecked = true;
  if (!state.user && state.mooc.status === "ready") {
    // 退出登录后课程列表不该继续留在页面上，避免让人误以为仍是账号内的数据
    state.mooc.status = "auth";
    state.mooc.items = [];
    state.mooc.note = "";
    if (state.step === 5) renderMooc();
    return;
  }
  if (state.step === 5 && state.mooc.status === "auth" && state.user) {
    loadMooc(state.interestMajor);
  }
}

async function syncAuth() {
  try {
    const payload = await api.session();
    setUser(payload?.user || null);
  } catch {
    setUser(null);
  }
}

async function ensureSession() {
  if (state.user) return state.user;
  try {
    const payload = await api.session();
    setUser(payload?.user || null);
  } catch {
    setUser(null);
  }
  return state.user;
}

function openLogin({ onSuccess } = {}) {
  openLoginModal({
    onSuccess: (user) => {
      if (user) {
        setUser(user);
        if (loginCtl) loginCtl.setUser(user);
      }
      if (typeof onSuccess === "function") onSuccess(user);
    },
  });
}

/* ---------- 元数据 / 省份 --------------------------------------------- */
async function loadMeta() {
  ui.provinceGroups.innerHTML = '<p class="wz-loading">正在加载省份…</p>';
  ui.start.disabled = true;
  try {
    const raw = await api.choiceMeta();
    const meta = normalizeMeta(raw);
    if (!meta.provinces.length) throw new Error("没有拿到省份数据");
    state.meta = meta;
    state.metaReady = true;
    state.provinces = meta.provinces;
    state.modeLabels = meta.mode_labels || {};
    state.modeDesc = meta.mode_desc || {};
    state.groupsById = new Map((meta.groups || []).map((group) => [group.id, group]));
    state.scaleLabels = scaleWords(meta.quiz?.scale?.labels);
    renderProvinces();
    ui.provinceCount.textContent = `共 ${formatNumber(meta.provinces.length)} 个省级地区 · ${formatNumber(meta.majors_total || 0)} 个专业`;
    if (state.province) {
      await selectProvince(state.province, { initial: true });
    } else {
      ui.startNote.textContent = "先选一个省份";
    }
  } catch (error) {
    state.metaReady = false;
    ui.provinceGroups.innerHTML = `
      <div class="wz-empty">
        <h2>省份数据加载失败</h2>
        <p>${escapeHtml(error.message || "网络中断")}。这不影响你稍后再试。</p>
        <button class="hp-btn hp-btn--primary" type="button" data-meta-retry>重新加载</button>
      </div>`;
    ui.provinceCount.textContent = "省份加载失败";
    ui.start.disabled = true;
    ui.startNote.textContent = "数据没加载出来，先重试";
  }
}

function normalizeMeta(raw) {
  if (!raw || typeof raw !== "object") return { provinces: [], groups: [], quiz: {} };
  if (Array.isArray(raw.provinces)) return raw;
  // 兼容契约里 subjects 包一层的写法；实际后端是扁平的，两种都认
  if (raw.subjects && !Array.isArray(raw.subjects) && typeof raw.subjects === "object") {
    return {
      ...raw,
      subjects: raw.subjects.subjects || [],
      provinces: raw.subjects.provinces || raw.provinces || [],
      groups: raw.subjects.groups || raw.groups || [],
    };
  }
  return { ...raw, provinces: [], groups: raw.groups || [] };
}

function renderProvinces() {
  const query = (ui.provinceSearch.value || "").trim();
  const groups = new Map();
  state.provinces.forEach((province) => {
    const key = province.mode || "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(province);
  });
  const modes = Array.from(groups.keys()).sort((a, b) => {
    const ai = MODE_ORDER.indexOf(a);
    const bi = MODE_ORDER.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
  });

  ui.provinceGroups.innerHTML = modes.map((mode) => {
    const list = groups.get(mode);
    const label = modeLabel(mode);
    const cards = list.map((province) => {
      const year = Number(province.first) ? `${province.first} 年首考` : "尚未进入新高考";
      const active = province.name === state.province;
      return `
        <button class="wz-province${active ? " is-active" : ""}" type="button"
          data-province="${escapeHtml(province.name)}" aria-pressed="${active}">
          <span class="wz-province-name">${escapeHtml(province.name)}</span>
          <span class="wz-province-meta">${formatNumber(province.combo_count)} 种组合 · ${escapeHtml(year)}</span>
        </button>`;
    }).join("");
    return `
      <section class="wz-province-group" data-mode="${escapeHtml(mode)}">
        <h2>${escapeHtml(label)}<em>${formatNumber(list.length)} 个省份</em></h2>
        <div class="wz-province-grid">${cards}</div>
      </section>`;
  }).join("");

  applyProvinceFilter(query);
}

function applyProvinceFilter(query) {
  let visible = 0;
  const groups = ui.provinceGroups.querySelectorAll(".wz-province-group");
  groups.forEach((group) => {
    let groupVisible = 0;
    group.querySelectorAll(".wz-province").forEach((button) => {
      const hit = !query || button.dataset.province.includes(query);
      button.hidden = !hit;
      if (hit) {
        groupVisible += 1;
        visible += 1;
      }
    });
    group.hidden = groupVisible === 0;
  });
  ui.provinceEmpty.hidden = visible !== 0 || !state.metaReady;
}

async function selectProvince(name, { initial = false, focusStart = false } = {}) {
  const province = provinceMeta(name);
  if (!province) return;
  const changed = state.province !== name;
  state.province = name;
  writeSession(SKEY.province, name);
  renderProvinceSelection();

  ui.provinceSummary.hidden = false;
  ui.provinceMode.textContent = `你们省是${province.mode_label || modeLabel(province.mode)}，一共 ${formatNumber(province.combo_count)} 种组合`;
  ui.provinceDesc.textContent = state.modeDesc[province.mode] || "选科规则以本省考试院当年公布的文件为准。";
  ui.provinceCombos.textContent = "正在核对你们省的组合…";
  ui.start.disabled = false;
  ui.startNote.textContent = `已选 ${name} · 接下来 ${formatNumber(quizCount())} 道题，约 ${formatNumber(quizMinutes())} 分钟`;

  if (changed && state.report) clearReport();
  if (!initial && state.step >= 3) {
    // 省份变了，旧报告一定失效，直接回第 1 步会让人以为点击丢了
    applyStep(1, { focus: false });
  }

  const requestId = ++state.provinceComboReq;
  try {
    const data = await api.choiceCombos(name);
    if (requestId !== state.provinceComboReq) return;
    state.provinceCombos = Array.isArray(data.combos) ? data.combos : [];
    renderComboSummary(province);
  } catch {
    if (requestId !== state.provinceComboReq) return;
    state.provinceCombos = [];
    ui.provinceCombos.textContent = `共 ${formatNumber(province.combo_count)} 种组合，下一步会按你的答案挑 3 种。`;
  }

  if (focusStart) ui.start.focus({ preventScroll: true });
}

function renderProvinceSelection() {
  ui.provinceGroups.querySelectorAll(".wz-province").forEach((button) => {
    const active = button.dataset.province === state.province;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function renderComboSummary(province) {
  const combos = state.provinceCombos || [];
  if (!combos.length) {
    ui.provinceCombos.textContent = `共 ${formatNumber(province.combo_count)} 种组合，下一步会按你的答案挑 3 种。`;
    return;
  }
  const examples = combos.slice(0, 3).map((combo) => combo.label || (combo.subjects || []).join(" + ")).join("、");
  let breakdown = "";
  if (province.mode === "3+1+2") {
    const physics = combos.filter((combo) => combo.track === "物理类").length;
    const history = combos.filter((combo) => combo.track === "历史类").length;
    if (physics || history) {
      breakdown = `物理类 ${formatNumber(physics)} 种、历史类 ${formatNumber(history)} 种。`;
    }
  }
  ui.provinceCombos.textContent = `${breakdown}例如：${examples}。`;
}

function clearReport() {
  state.report = null;
  state.reportTop = 3;
  state.reportSignature = "";
  state.comboWindow = 0;
  state.majors = [];
  state.aiResult = null;
  removeSession(SKEY.report);
  ui.comboGrid.innerHTML = "";
  ui.majorGrid.innerHTML = "";
  ui.comboStatus.textContent = "";
  ui.majorStatus.textContent = "";
}

/* ---------- 步骤切换 ---------------------------------------------------- */
async function goToStep(target, options = {}) {
  let step = clamp(Number(target) || 1, 1, 5);
  if (step > 1 && !state.province) {
    toast("先在第 1 步选一个省份");
    step = 1;
  }

  if (step >= 3) {
    const ok = await ensureReport();
    if (!ok) return;
  }

  if (step === 5 && !state.majors.length) {
    toast("还没有专业推荐，先完成前四步");
    step = 4;
  }

  applyStep(step, { focus: !options.initial });
  if (step === 2) {
    await ensureQuiz();
  }
}

function applyStep(step, { focus = true, scroll = true } = {}) {
  state.step = step;
  ui.sections.forEach((section) => {
    const active = Number(section.dataset.step) === step;
    section.hidden = !active;
    section.classList.toggle("is-active", active);
  });
  ui.stepLinks.forEach((link) => {
    const active = Number(link.dataset.step) === step;
    if (active) link.setAttribute("aria-current", "step");
    else link.removeAttribute("aria-current");
  });

  if (scroll) window.scrollTo({ top: 0, behavior: "auto" });
  closeMobileNav();
  syncUrl();

  if (step === 3) renderCombos();
  if (step === 4) renderMajors();
  if (step === 5) initInterest();

  if (focus) {
    const heading = document.querySelector(`#wz-step-${step} h1`);
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  }
}

function syncUrl() {
  const url = new URL(window.location.href);
  url.hash = `step-${state.step}`;
  url.searchParams.delete("step");
  if (state.step === 2) url.searchParams.set("q", String(state.quizIndex + 1));
  else url.searchParams.delete("q");
  window.history.replaceState(null, "", url);
}

function closeMobileNav() {
  if (!ui.header.classList.contains("is-nav-open")) return;
  ui.header.classList.remove("is-nav-open");
  ui.burger.setAttribute("aria-expanded", "false");
  document.body.classList.remove("hp-nav-locked");
}

/* ---------- 问卷 -------------------------------------------------------- */
async function ensureQuiz() {
  if (state.quizReady) return true;
  if (state.quizLoading && state.quizPromise) return state.quizPromise;
  state.quizLoading = true;
  ui.quizLoading.hidden = false;
  ui.quizBody.hidden = true;
  ui.quizError.hidden = true;

  state.quizPromise = (async () => {
    try {
      const data = await api.choiceQuiz();
      const items = Array.isArray(data) ? data : data?.items;
      if (!Array.isArray(items) || !items.length) throw new Error("题库是空的");
      state.quiz = items.map((item, index) => ({
        ...item,
        id: String(item.id || `q${index + 1}`),
        title: String(item.title || ""),
        kind: item.kind === "scale" ? "scale" : "single",
        options: Array.isArray(item.options) ? item.options : [],
      })).filter((item) => item.title);
      if (!state.quiz.length) throw new Error("题库是空的");
      state.scaleLabels = scaleWords(data?.scale?.labels || state.meta?.quiz?.scale?.labels);
      state.quizReady = true;
      state.quizIndex = clamp(state.quizIndex, 0, state.quiz.length - 1);
      if (state.pendingQuizIndex !== null) {
        state.quizIndex = clamp(state.pendingQuizIndex, 0, state.quiz.length - 1);
        state.pendingQuizIndex = null;
      }
      ui.quizLoading.hidden = true;
      ui.quizBody.hidden = false;
      ui.quizError.hidden = true;
      renderQuestion();
      // 深链 ?q=3 在 applyStep 时还没有题库，syncUrl 会先写成 q=1；题目定位后要把地址改回来
      if (state.step === 2) syncUrl();
      return true;
    } catch (error) {
      state.quizReady = false;
      ui.quizLoading.hidden = true;
      ui.quizBody.hidden = true;
      ui.quizError.hidden = false;
      ui.quizError.querySelector("p").textContent = `${error.message || "网络中断"}。刷新页面或点下面的按钮重试。`;
      return false;
    } finally {
      state.quizLoading = false;
    }
  })();
  return state.quizPromise;
}

function renderQuestion({ focus = false } = {}) {
  if (!state.quizReady || !state.quiz.length) return;
  const question = currentQuiz();
  if (!question) return;
  const total = state.quiz.length;
  const index = state.quizIndex;
  const answer = state.answers[question.id];

  ui.progressBar.style.width = `${((index + 1) / total) * 100}%`;
  ui.progress.setAttribute("aria-valuemax", String(total));
  ui.progress.setAttribute("aria-valuenow", String(index + 1));
  ui.quizCount.textContent = `第 ${formatNumber(index + 1)} / ${formatNumber(total)} 题`;
  ui.quizTopic.textContent = question.topic || GROUP_LABELS[question.group] || "问卷";
  ui.quizPrev.disabled = index === 0;
  ui.quizNext.textContent = index === total - 1 ? "生成报告" : "下一题";

  const optionsHtml = question.kind === "scale"
    ? scaleOptionsHtml(question, answer)
    : singleOptionsHtml(question, answer);

  ui.question.innerHTML = `
    <div class="wz-q-head">
      <span class="wz-q-index">Q${String(index + 1).padStart(2, "0")}</span>
      <h2 id="wz-q-title" tabindex="-1">${escapeHtml(question.title)}</h2>
    </div>
    ${question.hint ? `<p class="wz-q-hint">${escapeHtml(question.hint)}</p>` : ""}
    ${optionsHtml}`;

  if (focus) {
    const heading = ui.question.querySelector("h2");
    if (heading) heading.focus({ preventScroll: true });
  }
}

function singleOptionsHtml(question, answer) {
  if (!question.options.length) {
    return '<p class="wz-muted">这道题暂时没有选项，跳过它不影响其他题目。</p>';
  }
  return `<div class="wz-options" role="radiogroup" aria-labelledby="wz-q-title">
    ${question.options.map((option, index) => {
      const value = String(option.id ?? index);
      const checked = String(answer) === value;
      const letter = String.fromCharCode(65 + index);
      return `
        <label class="wz-option${checked ? " is-selected" : ""}">
          <input type="radio" name="wz-${escapeHtml(question.id)}" value="${escapeHtml(value)}"${checked ? " checked" : ""}>
          <span class="wz-option-key">${letter}</span>
          <span class="wz-option-text">${escapeHtml(option.text || "")}</span>
        </label>`;
    }).join("")}
  </div>`;
}

function scaleOptionsHtml(question, answer) {
  const labels = state.scaleLabels.length ? state.scaleLabels : DEFAULT_SCALE;
  return `<div class="wz-scale-options" role="radiogroup" aria-labelledby="wz-q-title">
    ${labels.map((label, index) => {
      const value = index + 1;
      const checked = Number(answer) === value;
      return `
        <label class="wz-scale-option${checked ? " is-selected" : ""}">
          <input type="radio" name="wz-${escapeHtml(question.id)}" value="${value}"${checked ? " checked" : ""}>
          <span class="wz-scale-num">${formatNumber(value)}</span>
          <span class="wz-scale-word">${escapeHtml(label)}</span>
        </label>`;
    }).join("")}
  </div>`;
}

function onQuestionChange(event) {
  const input = event.target.closest('input[type="radio"]');
  if (!input) return;
  const question = currentQuiz();
  if (!question) return;
  state.answers[question.id] = question.kind === "scale" ? Number(input.value) : input.value;
  writeSession(SKEY.answers, state.answers);
  ui.question.querySelectorAll(".wz-option, .wz-scale-option").forEach((label) => {
    const radio = label.querySelector('input[type="radio"]');
    label.classList.toggle("is-selected", Boolean(radio && radio.checked));
  });
  ui.quizSave.textContent = "已保存到本机 · 刷新不会丢";
}

async function nextQuestion() {
  const question = currentQuiz();
  if (!question) return;
  if (state.answers[question.id] === undefined) {
    toast("先选一个答案，再继续");
    const input = activeOptionInput();
    if (input) input.focus({ preventScroll: true });
    return;
  }

  if (state.quizIndex < state.quiz.length - 1) {
    state.quizIndex += 1;
    syncUrl();
    renderQuestion({ focus: true });
    return;
  }

  const missing = missingQuestions();
  if (missing.length) {
    jumpToQuestion(missing[0]);
    toast(`还有 ${formatNumber(missing.length)} 题没答完`);
    return;
  }

  ui.quizNext.disabled = true;
  ui.quizNext.textContent = "正在生成…";
  const ok = await ensureReport({ force: true });
  ui.quizNext.disabled = false;
  ui.quizNext.textContent = "生成报告";
  if (ok) applyStep(3, { focus: true });
}

function prevQuestion() {
  if (state.quizIndex <= 0) return;
  state.quizIndex -= 1;
  syncUrl();
  renderQuestion({ focus: true });
}

function jumpToQuestion(question) {
  const index = state.quiz.findIndex((item) => item.id === question.id);
  if (index < 0) return;
  state.quizIndex = index;
  syncUrl();
  renderQuestion({ focus: true });
}

/* ---------- 报告 / 组合 ------------------------------------------------- */
async function ensureReport({ force = false } = {}) {
  if (!state.province) {
    toast("先在第 1 步选省份");
    applyStep(1, { focus: false });
    return false;
  }
  if (!force && state.report && state.reportSignature === answerSignature()) return true;
  if (!state.quizReady) {
    const ok = await ensureQuiz();
    if (!ok) {
      applyStep(2, { focus: false });
      return false;
    }
  }
  const missing = missingQuestions();
  if (missing.length) {
    applyStep(2, { focus: false });
    jumpToQuestion(missing[0]);
    toast(`还有 ${formatNumber(missing.length)} 题没答完`);
    return false;
  }
  return generateReport({ topCombos: 3 });
}

async function generateReport({ topCombos = 3, windowStart = 0, quiet = false } = {}) {
  if (!state.province || state.comboLoading) return false;
  state.comboLoading = true;
  if (!quiet) {
    ui.comboStatus.classList.remove("is-error");
    ui.comboStatus.textContent = "正在按你的答案生成报告…";
  }
  ui.comboMore.disabled = true;
  ui.toMajors.disabled = true;

  try {
    const data = await api.choiceReport({
      province: state.province,
      answers: state.answers,
      topCombos,
      topMajors: 12,
    });
    if (!data || !Array.isArray(data.combos) || !Array.isArray(data.majors)) {
      throw new Error("服务端返回的报告不完整");
    }
    state.report = data;
    state.reportTop = topCombos;
    state.reportSignature = answerSignature();
    state.majors = data.majors;
    state.aiResult = null;
    const combos = data.combos;
    state.comboWindow = combos.length ? clamp(windowStart, 0, Math.max(0, combos.length - 3)) : 0;

    writeSession(SKEY.report, {
      province: state.province,
      signature: state.reportSignature,
      top: state.reportTop,
      window: state.comboWindow,
      report: data,
    });

    if (state.step === 3) renderCombos();
    if (state.step === 4) renderMajors();
    if (state.step === 5) initInterest();
    ui.comboStatus.textContent = "";
    return true;
  } catch (error) {
    toast(`报告生成失败：${error.message}`);
    if (state.step === 3) {
      ui.comboStatus.classList.add("is-error");
      ui.comboStatus.textContent = `报告生成失败：${error.message}。可以检查网络后重试。`;
    }
    return false;
  } finally {
    state.comboLoading = false;
    ui.comboMore.disabled = false;
    ui.toMajors.disabled = false;
  }
}

function renderCombos() {
  const report = state.report;
  if (!report) return;
  const combos = Array.isArray(report.combos) ? report.combos : [];
  const start = combos.length ? clamp(state.comboWindow, 0, Math.max(0, combos.length - 3)) : 0;
  state.comboWindow = start;
  const slice = combos.slice(start, start + 3);

  ui.reportMeta.innerHTML = reportMetaHtml(report);
  if (!slice.length) {
    ui.comboStatus.classList.add("is-error");
    ui.comboStatus.textContent = "没有可用的组合推荐，回第 2 步检查一下答案是否完整。";
    ui.comboGrid.innerHTML = "";
    ui.comboMore.disabled = true;
    ui.comboMore.textContent = "没有更多了";
    return;
  }
  ui.comboStatus.textContent = "";
  ui.comboStatus.classList.remove("is-error");
  const total = Number(report.meta?.combos_available) || Number(provinceMeta(state.province)?.combo_count) || combos.length;
  const majorsTotal = Number(report.meta?.majors_total) || Number(state.meta?.majors_total) || 0;
  ui.comboGrid.innerHTML = slice.map((combo, index) => comboCard(combo, start + index, majorsTotal)).join("");
  // 服务端一次最多给 6 组；只有还能翻到新的一屏时才让「换一批」可点。
  const canMore = total > 3 && (state.reportTop < 6 || start + 3 < combos.length);
  ui.comboMore.disabled = !canMore;
  ui.comboMore.textContent = canMore ? "换一批" : "没有更多了";
}

function reportMetaHtml(report) {
  const province = provinceMeta(state.province);
  const total = Number(report.meta?.combos_available) || Number(province?.combo_count) || 0;
  const clusters = Array.isArray(report.profile?.top_clusters)
    ? report.profile.top_clusters.slice(0, 2).map(([key]) => clusterLabel(key)).filter(Boolean)
    : [];
  return `基于 <b>${escapeHtml(state.province)}</b> · ${escapeHtml(province?.mode_label || modeLabel(report.mode))}
    · 共 ${formatNumber(total)} 种组合${clusters.length ? ` · 兴趣前二：${escapeHtml(clusters.join("、"))}` : ""}`;
}

function comboCard(combo, index, totalMajors) {
  const subjects = (combo.subjects || []).map((subject) => `<span>${escapeHtml(subject)}</span>`).join("<i>+</i>");
  const score = Number(combo.score) || 0;
  const ratio = clamp(Number(combo.coverage_ratio) || 0, 0, 1);
  const coverage = Number(combo.coverage_majors) || 0;
  const groups = Number(combo.coverage_groups) || 0;
  const denominator = Number(totalMajors) || Number(state.report?.meta?.majors_total) || Number(state.meta?.majors_total) || 0;
  const strengths = Array.isArray(combo.strengths) ? combo.strengths.filter(Boolean) : [];
  const risks = Array.isArray(combo.risk) ? combo.risk.filter(Boolean) : (combo.risk ? [combo.risk] : []);
  const watch = combo.watch || "";
  const why = combo.why || "";
  const subjectFit = Number(combo.subject_fit);
  const clusterFit = Number(combo.cluster_fit);

  return `
    <article class="wz-combo">
      <p class="wz-combo-kicker">推荐 ${String(index + 1).padStart(2, "0")}${index === 0 ? " · 匹配最高" : ""}</p>
      <div class="wz-combo-top">
        <h2 class="wz-combo-name">${subjects}</h2>
        <div class="wz-ring" style="--pct:${clamp(score, 0, 100).toFixed(1)}" role="img"
          aria-label="组合匹配分 ${formatNumber(score)}">
          <span><b>${formatNumber(score)}</b><em>匹配分</em></span>
        </div>
      </div>
      <dl class="wz-combo-stats">
        <div><dt>可报比例</dt><dd>${nf1.format(ratio * 100)}%</dd></div>
        <div><dt>可报专业</dt><dd>${formatNumber(coverage)}<small>/ ${formatNumber(denominator)} 个专业可报</small></dd></div>
        <div><dt>专业类</dt><dd>${formatNumber(groups)} 类</dd></div>
      </dl>
      ${watch ? `<p class="wz-combo-watch"><b>注意</b> ${escapeHtml(watch)}</p>` : ""}
      <button class="wz-disclose" type="button" aria-expanded="false">
        为什么是它 <span aria-hidden="true">+</span>
      </button>
      <div class="wz-combo-detail" hidden>
        ${why ? `<p class="wz-combo-why">${escapeHtml(why)}</p>` : ""}
        ${Number.isFinite(subjectFit) || Number.isFinite(clusterFit) ? `
          <p class="wz-combo-fit-note">学科匹配 ${Number.isFinite(subjectFit) ? nf1.format(subjectFit) : "—"}
            · 兴趣簇匹配 ${Number.isFinite(clusterFit) ? nf1.format(clusterFit) : "—"}</p>` : ""}
        <div class="wz-combo-lists">
          <div>
            <h3>适合你的地方</h3>
            ${strengths.length ? `<ul>${strengths.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "<p>规则引擎没有给出额外优势项，主要看上面的匹配分。</p>"}
          </div>
          <div>
            <h3>要接受的代价</h3>
            ${risks.length ? `<ul>${risks.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "<p>没有额外的风险提示，但仍要逐项核对专业要求。</p>"}
          </div>
        </div>
      </div>
    </article>`;
}

async function moreCombos() {
  if (state.comboLoading) return;
  const report = state.report;
  if (!report) return;
  const combos = Array.isArray(report.combos) ? report.combos : [];
  const available = Number(report.meta?.combos_available) || combos.length;

  if (state.reportTop < 6 && available > 3) {
    const nextWindow = state.comboWindow + 3;
    ui.comboMore.disabled = true;
    ui.comboMore.textContent = "换一批中…";
    const ok = await generateReport({ topCombos: 6, windowStart: nextWindow, quiet: true });
    if (!ok) {
      renderCombos();
      return;
    }
    const newCombos = state.report?.combos || [];
    if (newCombos.length <= 3) {
      state.comboWindow = 0;
      renderCombos();
      toast(`你们省一共 ${formatNumber(newCombos.length)} 种组合，已经全部列出`);
      return;
    }
    renderCombos();
    return;
  }

  if (combos.length > 3 && state.comboWindow + 3 < combos.length) {
    state.comboWindow += 3;
    renderCombos();
    return;
  }

  toast(`服务端最多给到 ${formatNumber(combos.length)} 组推荐，已经全部看过`);
}

/* ---------- 专业 -------------------------------------------------------- */
function groupEligible(group, subjects) {
  if (!group) return null;
  const required = Array.isArray(group.required) ? group.required : [];
  const anyOf = Array.isArray(group.any_of) ? group.any_of : [];
  if (required.some((name) => !subjects.includes(name))) return false;
  if (anyOf.length && !anyOf.some((name) => subjects.includes(name))) return false;
  return true;
}

function topCombos() {
  return Array.isArray(state.report?.combos) ? state.report.combos.slice(0, 3) : [];
}

function majorFit(major) {
  const group = state.groupsById.get(major.group_id);
  const combos = topCombos();
  if (!group || !combos.length) return { count: 0, total: combos.length, known: false };
  let count = 0;
  combos.forEach((combo) => {
    if (groupEligible(group, combo.subjects || [])) count += 1;
  });
  return { count, total: combos.length, known: true };
}

function renderMajors() {
  const report = state.report;
  if (!report) return;
  const majors = Array.isArray(state.majors) ? state.majors : [];
  const onlyEligible = ui.majorEligible.checked;
  const rows = majors.map((major) => ({ major, fit: majorFit(major) }));
  const visible = onlyEligible ? rows.filter((row) => row.fit.count > 0) : rows;

  const eligibleCount = rows.filter((row) => row.fit.count > 0).length;
  ui.majorCount.textContent = onlyEligible
    ? `${formatNumber(visible.length)} 个可报（共 ${formatNumber(majors.length)} 个推荐）`
    : `${formatNumber(majors.length)} 个专业 · ${formatNumber(eligibleCount)} 个可报`;
  ui.majorMeta.innerHTML = reportMetaHtml(report);
  ui.majorStatus.textContent = "";
  ui.majorStatus.classList.remove("is-error");

  if (!visible.length) {
    ui.majorGrid.innerHTML = "";
    ui.majorStatus.classList.add("is-error");
    ui.majorStatus.textContent = "推荐组合暂时没有可报的专业。取消上面的筛选，看看其他方向。";
    return;
  }
  ui.majorGrid.innerHTML = visible.map((row) => majorCard(row.major, row.fit)).join("");
}

function majorCard(major, fit) {
  const group = state.groupsById.get(major.group_id);
  const groupName = major.group || group?.name || "专业类";
  const cluster = major.cluster_name || clusterLabel(major.cluster);
  const requirement = group?.requirement || "按专业类通用要求";
  const fitText = !fit.known
    ? "专业类要求待核对"
    : fit.count === fit.total
      ? `${formatNumber(fit.total)} 个推荐组合都可报`
      : fit.count > 0
        ? `${formatNumber(fit.count)} / ${formatNumber(fit.total)} 个推荐组合可报`
        : "推荐组合暂不可报";
  const warn = fit.known && fit.count === 0;
  const href = `./major.html?major=${encodeURIComponent(major.name || "")}`;

  return `
    <article class="wz-major">
      <div class="wz-major-head">
        <div>
          <h2><a class="wz-major-link" href="${href}">${escapeHtml(major.name || "未命名专业")}</a></h2>
          <p class="wz-major-sub">${escapeHtml(groupName)}<i>·</i>${escapeHtml(cluster)}</p>
        </div>
        <p class="wz-major-score"><b>${formatNumber(major.score)}</b><span>匹配分</span></p>
      </div>
      <p class="wz-major-fit${warn ? " is-warn" : ""}">${escapeHtml(fitText)}</p>
      <div class="wz-major-foot">
        <span class="wz-major-req">选科要求：${escapeHtml(requirement)}</span>
        <button class="wz-college-btn" type="button" data-college-major="${escapeHtml(major.name || "")}">
          看哪些学校强 ↗
        </button>
      </div>
    </article>`;
}

/* ---------- 院校抽屉 ---------------------------------------------------- */
function trackOptions(mode) {
  if (mode === "3+1+2") return ["物理类", "历史类"];
  if (mode === "old") return ["文科", "理科"];
  if (mode === "3+3") return ["综合改革"];
  return ["物理类", "历史类"];
}

function defaultTrack(province, combo) {
  const meta = provinceMeta(province);
  const subjects = combo?.subjects || [];
  if (combo?.track) return combo.track;
  if (meta?.mode === "3+1+2") return subjects.includes("物理") ? "物理类" : "历史类";
  if (meta?.mode === "old") return subjects.includes("物理") ? "理科" : "文科";
  if (meta?.mode === "3+3") return "综合改革";
  return subjects.includes("物理") ? "物理类" : "历史类";
}

function fillDrawerProvinces() {
  const options = state.provinces.map((province) => (
    `<option value="${escapeHtml(province.name)}">${escapeHtml(province.name)}</option>`
  )).join("");
  ui.drawerProvince.innerHTML = options;
  if (state.drawer.province) ui.drawerProvince.value = state.drawer.province;
}

function fillDrawerTracks() {
  const meta = provinceMeta(state.drawer.province);
  const list = trackOptions(meta?.mode);
  if (state.drawer.track && !list.includes(state.drawer.track)) list.push(state.drawer.track);
  ui.drawerTrack.innerHTML = list.map((track) => (
    `<option value="${escapeHtml(track)}">${escapeHtml(track)}</option>`
  )).join("");
  ui.drawerTrack.value = state.drawer.track || list[0] || "";
  if (!state.drawer.track) state.drawer.track = ui.drawerTrack.value;
}

function updateDrawerSub() {
  let suffix = "按最低位次升序";
  if (state.drawer.error) {
    const status = Number(state.drawer.error.status) || 0;
    suffix = status === 404 || status >= 500 ? "院校数据接入中" : "院校数据暂不可用";
  } else if (state.drawer.data) {
    const items = Array.isArray(state.drawer.data.items) ? state.drawer.data.items : [];
    suffix = items.length ? "按最低位次升序" : "暂无院校数据";
  }
  ui.drawerSub.textContent = `${state.drawer.major || "专业"} · ${state.drawer.province || "省份"} · ${state.drawer.track || "科类"} · ${suffix}`;
}

function openDrawer(major, trigger) {
  if (!major) return;
  window.clearTimeout(state.drawer.closeTimer);
  const reportCombo = state.report?.combos?.[0];
  state.drawer.open = true;
  state.drawer.major = major;
  state.drawer.province = state.province || state.provinces[0]?.name || "";
  state.drawer.track = defaultTrack(state.drawer.province, reportCombo);
  state.drawer.data = null;
  state.drawer.error = null;
  state.drawer.loading = true;
  state.drawer.trigger = trigger instanceof HTMLElement ? trigger : document.activeElement;
  state.drawer.req += 1;

  ui.drawerTitle.textContent = major;
  updateDrawerSub();
  fillDrawerProvinces();
  fillDrawerTracks();
  ui.drawerNote.textContent = "";
  ui.drawerBody.innerHTML = '<p class="wz-loading">正在查院校数据…</p>';
  ui.drawer.hidden = false;
  lockPage();
  window.requestAnimationFrame(() => ui.drawer.classList.add("is-open"));
  ui.drawerClose.focus({ preventScroll: true });
  loadColleges();
}

function closeDrawer({ restoreFocus = true } = {}) {
  if (!state.drawer.open) return;
  state.drawer.open = false;
  state.drawer.req += 1;
  state.drawer.loading = false;
  ui.drawer.classList.remove("is-open");
  unlockPage();
  const trigger = state.drawer.trigger;
  window.clearTimeout(state.drawer.closeTimer);
  state.drawer.closeTimer = window.setTimeout(() => {
    ui.drawer.hidden = true;
    if (restoreFocus && trigger && document.contains(trigger)) {
      trigger.focus({ preventScroll: true });
    }
  }, 240);
}

async function loadColleges() {
  if (!state.drawer.open) return;
  const requestId = ++state.drawer.req;
  state.drawer.loading = true;
  state.drawer.data = null;
  state.drawer.error = null;
  renderDrawerBody();
  try {
    const data = await api.majorColleges({
      name: state.drawer.major,
      province: state.drawer.province,
      track: state.drawer.track,
      limit: 20,
    });
    if (requestId !== state.drawer.req || !state.drawer.open) return;
    state.drawer.data = data || {};
  } catch (error) {
    if (requestId !== state.drawer.req || !state.drawer.open) return;
    state.drawer.error = error;
  } finally {
    if (requestId === state.drawer.req && state.drawer.open) {
      state.drawer.loading = false;
      renderDrawerBody();
    }
  }
}

function renderDrawerBody() {
  updateDrawerSub();
  if (state.drawer.loading) {
    ui.drawerBody.innerHTML = '<p class="wz-loading">正在查院校数据…</p>';
    ui.drawerNote.textContent = "";
    return;
  }

  if (state.drawer.error) {
    const status = Number(state.drawer.error.status) || 0;
    if (status === 404 || status >= 500) {
      ui.drawerNote.textContent = "";
      ui.drawerBody.innerHTML = drawerFallbackHtml("这个院校接口还没上线，或后端暂时不可用。");
    } else {
      ui.drawerNote.textContent = "";
      ui.drawerBody.innerHTML = `
        <div class="wz-empty">
          <h3>院校数据加载失败</h3>
          <p>${escapeHtml(state.drawer.error.message || "网络中断")}</p>
          <button class="hp-btn hp-btn--primary" type="button" data-drawer-retry>重试</button>
          <p><a class="wz-text-link" href="${majorHref(state.drawer.major)}">先看专业详情 ↗</a></p>
        </div>`;
    }
    return;
  }

  const data = state.drawer.data;
  if (!data) {
    ui.drawerBody.innerHTML = '<p class="wz-loading">正在查院校数据…</p>';
    return;
  }

  const items = Array.isArray(data.items) ? [...data.items] : [];
  items.sort((a, b) => {
    const ar = Number.isFinite(Number(a.best_rank)) ? Number(a.best_rank) : Infinity;
    const br = Number.isFinite(Number(b.best_rank)) ? Number(b.best_rank) : Infinity;
    return ar - br;
  });

  const note = data.note || (data.granularity === "cross_province"
    ? "你省的投档数据只到专业组粒度；下表用有专业级数据的省份排序，用来比较院校强弱，不等同于你省的录取位次。"
    : "");
  ui.drawerNote.textContent = note;

  if (!items.length) {
    ui.drawerBody.innerHTML = drawerFallbackHtml("暂时没有查到这所专业对应的院校数据。");
    return;
  }

  const total = Number(data.total) || items.length;
  ui.drawerBody.innerHTML = `
    <p class="wz-drawer-summary">共 ${formatNumber(total)} 所院校有相关专业数据，这里按最低位次列出前 ${formatNumber(items.length)} 所。</p>
    <div class="wz-college-list">
      ${items.map((item, index) => collegeCard(item, index)).join("")}
    </div>
    <p class="wz-drawer-source">数据来自 ${escapeHtml((data.data_provinces || []).join("、") || "外省专业级投档表")}；具体专业组以你省考试院公布为准。</p>`;
}

function collegeCard(item, index) {
  const rank = Number(item.best_rank);
  const score = Number(item.best_score);
  const tags = Array.isArray(item.tags) ? item.tags.filter(Boolean) : [];
  const source = [item.source_province, item.source_track].filter(Boolean).join(" · ");
  const year = item.best_year ? String(item.best_year) : "";
  const plan = Number(item.plan_total);
  const sourceLine = [
    source ? `数据来自 ${source}` : "",
    year ? `${year} 年` : "",
    plan ? `计划 ${formatNumber(plan)} 人` : "",
  ].filter(Boolean).join(" · ");

  return `
    <article class="wz-college">
      <div class="wz-college-head">
        <span class="wz-college-rank">${formatNumber(index + 1)}</span>
        <h3>${escapeHtml(item.college || "未命名院校")}</h3>
      </div>
      ${tags.length ? `<div class="wz-college-tags">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
      <dl class="wz-college-stats">
        <div><dt>最低位次</dt><dd>${Number.isFinite(rank) && rank > 0 ? formatNumber(rank) : "—"}</dd></div>
        <div><dt>最低分</dt><dd>${Number.isFinite(score) && score > 0 ? formatNumber(score) : "—"}</dd></div>
        <div><dt>年份</dt><dd>${year || "—"}</dd></div>
      </dl>
      <p class="wz-college-source">${escapeHtml(sourceLine || "数据口径待补充")}</p>
    </article>`;
}

function drawerFallbackHtml(reason) {
  return `
    <div class="wz-drawer-fallback">
      <h3>院校数据正在接入，先看专业详情</h3>
      <p>${escapeHtml(reason)} 专业本身学什么、毕业去哪、选科要求是什么，详情页已经能看。</p>
      <a class="hp-btn hp-btn--primary" href="${majorHref(state.drawer.major)}">先看专业详情</a>
    </div>`;
}

function majorHref(name) {
  return `./major.html?major=${encodeURIComponent(name || "")}`;
}

/* ---------- 第 5 步：先导课 / AI / 二次检验 --------------------------- */
function initInterest() {
  state.interestMajor = state.interestMajor || "";
  ui.interestSelect.innerHTML = "";
  ui.retestList.innerHTML = "";
  ui.verdict.hidden = true;
  ui.aiBody.innerHTML = "";
  ui.aiNote.textContent = "";
  ui.aiGenerate.disabled = true;
  ui.moocList.innerHTML = '<p class="wz-muted">选一个专业后加载课程。</p>';
  ui.moocNote.textContent = "";
  // 只清空不重绘的话，第 5 步会是一块空白；专业下拉、AI 兜底文案和课程都靠这里落回页面
  renderInterest();
}

function updateInterestDetail() {
  const name = state.interestMajor;
  ui.interestDetail.href = majorHref(name);
  ui.moocAll.href = `./mooc.html?major=${encodeURIComponent(name || "")}`;
}

async function loadMooc(major) {
  if (!major) return;
  const requestId = ++state.mooc.req;
  state.mooc = { status: "loading", items: [], note: "", total: 0, major, error: "", req: requestId };
  renderMooc();
  try {
    const data = await api.choiceMooc({ major, limit: 4 });
    if (requestId !== state.mooc.req) return;
    state.mooc.status = "ready";
    state.mooc.items = Array.isArray(data.items) ? data.items : [];
    state.mooc.note = data.tip || "";
    state.mooc.total = Number(data.total) || state.mooc.items.length;
  } catch (error) {
    if (requestId !== state.mooc.req) return;
    state.mooc.status = error.status === 401 ? "auth" : "error";
    state.mooc.error = error.message || "网络中断";
    state.mooc.items = [];
  }
  renderMooc();
}

function renderMooc() {
  const { status, items, note, error, major } = state.mooc;
  updateInterestDetail();

  if (status === "loading") {
    ui.moocList.innerHTML = '<p class="wz-loading">正在按这个专业挑课…</p>';
    ui.moocNote.textContent = "";
    return;
  }
  if (status === "auth") {
    ui.moocList.innerHTML = `
      <div class="wz-empty">
        <h3>先导课按账号开放</h3>
        <p>登录后，赤鲤会给「${escapeHtml(major)}」挑 3–4 门公开课，标明平台、时长和推荐理由。</p>
        <button class="hp-btn hp-btn--primary" type="button" data-mooc-login>登录后查看课程</button>
      </div>`;
    ui.moocNote.textContent = "未登录也可以继续做二次检验，只是看不到课程推荐。";
    return;
  }
  if (status === "error") {
    ui.moocList.innerHTML = `
      <div class="wz-empty">
        <h3>课程加载失败</h3>
        <p>${escapeHtml(error)}</p>
        <button class="hp-btn hp-btn--primary" type="button" data-mooc-retry>重试</button>
      </div>`;
    ui.moocNote.textContent = "";
    return;
  }
  if (!items.length) {
    ui.moocList.innerHTML = `<p class="wz-muted">这个专业的先导课还在整理。可以先去<a class="wz-text-link" href="./mooc.html?major=${encodeURIComponent(major)}">课程库</a>按关键词搜。</p>`;
    ui.moocNote.textContent = note || "";
    return;
  }

  ui.moocList.innerHTML = items.slice(0, 4).map(courseCard).join("");
  ui.moocNote.textContent = note || "课程来自公开平台，点开会在新标签页。";
}

function courseCard(item) {
  const platform = [item.platform, item.provider].filter(Boolean).filter((value, index, list) => list.indexOf(value) === index).join(" · ");
  const meta = [];
  // 后端现在给的是 weeks / reason；保留 hours / why 的兼容，避免接口字段演进时课程卡空白
  if (item.hours) meta.push(`${typeof item.hours === "number" ? formatNumber(item.hours) : item.hours} 小时`);
  else if (item.weeks) meta.push(`${typeof item.weeks === "number" ? formatNumber(item.weeks) : item.weeks} 周`);
  if (item.level) meta.push(item.level);
  if (item.rating) meta.push(`${typeof item.rating === "number" ? nf1.format(item.rating) : item.rating} 分`);
  if (item.learners) meta.push(`${typeof item.learners === "number" ? formatNumber(item.learners) : item.learners} 人学过`);
  const why = item.why || item.reason || item.desc || "";
  const inner = `
    <span class="wz-course-platform">${escapeHtml(platform)}</span>
    <h3>${escapeHtml(item.title || "未命名课程")}</h3>
    ${meta.length ? `<p class="wz-course-meta">${escapeHtml(meta.join(" · "))}</p>` : ""}
    ${why ? `<p class="wz-course-why">${escapeHtml(why)}</p>` : ""}
    ${item.url ? '<span class="wz-course-go">去听课 ↗</span>' : ""}`;

  if (!item.url) return `<div class="wz-course">${inner}</div>`;
  return `<a class="wz-course" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${inner}</a>`;
}

function renderRetest() {
  const major = state.interestMajor;
  const saved = (state.retestByMajor[major] && typeof state.retestByMajor[major] === "object")
    ? state.retestByMajor[major]
    : {};
  ui.retestList.innerHTML = RETEST_QUESTIONS.map((text, index) => {
    const value = Number(saved[index]);
    return `
      <fieldset class="wz-retest-q">
        <legend><span>0${index + 1}</span>${escapeHtml(text)}</legend>
        <div class="wz-scale-options" role="radiogroup" aria-label="第 ${formatNumber(index + 1)} 个检验问题">
          ${[1, 2, 3, 4, 5].map((score) => {
            const checked = value === score;
            return `
              <label class="wz-scale-option${checked ? " is-selected" : ""}">
                <input type="radio" name="wz-retest-${index}" value="${score}"${checked ? " checked" : ""}>
                <span class="wz-scale-num">${formatNumber(score)}</span>
                <span class="wz-scale-word">${escapeHtml(scaleLabel(score))}</span>
              </label>`;
          }).join("")}
        </div>
      </fieldset>`;
  }).join("");
  updateVerdict();
}

function onRetestChange(event) {
  const input = event.target.closest('input[type="radio"]');
  if (!input) return;
  const match = /^wz-retest-(\d)$/.exec(input.name);
  if (!match) return;
  const index = Number(match[1]);
  const major = state.interestMajor;
  if (!major) return;
  if (!state.retestByMajor[major] || typeof state.retestByMajor[major] !== "object") {
    state.retestByMajor[major] = {};
  }
  state.retestByMajor[major][index] = Number(input.value);
  writeSession(SKEY.retest, state.retestByMajor);
  ui.retestList.querySelectorAll(".wz-scale-option").forEach((label) => {
    const radio = label.querySelector('input[type="radio"]');
    label.classList.toggle("is-selected", Boolean(radio && radio.checked));
  });
  updateVerdict();
}

function updateVerdict() {
  const major = state.interestMajor;
  const saved = state.retestByMajor[major] || {};
  const values = [0, 1, 2].map((index) => Number(saved[index])).filter((value) => value >= 1 && value <= 5);
  if (values.length < 3) {
    ui.verdict.hidden = true;
    ui.verdict.innerHTML = "";
    return;
  }
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  const level = average >= 4 ? "high" : average >= 2 ? "mid" : "low";
  const copy = {
    high: "你愿意为它付出时间，这比「听起来有趣」可靠。下一步：把先导课学完，再找一份大一课表看看。",
    mid: "兴趣可能存在，但还没到愿意持续投入的程度。先完成一门 3–6 小时的先导课，再回来重答这三个问题。",
    low: "不是你不努力，是这件事暂时没让你愿意投入。回第 4 步换一个方向再测，别用「热门」说服自己。",
  }[level];
  const title = {
    high: "建议深入了解",
    mid: "需要再试试先导课",
    low: "建议换一个专业",
  }[level];

  ui.verdict.hidden = false;
  ui.verdict.dataset.level = level;
  ui.verdict.innerHTML = `
    <div class="wz-verdict-score"><b>${nf1.format(average)}</b><span>/ 5 兴趣匹配度</span></div>
    <h3>${title}</h3>
    <p class="wz-verdict-copy">${copy}</p>
    ${level === "high" ? "" : '<button class="hp-btn hp-btn--ghost" type="button" data-back-majors>回第 4 步换一个专业</button>'}`;
}

function builtinInsight(major) {
  return {
    source: "builtin",
    daily: [
      `大一上学期，公共课占掉一半时间：高数、英语、思政。专业导论课会先告诉你「${major}」四年要学什么，也最容易让人产生落差。`,
      "大二开始上专业核心课，作业从刷题变成实验报告、课程设计或小组展示。截止日前一周才开始，通常来不及。",
      "每周大约有 2–3 个下午被实验、上机或实践课占掉；剩下的时间要自己查资料、补基础，没人盯着。",
      "期末前两周，背诵和刷题的比例会突然变高。平时理解得再好，也要留出熟练的时间。",
    ],
    questions: [
      "如果连续一个月，每周要在这门专业上多花 10 小时，你愿意吗？",
      "如果前两年成绩只是中游，你愿意继续读到毕业，而不是马上换方向吗？",
      "如果毕业后的第一份工作起薪普通、要熬三年，你还会选它吗？",
    ],
    reality: "招生宣传展示的是这个专业最好的去向；更常见的日常，是普通课程、普通作业和普通成绩。先确认你能接受「普通的一天」。",
  };
}

function normalizeInsight(raw) {
  if (!raw || typeof raw !== "object") return null;
  const isText = (value) => typeof value === "string" && value.trim().length > 0;
  const daily = Array.isArray(raw.daily) ? raw.daily.filter(isText).slice(0, 4) : [];
  const questions = Array.isArray(raw.questions) ? raw.questions.filter(isText).slice(0, 3) : [];
  const reality = isText(raw.reality) ? raw.reality.trim() : "";
  if (daily.length < 2 || questions.length < 3 || !reality) return null;
  return { daily, questions, reality };
}

function parseAIJson(content) {
  if (content && typeof content === "object") return content;
  let text = String(content || "").trim();
  text = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) text = text.slice(start, end + 1);
  return JSON.parse(text);
}

function renderAIInsight() {
  const major = state.interestMajor;
  const data = state.aiResult || builtinInsight(major);
  const tag = data.source === "ai"
    ? `AI 生成${data.model ? ` · ${data.model}` : ""}`
    : "内置参考 · 未使用 AI";
  ui.aiBody.innerHTML = `
    <span class="wz-ai-tag">${escapeHtml(tag)}</span>
    <h3>真实的一天</h3>
    <ol>${data.daily.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ol>
    <div class="wz-ai-questions">
      <h3>三个灵魂拷问</h3>
      <ol>${data.questions.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ol>
    </div>
    <p class="wz-ai-reality">${escapeHtml(data.reality)}</p>`;
  ui.aiNote.textContent = data.source === "ai"
    ? "AI 可能出错，只作参考；真正的判断还是靠先导课和你的时间投入。"
    : `内置参考文案。配置 AI 后，可按「${major}」重新生成。`;
  ui.aiGenerate.disabled = state.aiBusy || !major;
}

function renderInterest() {
  const majors = Array.isArray(state.majors) ? state.majors : [];
  ui.interestSelect.innerHTML = "";
  if (!majors.length) {
    ui.interestSelect.disabled = true;
    ui.aiGenerate.disabled = true;
    ui.aiBody.innerHTML = "";
    return;
  }
  ui.interestSelect.disabled = false;
  const names = majors.map((major) => major.name);
  if (!names.includes(state.interestMajor)) {
    state.interestMajor = majors[0].name;
    writeSession(SKEY.interest, state.interestMajor);
  }
  ui.interestSelect.innerHTML = majors.map((major) => (
    `<option value="${escapeHtml(major.name)}">${escapeHtml(major.name)} · ${escapeHtml(major.group || major.cluster_name || "")}</option>`
  )).join("");
  ui.interestSelect.value = state.interestMajor;
  updateInterestDetail();
  renderRetest();
  renderAIInsight();
  if (state.mooc.major !== state.interestMajor || !["ready", "loading", "auth"].includes(state.mooc.status)) {
    loadMooc(state.interestMajor);
  } else {
    renderMooc();
  }
}

async function generateAIInsight() {
  if (state.aiBusy) return;
  const major = state.interestMajor;
  if (!major) {
    toast("先选一个专业");
    return;
  }
  const config = readAIConfig();
  if (!config) {
    openAIModal();
    toast("先配置一个 AI 厂商的 Key");
    return;
  }
  const user = await ensureSession();
  if (!user) {
    openLogin({ onSuccess: () => generateAIInsight() });
    return;
  }

  state.aiBusy = true;
  ui.aiGenerate.disabled = true;
  ui.aiGenerate.textContent = "生成中…";
  ui.aiBody.innerHTML = '<p class="wz-ai-loading">正在让模型读你的报告…</p>';
  try {
    const combo = state.report?.combos?.[0];
    const comboLabel = combo?.label || (combo?.subjects || []).join(" + ") || "未定";
    const majorInfo = (state.majors || []).find((item) => item.name === major);
    const messages = [
      {
        role: "system",
        content: "你是一名务实的高中生涯规划老师。只讲具体事实，不夸张，不用感叹号，不用 emoji。",
      },
      {
        role: "user",
        content: `请为高一学生写专业「${major}」的真实学习日常和三个灵魂拷问。
省份：${state.province}
推荐组合：${comboLabel}
专业类：${majorInfo?.group || ""}
兴趣簇：${majorInfo?.cluster_name || ""}

只输出 JSON，不要 markdown 代码块，结构：
{"daily":["..."],"questions":["..."],"reality":"..."}
daily 3–4 条，每条包含具体课程、作业或时间安排；questions 3 条，追问「愿不愿意付出时间」，不要问「喜不喜欢」；reality 一句话，写最容易被招生宣传忽略的现实。`,
      },
    ];
    const data = await api.aiChat({ ai: config, messages, json: true });
    const insight = normalizeInsight(parseAIJson(data.content));
    if (!insight) throw new Error("模型返回的不是预期结构");
    state.aiResult = {
      ...insight,
      source: "ai",
      model: data.model || config.model,
      providerName: data.provider_name || "",
    };
    renderAIInsight();
    ui.aiNote.textContent = `由 ${data.model || config.model} 生成 · AI 可能出错，只作参考。`;
  } catch (error) {
    state.aiResult = builtinInsight(major);
    renderAIInsight();
    ui.aiNote.textContent = `AI 生成失败，已保留内置参考：${error.message}`;
    toast(isLoginRequired(error) ? "登录已过期，请重新登录" : "AI 生成失败，先用内置参考");
  } finally {
    state.aiBusy = false;
    ui.aiGenerate.disabled = false;
    ui.aiGenerate.textContent = "用 AI 重写";
  }
}

/* ---------- AI 设置弹窗 -------------------------------------------------- */
function lockPage() {
  pageLock += 1;
  if (pageLock === 1) document.body.classList.add("wz-no-scroll");
}

function unlockPage() {
  pageLock = Math.max(0, pageLock - 1);
  if (pageLock === 0) document.body.classList.remove("wz-no-scroll");
}

function providerById(id) {
  return (state.providers || []).find((provider) => provider.id === id) || null;
}

function currentProvider() {
  return providerById(ui.aiProvider.value) || state.providers[0] || null;
}

async function loadProviders() {
  if (state.providers.length) return state.providers;
  if (!state.providersPromise) {
    state.providersPromise = api.aiProviders()
      .then((data) => {
        state.providers = Array.isArray(data.providers) ? data.providers : [];
        return state.providers;
      })
      .catch((error) => {
        state.providersPromise = null;
        throw error;
      });
  }
  return state.providersPromise;
}

function renderProviderOptions(selected) {
  const providers = state.providers || [];
  if (!providers.length) {
    ui.aiProvider.innerHTML = '<option value="">厂商列表为空</option>';
    ui.aiProvider.disabled = true;
    return;
  }
  ui.aiProvider.disabled = false;
  ui.aiProvider.innerHTML = providers.map((provider) => (
    `<option value="${escapeHtml(provider.id)}">${escapeHtml(provider.name || provider.id)}${provider.free ? " · 有免费额度" : ""}</option>`
  )).join("");
  if (selected && providers.some((provider) => provider.id === selected)) {
    ui.aiProvider.value = selected;
  } else {
    ui.aiProvider.value = providers[0].id;
  }
  updateProviderHint();
}

function updateProviderHint() {
  const provider = currentProvider();
  if (!provider) {
    ui.aiProviderHint.textContent = "";
    ui.aiHelp.hidden = true;
    return;
  }
  const parts = [];
  if (provider.default_model) parts.push(`默认模型 ${provider.default_model}`);
  if (provider.free) parts.push("有免费额度");
  if (provider.notes) parts.push(provider.notes);
  ui.aiProviderHint.textContent = parts.join(" · ");
  const href = provider.signup || provider.docs || "";
  ui.aiHelp.hidden = !href;
  if (href) ui.aiHelp.href = href;
}

function applyAISettings(config) {
  const provider = providerById(config?.provider) || state.providers[0] || null;
  if (provider) ui.aiProvider.value = provider.id;
  updateProviderHint();
  ui.aiModel.value = config?.model || provider?.default_model || provider?.models?.[0] || "";
  const key = config?.key || "";
  ui.aiKey.value = "";
  ui.aiKey.placeholder = key ? `已保存 ${maskKey(key)}，留空则不修改` : "粘贴厂商控制台里的 Key";
  ui.aiMasked.textContent = key ? maskKey(key) : "未配置";
}

function setAIStatus(text, kind = "") {
  ui.aiStatus.textContent = text;
  ui.aiStatus.classList.toggle("is-error", kind === "error");
  ui.aiStatus.classList.toggle("is-ok", kind === "ok");
}

function collectAISettings() {
  const provider = currentProvider();
  const providerId = provider?.id || ui.aiProvider.value || "";
  const typedKey = ui.aiKey.value.trim();
  const prior = state.aiDraft || readAIConfig() || {};
  const key = typedKey || (prior.provider === providerId ? prior.key : "");
  const model = ui.aiModel.value.trim() || provider?.default_model || provider?.models?.[0] || "";
  return { provider: providerId, key, model };
}

async function openAIModal({ draft = null, autoTest = false } = {}) {
  if (!ui.aiModal.hidden) return;
  const active = document.activeElement;
  state.aiTrigger = active instanceof HTMLElement ? active : null;
  state.aiDraft = draft ? { ...draft } : null;
  ui.aiModal.hidden = false;
  lockPage();
  setAIStatus("");
  ui.aiProvider.innerHTML = '<option value="">正在加载厂商…</option>';
  ui.aiProvider.disabled = true;
  ui.aiProviderHint.textContent = "";
  ui.aiHelp.hidden = true;
  ui.aiKey.value = "";
  ui.aiKey.placeholder = "粘贴厂商控制台里的 Key";
  ui.aiMasked.textContent = "未配置";
  ui.aiModel.value = "";
  ui.aiClose.focus({ preventScroll: true });

  try {
    await loadProviders();
    if (ui.aiModal.hidden) return;
    const config = state.aiDraft || readAIConfig();
    renderProviderOptions(config?.provider);
    applyAISettings(config);
    ui.aiKey.focus({ preventScroll: true });
    if (autoTest) runPing();
  } catch (error) {
    if (ui.aiModal.hidden) return;
    ui.aiProvider.innerHTML = '<option value="">厂商列表加载失败</option>';
    ui.aiProvider.disabled = true;
    setAIStatus(`厂商列表加载失败：${error.message}`, "error");
  }
}

function closeAIModal({ restoreFocus = true } = {}) {
  if (ui.aiModal.hidden) return;
  ui.aiModal.hidden = true;
  unlockPage();
  if (restoreFocus && state.aiTrigger && document.contains(state.aiTrigger)) {
    state.aiTrigger.focus({ preventScroll: true });
  }
}

function saveAIConfig() {
  const settings = collectAISettings();
  if (!settings.provider) {
    setAIStatus("还没选厂商。", "error");
    return;
  }
  if (!settings.key) {
    setAIStatus("先填写 API Key，再保存。", "error");
    ui.aiKey.focus({ preventScroll: true });
    return;
  }
  if (!settings.model) {
    setAIStatus("这个厂商没有默认模型，手动填一个模型名。", "error");
    ui.aiModel.focus({ preventScroll: true });
    return;
  }
  try {
    window.localStorage.setItem(AI_KEY, JSON.stringify(settings));
  } catch {
    setAIStatus("浏览器禁用了本地存储，Key 存不进去。换一个浏览器或关闭无痕模式。", "error");
    return;
  }
  state.aiDraft = null;
  ui.aiMasked.textContent = maskKey(settings.key);
  ui.aiKey.value = "";
  ui.aiKey.placeholder = `已保存 ${maskKey(settings.key)}，留空则不修改`;
  setAIStatus("已保存到本机浏览器，只在这个页面发请求时使用。", "ok");
  toast("AI 配置已保存");
}

function clearAIConfig() {
  try {
    window.localStorage.removeItem(AI_KEY);
  } catch {
    /* ignore */
  }
  state.aiDraft = null;
  ui.aiKey.value = "";
  ui.aiMasked.textContent = "未配置";
  ui.aiKey.placeholder = "粘贴厂商控制台里的 Key";
  setAIStatus("已清除本机配置。", "");
}

async function runPing() {
  const settings = collectAISettings();
  if (!settings.key) {
    setAIStatus("先填写 API Key，再测试连接。", "error");
    ui.aiKey.focus({ preventScroll: true });
    return;
  }
  const user = await ensureSession();
  if (!user) {
    const draft = { ...settings };
    closeAIModal({ restoreFocus: false });
    openLogin({ onSuccess: () => openAIModal({ draft, autoTest: true }) });
    return;
  }

  ui.aiTest.disabled = true;
  ui.aiSave.disabled = true;
  setAIStatus("正在连接厂商接口…");
  try {
    const data = await api.aiPing({ ai: settings });
    if (data && data.ok === false) throw new Error(data.error || "连接失败");
    const latency = Number(data?.latency_ms);
    const reply = typeof data?.reply === "string" ? data.reply.trim() : "";
    setAIStatus(
      `连接成功 · ${data?.model || settings.model}${Number.isFinite(latency) ? ` · ${formatNumber(latency)} ms` : ""}${reply ? ` · ${reply.slice(0, 30)}` : ""}`,
      "ok",
    );
  } catch (error) {
    if (isLoginRequired(error)) {
      setAIStatus("登录已过期，请重新登录后再测试。", "error");
    } else {
      setAIStatus(`连接失败：${error.message}`, "error");
    }
  } finally {
    ui.aiTest.disabled = false;
    ui.aiSave.disabled = false;
  }
}

/* ---------- 焦点陷阱 / 事件 -------------------------------------------- */
function focusable(root) {
  return Array.from(root.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((node) => node.offsetParent !== null);
}

function trapLayerKeys(event, root, close) {
  if (event.key === "Escape") {
    event.preventDefault();
    close();
    return;
  }
  if (event.key !== "Tab") return;
  const nodes = focusable(root);
  if (!nodes.length) return;
  const first = nodes[0];
  const last = nodes[nodes.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function bindEvents() {
  ui.burger.addEventListener("click", () => {
    const open = !ui.header.classList.contains("is-nav-open");
    ui.header.classList.toggle("is-nav-open", open);
    ui.burger.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("hp-nav-locked", open);
  });

  ui.nav.addEventListener("click", (event) => {
    const link = event.target.closest("[data-step]");
    if (!link) return;
    goToStep(Number(link.dataset.step));
  });

  document.addEventListener("click", (event) => {
    if (!ui.header.classList.contains("is-nav-open")) return;
    if (!ui.header.contains(event.target)) closeMobileNav();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!ui.header.classList.contains("is-nav-open")) return;
    closeMobileNav();
    ui.burger.focus({ preventScroll: true });
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 940) closeMobileNav();
  });

  ui.provinceGroups.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-meta-retry]");
    if (retry) {
      loadMeta();
      return;
    }
    const button = event.target.closest("[data-province]");
    if (button) selectProvince(button.dataset.province, { focusStart: true });
  });
  ui.provinceSearch.addEventListener("input", () => applyProvinceFilter(ui.provinceSearch.value.trim()));
  ui.start.addEventListener("click", async () => {
    if (!state.province) {
      toast("先选一个省份");
      return;
    }
    applyStep(2);
    await ensureQuiz();
    if (state.pendingQuizIndex !== null) {
      state.quizIndex = clamp(state.pendingQuizIndex, 0, Math.max(0, state.quiz.length - 1));
      state.pendingQuizIndex = null;
      renderQuestion();
      syncUrl();
    }
  });

  ui.quizRetry.addEventListener("click", () => {
    state.quizPromise = null;
    ensureQuiz();
  });
  ui.quizPrev.addEventListener("click", prevQuestion);
  ui.quizNext.addEventListener("click", nextQuestion);
  ui.question.addEventListener("change", onQuestionChange);
  document.addEventListener("keydown", onGlobalKey);

  ui.comboGrid.addEventListener("click", (event) => {
    const button = event.target.closest(".wz-disclose");
    if (!button) return;
    const detail = button.nextElementSibling;
    const open = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!open));
    if (detail) detail.hidden = open;
  });
  ui.comboMore.addEventListener("click", moreCombos);
  ui.toMajors.addEventListener("click", () => goToStep(4));

  ui.majorEligible.addEventListener("change", renderMajors);
  ui.majorGrid.addEventListener("click", (event) => {
    const button = event.target.closest("[data-college-major]");
    if (!button) return;
    openDrawer(button.dataset.collegeMajor, button);
  });

  ui.drawerClose.addEventListener("click", () => closeDrawer());
  ui.drawer.querySelectorAll("[data-drawer-close]").forEach((node) => {
    node.addEventListener("click", () => closeDrawer());
  });
  ui.drawer.addEventListener("keydown", (event) => trapLayerKeys(event, ui.drawer, () => closeDrawer()));
  ui.drawerProvince.addEventListener("change", () => {
    state.drawer.province = ui.drawerProvince.value;
    state.drawer.track = defaultTrack(state.drawer.province, state.report?.combos?.[0]);
    fillDrawerTracks();
    updateDrawerSub();
    loadColleges();
  });
  ui.drawerTrack.addEventListener("change", () => {
    state.drawer.track = ui.drawerTrack.value;
    updateDrawerSub();
    loadColleges();
  });
  ui.drawerBody.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-drawer-retry]");
    if (retry) loadColleges();
  });

  ui.interestSelect.addEventListener("change", () => {
    state.interestMajor = ui.interestSelect.value;
    writeSession(SKEY.interest, state.interestMajor);
    state.aiResult = null;
    updateInterestDetail();
    renderRetest();
    renderAIInsight();
    loadMooc(state.interestMajor);
  });
  ui.moocList.addEventListener("click", (event) => {
    if (event.target.closest("[data-mooc-login]")) {
      openLogin({ onSuccess: () => loadMooc(state.interestMajor) });
      return;
    }
    if (event.target.closest("[data-mooc-retry]")) loadMooc(state.interestMajor);
  });
  ui.aiGenerate.addEventListener("click", generateAIInsight);
  ui.retestList.addEventListener("change", onRetestChange);
  ui.verdict.addEventListener("click", (event) => {
    if (event.target.closest("[data-back-majors]")) goToStep(4);
  });

  ui.aiOpen.addEventListener("click", () => openAIModal());
  ui.aiClose.addEventListener("click", () => closeAIModal());
  ui.aiModal.querySelectorAll("[data-ai-close]").forEach((node) => {
    node.addEventListener("click", () => closeAIModal());
  });
  ui.aiModal.addEventListener("keydown", (event) => trapLayerKeys(event, ui.aiModal, () => closeAIModal()));
  ui.aiProvider.addEventListener("change", () => {
    const provider = currentProvider();
    ui.aiModel.value = provider?.default_model || provider?.models?.[0] || "";
    updateProviderHint();
    setAIStatus("");
  });
  ui.aiSave.addEventListener("click", saveAIConfig);
  ui.aiTest.addEventListener("click", runPing);
  ui.aiClear.addEventListener("click", clearAIConfig);
}

function onGlobalKey(event) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
  if (!ui.aiModal.hidden || state.drawer.open) return;
  if (state.step !== 2 || !state.quizReady) return;
  const target = event.target;
  if (target instanceof Element && target.matches("input:not([type=radio]):not([type=checkbox]), textarea, select, [contenteditable=true]")) {
    return;
  }
  if (!/^[1-5]$/.test(event.key)) return;
  const question = currentQuiz();
  if (!question) return;
  const count = question.kind === "scale" ? 5 : question.options.length;
  const index = Number(event.key) - 1;
  if (index < 0 || index >= count) return;
  const input = ui.question.querySelectorAll('input[type="radio"]')[index];
  if (!input) return;
  event.preventDefault();
  input.checked = true;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch((error) => {
    // 初始化失败也要给人一条出路，不能只剩空白
    toast(`向导初始化失败：${error.message}`);
    const main = byId("wz-main");
    if (main) {
      main.insertAdjacentHTML("afterbegin", `<div class="wz-empty"><h2>页面加载失败</h2><p>${escapeHtml(error.message)}</p><p><a class="hp-btn hp-btn--primary" href="./wizard.html">重新打开</a></p></div>`);
    }
  });
});
