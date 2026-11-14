/**
 * 门户页脚本：只做两件事——填省份下拉、把分数带到预测页。
 * 不加载预测模型，不请求 /api/predict，保证首页首屏快。
 */

import { api } from "./api.js";
import { mountUserMenu, bindNavMore } from "./session.js";

const els = {
  form: document.getElementById("portal-quick"),
  province: document.getElementById("q-province"),
  track: document.getElementById("q-track"),
  score: document.getElementById("q-score"),
  hint: document.getElementById("quick-hint"),
  toast: document.getElementById("toast"),
};

let meta = null;
let toastTimer = 0;

function toast(message) {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 2600);
}

function availableProvinces() {
  if (!meta) return [];
  return Object.entries(meta.provinces)
    .filter(([, info]) => info.available !== false && (info.tracks || []).length)
    .map(([name]) => name);
}

function syncTracks() {
  if (!meta) return;
  const info = meta.provinces[els.province.value];
  const tracks = (info && info.tracks) || [];
  els.track.innerHTML = tracks
    .map((t) => `<option value="${t}">${t}</option>`)
    .join("") || `<option value="">暂无数据</option>`;
  els.track.disabled = !tracks.length;
  syncHint();
}

function syncHint() {
  if (!meta) return;
  const province = els.province.value;
  const info = meta.provinces[province];
  if (!info) return;
  const line = info.line || {};
  const track = els.track.value;
  const cut = line[track];
  if (cut) {
    els.hint.textContent = `${province} · ${track} · ${meta.years[meta.years.length - 1]} 本科线 ${cut} 分。填分数，或直接点下面的卡片。`;
  } else {
    els.hint.textContent = "填分数，或直接点下面的卡片从任意一步开始。";
  }
}

function onSubmit(event) {
  event.preventDefault();
  const province = els.province.value;
  const track = els.track.value;
  const raw = els.score.value.trim();

  if (!province || !track) {
    toast("先选一个省份和科类");
    return;
  }
  if (!raw) {
    els.score.focus();
    toast("填一个分数，或者直接点下面的功能卡");
    return;
  }
  const score = Number(raw);
  if (!Number.isFinite(score) || score < 0 || score > 750) {
    els.score.focus();
    toast("分数要在 0 – 750 之间");
    return;
  }

  const params = new URLSearchParams({ province, track, score: String(score) });
  window.location.href = `./predict.html?${params}`;
}

function ping() {
  // 后端没起来时，别让用户以为是自己填错了
  const sid = window.setTimeout(() => {
    els.hint.textContent = "连不上服务：确认 python run.py 的窗口还开着。";
  }, 4000);
  api
    .meta()
    .then((data) => {
      window.clearTimeout(sid);
      meta = data;
      const names = availableProvinces();
      els.province.innerHTML = names
        .map((name) => `<option value="${name}">${name}</option>`)
        .join("");
      syncTracks();
    })
    .catch(() => {
      window.clearTimeout(sid);
      els.hint.textContent = "连不上服务：确认 python run.py 的窗口还开着。";
    });
}

function init() {
  mountUserMenu();
  bindNavMore();
  ping();
  els.province.addEventListener("change", syncTracks);
  els.track.addEventListener("change", syncHint);
  els.form.addEventListener("submit", onSubmit);
}

init();
