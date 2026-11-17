/** 一分一段查询：分数 ↔ 位次互查，并对齐近三年。 */

import { api } from "./api.js";
import { mountUserMenu, bindNavMore } from "./session.js";
import { escapeHtml as esc, formatNumber as nf, toast } from "./ui.js";

const state = { meta: null };

const els = {
  form: document.getElementById("curve-form"),
  province: document.getElementById("province"),
  track: document.getElementById("track"),
  score: document.getElementById("score"),
  rank: document.getElementById("rank"),
  submit: document.getElementById("curve-submit"),
  hint: document.getElementById("curve-input-hint"),
  examples: document.getElementById("curve-examples"),
  result: document.getElementById("curve-result"),
  title: document.getElementById("curve-title"),
  meta: document.getElementById("curve-meta"),
  cards: document.getElementById("curve-cards"),
  rows: document.getElementById("curve-rows"),
  note: document.getElementById("curve-note"),
  loading: document.getElementById("loading"),
};

/** 示例分数按当前省份的本科线现算，换省/换科类都不会挂着上一个省的数。 */
const EXAMPLE_OFFSETS = [150, 90, 30];

function exampleCases() {
  const province = els.province.value;
  const track = els.track.value;
  const info = state.meta.provinces[province];
  if (!info) return [];
  const line = (info.line || {})[track];
  if (typeof line !== "number") return [];
  return EXAMPLE_OFFSETS.map((offset) => ({ province, track, score: line + offset }));
}

async function boot() {
  try {
    state.meta = await api.meta();
  } catch (error) {
    toast(error.message);
    return;
  }

  mountUserMenu();
  bindNavMore();
  fillProvinces();
  syncTracks();
  renderExamples();

  els.province.addEventListener("change", syncTracks);
  els.track.addEventListener("change", updateHint);
  els.track.addEventListener("change", renderExamples);
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    query();
  });
  els.score.addEventListener("input", () => {
    if (els.score.value.trim()) els.rank.value = "";
    updateHint();
  });
  els.rank.addEventListener("input", () => {
    if (els.rank.value.trim()) els.score.value = "";
    updateHint();
  });

  applyFromUrl();
}

function fillProvinces() {
  els.province.innerHTML = Object.entries(state.meta.provinces)
    .map(([name]) => {
      return `<option value="${esc(name)}">${esc(name)}</option>`;
    })
    .join("");
}

function syncTracks() {
  if (!state.meta) return;
  const info = state.meta.provinces[els.province.value];
  const tracks = info.tracks || [];
  if (!tracks.length) {
    els.track.innerHTML = `<option value="">暂无数据</option>`;
    els.track.disabled = true;
    els.submit.disabled = true;
  } else {
    els.track.innerHTML = tracks.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    els.track.disabled = false;
    els.submit.disabled = false;
  }
  updateHint();
}

function updateHint() {
  if (!state.meta) return;
  const province = els.province.value;
  const info = state.meta.provinces[province];
  const track = els.track.value;
  const line = (info.line || {})[track];
  const candidates = (info.candidates || {})[track];
  if (!line || !candidates) {
    // 只收录分数齐全的省份，正常不会走到这里；真缺了就说清楚缺什么。
    els.hint.textContent = `${province} 暂时没有${track}的数据，换个科类试试。`;
    return;
  }
  const year = state.meta.years[state.meta.years.length - 1];
  els.hint.textContent = `${province} · ${track} · ${year} 本科线 ${line} 分 · 表内 ${nf(candidates)} 人，分数与位次可互查。`;
}

function renderExamples() {
  if (!state.meta) return;
  const cases = exampleCases();
  els.examples.innerHTML = cases
    .map(
      (item) =>
        `<button type="button" class="example" data-province="${esc(item.province)}" data-track="${esc(item.track)}" data-score="${item.score}">${esc(item.province)} ${esc(item.track)} <b>${item.score}</b></button>`,
    )
    .join("");
  els.examples.querySelectorAll("[data-score]").forEach((button) => {
    button.addEventListener("click", () => {
      els.province.value = button.dataset.province;
      syncTracks();
      els.track.value = button.dataset.track;
      els.score.value = button.dataset.score;
      els.rank.value = "";
      updateHint();
      query();
    });
  });
}

function applyFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const province = params.get("province");
  const track = params.get("track");
  if (province && state.meta.provinces[province]) {
    els.province.value = province;
    syncTracks();
    if (track && (state.meta.provinces[province].tracks || []).includes(track)) {
      els.track.value = track;
    }
  }
  const score = params.get("score");
  const rank = params.get("rank");
  if (score) els.score.value = score;
  if (rank) els.rank.value = rank;
  updateHint();
  renderExamples();
  if (score || rank) query();
}

function setBusy(isBusy) {
  els.loading.hidden = !isBusy;
  els.submit.disabled = isBusy;
}

async function query() {
  const province = els.province.value;
  const track = els.track.value;
  const scoreText = els.score.value.trim();
  const rankText = els.rank.value.trim();

  if (!scoreText && !rankText) {
    toast("填一个分数或位次就能查");
    els.score.focus();
    return;
  }
  if (scoreText) {
    const score = Number(scoreText);
    if (!Number.isFinite(score) || score < 0 || score > 750) {
      toast("分数需要在 0 ~ 750 之间");
      els.score.focus();
      return;
    }
  }
  if (rankText) {
    const rank = Number(rankText);
    if (!Number.isFinite(rank) || rank < 1) {
      toast("位次需要大于 0");
      els.rank.focus();
      return;
    }
  }

  setBusy(true);
  try {
    const data = await api.curve({
      province,
      track,
      score: scoreText || null,
      rank: rankText || null,
    });
    render(data);
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(false);
  }
}

function render(data) {
  const latest = data.rows[0];
  const oldest = data.rows[data.rows.length - 1];
  const inputMode = data.input.score !== null && data.input.score !== undefined ? "score" : "rank";

  els.title.textContent = inputMode === "score" ? `${latest.score} 分在全省的位次` : `全省第 ${nf(latest.rank)} 名对应的分数`;
  els.meta.textContent = `${data.province} · ${data.track} · 覆盖 ${data.years[data.years.length - 1]}–${data.years[0]} 年 · 本科线 ${data.line} 分 · 表内 ${nf(data.candidates)} 人`;

  els.cards.innerHTML = data.rows
    .map((row, index) => {
      const isLatest = index === 0;
      return `
        <article class="curve-card${isLatest ? " is-latest" : ""}">
          <p class="curve-year">${row.year} 年${isLatest ? " · 最新" : ""}</p>
          <p class="curve-rank"><b>${nf(row.rank)}</b><i>名</i></p>
          <p class="curve-sub">${row.score} 分 · 超本科线 ${row.above_line} 分 · 全省前 ${row.percentile}%</p>
        </article>`;
    })
    .join("");

  els.rows.innerHTML = data.rows
    .map(
      (row) => `
        <tr>
          <td>${row.year}</td>
          <td>${row.score}</td>
          <td>${nf(row.rank)}</td>
          <td>${row.above_line} 分</td>
          <td>${row.line}</td>
          <td>${nf(row.candidates)}</td>
        </tr>`,
    )
    .join("");

  const diff = latest.rank - oldest.rank;
  const trend =
    diff === 0
      ? "三年里同一分数对应的位次基本没变，题目难度和考生规模都比较稳定。"
      : `同样 ${latest.score} 分，${latest.year} 年比 ${oldest.year} 年${diff > 0 ? "靠后" : "靠前"} ${nf(Math.abs(diff))} 名——${diff > 0 ? "考生变多或试卷变简单时，同样的分数会被稀释" : "说明高分段人数变少，同样的分数更值钱"}。这也是为什么填志愿要看位次，而不是直接比分数。`;

  els.note.textContent = `${trend} 数据来自 ${data.province}教育考试院公布的逐分段统计表，只统计到本科线以上；` +
    `本科线以下的考生不在这张表里。${data.note}`;

  els.result.hidden = false;
  els.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

boot();
