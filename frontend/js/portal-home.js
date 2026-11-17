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
/* 选科模式互动面板：Tab 切换 + 组合矩阵 + 省份查询                          */
/* ------------------------------------------------------------------------ */

const MODE_META = {
  "312": {
    name: "3+1+2",
    count: 12,
    provinces: "23 省",
    desc: "首选物理或历史，再从化学、生物、政治、地理里选 2 门。同一个组合，能报的专业差别很大。",
  },
  "33": {
    name: "3+3",
    count: 20,
    provinces: "6 省市",
    desc: "从物理、化学、生物、政治、历史、地理里任意选 3 门，共 20 种。",
  },
  zj: {
    name: "浙江 7 选 3",
    count: 35,
    provinces: "1 省",
    desc: "比 3+3 多一门技术，7 门里选 3 门，可选面最宽，共 35 种。",
  },
  old: {
    name: "老高考",
    count: 2,
    provinces: "2 省区",
    desc: "不分选考，直接分文理科。语数外 + 文综或理综。",
  },
};

const SUBJ_FULL = {
  物: "物理", 化: "化学", 生: "生物", 政: "政治",
  史: "历史", 地: "地理", 技: "技术", 文: "文科", 理: "理科",
};

function pickCombos(list, k) {
  const out = [];
  const walk = (start, chosen) => {
    if (chosen.length === k) {
      out.push(chosen.slice());
      return;
    }
    for (let i = start; i < list.length; i += 1) {
      chosen.push(list[i]);
      walk(i + 1, chosen);
      chosen.pop();
    }
  };
  walk(0, []);
  return out;
}

function combosOf(mode) {
  if (mode === "312") {
    const rest = ["化", "生", "政", "地"];
    return ["物", "史"].flatMap((first) => pickCombos(rest, 2).map((pair) => [first, ...pair]));
  }
  if (mode === "33") return pickCombos(["物", "化", "生", "政", "史", "地"], 3);
  if (mode === "zj") return pickCombos(["物", "化", "生", "政", "史", "地", "技"], 3);
  return [["文"], ["理"]];
}

function rollNumber(node, target) {
  if (!node) return;
  const from = Number(node.textContent) || 0;
  if (prefersReducedMotion() || from === target) {
    node.textContent = String(target);
    return;
  }
  const start = window.performance.now();
  const duration = 420;
  const tick = (now) => {
    const progress = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = String(Math.round(from + (target - from) * eased));
    if (progress < 1) window.requestAnimationFrame(tick);
    else node.textContent = String(target);
  };
  window.requestAnimationFrame(tick);
}

function initModePanel() {
  const panel = document.querySelector("[data-mode-panel]");
  if (!panel) return;

  const tabs = Array.from(panel.querySelectorAll("[data-mtab]"));
  const countEl = panel.querySelector("[data-mcount]");
  const provEl = panel.querySelector("[data-mprovinces]");
  const descEl = panel.querySelector("[data-mdesc]");
  const barEl = panel.querySelector("[data-mbar]");
  const grid = panel.querySelector("[data-mgrid]");
  const input = panel.querySelector("#hp-mprovince");
  const goBtn = panel.querySelector("#hp-mgo");
  const result = panel.querySelector("#hp-mresult");
  const datalist = panel.querySelector("#hp-mprovs");

  if (!tabs.length || !grid) return;

  // 省份清单一次性铺进 datalist
  const ALL_PROVINCES = Object.entries(PROVINCES).flatMap(([mode, rows]) =>
    rows.map(([name, year]) => ({ name, year, mode }))
  );
  if (datalist) {
    datalist.innerHTML = ALL_PROVINCES.map((item) => `<option value="${item.name}"></option>`).join("");
  }

  // 支持 ?mode=zj 直接打开某一档（便于分享和截图）
  const wanted = new URLSearchParams(window.location.search).get("mode");
  let current = wanted && MODE_META[wanted] ? wanted : "312";

  const toneOf = (combo) => {
    if (combo[0] === "物" || combo.includes("物")) return "phys";
    if (combo[0] === "史" || combo.includes("史")) return "hist";
    if (combo[0] === "文") return "hist";
    if (combo[0] === "理") return "phys";
    return "mix";
  };

  const renderGrid = (mode) => {
    const combos = combosOf(mode);
    grid.innerHTML = combos
      .map((combo, index) => {
        const short = combo.join("");
        const full = combo.map((key) => SUBJ_FULL[key] || key).join(" + ");
        return `<li class="hp-combo" data-tone="${toneOf(combo)}" style="--i:${index}" title="${full}">${short}</li>`;
      })
      .join("");
    grid.classList.remove("is-refresh");
    // 强制重排，让入场动画每次切换都重放
    void grid.offsetWidth;
    grid.classList.add("is-refresh");
  };

  const applyMode = (mode, { scroll = false } = {}) => {
    const meta = MODE_META[mode];
    if (!meta || mode === current) return;
    current = mode;

    tabs.forEach((tab) => {
      const on = tab.dataset.mtab === mode;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });

    rollNumber(countEl, meta.count);
    if (barEl) barEl.style.width = `${Math.round((meta.count / 35) * 100)}%`;
    if (provEl) provEl.textContent = meta.provinces;
    if (descEl) descEl.textContent = meta.desc;
    renderGrid(mode);
    if (scroll && window.matchMedia("(max-width: 640px)").matches) {
      panel.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => applyMode(tab.dataset.mtab));
  });

  // 初次渲染：按 URL 参数或默认 3+1+2
  if (current !== "312") {
    const meta = MODE_META[current];
    tabs.forEach((tab) => {
      const on = tab.dataset.mtab === current;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (countEl) countEl.textContent = String(meta.count);
    if (barEl) barEl.style.width = `${Math.round((meta.count / 35) * 100)}%`;
    if (provEl) provEl.textContent = meta.provinces;
    if (descEl) descEl.textContent = meta.desc;
  }
  renderGrid(current);

  const lookup = (raw) => {
    const name = String(raw || "").trim().replace(/省$|市$|自治区$|维吾尔|回族|壮族|特别行政区$/g, "");
    if (!name) return null;
    return (
      ALL_PROVINCES.find((item) => item.name === name) ||
      ALL_PROVINCES.find((item) => item.name.startsWith(name) || name.startsWith(item.name)) ||
      null
    );
  };

  const showProvince = () => {
    if (!input || !result) return;
    const hit = lookup(input.value);
    if (!hit) {
      result.hidden = false;
      result.textContent = "没找到这个省份，试试「江苏」「山东」「新疆」这样的写法。";
      return;
    }
    const meta = MODE_META[hit.mode];
    const yearText = hit.year ? `${hit.year} 年首届新高考` : "仍按文理分科填报";
    result.hidden = false;
    result.innerHTML =
      `<b>${hit.name}</b> · ${yearText} · <b>${meta.name}</b> · 共 <b>${meta.count}</b> 种组合 ` +
      `<a href="./wizard.html" data-jump="${hit.name}">去按本省规则测一测 →</a>`;
    input.value = hit.name;
    applyMode(hit.mode);
  };

  if (goBtn) goBtn.addEventListener("click", showProvince);
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        showProvince();
      }
    });
    input.addEventListener("change", showProvince);
  }
  if (result) {
    result.addEventListener("click", (event) => {
      const link = event.target.closest("[data-jump]");
      if (!link) return;
      // 把省份写进向导的 sessionStorage，进去就不用再选一次
      try {
        sessionStorage.setItem("chili.wizard.province.v1", JSON.stringify(link.dataset.jump));
      } catch {
        /* 隐私模式下写不进去，退化成本地选择省份 */
      }
    });
  }
}

/* ------------------------------------------------------------------------ */

initHeader();
initReveal();
initCounters();
initFaq();
initProvinces();
initModePanel();
initHealth();
mountLoginButton();
