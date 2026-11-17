/** 顶栏用户菜单：显示当前账号、退出登录。四个页面共用。 */

import { api } from "./api.js";

const SNIPPET = `
  <button class="user-btn" id="user-btn" type="button"
          aria-haspopup="menu" aria-expanded="false" aria-label="账号菜单">
    <span class="user-avatar" id="user-avatar" aria-hidden="true">·</span>
    <span class="user-email" id="user-email"></span>
    <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </button>
  <div class="user-pop" id="user-pop" role="menu" hidden>
    <p class="user-pop-mail" id="user-pop-mail"></p>
    <p class="user-pop-hint">登录状态 7 天内有效</p>
    <a class="user-pop-link" href="./help.html" role="menuitem">帮助中心</a>
    <a class="user-pop-link" href="./privacy.html" role="menuitem">隐私政策</a>
    <button class="user-logout" id="user-logout" type="button" role="menuitem">退出登录</button>
  </div>
`;

let mounted = false;

export async function mountUserMenu() {
  const slot = document.querySelector(".topbar-side");
  if (!slot || mounted) return null;

  let data;
  try {
    data = await api.me();
  } catch {
    return null; // 没登录或服务没起来：api.request 已经把未登录的人送去登录页了
  }
  const user = data && data.user;
  if (!user) return null;

  const root = document.createElement("div");
  root.className = "user-chip";
  root.id = "user-chip";
  root.innerHTML = SNIPPET;
  slot.appendChild(root);
  mounted = true;

  const button = root.querySelector("#user-btn");
  const pop = root.querySelector("#user-pop");
  const avatar = root.querySelector("#user-avatar");
  const emailNode = root.querySelector("#user-email");
  const popMail = root.querySelector("#user-pop-mail");
  const logout = root.querySelector("#user-logout");

  const initial = (user.email || "?").trim().charAt(0).toUpperCase();
  avatar.textContent = initial;
  emailNode.textContent = user.email;
  popMail.textContent = user.email;
  root.title = user.email;

  function close() {
    pop.hidden = true;
    button.setAttribute("aria-expanded", "false");
    root.classList.remove("is-open");
  }

  function open() {
    pop.hidden = false;
    button.setAttribute("aria-expanded", "true");
    root.classList.add("is-open");
    logout.focus({ preventScroll: true });
  }

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (pop.hidden) open();
    else close();
  });

  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      close();
      button.focus({ preventScroll: true });
    }
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) close();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !pop.hidden) close();
  });

  logout.addEventListener("click", async () => {
    logout.disabled = true;
    logout.textContent = "正在退出…";
    try {
      await api.logout();
    } catch {
      /* 就算请求失败，Cookie 也已经让服务端作废了，直接跳走 */
    }
    window.location.replace("/login.html");
  });

  return { user, close };
}

/**
 * 顶栏「更多」下拉：所有页面共用的纯交互，不依赖登录。
 * 在 mountUserMenu 之外单独导出，登录页之外每页都调一次。
 */
export function bindNavMore() {
  const wrap = document.querySelector(".nav-more");
  const btn = wrap && wrap.querySelector(".nav-more-btn");
  const pop = wrap && wrap.querySelector(".nav-more-pop");
  if (!wrap || !btn || !pop) return;

  const close = () => {
    pop.hidden = true;
    btn.setAttribute("aria-expanded", "false");
  };

  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = pop.hidden;
    pop.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
  });

  pop.addEventListener("click", () => close());
  document.addEventListener("click", (event) => {
    if (!wrap.contains(event.target)) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}
