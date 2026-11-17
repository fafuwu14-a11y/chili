// AI 顾问 · 引导式对话
// 和 major-advisor 的区别：那边是学生问、AI 答；这边是 AI 问、学生答。
// 页面进来自动开场，一次只问一个问题，六到八轮收敛出方向。

import { mountLoginButton, openLoginModal } from "./login-modal.js";

const AI_KEY = "chili.ai.config";
const REPORT_KEY = "chili.wizard.report.v1";
const MAX_TURN = 8;

const state = {
  turn: 0,
  history: [],
  done: false,
  busy: false,
  profile: null,
  province: "",
  ai: null,
};

const el = (id) => document.getElementById(id);
const stream = el("ac-stream");
const form = el("ac-form");
const input = el("ac-input");
const sendBtn = el("ac-send");
const statusNode = el("ac-status");
const bar = el("ac-progress-bar");

function readJSON(storage, key) {
  try {
    const raw = storage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readAI() {
  const saved = readJSON(localStorage, AI_KEY);
  if (!saved || !saved.provider) return null;
  if (!saved.key && saved.provider !== "local") return null;
  return {
    provider: saved.provider,
    model: saved.model || "",
    base_url: saved.base_url || "",
    key: saved.key || "",
  };
}

function readProfile() {
  const saved = readJSON(sessionStorage, REPORT_KEY) || readJSON(localStorage, REPORT_KEY);
  const report = saved && saved.report ? saved.report : saved;
  if (!report || !report.profile) return { profile: null, province: "" };
  return { profile: report.profile, province: saved.province || report.province || "" };
}

// ---------------------------------------------------------------- 渲染

function scrollBottom() {
  requestAnimationFrame(() => {
    stream.scrollTop = stream.scrollHeight;
  });
}

function addMe(text) {
  const node = document.createElement("div");
  node.className = "ac-msg ac-msg--me";
  node.textContent = text;
  stream.appendChild(node);
  scrollBottom();
}

function addAI(reply) {
  const wrap = document.createElement("div");
  wrap.className = "ac-msg ac-msg--ai";

  if (reply.say) {
    const say = document.createElement("div");
    say.className = "ac-say";
    say.textContent = reply.say;
    wrap.appendChild(say);
  }

  if (reply.ask) {
    const ask = document.createElement("div");
    ask.className = "ac-ask";
    ask.textContent = reply.ask;
    wrap.appendChild(ask);
  }

  const options = Array.isArray(reply.options) ? reply.options.filter(Boolean).slice(0, 4) : [];
  if (options.length && !reply.done) {
    const box = document.createElement("div");
    box.className = "ac-options";
    options.forEach((text) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ac-option";
      btn.textContent = text;
      btn.addEventListener("click", () => {
        if (state.busy || state.done) return;
        pickOption(box, btn, text);
        request(text);
      });
      box.appendChild(btn);
    });
    wrap.appendChild(box);
  }

  stream.appendChild(wrap);
  scrollBottom();
}

function pickOption(box, btn, text) {
  box.classList.add("is-spent");
  btn.classList.add("is-picked");
  box.querySelectorAll("button").forEach((node) => {
    node.disabled = true;
  });
}

function addTyping() {
  const node = document.createElement("div");
  node.className = "ac-typing";
  node.id = "ac-typing";
  node.innerHTML = "<span></span><span></span><span></span>";
  stream.appendChild(node);
  scrollBottom();
  return node;
}

function removeTyping() {
  const node = el("ac-typing");
  if (node) node.remove();
}

function addError(message, actions) {
  const node = document.createElement("div");
  node.className = "ac-error";
  node.append(document.createTextNode(message));
  (actions || []).forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = item.label;
    btn.addEventListener("click", item.onClick);
    node.appendChild(btn);
  });
  stream.appendChild(node);
  scrollBottom();
}

function setStatus(text) {
  statusNode.textContent = text;
}

function setStage(stage) {
  const order = ["interest", "ability", "value", "reality", "close"];
  const now = order.indexOf(stage);
  document.querySelectorAll("#ac-stages li").forEach((node) => {
    const index = order.indexOf(node.dataset.stage);
    node.classList.toggle("is-done", now >= 0 && index < now);
    node.classList.toggle("is-now", index === now);
  });
}

function setProgress(turn, done) {
  const ratio = done ? 1 : Math.min(1, turn / 6);
  bar.style.width = `${Math.round(ratio * 100)}%`;
}

function setBusy(busy) {
  state.busy = busy;
  sendBtn.disabled = busy || state.done;
  input.disabled = state.done;
  setStatus(
    state.done ? "已经聊完，可以看结论" : busy ? "正在想下一个问题" : `第 ${state.turn + 1} 轮 / 最多 ${MAX_TURN} 轮`,
  );
}

// ---------------------------------------------------------------- 会话

function applyReply(reply) {
  addAI(reply);
  state.turn = Number(reply.turn || 0) + 1;
  setProgress(state.turn, reply.done);
  setStage(reply.stage);
  if (reply.done) {
    state.done = true;
    if (reply.suggestion) addSummary(reply.suggestion);
  }
  setBusy(false);
  if (state.done) {
    input.placeholder = "聊完了。想重新开始就点上面的「重新聊一次」。";
  }
}

function addSummary(suggestion) {
  const directions = Array.isArray(suggestion.directions) ? suggestion.directions : [];
  const card = document.createElement("div");
  card.className = "ac-summary";

  const title = document.createElement("h3");
  title.textContent = "聊到这儿，先说三个方向";
  card.appendChild(title);

  if (directions.length) {
    const list = document.createElement("ol");
    directions.forEach((item) => {
      const li = document.createElement("li");
      const strong = document.createElement("b");
      strong.textContent = item;
      li.appendChild(strong);
      list.appendChild(li);
    });
    card.appendChild(list);
  }

  if (suggestion.why) {
    const why = document.createElement("p");
    why.textContent = suggestion.why;
    why.style.margin = "0 0 14px";
    why.style.fontSize = "14px";
    why.style.lineHeight = "1.75";
    why.style.color = "var(--ink-2, #6b5c5d)";
    card.appendChild(why);
  }

  const actions = document.createElement("div");
  actions.className = "ac-summary-actions";

  const toMajor = document.createElement("a");
  toMajor.className = "hp-btn hp-btn--primary hp-btn--sm";
  toMajor.href = "./major.html";
  toMajor.textContent = "去专业库看看";
  actions.appendChild(toMajor);

  const again = document.createElement("button");
  again.type = "button";
  again.className = "hp-btn hp-btn--ghost hp-btn--sm";
  again.textContent = "重新聊一次";
  again.addEventListener("click", () => window.location.reload());
  actions.appendChild(again);

  card.appendChild(actions);
  stream.appendChild(card);
  scrollBottom();
}

async function request(answer) {
  if (state.busy) return;

  if (answer) {
    addMe(answer);
    state.history.push({ role: "user", content: answer });
  }

  setBusy(true);
  addTyping();

  try {
    const response = await fetch("/api/ai/coach", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ai: state.ai,
        history: state.history.slice(-8),
        profile: state.profile,
        province: state.province,
        turn: state.turn,
        timeout: 90,
      }),
    });

    const payload = await response.json().catch(() => ({}));
    removeTyping();

    if (!response.ok || payload.ok === false) {
      handleError(response.status, payload);
      setBusy(false);
      return;
    }

    const reply = payload.data || {};
    if (reply.say || reply.ask) {
      state.history.push({
        role: "assistant",
        content: [reply.say, reply.ask].filter(Boolean).join(" "),
      });
    }
    applyReply(reply);
  } catch (error) {
    removeTyping();
    addError("网络没接上，检查一下服务是不是停了。", [
      { label: "重试", onClick: () => request("") },
    ]);
    setBusy(false);
  }
}

function handleError(status, payload) {
  const code = payload.code || "";

  if (status === 401 && code === "login_required") {
    addError("这个功能要登录才能用（防止别人刷你的 Key）。", [
      {
        label: "现在登录",
        onClick: () => openLoginModal({ onSuccess: () => window.location.reload() }),
      },
    ]);
    return;
  }

  if (code === "ai_unauthorized" || code === "ai_forbidden") {
    addError("Key 被拒了，可能填错或者已经停用。", [
      { label: "去 AI 设置", onClick: () => (window.location.href = "./ai-setup.html") },
    ]);
    return;
  }

  if (code === "ai_rate_limited") {
    addError("调用太频繁，等十几秒再点下面重试。", [
      { label: "重试", onClick: () => request("") },
    ]);
    return;
  }

  if (code === "ai_timeout" || code === "ai_unreachable") {
    addError("模型那边没回应。换个模型或过会儿再试。", [
      { label: "重试", onClick: () => request("") },
      { label: "去 AI 设置", onClick: () => (window.location.href = "./ai-setup.html") },
    ]);
    return;
  }

  addError(payload.error || "这次没聊成，再试一次。", [
    { label: "重试", onClick: () => request("") },
  ]);
}

// ---------------------------------------------------------------- 启动

function renderProfile(profile) {
  const card = el("ac-profile-card");
  const box = el("ac-profile");
  if (!profile || !card || !box) return;

  const rows = [];
  const top = Array.isArray(profile.top_subjects)
    ? profile.top_subjects.slice(0, 2).map((item) => (Array.isArray(item) ? item[0] : item))
    : [];

  if (top.length) rows.push(["擅长", top.join(" / ")]);
  if (profile.riasec_summary && profile.riasec_summary.title) {
    rows.push(["兴趣类型", profile.riasec_summary.title]);
  }
  if (profile.tendency && profile.tendency.label) rows.push(["倾向", profile.tendency.label]);

  if (!rows.length) return;

  box.textContent = "";
  rows.forEach(([key, value]) => {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    row.append(dt, dd);
    box.appendChild(row);
  });
  card.hidden = false;
}

function showSetupHint() {
  const card = el("ac-setup-card");
  if (card) card.hidden = false;

  const wrap = document.createElement("div");
  wrap.className = "ac-msg ac-msg--ai";
  const say = document.createElement("div");
  say.className = "ac-say";
  say.textContent =
    "我还没接上模型，现在说不了话。去「AI 设置」选一家、填个 Key（DeepSeek 最省事，充 10 块够聊很久），回来就能开始了。";
  wrap.appendChild(say);

  const box = document.createElement("div");
  box.className = "ac-options";
  const btn = document.createElement("a");
  btn.className = "hp-btn hp-btn--primary hp-btn--sm";
  btn.href = "./ai-setup.html";
  btn.textContent = "去 AI 设置";
  box.appendChild(btn);
  wrap.appendChild(box);

  stream.appendChild(wrap);
  setStatus("等一个 Key");
  input.disabled = true;
  sendBtn.disabled = true;
}

function bindInput() {
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(140, input.scrollHeight)}px`;
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (state.busy || state.done) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.style.height = "auto";
    request(text);
  });
}

function bindBurger() {
  const burger = el("ac-burger");
  const nav = el("ac-nav");
  if (!burger || !nav) return;
  burger.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    burger.setAttribute("aria-expanded", open ? "true" : "false");
  });
}

function init() {
  mountLoginButton({ slot: document.querySelector("[data-login-slot]") });
  bindBurger();
  bindInput();
  setStage("interest");
  setProgress(0, false);

  const saved = readProfile();
  state.profile = saved.profile;
  state.province = saved.province;
  renderProfile(saved.profile);

  state.ai = readAI();
  if (!state.ai) {
    showSetupHint();
    return;
  }

  // 从专业库「问 AI：我适合吗」跳过来时，带着专业名开场
  const focus = new URLSearchParams(window.location.search).get("major");
  if (focus) {
    const seed = `我在看【${focus}】这个专业，想聊聊适不适合我。`;
    addMe(seed);
    state.history.push({ role: "user", content: seed });
  }

  setStatus("正在准备第一个问题");
  request("");
}

init();
