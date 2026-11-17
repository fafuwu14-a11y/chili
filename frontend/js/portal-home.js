/**
 * 门户首页交互：导航下拉、汉堡菜单、FAQ 手风琴、滚动淡入、数字滚动、省份展开、登录按钮。
 *
 * 只请求两个真实存在的接口：GET /api/health（原生 fetch）与 api.me()。
 * 其余内容全部来自页面里的静态数据。
 */

import { mountLoginButton } from "./login-modal.js";

// 给 <html> 打标记，portal.css 里的 [data-reveal] 才会先隐藏再淡入。
// index.html 的 <head> 里也有一行同样的内联脚本，用来防止首屏闪一下。
document.documentElement.classList.add("hp-js");

const MOBILE_NAV = "(max-width: 940px)";
const prefersReducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ------------------------------------------------------------------------ */
/* 顶栏：滚动阴影、汉堡菜单、高三工具下拉                                    */
/* ------------------------------------------------------------------------ */

function initHeader() {
  const header = document.getElementById("hp-header");
  if (!header) return;

  const burger = document.getElementById("hp-burger");
  const nav = document.getElementById("hp-nav");

  const onScroll = () => {
    header.classList.toggle("is-scrolled", window.scrollY > 8);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  function setNavOpen(open) {
    header.classList.toggle("is-nav-open", open);
    if (burger) {
      burger.setAttribute("aria-expanded", String(open));
      burger.setAttribute("aria-label", open ? "关闭菜单" : "打开菜单");
    }
    document.body.classList.toggle("hp-nav-locked", open && window.matchMedia(MOBILE_NAV).matches);
  }

  if (burger) {
    burger.addEventListener("click", () => setNavOpen(!header.classList.contains("is-nav-open")));
  }

  // 移动端点了链接就收起菜单，别挡着内容
  if (nav) {
    nav.addEventListener("click", (event) => {
      if (event.target.closest("a") && window.matchMedia(MOBILE_NAV).matches) setNavOpen(false);
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (header.classList.contains("is-nav-open")) {
      setNavOpen(false);
      if (burger) burger.focus({ preventScroll: true });
    }
  });

  // 从移动端宽度拉回桌面时，别留下一个「已展开」的状态
  let isMobile = window.matchMedia(MOBILE_NAV).matches;
  window.addEventListener("resize", () => {
    const next = window.matchMedia(MOBILE_NAV).matches;
    if (isMobile !== next) {
      isMobile = next;
      setNavOpen(false);
    }
  });

  document.querySelectorAll("[data-dropdown]").forEach((wrap) => {
    const button = wrap.querySelector(".hp-nav-more-btn");
    const pop = wrap.querySelector(".hp-more-pop");
    if (!button || !pop) return;

    const setOpen = (open) => {
      pop.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    };

    button.addEventListener("click", (event) => {
      event.stopPropagation();
      setOpen(pop.hidden);
    });

    wrap.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !pop.hidden) {
        setOpen(false);
        button.focus({ preventScroll: true });
      }
    });

    // 点到别处、或焦点移出下拉，都收起
    document.addEventListener("click", (event) => {
      if (!wrap.contains(event.target)) setOpen(false);
    });
    wrap.addEventListener("focusout", (event) => {
      if (!wrap.contains(event.relatedTarget)) setOpen(false);
    });
    pop.addEventListener("click", (event) => {
      if (event.target.closest("a")) setOpen(false);
    });
  });
}

/* ------------------------------------------------------------------------ */
/* 滚动淡入 + 数字滚动                                                       */
/* ------------------------------------------------------------------------ */

function initReveal() {
  const targets = Array.from(document.querySelectorAll("[data-reveal]"));
  if (!targets.length) return;
  // 告诉 index.html 里的兜底定时器：淡入逻辑已经在跑了
  window.__hpRevealReady = true;

  if (prefersReducedMotion() || !("IntersectionObserver" in window)) {
    targets.forEach((node) => node.classList.add("is-in"));
    return;
  }

  // 卡片按顺序错开一点，别整块一起动（--hp-delay 只影响入场动画，不影响 hover）
  document.querySelectorAll(".hp-pain-grid, .hp-flow-list, .hp-mode-grid").forEach((grid) => {
    Array.from(grid.querySelectorAll("[data-reveal]")).forEach((node, index) => {
      node.style.setProperty("--hp-delay", `${Math.min(index, 5) * 70}ms`);
    });
  });

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-in");
        observer.unobserve(entry.target);
      });
    },
    { rootMargin: "0px 0px -6% 0px", threshold: 0.08 }
  );

  targets.forEach((node) => observer.observe(node));
}

function initCounters() {
  const counters = Array.from(document.querySelectorAll("[data-count]"));
  if (!counters.length) return;

  const finish = (node) => {
    node.textContent = String(Number(node.dataset.count));
  };

  if (prefersReducedMotion() || !("IntersectionObserver" in window) || !("requestAnimationFrame" in window)) {
    counters.forEach(finish);
    return;
  }

  // 先把数字清零，否则首屏会先显示 HTML 里的目标值、再跳回 0 开始数
  counters.forEach((node) => { node.textContent = "0"; });

  const run = (node) => {
    const target = Number(node.dataset.count);
    if (!Number.isFinite(target)) return;
    const duration = 900;
    const start = window.performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      node.textContent = String(Math.round(target * eased));
      if (progress < 1) window.requestAnimationFrame(tick);
      else node.textContent = String(target);
    };
    node.textContent = "0";
    window.requestAnimationFrame(tick);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        run(entry.target);
      });
    },
    { threshold: 0.4 }
  );

  counters.forEach((node) => observer.observe(node));
}

/* ------------------------------------------------------------------------ */
/* FAQ 手风琴                                                               */
/* ------------------------------------------------------------------------ */

function initFaq() {
  const root = document.querySelector("[data-faq]");
  if (!root) return;

  const items = Array.from(root.querySelectorAll(".hp-faq-item"));

  const collapse = (item) => {
    const button = item.querySelector(".hp-faq-q");
    if (!button) return;
    button.setAttribute("aria-expanded", "false");
    item.classList.remove("is-open");
  };

  const expand = (item) => {
    const button = item.querySelector(".hp-faq-q");
    if (!button) return;
    button.setAttribute("aria-expanded", "true");
    item.classList.add("is-open");
  };

  items.forEach((item) => {
    const button = item.querySelector(".hp-faq-q");
    if (!button) return;
    button.addEventListener("click", () => {
      const isOpen = button.getAttribute("aria-expanded") === "true";
      items.forEach((other) => {
        if (other !== item) collapse(other);
      });
      if (isOpen) collapse(item);
      else expand(item);
    });
  });

  // 深链：#hp-faq-title 打开时默认展开第一条，别让用户看到一堵标题
  if (items.length && window.location.hash === "#hp-faq") expand(items[0]);
}

/* ------------------------------------------------------------------------ */
/* 全国选科覆盖：省份静态数据                                                */
/* ------------------------------------------------------------------------ */

const PROVINCES = {
  // 第三批 8 省：2021 年首届新高考
  "312": [
    ["河北", 2021], ["辽宁", 2021], ["江苏", 2021], ["福建", 2021],
    ["湖北", 2021], ["湖南", 2021], ["广东", 2021], ["重庆", 2021],
    // 第四批 7 省：2024 年首届
    ["甘肃", 2024], ["吉林", 2024], ["黑龙江", 2024], ["安徽", 2024],
    ["江西", 2024], ["贵州", 2024], ["广西", 2024],
    // 第五批 8 省：2025 年首届
    ["山西", 2025], ["内蒙古", 2025], ["河南", 2025], ["四川", 2025],
    ["云南", 2025], ["陕西", 2025], ["青海", 2025], ["宁夏", 2025],
  ],
  "33": [
    ["上海", 2017], ["浙江", 2017],
    ["北京", 2020], ["天津", 2020], ["山东", 2020], ["海南", 2020],
  ],
  old: [
    ["西藏", 0], ["新疆", 0],
  ],
};

function initProvinces() {
  document.querySelectorAll("[data-prov-list]").forEach((list) => {
    const card = list.closest("[data-mode]");
    const mode = card ? card.dataset.mode : "";
    const rows = PROVINCES[mode] || [];
    list.innerHTML = rows
      .map(([name, year]) => {
        const title = year ? `${year} 年首届新高考` : "仍按文理分科填报";
        return `<li title="${title}">${name}${year ? `<span class="hp-prov-year">${year}</span>` : ""}</li>`;
      })
      .join("");
  });

  document.querySelectorAll("[data-prov-toggle]").forEach((button) => {
    const card = button.closest("[data-mode]");
    const list = card ? card.querySelector("[data-prov-list]") : null;
    if (!list) return;

    const labelNode = Array.from(button.childNodes).find(
      (node) => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim()
    );

    button.addEventListener("click", () => {
      const open = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!open));
      list.hidden = open;
      card.classList.toggle("is-open", !open);
      if (labelNode) labelNode.nodeValue = open ? "展开省份" : "收起省份";
    });
  });
}

/* ------------------------------------------------------------------------ */
/* 本地服务状态                                                             */
/* ------------------------------------------------------------------------ */

async function initHealth() {
  const box = document.querySelector("[data-service-status]");
  if (!box) return;
  const text = box.querySelector("[data-service-text]");
  if (!text) return;

  try {
    const response = await fetch("/api/health", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) throw new Error("unhealthy");
    box.dataset.state = "on";
    const source = typeof payload.source === "string" ? payload.source : "";
    text.textContent = source ? `本地服务运行中 · 数据源 ${source}` : "本地服务运行中";
    box.title = source ? `数据源：${source}` : "本地服务运行中";
  } catch {
    box.dataset.state = "off";
    text.textContent = "本地服务未连接 · 静态页面仍可浏览";
    box.title = "启动 python -m http.server 或后端服务后可登录与测评";
  }
}

/* ------------------------------------------------------------------------ */

initHeader();
initReveal();
initCounters();
initFaq();
initProvinces();
initHealth();
mountLoginButton();
