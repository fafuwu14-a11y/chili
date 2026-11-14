import { api } from "./api.js";
import { escapeHtml as esc, toast } from "./ui.js";
import { mountUserMenu, bindNavMore } from "./session.js";

const QUICK_MAJORS = [
  "计算机科学与技术",
  "临床医学",
  "金融学类",
  "法学",
  "汉语言文学",
  "数学类",
  "电子信息类",
  "会计学",
];

const PLATFORM_CLASS = {
  中国大学MOOC: "is-mooc",
  学堂在线: "is-xuetang",
  B站: "is-bili",
  网易公开课: "is-163",
};

const state = { majors: [], major: "" };

const els = {
  form: document.getElementById("mooc-form"),
  major: document.getElementById("major"),
  options: document.getElementById("major-options"),
  quick: document.getElementById("quick-majors"),
  submit: document.getElementById("mooc-submit"),
  result: document.getElementById("mooc-result"),
  meta: document.getElementById("mooc-meta"),
  courses: document.getElementById("courses"),
  tip: document.getElementById("mooc-tip"),
  loading: document.getElementById("loading"),
};

async function init() {
  bind();
  renderQuick();
  try {
    state.majors = await api.moocMajors();
    els.options.innerHTML = state.majors.map((name) => `<option value="${esc(name)}"></option>`).join("");
  } catch {
    /* datalist is a nicety; the page still works without it */
  }

  const fromUrl = new URLSearchParams(window.location.search).get("major");
  if (fromUrl) {
    els.major.value = fromUrl;
    await recommend(fromUrl, { scroll: false });
  }
}

function bind() {
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = els.major.value.trim();
    if (!value) {
      toast("请先填写专业名称");
      els.major.focus();
      return;
    }
    recommend(value);
  });

  els.quick.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-major]");
    if (!button) return;
    els.major.value = button.dataset.major;
    recommend(button.dataset.major);
  });
}

function renderQuick() {
  els.quick.innerHTML = QUICK_MAJORS.map(
    (name) => `<button type="button" class="example" data-major="${esc(name)}">${esc(name)}</button>`,
  ).join("");
}

async function recommend(major, { scroll = true } = {}) {
  setLoading(true);
  try {
    const data = await api.mooc(major, 6);
    state.major = data.major;
    render(data);
    const params = new URLSearchParams({ major: data.major });
    window.history.replaceState(null, "", `?${params}`);
    if (scroll) {
      const top = els.result.getBoundingClientRect().top + window.scrollY - 80;
      window.scrollTo({ top, behavior: "smooth" });
    }
  } catch (error) {
    toast(error.message);
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  els.loading.hidden = !isLoading;
  els.submit.disabled = isLoading;
  els.submit.firstElementChild.textContent = isLoading ? "推荐中…" : "推荐先导课";
}

function render(data) {
  els.result.hidden = false;
  els.meta.innerHTML = `专业 <b>${esc(data.major)}</b> · 为你挑了 <b>${data.total}</b> 门课，按相关度排序`;
  els.courses.innerHTML = data.items.map(courseCard).join("");
  els.tip.textContent = data.tip;
}

function courseCard(item) {
  const platformClass = PLATFORM_CLASS[item.platform] || "";
  return `
    <article class="course">
      <header class="course-head">
        <span class="course-platform ${platformClass}">${esc(item.platform)}</span>
        <span class="course-level">${esc(item.level)}</span>
        <span class="course-match ${item.match ? "" : "course-match--general"}">${
          item.match ? `匹配 <b>${item.match}</b>` : "通识补充"
        }</span>
      </header>

      <h3>${esc(item.title)}</h3>
      <p class="course-provider">${esc(item.provider)}</p>

      <dl class="course-meta">
        <div><dt>建议投入</dt><dd>${item.weeks} 周</dd></div>
        <div><dt>评分</dt><dd>${item.rating.toFixed(1)}</dd></div>
        <div><dt>学习人数</dt><dd>${esc(item.learners)}</dd></div>
      </dl>

      <p class="course-desc">${esc(item.desc)}</p>

      <div class="course-foot">
        <div class="tags">${item.tags.map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</div>
        <a class="course-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">
          去平台看看
          <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </a>
      </div>

      <p class="course-reason">${esc(item.reason)}</p>
    </article>`;
}

mountUserMenu();
bindNavMore();
init();
