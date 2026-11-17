/**
 * 登录 / 注册弹窗：在门户首页原地登录，不跳转页面。
 *
 * 用法：
 *   import { mountLoginButton, openLoginModal } from "./login-modal.js";
 *   mountLoginButton();                          // 接管顶栏 [data-login-slot]
 *   openLoginModal({ onSuccess(user) { ... } });  // 手动打开
 *
 * 依赖：api.js 的 api.me / api.login / api.register / api.logout
 * （它们内部就是 POST /api/auth/login|register，JSON body）。
 * 样式在 css/portal.css，类名前缀 lm-。
 */

import { api } from "./api.js";

const DEMO_EMAIL = "demo@chili.dev";
const DEMO_PASSWORD = "chili2026";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PASSWORD_MIN = 8;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const EYE_ON = `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="12" r="2.5" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>`;
const EYE_OFF = `<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 4l16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M9.9 5.9A9.6 9.6 0 0 1 12 5.8c6 0 9.5 6.2 9.5 6.2a17 17 0 0 1-3.1 3.9M6.4 7.6A17.3 17.3 0 0 0 2.5 12S6 18.2 12 18.2c1.3 0 2.5-.2 3.6-.7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

const DIALOG_HTML = `
  <div class="lm-dialog">
    <button class="lm-close" type="button" aria-label="关闭登录窗口" data-close>
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </button>

    <header class="lm-head">
      <p class="lm-eyebrow"><i aria-hidden="true"></i>赤鲤账号</p>
      <h2 class="lm-title" id="lm-title">登录赤鲤</h2>
      <p class="lm-sub" id="lm-sub">登录后测评进度跟着账号走；不登录也能先测，答案留在你自己的浏览器里。</p>
    </header>

    <div class="lm-tabs" role="tablist" aria-label="登录或注册">
      <button class="lm-tab is-active" type="button" role="tab" id="lm-tab-login" aria-selected="true" aria-controls="lm-form">登录</button>
      <button class="lm-tab" type="button" role="tab" id="lm-tab-register" aria-selected="false" aria-controls="lm-form" tabindex="-1">注册</button>
    </div>

    <form class="lm-form" id="lm-form" role="tabpanel" aria-labelledby="lm-tab-login" novalidate>
      <div class="lm-field">
        <label for="lm-email">邮箱</label>
        <input id="lm-email" name="email" type="email" inputmode="email" autocomplete="email"
               placeholder="name@example.com" required aria-describedby="lm-email-err" />
        <p class="lm-error" id="lm-email-err" hidden></p>
      </div>

      <div class="lm-field">
        <label for="lm-password">密码</label>
        <div class="lm-pw">
          <input id="lm-password" name="password" type="password" autocomplete="current-password"
                 placeholder="至少 8 位" required aria-describedby="lm-password-err" />
          <button class="lm-pw-toggle" type="button" aria-label="显示密码" aria-pressed="false" data-pw-toggle>
            <span data-eye-on>${EYE_ON}</span>
            <span data-eye-off hidden>${EYE_OFF}</span>
          </button>
        </div>
        <p class="lm-error" id="lm-password-err" hidden></p>
      </div>

      <div class="lm-field" id="lm-confirm-field" hidden>
        <label for="lm-confirm">确认密码</label>
        <div class="lm-pw">
          <input id="lm-confirm" name="confirm" type="password" autocomplete="new-password"
                 placeholder="再输一次" aria-describedby="lm-confirm-err" />
          <button class="lm-pw-toggle" type="button" aria-label="显示密码" aria-pressed="false" data-pw-toggle>
            <span data-eye-on>${EYE_ON}</span>
            <span data-eye-off hidden>${EYE_OFF}</span>
          </button>
        </div>
        <p class="lm-error" id="lm-confirm-err" hidden></p>
      </div>

      <p class="lm-form-error" id="lm-form-error" role="alert" hidden></p>

      <button class="lm-submit" type="submit" data-submit>
        <span class="lm-spinner" aria-hidden="true"></span>
        <span data-submit-label>登录</span>
      </button>
    </form>

    <div class="lm-demo">
      <p>演示账号：<code>${DEMO_EMAIL}</code> / <code>${DEMO_PASSWORD}</code></p>
      <button class="lm-demo-fill" type="button" data-demo-fill>一键填入</button>
    </div>

    <p class="lm-legal">继续即表示你同意 <a href="./terms.html">用户协议</a> 与 <a href="./privacy.html">隐私政策</a>。</p>
  </div>
`;

/** 当前打开的弹窗（单例），再次打开会先关掉旧的。 */
let current = null;

/** 把后端 / 网络错误翻成人话。 */
function friendlyError(error) {
  const status = Number(error && error.status) || 0;
  const code = String((error && error.code) || "");
  if (status === 429 || code === "too_many_attempts" || code === "rate_limited") {
    return "尝试次数过多，请 10 分钟后再试";
  }
  if (status === 401 || code === "bad_credentials") return "邮箱或密码不对";
  if (code === "email_taken") return "这个邮箱已经注册过了，直接登录吧";
  if (code === "email_invalid") return "邮箱格式看起来不对";
  if (code === "password_weak" || code === "password_invalid") return "密码至少 8 位，建议字母和数字都用上";
  if (code === "login_required") return "登录状态过期了，请重新登录";
  if (status === 0) return (error && error.message) || "连不上本地服务，请确认后端已经启动";
  return (error && error.message) || "出了点问题，请稍后再试";
}

function focusableItems(root) {
  return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
    (node) => !node.hasAttribute("hidden") && node.offsetParent !== null
  );
}

/* 引用计数：连开两次时，先关掉的那个不能把后开的锁解了 */
let lockCount = 0;

function lockScroll() {
  lockCount += 1;
  if (lockCount > 1) return;
  const gap = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
  document.body.classList.add("lm-scroll-lock");
  if (gap > 0) document.body.style.setProperty("--lm-gutter", `${gap}px`);
}

function unlockScroll() {
  lockCount = Math.max(0, lockCount - 1);
  if (lockCount > 0) return;
  document.body.classList.remove("lm-scroll-lock");
  document.body.style.removeProperty("--lm-gutter");
}

/**
 * 打开登录弹窗。
 * @param {{ onSuccess?: (user: object|null) => void, initialMode?: "login"|"register" }} options
 * @returns {{ close: () => void }}
 */
export function openLoginModal(options = {}) {
  const { onSuccess = null, initialMode = "login" } = options;

  // 已经开着就换一个新的，避免重复 id；正在淡出的旧节点也一并清掉
  if (current) current.close({ restoreFocus: false });
  document.querySelectorAll(".lm-overlay").forEach((node) => node.remove());

  const lastFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const root = document.createElement("div");
  root.className = "lm-overlay";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-labelledby", "lm-title");
  root.setAttribute("aria-describedby", "lm-sub");
  root.innerHTML = DIALOG_HTML;
  lockScroll();
  document.body.appendChild(root);

  const $ = (selector) => root.querySelector(selector);
  const closeBtn = $("[data-close]");
  const form = $("#lm-form");
  const title = $("#lm-title");
  const sub = $("#lm-sub");
  const tabLogin = $("#lm-tab-login");
  const tabRegister = $("#lm-tab-register");
  const emailInput = $("#lm-email");
  const passwordInput = $("#lm-password");
  const confirmInput = $("#lm-confirm");
  const confirmField = $("#lm-confirm-field");
  const formError = $("#lm-form-error");
  const submitBtn = $("[data-submit]");
  const submitLabel = $("[data-submit-label]");

  const fields = {
    email: { input: emailInput, error: $("#lm-email-err") },
    password: { input: passwordInput, error: $("#lm-password-err") },
    confirm: { input: confirmInput, error: $("#lm-confirm-err") },
  };

  let mode = "login";
  let busy = false;
  let closed = false;

  function clearFieldError(name) {
    const field = fields[name];
    if (!field) return;
    field.error.textContent = "";
    field.error.hidden = true;
    field.input.removeAttribute("aria-invalid");
  }

  function clearErrors() {
    Object.keys(fields).forEach(clearFieldError);
    formError.textContent = "";
    formError.hidden = true;
  }

  function showFieldError(name, message) {
    const field = fields[name];
    if (!field) return;
    field.error.textContent = message;
    field.error.hidden = false;
    field.input.setAttribute("aria-invalid", "true");
    field.input.focus({ preventScroll: true });
  }

  function showFormError(message) {
    formError.textContent = message;
    formError.hidden = false;
  }

  function setBusy(next) {
    busy = next;
    submitBtn.disabled = next;
    submitBtn.classList.toggle("is-busy", next);
    submitBtn.setAttribute("aria-busy", String(next));
    form.setAttribute("aria-busy", String(next));
    // 请求期间不许切 tab，否则按钮文案和实际提交的模式会对不上
    tabLogin.disabled = next;
    tabRegister.disabled = next;
    submitLabel.textContent = next
      ? mode === "register"
        ? "正在注册…"
        : "正在登录…"
      : mode === "register"
        ? "注册并登录"
        : "登录";
  }

  function setMode(next, options = {}) {
    const { focus = true } = options;
    mode = next === "register" ? "register" : "login";
    const isRegister = mode === "register";

    tabLogin.classList.toggle("is-active", !isRegister);
    tabRegister.classList.toggle("is-active", isRegister);
    tabLogin.setAttribute("aria-selected", String(!isRegister));
    tabRegister.setAttribute("aria-selected", String(isRegister));
    tabLogin.tabIndex = isRegister ? -1 : 0;
    tabRegister.tabIndex = isRegister ? 0 : -1;
    form.setAttribute("aria-labelledby", isRegister ? "lm-tab-register" : "lm-tab-login");

    confirmField.hidden = !isRegister;
    passwordInput.setAttribute("autocomplete", isRegister ? "new-password" : "current-password");
    passwordInput.setAttribute("placeholder", isRegister ? "至少 8 位，建议字母加数字" : "至少 8 位");
    title.textContent = isRegister ? "注册赤鲤账号" : "登录赤鲤";
    sub.textContent = isRegister
      ? "一个邮箱就够了。注册后会自动登录，测评进度存在账号里。"
      : "登录后测评进度跟着账号走；不登录也能先测，答案留在你自己的浏览器里。";
    submitLabel.textContent = isRegister ? "注册并登录" : "登录";
    clearErrors();
    if (focus) emailInput.focus({ preventScroll: true });
  }

  function close(closeOptions = {}) {
    const { restoreFocus = true } = closeOptions;
    if (closed) return;
    closed = true;
    if (current && current.root === root) current = null;
    // 立刻摘掉键盘监听，避免淡出期间旧弹窗把 Esc 吃掉
    document.removeEventListener("keydown", onKeydown, true);

    const remove = () => {
      root.remove();
      unlockScroll();
      if (restoreFocus && lastFocus && lastFocus.isConnected) {
        lastFocus.focus({ preventScroll: true });
      }
    };
    root.classList.remove("is-in");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) remove();
    else window.setTimeout(remove, 210);
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusableItems(root);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (!root.contains(active)) {
      event.preventDefault();
      first.focus();
      return;
    }
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  root.addEventListener("click", (event) => {
    if (event.target === root) close();
  });
  closeBtn.addEventListener("click", () => close());

  [tabLogin, tabRegister].forEach((tab) => {
    tab.addEventListener("click", () => setMode(tab === tabRegister ? "register" : "login"));
    tab.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const nextIsRegister = !(tab === tabRegister);
      const nextTab = nextIsRegister ? tabRegister : tabLogin;
      setMode(nextIsRegister ? "register" : "login", { focus: false });
      nextTab.focus();
    });
  });

  Object.entries(fields).forEach(([name, field]) => {
    field.input.addEventListener("input", () => {
      clearFieldError(name);
      if (!formError.hidden) {
        formError.hidden = true;
        formError.textContent = "";
      }
    });
  });

  root.querySelectorAll("[data-pw-toggle]").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const input = toggle.parentElement.querySelector("input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.setAttribute("aria-pressed", String(show));
      toggle.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
      const eyeOn = toggle.querySelector("[data-eye-on]");
      const eyeOff = toggle.querySelector("[data-eye-off]");
      if (eyeOn) eyeOn.hidden = show;
      if (eyeOff) eyeOff.hidden = !show;
      input.focus({ preventScroll: true });
    });
  });

  $("[data-demo-fill]").addEventListener("click", () => {
    setMode("login", { focus: false });
    emailInput.value = DEMO_EMAIL;
    passwordInput.value = DEMO_PASSWORD;
    confirmInput.value = "";
    clearErrors();
    submitBtn.focus({ preventScroll: true });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    clearErrors();

    const values = {
      email: emailInput.value.trim(),
      password: passwordInput.value,
      confirm: confirmInput.value,
    };

    if (!values.email) return showFieldError("email", "请输入邮箱");
    if (!EMAIL_RE.test(values.email)) return showFieldError("email", "邮箱格式看起来不对，例如 name@example.com");
    if (!values.password) return showFieldError("password", "请输入密码");
    if (mode === "register") {
      if (values.password.length < PASSWORD_MIN) return showFieldError("password", `密码至少 ${PASSWORD_MIN} 位`);
      if (!values.confirm) return showFieldError("confirm", "请再输入一次密码");
      if (values.confirm !== values.password) return showFieldError("confirm", "两次输入的密码不一样");
    }

    const submittedMode = mode;
    setBusy(true);
    try {
      const payload =
        submittedMode === "register"
          ? await api.register(values.email, values.password)
          : await api.login(values.email, values.password);
      const user = (payload && payload.user) || null;
      const callback = typeof onSuccess === "function" ? onSuccess : null;

      if (closed) {
        // 请求还没回来用户就按 Esc 关了弹窗：登录其实已经成功，
        // 仍然把状态同步出去，别让顶栏停留在「登录 / 注册」。
        if (callback) callback(user);
        else document.dispatchEvent(new CustomEvent("chili:auth-change", { detail: { user, mode: submittedMode } }));
        return;
      }
      close({ restoreFocus: !callback });
      if (callback) {
        // mountLoginButton 的回调会通过 applyUser 再派发一次 chili:auth-change，这里不重复派发
        callback(user);
      } else {
        document.dispatchEvent(new CustomEvent("chili:auth-change", { detail: { user, mode: submittedMode } }));
      }
    } catch (error) {
      if (closed) return;
      if (error && error.code === "email_taken") {
        setMode("login", { focus: false });
        showFormError("这个邮箱已经注册过了，换到登录试试");
        passwordInput.focus({ preventScroll: true });
      } else {
        showFormError(friendlyError(error));
        if (error && (error.status === 401 || error.code === "bad_credentials")) {
          passwordInput.select();
        }
      }
    } finally {
      if (!closed) setBusy(false);
    }
  });

  setMode(initialMode, { focus: false });

  // 入场：下一帧再加 is-in，CSS 才能跑过渡
  window.requestAnimationFrame(() => {
    if (closed) return;
    root.classList.add("is-in");
    emailInput.focus({ preventScroll: true });
  });

  document.addEventListener("keydown", onKeydown, true);

  current = { root, close };
  return { close };
}

/** 预置的演示账号，供「一键填入」与文案共用。 */
export const demoAccount = Object.freeze({ email: DEMO_EMAIL, password: DEMO_PASSWORD });

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * 接管顶栏登录区：未登录显示「登录 / 注册」，登录后显示头像 + 邮箱菜单。
 * 退出登录只换回按钮，不跳转页面。
 *
 * @param {{ slot?: Element|null, onSuccess?: Function, onLogout?: Function }} options
 * @returns {{ refresh: () => Promise<object|null>, setUser: (user: object|null) => void, getUser: () => object|null }}
 */
export function mountLoginButton(options = {}) {
  const slot = options.slot || document.querySelector("[data-login-slot]");
  const noop = { refresh: async () => null, setUser: () => {}, getUser: () => null };
  if (!slot) return noop;

  let user = null;
  let unbindMenu = null;

  const emit = () => {
    document.dispatchEvent(new CustomEvent("chili:auth-change", { detail: { user } }));
  };

  function clearMenuBinding() {
    if (unbindMenu) {
      unbindMenu();
      unbindMenu = null;
    }
  }

  function renderLoginButton() {
    clearMenuBinding();
    slot.innerHTML = `
      <button class="lm-login-btn" type="button" aria-haspopup="dialog">
        登录 / 注册
        <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>`;
    slot.querySelector("button").addEventListener("click", () => {
      openLoginModal({
        onSuccess: (nextUser) => {
          applyUser(nextUser, { focus: true });
          if (typeof options.onSuccess === "function") options.onSuccess(nextUser);
        },
      });
    });
  }

  function renderUserMenu(nextUser, focus) {
    clearMenuBinding();
    const email = String(nextUser.email || "已登录");
    const initial = (email.trim().charAt(0) || "赤").toUpperCase();
    slot.innerHTML = `
      <div class="lm-user">
        <button class="lm-user-btn" type="button" aria-haspopup="true" aria-expanded="false"
                aria-label="账号菜单：${escapeHtml(email)}">
          <span class="lm-user-avatar" aria-hidden="true">${escapeHtml(initial)}</span>
          <span class="lm-user-email">${escapeHtml(email)}</span>
        </button>
        <div class="lm-user-pop" hidden>
          <p class="lm-user-mail">${escapeHtml(email)}</p>
          <p class="lm-user-hint">已登录 · 数据保存在本机</p>
          <a class="lm-user-link" href="./wizard.html">我的选科测评</a>
          <a class="lm-user-link" href="./help.html">帮助中心</a>
          <button class="lm-user-logout" type="button">退出登录</button>
        </div>
      </div>`;

    const wrap = slot.querySelector(".lm-user");
    const button = slot.querySelector(".lm-user-btn");
    const pop = slot.querySelector(".lm-user-pop");
    const logoutBtn = slot.querySelector(".lm-user-logout");

    const setOpen = (open) => {
      pop.hidden = !open;
      wrap.classList.toggle("is-open", open);
      button.setAttribute("aria-expanded", String(open));
    };

    const onDocumentClick = (event) => {
      if (!wrap.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape" && !pop.hidden) {
        setOpen(false);
        button.focus({ preventScroll: true });
      }
    };

    button.addEventListener("click", () => setOpen(pop.hidden));
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKey);

    logoutBtn.addEventListener("click", async () => {
      logoutBtn.disabled = true;
      logoutBtn.textContent = "正在退出…";
      try {
        await api.logout();
      } catch {
        // 后端断线也按用户意愿退回未登录状态
      }
      applyUser(null, { force: true });
      if (typeof options.onLogout === "function") options.onLogout();
    });

    unbindMenu = () => {
      document.removeEventListener("click", onDocumentClick);
      document.removeEventListener("keydown", onKey);
    };

    if (focus) button.focus({ preventScroll: true });
  }

  function applyUser(nextUser, { focus = false, force = false } = {}) {
    const next = nextUser || null;
    const sameUser = Boolean(user && next && (user.id === next.id || user.email === next.email));
    const alreadyLoggedOut = !user && !next && Boolean(slot.querySelector(".lm-login-btn"));
    user = next;
    if (force || (!sameUser && !alreadyLoggedOut)) {
      if (next) renderUserMenu(next, focus);
      else renderLoginButton();
      emit();
    }
    return user;
  }

  async function refresh() {
    try {
      const payload = await api.me();
      applyUser((payload && payload.user) || null);
    } catch {
      applyUser(null);
    }
    return user;
  }

  renderLoginButton();
  refresh();

  return {
    refresh,
    setUser: (next) => applyUser(next, { force: true }),
    getUser: () => user,
  };
}

export { DEMO_EMAIL as demoEmail, DEMO_PASSWORD as demoPassword };
