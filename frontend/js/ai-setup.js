/**
 * 接入 AI · 配置页
 *
 * 只做三件事：把 13 家厂商摆出来、把用户填的配置存进浏览器、用 /api/ai/ping 验一次。
 * 配置结构同时给 wizard.html 复用：
 *   { provider, model, base_url, key }
 */

const STORAGE_KEY = "chili.ai.config";

/** 后端 /api/ai/providers 拉不到时的兜底，保证页面不会空白。 */
const FALLBACK = [
  { id: "deepseek", name: "DeepSeek（深度求索）", base_url: "https://api.deepseek.com/v1", default_model: "deepseek-chat", signup: "https://platform.deepseek.com/sign_up" },
  { id: "qwen", name: "通义千问（阿里云百炼）", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", default_model: "qwen-plus", signup: "https://bailian.console.aliyun.com/" },
  { id: "doubao", name: "豆包（火山方舟）", base_url: "https://ark.cn-beijing.volces.com/api/v3", default_model: "doubao-1-5-pro-32k-250115", signup: "https://console.volcengine.com/ark" },
  { id: "kimi", name: "Kimi（月之暗面）", base_url: "https://api.moonshot.cn/v1", default_model: "kimi-k2-0905-preview", signup: "https://platform.moonshot.cn/" },
  { id: "zhipu", name: "智谱 GLM", base_url: "https://open.bigmodel.cn/api/paas/v4", default_model: "glm-4-plus", signup: "https://open.bigmodel.cn/" },
  { id: "ernie", name: "文心一言（百度千帆）", base_url: "https://qianfan.baidubce.com/v2", default_model: "ernie-4.5-turbo-128k", signup: "https://console.bce.baidu.com/qianfan/" },
  { id: "spark", name: "讯飞星火", base_url: "https://spark-api-open.xf-yun.com/v1", default_model: "generalv3.5", signup: "https://console.xfyun.cn/" },
  { id: "hunyuan", name: "腾讯混元", base_url: "https://api.hunyuan.cloud.tencent.com/v1", default_model: "hunyuan-turbos-latest", signup: "https://console.cloud.tencent.com/hunyuan" },
  { id: "minimax", name: "MiniMax", base_url: "https://api.minimax.chat/v1", default_model: "MiniMax-Text-01", signup: "https://platform.minimaxi.com/" },
  { id: "stepfun", name: "阶跃星辰 StepFun", base_url: "https://api.stepfun.com/v1", default_model: "step-2-16k", signup: "https://platform.stepfun.com/" },
  { id: "siliconflow", name: "硅基流动 SiliconFlow", base_url: "https://api.siliconflow.cn/v1", default_model: "Qwen/Qwen2.5-7B-Instruct", signup: "https://cloud.siliconflow.cn/" },
  { id: "openrouter", name: "OpenRouter（聚合）", base_url: "https://openrouter.ai/api/v1", default_model: "deepseek/deepseek-chat", signup: "https://openrouter.ai/keys" },
  { id: "local", name: "本地 Ollama", base_url: "http://127.0.0.1:11434/v1", default_model: "qwen2.5:7b", signup: "https://ollama.com/download" },
];

const $ = (id) => document.getElementById(id);

const el = {
  vendors: $("ai-vendors"),
  select: $("ai-provider"),
  key: $("ai-key"),
  eye: $("ai-eye"),
  model: $("ai-model"),
  modelHint: $("ai-model-hint"),
  base: $("ai-base"),
  keyHint: $("ai-key-hint"),
  form: $("ai-form"),
  save: $("ai-save"),
  test: $("ai-test"),
  clear: $("ai-clear"),
  status: $("ai-status"),
  statusText: document.querySelector(".ai-status-text"),
  result: $("ai-result"),
};

let providers = FALLBACK.slice();
let current = loadConfig();

/* ------------------------------------------------------------------ 存储 */

function loadConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { provider: "deepseek", model: "", base_url: "", key: "" };
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") throw new Error("bad config");
    return {
      provider: String(parsed.provider || "deepseek"),
      model: String(parsed.model || ""),
      base_url: String(parsed.base_url || parsed.baseUrl || ""),
      key: String(parsed.key || parsed.api_key || ""),
    };
  } catch {
    return { provider: "deepseek", model: "", base_url: "", key: "" };
  }
}

function persist(config) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

function providerOf(id) {
  return providers.find((item) => item.id === id) || providers[0] || FALLBACK[0];
}

/* ------------------------------------------------------------------ 渲染 */

function renderSelect() {
  el.select.innerHTML = "";
  for (const provider of providers) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.name;
    el.select.append(option);
  }
}

function renderVendors() {
  el.vendors.innerHTML = "";
  for (const provider of providers) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "ai-vendor";
    card.dataset.provider = provider.id;
    card.setAttribute("role", "option");
    card.setAttribute("aria-selected", String(provider.id === current.provider));

    const model = provider.default_model || (provider.models && provider.models[0]) || "";
    const free = provider.free ? '<span class="ai-vendor-tag">有免费额度</span>' : "";
    const local = provider.id === "local" ? '<span class="ai-vendor-tag">免 Key</span>' : "";

    card.innerHTML =
      `<span class="ai-vendor-name">${escapeHtml(shortName(provider.name))}${free}${local}</span>` +
      `<span class="ai-vendor-model">${escapeHtml(model || provider.base_url)}</span>`;

    card.addEventListener("click", () => choose(provider.id));
    el.vendors.append(card);
  }
  markActive();
}

function shortName(name) {
  return String(name || "").replace(/（.*?）/g, "").replace(/\(.*?\)/g, "").trim() || "未命名";
}

function markActive() {
  for (const card of el.vendors.querySelectorAll(".ai-vendor")) {
    const active = card.dataset.provider === current.provider;
    card.classList.toggle("is-active", active);
    card.setAttribute("aria-selected", String(active));
  }
  el.select.value = current.provider;
}

function fillForm({ keepKey = false } = {}) {
  const provider = providerOf(current.provider);
  el.base.value = current.base_url || provider.base_url || "";
  el.model.value = current.model || provider.default_model || "";
  el.modelHint.textContent = provider.default_model
    ? `默认 ${provider.default_model}${provider.models && provider.models.length > 1 ? "，可选：" + provider.models.slice(0, 4).join(" / ") : ""}`
    : "";
  el.keyHint.textContent = provider.id === "local"
    ? "本地 Ollama 不需要 Key，留空即可（先 ollama serve）。"
    : "Key 只保存到这台电脑的浏览器，不上传服务器。";
  if (!keepKey) el.key.value = current.key || "";
  refreshStatus();
  markActive();
}

function refreshStatus() {
  const provider = providerOf(current.provider);
  const ready = provider.id === "local" || Boolean(current.key);
  el.status.classList.toggle("is-ok", ready && Boolean(current.key || provider.id === "local"));
  el.status.classList.remove("is-bad");
  el.statusText.textContent = ready
    ? `已配置：${shortName(provider.name)} · ${current.model || provider.default_model || "默认模型"}`
    : "尚未配置 Key，AI 增强功能将不可用";
  if (provider.id === "local" && !current.key) {
    el.statusText.textContent = `本地模式：${current.model || provider.default_model || "默认模型"} · 无需 Key`;
  }
}

/* ------------------------------------------------------------------ 交互 */

function choose(id) {
  if (id === current.provider) return;
  current.provider = id;
  current.base_url = "";
  current.model = "";
  // 换厂商时旧 Key 一定不对，清空但保留在输入框里方便用户看见自己被清了
  current.key = "";
  persist(current);
  fillForm();
  setResult("已切换厂商，记得重新填 Key 再测试。", "");
}

function collect() {
  return {
    provider: el.select.value || current.provider,
    key: el.key.value.trim(),
    model: el.model.value.trim(),
    base_url: el.base.value.trim(),
  };
}

function setResult(text, tone) {
  el.result.textContent = text || "";
  el.result.classList.toggle("is-ok", tone === "ok");
  el.result.classList.toggle("is-bad", tone === "bad");
}

function setBusy(busy, label) {
  el.test.disabled = busy;
  el.test.textContent = busy ? "测试中…" : "测试连接";
  if (label) el.test.textContent = busy ? label : "测试连接";
}

async function testConnection() {
  const config = collect();
  if (!config.key && config.provider !== "local") {
    setResult("先填 API Key，本地 Ollama 才允许留空。", "bad");
    el.key.focus();
    return;
  }
  if (!config.model && !providerOf(config.provider).default_model) {
    setResult("请填模型名。", "bad");
    el.model.focus();
    return;
  }

  setBusy(true);
  setResult("正在发一句话给模型，通常 1–5 秒…", "");
  try {
    const response = await fetch("/api/ai/ping", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ai: {
          provider: config.provider,
          key: config.key,
          model: config.model,
          base_url: config.base_url,
        },
        timeout: 30,
      }),
    });
    const payload = await response.json().catch(() => ({}));

    if (response.status === 401) {
      setResult("测试连接需要先登录。点右上角「登录 / 注册」，用演示账号也行。", "bad");
      return;
    }
    if (!response.ok || payload.ok === false) {
      const code = payload.code || "";
      setResult(humanError(code, payload.error, response.status), "bad");
      return;
    }

    const data = payload.data || {};
    setResult(
      `连接正常 · ${data.provider_name || shortName(config.provider)} · ${data.model || config.model} · ${data.latency_ms || "?"} ms · 模型回了「${data.reply || "收到"}」`,
      "ok"
    );
  } catch {
    setResult("连不上本地服务。确认 python run.py 还开着。", "bad");
  } finally {
    setBusy(false);
  }
}

function humanError(code, message, status) {
  const table = {
    ai_unauthorized: "Key 不对或已失效（401）。重新复制一次，注意别带空格。",
    ai_forbidden: "这个 Key 没有该模型的权限（403）。换默认模型，或去控制台开通。",
    ai_not_found: "模型名或接口地址不存在（404）。检查模型名，豆包要填推理接入点 ep-xxxx。",
    ai_rate_limited: "请求太频繁或额度用完了（429）。等一分钟，或去控制台看余额。",
    ai_bad_request: "请求参数被厂商拒绝（400）。多半是模型名不对。",
    ai_upstream: "厂商服务端出错（5xx）。过一会儿再试。",
    ai_timeout: "请求超时。检查网络，或换个模型。",
    ai_unreachable: "连不上厂商地址。检查 base_url，或用本地 Ollama。",
    ai_bad_response: "厂商返回了看不懂的内容，多半是接口地址填错。",
    provider_unknown: "没找到这个厂商。刷新页面重选。",
  };
  return table[code] || message || `请求失败（${status}）`;
}

function save() {
  const config = collect();
  if (!config.key && config.provider !== "local") {
    setResult("Key 是空的，保存后 AI 功能仍然用不了。还是先填上吧。", "bad");
    el.key.focus();
    return;
  }
  current = config;
  persist(current);
  refreshStatus();
  markActive();
  setResult("已保存到这台电脑的浏览器。选科测评里会直接生效。", "ok");
}

function clearConfig() {
  localStorage.removeItem(STORAGE_KEY);
  current = { provider: "deepseek", model: "", base_url: "", key: "" };
  el.key.value = "";
  fillForm();
  setResult("配置已清除。规则引擎照常可用，AI 增强关闭。", "");
}

/* ------------------------------------------------------------------ 启动 */

async function loadProviders() {
  try {
    const response = await fetch("/api/ai/providers", { credentials: "same-origin" });
    const payload = await response.json();
    const list = payload && payload.ok !== false ? payload.data.providers : null;
    if (Array.isArray(list) && list.length) providers = list;
  } catch {
    /* 后端没起来就用兜底，页面照样能填 */
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function bind() {
  el.form.addEventListener("submit", (event) => {
    event.preventDefault();
    save();
  });
  el.test.addEventListener("click", testConnection);
  el.clear.addEventListener("click", clearConfig);
  el.select.addEventListener("change", () => choose(el.select.value));

  el.eye.addEventListener("click", () => {
    const shown = el.key.type === "text";
    el.key.type = shown ? "password" : "text";
    el.eye.textContent = shown ? "显示" : "隐藏";
    el.eye.setAttribute("aria-pressed", String(!shown));
    el.eye.setAttribute("aria-label", shown ? "显示 Key" : "隐藏 Key");
  });

  // 厂商卡支持上下键切换，键盘用户不用去拉下拉
  el.vendors.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const cards = [...el.vendors.querySelectorAll(".ai-vendor")];
    const index = cards.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    const next = cards[(index + (event.key === "ArrowDown" ? 1 : -1) + cards.length) % cards.length];
    next.focus();
    choose(next.dataset.provider);
  });
}

async function boot() {
  bind();
  bindShell();
  await loadProviders();
  renderSelect();
  renderVendors();
  fillForm();
  if (current.key) setResult("检测到本机已有配置，可以直接测试连接。", "");
}

/** 顶栏：汉堡菜单 + 右上角登录区（复用门户的弹窗）。 */
function bindShell() {
  const burger = $("hp-burger");
  const nav = $("hp-nav");
  if (burger && nav) {
    const toggle = (open) => {
      const next = open ?? !nav.classList.contains("is-open");
      nav.classList.toggle("is-open", next);
      burger.setAttribute("aria-expanded", String(next));
      burger.setAttribute("aria-label", next ? "关闭菜单" : "打开菜单");
    };
    burger.addEventListener("click", () => toggle());
    nav.addEventListener("click", (event) => {
      if (event.target.closest("a")) toggle(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") toggle(false);
    });
  }

  const slot = document.querySelector("[data-login-slot]");
  if (!slot) return;
  import("./login-modal.js")
    .then(({ mountLoginButton }) => mountLoginButton({ slot }))
    .catch(() => {
      slot.innerHTML = '<a class="hp-btn hp-btn--ghost hp-btn--sm" href="./login.html">登录 / 注册</a>';
    });
}

boot();

