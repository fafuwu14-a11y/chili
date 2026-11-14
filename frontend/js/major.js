/** 专业集合页：门类树 → 专业列表 → 专业详情（含先导课分支）。 */

import { api } from "./api.js";
import { escapeHtml as esc, formatNumber, toast } from "./ui.js";
import { mountUserMenu, bindNavMore } from "./session.js";

/** 投档表里的省份 key → 页面上的名字（只含有专业级投放的省） */
const PROVINCE_NAMES = {
  js: "江苏",
  gd: "广东",
  sx: "山西",
  hb: "湖北",
  he: "河北",
  ln: "辽宁",
  sd: "山东",
  zj: "浙江",
};

/** 后端 /api/majors 的上限是 400，一次拉满就够浏览用 */
const LIST_LIMIT = 400;

const state = {
  meta: null,
  category: "",
  group: "",
  q: "",
  selected: "",
};

const els = {
  tree: document.getElementById("major-tree"),
  form: document.getElementById("major-search"),
  q: document.getElementById("major-q"),
  submit: document.getElementById("major-submit"),
  head: document.getElementById("major-list-head"),
  list: document.getElementById("major-list"),
  empty: document.getElementById("major-empty"),
  detail: document.getElementById("major-detail"),
};

/** 当前选中的门类 / 专业类名字，用于列表标题 */
function scopeName() {
  const cat = (state.meta?.categories || []).find((item) => item.id === state.category);
  if (!cat) return "全部专业";
  if (!state.group) return cat.name;
  const group = cat.groups.find((item) => item.id === state.group);
  return group ? `${cat.name} / ${group.name}` : cat.name;
}

async function init() {
  bind();
  try {
    state.meta = await api.majorMeta();
    readUrl();
    renderTree();
    await refreshList();
    if (state.selected) await loadDetail(state.selected, { syncUrl: false });
  } catch (error) {
    els.tree.innerHTML = "";
    els.list.innerHTML = "";
    toast(error.message);
  }
}

/** 从地址栏恢复浏览位置，保证刷新和分享不丢上下文 */
function readUrl() {
  const params = new URLSearchParams(window.location.search);
  const category = params.get("category") || "";
  const group = params.get("group") || "";
  const cat = (state.meta?.categories || []).find((item) => item.id === category);
  if (cat) {
    state.category = category;
    if (group && cat.groups.some((item) => item.id === group)) state.group = group;
  }
  state.q = (params.get("q") || "").trim();
  state.selected = (params.get("major") || "").trim();
  els.q.value = state.q;
}

/** 地址栏只保留有意义的筛选，避免刷新后停在别的门类 */
function syncUrl() {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  else if (state.group) {
    params.set("category", state.category);
    params.set("group", state.group);
  } else if (state.category) {
    params.set("category", state.category);
  }
  if (state.selected) params.set("major", state.selected);
  const query = params.toString();
  window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

function bind() {
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.q = els.q.value.trim();
    // 搜索是全库范围，先清掉门类筛选，免得搜不到还以为目录漏了
    if (state.q) {
      state.category = "";
      state.group = "";
      renderTree();
    }
    refreshList();
  });

  els.tree.addEventListener("click", (event) => {
    const groupBtn = event.target.closest(".major-group");
    if (groupBtn) {
      state.category = groupBtn.dataset.category;
      state.group = groupBtn.dataset.group;
      state.q = "";
      els.q.value = "";
      renderTree();
      refreshList();
      return;
    }

    const catBtn = event.target.closest(".major-cat");
    if (!catBtn) return;
    const id = catBtn.dataset.category || "";
    // 再点一次已选中的门类，回到「全部专业」
    const same = id === state.category && !state.group;
    state.category = !id || same ? "" : id;
    state.group = "";
    state.q = "";
    els.q.value = "";
    renderTree();
    refreshList();
  });

  els.list.addEventListener("click", (event) => {
    const item = event.target.closest(".major-item");
    if (!item) return;
    loadDetail(item.dataset.name);
  });

  els.detail.addEventListener("click", (event) => {
    if (event.target.closest(".major-detail-close")) closeDetail();
  });
}

function renderTree() {
  const total = state.meta?.total_majors || 0;
  const all = `
    <button type="button" class="major-cat major-cat--all${state.category ? "" : " is-active"}" data-category="">
      <span>全部专业</span><em>${formatNumber(total)}</em>
    </button>`;

  const blocks = (state.meta?.categories || [])
    .map((cat) => {
      const count = cat.groups.reduce((sum, group) => sum + (group.count || 0), 0);
      const open = cat.id === state.category;
      const groupItems = cat.groups
        .map(
          (group) => `
          <li>
            <button type="button" class="major-group${
              open && group.id === state.group ? " is-active" : ""
            }" data-category="${esc(cat.id)}" data-group="${esc(group.id)}">
              <span>${esc(group.name)}</span><em>${group.count}</em>
            </button>
          </li>`,
        )
        .join("");
      return `
        <div class="major-tree-group">
          <button type="button" class="major-cat${
            cat.id === state.category ? " is-active" : ""
          }" data-category="${esc(cat.id)}" aria-expanded="${open}">
            <span>${esc(cat.name)}</span><em>${count}</em>
            <i class="major-caret" aria-hidden="true">▾</i>
          </button>
          <ul class="major-groups"${open ? "" : " hidden"}>${groupItems}</ul>
        </div>`;
    })
    .join("");

  els.tree.innerHTML = all + blocks;
}

async function refreshList() {
  els.list.innerHTML = '<div class="skeleton skeleton--line"></div><div class="skeleton skeleton--line"></div><div class="skeleton skeleton--line"></div>';
  els.empty.hidden = true;
  try {
    const data = await api.majors({
      q: state.q,
      category: state.category,
      group: state.group,
      limit: LIST_LIMIT,
    });
    renderList(data);
    syncUrl();
  } catch (error) {
    els.list.innerHTML = "";
    toast(error.message);
  }
}

function renderList(data) {
  const scope = state.q ? `搜索「${state.q}」` : scopeName();
  const clipped =
    data.listed < data.total
      ? `，按招生规模排序先列前 ${data.listed} 个，点左侧门类可以缩小范围`
      : "";
  els.head.innerHTML = `${esc(scope)} · 共 <b>${formatNumber(data.total)}</b> 个专业${clipped}`;
  els.empty.hidden = data.items.length > 0;

  els.list.innerHTML = data.items
    .map(
      (item) => `
      <button type="button" class="major-item${item.name === state.selected ? " is-active" : ""}" data-name="${esc(item.name)}">
        <span class="major-item-body">
          <span class="major-item-name">${esc(item.name)}</span>
          <span class="major-item-meta">${esc(item.group)} · ${formatNumber(item.count)} 个招生单元 · ${
            item.provinces.length
          } 省有数据</span>
        </span>
        <span class="major-item-score"><b>${item.score_median}</b><i>中位分</i></span>
      </button>`,
    )
    .join("");
}

async function loadDetail(name, { syncUrl: sync = true, scroll = true } = {}) {
  state.selected = name;
  els.detail.hidden = false;
  els.detail.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
  markSelected();
  try {
    const data = await api.majorDetail(name);
    renderDetail(data);
    loadOutlook(name);
    loadTrend(name);
    if (sync) syncUrl();
    if (scroll && window.matchMedia("(max-width: 1024px)").matches) {
      els.detail.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (error) {
    els.detail.hidden = true;
    els.detail.innerHTML = "";
    toast(error.message);
  }
}

/** 前景分析单独请求：慢一点也没关系，详情先显示出来。 */
async function loadOutlook(name) {
  const box = document.getElementById("major-outlook");
  if (!box) return;
  const body = box.querySelector(".major-outlook-body");
  if (!body) return;
  try {
    const data = await api.majorOutlook(name);
    // 用户可能已经点了别的专业，旧响应直接丢掉
    if (state.selected !== name) return;
    body.innerHTML = renderOutlook(data);
  } catch (error) {
    body.innerHTML = `<p class="trend-empty">前景分析暂时给不出来：${esc(error.message)}</p>`;
  }
}

/** 趋势单独请求：慢一点也没关系，详情先显示出来。 */
async function loadTrend(name) {
  const box = document.getElementById("major-trend");
  if (!box) return;
  try {
    const data = await api.majorTrend(name);
    // 用户可能已经点了别的专业，旧响应直接丢掉
    if (state.selected !== name) return;
    const body = box.querySelector(".major-trend-body");
    if (body) body.innerHTML = renderTrend(data);
  } catch (error) {
    const body = box.querySelector(".major-trend-body");
    if (body) body.innerHTML = `<p class="trend-empty">趋势暂时算不出来：${esc(error.message)}</p>`;
  }
}

function closeDetail() {
  state.selected = "";
  els.detail.hidden = true;
  els.detail.innerHTML = "";
  markSelected();
  syncUrl();
}

function markSelected() {
  for (const node of els.list.querySelectorAll(".major-item")) {
    node.classList.toggle("is-active", node.dataset.name === state.selected);
  }
}

function renderDetail(data) {
  const rows = data.by_province
    .map(
      (row) => `
      <tr>
        <td>${esc(PROVINCE_NAMES[row.key] || row.key)}</td>
        <td>${formatNumber(row.count)}</td>
        <td>${row.median}</td>
      </tr>`,
    )
    .join("");

  const courses = data.courses.length
    ? data.courses
        .map(
          (course) => `
        <li class="major-course">
          <a class="major-course-title" href="${esc(course.url)}" target="_blank" rel="noopener noreferrer">${esc(
            course.title,
          )}</a>
          <span class="major-course-meta">${esc(course.platform)} · ${course.weeks} 周${
            course.match ? ` · 匹配 ${course.match}` : ""
          }</span>
        </li>`,
        )
        .join("")
    : '<li class="major-course">课程库里暂时没匹配到，可以到先导课页面按名字再搜搜看。</li>';

  els.detail.innerHTML = `
    <button type="button" class="major-detail-close" aria-label="关闭详情">×</button>

    <header class="major-detail-head">
      <p class="major-detail-path">${esc(data.category_name)} / ${esc(data.group)}</p>
      <h3>${esc(data.name)}</h3>
      <div class="major-stats">
        <div><b>${formatNumber(data.count)}</b><span>招生单元</span></div>
        <div><b>${data.provinces.length}</b><span>覆盖省份</span></div>
        <div><b>${data.score_median}</b><span>录取中位分</span></div>
      </div>
      <p class="major-range">${data.provinces.length} 省最低分区间 ${data.score_min}–${data.score_max}</p>
    </header>

    <section class="major-block">
      <h4>各省招生规模与中位分</h4>
      <table class="major-table">
        <thead><tr><th>省份</th><th>招生单元</th><th>中位分</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="major-block-note">招生单元数是投档表里该专业出现的条数，可以粗略看成开设院校数量。</p>
    </section>

    <section class="major-block">
      <h4>先导课</h4>
      <ul class="major-courses">${courses}</ul>
      <a class="text-link" href="./mooc.html?major=${encodeURIComponent(data.name)}">看这个专业的全部先导课 ↗</a>
    </section>

    <section class="major-block" id="major-outlook">
      <h4>四年后会怎样</h4>
      <div class="major-outlook-body">
        <div class="skeleton skeleton--line"></div>
      </div>
    </section>

    <section class="major-block" id="major-trend">
      <h4>依据：招生规模与热度变化</h4>
      <div class="major-trend-body">
        <div class="skeleton skeleton--line"></div>
      </div>
    </section>

    <p class="major-block-note">分数是 2026 年录取最低分的中位数；同一专业在不同学校差距很大，填志愿时仍以具体院校专业组为准。</p>`;
}

/**
 * 前景区：一句话判断 + 三块具体分析 + 四年路线。
 * 路线那块是写给「已经决定要走这条路」的人看的，所以只写动作，不写感慨。
 */
function renderOutlook(data) {
  const blocks = [
    ["这四年学什么", data.what, ""],
    ["毕业时的市场", data.market, ""],
    ["要付的代价", data.risk, "is-risk"],
  ]
    .filter((row) => row[1])
    .map(
      (row) => `
        <div class="outlook-item ${row[2]}">
          <h5>${row[0]}</h5>
          <p>${esc(row[1])}</p>
        </div>`
    );

  const steps = (data.path || [])
    .map((line, index) => {
      const cut = line.indexOf("：");
      const head = cut > 0 ? line.slice(0, cut) : `第 ${index + 1} 步`;
      const rest = cut > 0 ? line.slice(cut + 1) : line;
      return `<li class="outlook-step">
          <span class="outlook-step-head">${esc(head)}</span>
          <span class="outlook-step-text">${esc(rest)}</span>
        </li>`;
    })
    .join("");

  const foot = [data.signal, data.basis].filter(Boolean).map(esc).join(" ");

  return `
    <p class="outlook-verdict">${esc(data.verdict)}</p>
    <div class="outlook-grid">${blocks.join("")}</div>
    ${
      steps
        ? `<div class="outlook-route">
            <h5>如果你已经决定走这条路</h5>
            <ol class="outlook-path">${steps}</ol>
          </div>`
        : ""
    }
    <p class="outlook-note">${esc(foot)}</p>`;
}

/** 规模/热度档位 → chip 的配色类名（扩张红、收缩金、升温红、降温灰）。 */
function levelClass(level) {
  if (level.includes("扩张")) return "is-expand";
  if (level.includes("收缩")) return "is-shrink";
  if (level.includes("升温")) return "is-hot";
  if (level.includes("降温")) return "is-cool";
  return "is-flat";
}

function trendRow(row) {
  return `
    <tr>
      <td>${row.year}</td>
      <td>${formatNumber(row.units)}</td>
      <td>${formatNumber(row.colleges)}</td>
      <td>${row.median ?? "—"}</td>
      <td>${row.rank_share == null ? "—" : `${row.rank_share}%`}</td>
    </tr>`;
}

/**
 * 趋势区：能算同比的省给卡片，只有一年的省给一行说明，
 * 专业组制的省统一说明算不了——缺什么就说缺什么，不硬凑四年。
 */
function renderTrend(data) {
  const cards = [];
  const singles = [];

  for (const province of data.provinces) {
    for (const block of province.tracks) {
      if (block.status === "ok") {
        cards.push(`
          <li class="trend-card">
            <div class="trend-head">
              <b>${esc(province.province)} · ${esc(block.track)}</b>
              <span class="trend-chip ${levelClass(block.scale_level)}">${esc(block.scale_level)}</span>
              <span class="trend-chip ${levelClass(block.heat_level)}">热度${esc(block.heat_level)}</span>
            </div>
            <table class="trend-table">
              <thead>
                <tr><th>年份</th><th>招生单元</th><th>院校数</th><th>中位分</th><th>位次占比</th></tr>
              </thead>
              <tbody>${block.years.map(trendRow).join("")}</tbody>
            </table>
            ${block.note ? `<p class="trend-gap">${esc(block.note)}</p>` : ""}
          </li>`);
      } else if (block.status === "single" && block.years.length) {
        const year = block.years[0];
        singles.push(
          `<li>${esc(province.province)}（${esc(block.track)}）：只有 ${year.year} 一年，招生单元 ${formatNumber(
            year.units,
          )}、开设院校 ${formatNumber(year.colleges)}，看不了同比。</li>`,
        );
      }
    }
  }

  const parts = [`<p class="trend-summary">${esc(data.summary)}</p>`];
  if (cards.length) parts.push(`<ul class="trend-list">${cards.join("")}</ul>`);
  if (singles.length) parts.push(`<ul class="trend-flat">${singles.join("")}</ul>`);
  if (data.unsupported.length) {
    parts.push(
      `<p class="trend-gap">${data.unsupported.join("、")}按院校专业组公布投档，表里没有专业名，这些省暂时算不了专业级趋势。</p>`,
    );
  }
  parts.push(
    `<p class="major-block-note">位次占比 = 中位分对应的省内排名 ÷ 当年考生人数，越小说明这个专业在省内越靠前。分数跨年不能直接相减，所以看比例不看裸分。</p>`,
  );
  return parts.join("");
}

mountUserMenu();
bindNavMore();
init();
