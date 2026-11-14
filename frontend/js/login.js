/** 登录 / 注册页。所有校验先在前端做一遍，后端仍然是最终裁决。 */

import { api } from "./api.js";
import { toast } from "./ui.js";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PASSWORD_MIN = 8;

const els = {
  tabs: Array.from(document.querySelectorAll(".auth-tab")),
  title: document.getElementById("auth-title"),
  sub: document.getElementById("auth-sub"),
  form: document.getElementById("auth-form"),
  email: document.getElementById("email"),
  emailField: document.getElementById("email-field"),
  emailError: document.getElementById("email-error"),
  password: document.getElementById("password"),
  passwordField: document.getElementById("password-field"),
  passwordError: document.getElementById("password-error"),
  confirm: document.getElementById("confirm"),
  confirmField: document.getElementById("confirm-field"),
  confirmError: document.getElementById("confirm-error"),
  pwToggle: document.getElementById("pw-toggle"),
  strength: document.getElementById("strength"),
  caps: document.getElementById("caps-hint"),
  formError: document.getElementById("form-error"),
  submit: document.getElementById("auth-submit"),
  submitText: document.getElementById("submit-text"),
};

const state = { mode: "login", busy: false, touched: { email: false, password: false, confirm: false } };

const COPY = {
  login: {
    title: "欢迎回来",
    sub: "用注册时的邮箱和密码登录。",
    submit: "登录",
    autocomplete: "current-password",
    placeholder: "输入密码",
  },
  register: {
    title: "建一个账号",
    sub: "只要邮箱和密码，问题全部在这台电脑上算。",
    submit: "注册并登录",
    autocomplete: "new-password",
    placeholder: "至少 8 位，含字母和数字",
  },
};

/* ------------------------------------------------------------ 小工具 */

function showError(node, message) {
  const has = Boolean(message);
  node.textContent = message || "";
  node.hidden = !has;
}

function markInvalid(input, invalid) {
  if (invalid) input.setAttribute("aria-invalid", "true");
  else input.removeAttribute("aria-invalid");
}

function setBusy(busy) {
  state.busy = busy;
  els.submit.disabled = busy;
  els.submit.classList.toggle("is-busy", busy);
  els.submit.setAttribute("aria-busy", String(busy));
}

/** 只接受站内相对路径，挡掉 next=//evil.com 这类开放跳转。 */
function safeNext() {
  const raw = new URLSearchParams(window.location.search).get("next") || "";
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/";
  return raw;
}

/* ------------------------------------------------------------ 切换模式 */

function setMode(mode, { focus = true } = {}) {
  state.mode = mode;
  const copy = COPY[mode];
  const isRegister = mode === "register";

  for (const tab of els.tabs) {
    const active = tab.dataset.mode === mode;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  }

  els.title.textContent = copy.title;
  els.sub.textContent = copy.sub;
  els.submitText.textContent = copy.submit;
  els.password.autocomplete = copy.autocomplete;
  els.password.placeholder = copy.placeholder;

  els.confirmField.hidden = !isRegister;
  els.strength.hidden = !isRegister;

  /* 换模式时清掉「刚才是登录/注册」留下的错误，保留已填的邮箱 */
  showError(els.formError, "");
  showError(els.passwordError, "");
  showError(els.confirmError, "");
  markInvalid(els.password, false);
  if (!isRegister) {
    els.password.value = "";
    state.touched.password = false;
  }

  renderStrength();
  els.formError.hidden = true;
  if (focus) {
    /* 邮箱已经填了就接着填密码，否则先填邮箱 */
    const target = els.email.value.trim() ? els.password : els.email;
    window.requestAnimationFrame(() => target.focus({ preventScroll: true }));
  }
}

/* ------------------------------------------------------------ 校验 */

function validateEmail(force) {
  if (!force && !state.touched.email) return true;
  const value = els.email.value.trim();
  if (!value) {
    showError(els.emailError, "邮箱不能为空");
    markInvalid(els.email, true);
    return false;
  }
  if (!EMAIL_RE.test(value)) {
    showError(els.emailError, "邮箱格式不对，检查一下 @ 和域名");
    markInvalid(els.email, true);
    return false;
  }
  showError(els.emailError, "");
  markInvalid(els.email, false);
  return true;
}

function passwordChecks(value) {
  return {
    len: value.length >= PASSWORD_MIN,
    letter: /[A-Za-z]/.test(value),
    digit: /\d/.test(value),
  };
}

function renderStrength() {
  if (state.mode !== "register") return;
  const checks = passwordChecks(els.password.value);
  for (const item of els.strength.querySelectorAll("li")) {
    item.classList.toggle("is-ok", Boolean(checks[item.dataset.rule]));
  }
}

function validatePassword(force) {
  if (!force && !state.touched.password) return true;
  const value = els.password.value;
  if (!value) {
    showError(els.passwordError, "密码不能为空");
    markInvalid(els.password, true);
    return false;
  }
  if (state.mode === "login") {
    showError(els.passwordError, "");
    markInvalid(els.password, false);
    return true;
  }
  const checks = passwordChecks(value);
  const missing = [];
  if (!checks.len) missing.push(`至少 ${PASSWORD_MIN} 位`);
  if (!checks.letter) missing.push("字母");
  if (!checks.digit) missing.push("数字");
  if (missing.length) {
    showError(els.passwordError, `还缺：${missing.join("、")}`);
    markInvalid(els.password, true);
    return false;
  }
  showError(els.passwordError, "");
  markInvalid(els.password, false);
  return true;
}

function validateConfirm(force) {
  if (state.mode !== "register") return true;
  if (!force && !state.touched.confirm) return true;
  const value = els.confirm.value;
  if (!value) {
    showError(els.confirmError, "再输一次密码");
    markInvalid(els.confirm, true);
    return false;
  }
  if (value !== els.password.value) {
    showError(els.confirmError, "两次输入不一样");
    markInvalid(els.confirm, true);
    return false;
  }
  showError(els.confirmError, "");
  markInvalid(els.confirm, false);
  return true;
}

/* ------------------------------------------------------------ 提交 */

async function onSubmit(event) {
  event.preventDefault();
  if (state.busy) return;

  state.touched = { email: true, password: true, confirm: true };
  const ok = [validateEmail(true), validatePassword(true), validateConfirm(true)].every(Boolean);
  if (!ok) {
    const firstInvalid = els.form.querySelector('[aria-invalid="true"]');
    if (firstInvalid) firstInvalid.focus();
    return;
  }

  const email = els.email.value.trim().toLowerCase();
  const password = els.password.value;
  showError(els.formError, "");
  setBusy(true);

  try {
    if (state.mode === "register") {
      await api.register(email, password);
    } else {
      await api.login(email, password);
    }
    toast(state.mode === "register" ? "注册好了，正在进入" : "登录成功，正在进入");
    window.location.replace(safeNext());
  } catch (error) {
    handleFailure(error, email);
  } finally {
    setBusy(false);
  }
}

function handleFailure(error, email) {
  if (error.code === "email_taken") {
    setMode("login", { focus: false });
    els.email.value = email;
    showError(
      els.formError,
      "这个邮箱已经注册过了。已经帮你切到「登录」，输入密码就行。",
    );
    els.password.focus();
    return;
  }

  if (error.code === "too_many_attempts" || error.status === 429) {
    showError(els.formError, error.message);
    return;
  }

  if (error.status === 401) {
    showError(els.formError, error.message);
    els.password.select();
    return;
  }

  if (error.code === "password_weak" || error.code === "password_invalid") {
    showError(els.passwordError, error.message);
    markInvalid(els.password, true);
    els.password.focus();
    return;
  }

  if (error.code === "email_invalid") {
    showError(els.emailError, error.message);
    markInvalid(els.email, true);
    els.email.focus();
    return;
  }

  showError(els.formError, error.message);
}

/* ------------------------------------------------------------ 事件 */

for (const tab of els.tabs) {
  tab.addEventListener("click", () => {
    if (state.busy || tab.dataset.mode === state.mode) return;
    setMode(tab.dataset.mode);
  });
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const next = state.mode === "login" ? "register" : "login";
    setMode(next);
    els.tabs.find((item) => item.dataset.mode === next)?.focus();
  });
}

els.email.addEventListener("focus", () => {
  state.touched.email = true;
});
els.email.addEventListener("blur", () => {
  state.touched.email = true;
  validateEmail(false);
});
els.email.addEventListener("input", () => {
  if (!els.emailError.hidden) validateEmail(true);
});

els.password.addEventListener("focus", () => {
  state.touched.password = true;
});
els.password.addEventListener("input", () => {
  if (state.mode === "register") renderStrength();
  if (!els.passwordError.hidden) validatePassword(true);
  if (!els.confirmError.hidden) validateConfirm(false);
});
els.password.addEventListener("blur", () => {
  state.touched.password = true;
  validatePassword(false);
});

els.confirm.addEventListener("input", () => {
  state.touched.confirm = true;
  if (!els.confirmError.hidden) validateConfirm(false);
});
els.confirm.addEventListener("blur", () => {
  state.touched.confirm = true;
  validateConfirm(false);
});

els.pwToggle.addEventListener("click", () => {
  const visible = els.password.type === "text";
  const nextType = visible ? "password" : "text";
  els.password.type = nextType;
  if (!els.confirmField.hidden) els.confirm.type = nextType;
  els.pwToggle.setAttribute("aria-pressed", String(!visible));
  els.pwToggle.setAttribute("aria-label", visible ? "显示密码" : "隐藏密码");
  els.password.focus({ preventScroll: true });
});

function detectCaps(event) {
  if (typeof event.getModifierState !== "function") return;
  els.caps.hidden = !event.getModifierState("CapsLock");
}
for (const input of [els.password, els.confirm]) {
  input.addEventListener("keydown", detectCaps);
  input.addEventListener("keyup", detectCaps);
  input.addEventListener("blur", () => {
    els.caps.hidden = true;
  });
}

els.form.addEventListener("submit", onSubmit);

/* ------------------------------------------------------------ 启动 */

(function boot() {
  const params = new URLSearchParams(window.location.search);
  const wanted = params.get("mode") === "register" ? "register" : "login";
  setMode(wanted, { focus: false });

  /* 已经登录过就别让人再输一遍 */
  api.me().then((data) => {
    if (data && data.user) window.location.replace(safeNext());
  }).catch(() => {
    /* 没登录 / 服务没起来，留在这一页；触屏设备不抢焦点，免得一进来就弹键盘 */
    if (window.matchMedia("(pointer: fine)").matches) {
      window.requestAnimationFrame(() => els.email.focus({ preventScroll: true }));
    }
  });
})();
