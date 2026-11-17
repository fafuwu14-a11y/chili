/**
 * 培优扶弱：只读测评结果里的学科强弱，给优势科目四级路径、弱势科目失分诊断。
 * 数据来源：sessionStorage 里的 wizard 报告（chili.wizard.report.v1）。
 * 没有报告时支持 ?demo=1 用样例画像，方便演示与截图；页面上会明确标注“样例”。
 */

const REPORT_KEY = "chili.wizard.report.v1";
const AI_KEY = "chili.ai.config";

/** 每门科目的四级路径与常见失分类型。文案是教学方法论，不含任何编造的数据。 */
const SUBJECTS = {
  physics: {
    name: "物理",
    short: "物",
    color: "#E60012",
    ladder: [
      ["课内拔高", "遮住课本例题自己重做一遍，每周把错题按「受力 / 过程 / 能量」三类归档。"],
      ["竞赛入门", "限时 2 小时做一套近三年省赛预赛真题；正确率低于 40% 就停，先把课内补稳。"],
      ["强基计划", "查目标高校强基简章，确认物理是否在笔试科目里——多数学校考数学与物理。"],
      ["大学先修", "中国大学 MOOC《大学物理》前四讲，重点看微积分怎么用在变力与变加速上。"],
    ],
    weak: [
      ["概念混淆", "受力分析常漏力：先画重力，再逐个接触面找弹力与摩擦，最后补场力。"],
      ["过程断链", "多过程题不会分段：每段单独列已知量与未知量，段与段之间用速度或位移衔接。"],
      ["计算与方向", "矢量方向丢分：所有矢量先标正方向，结果带符号再解释含义。"],
    ],
  },
  chemistry: {
    name: "化学",
    short: "化",
    color: "#1F7A8C",
    ladder: [
      ["课内拔高", "方程式按「氧化还原 / 离子 / 有机」分类默写，每周默一类，错一个整类重默。"],
      ["竞赛入门", "做省赛预赛真题，重点看结构化学与有机推断，这部分课内几乎不覆盖。"],
      ["强基计划", "化学多出现在综合卷与面试，准备「一个化学现象怎么用原理解释」的口头表达。"],
      ["大学先修", "《普通化学原理》前三章，重点看化学平衡与电化学的定量计算。"],
    ],
    weak: [
      ["方程式写不全", "配平与条件常漏：写完后回头检查电荷守恒、原子守恒、反应条件三项。"],
      ["实验题读不懂", "装置图看不懂：先标出每个装置的作用（发生 / 净化 / 收集 / 尾气），再答操作。"],
      ["计算凭感觉", "物质的量换算链条断：一律先写 n = m/M 或 n = cV，再往下推。"],
    ],
  },
  biology: {
    name: "生物",
    short: "生",
    color: "#3E8E5A",
    ladder: [
      ["课内拔高", "课本原图默画：光合、呼吸、遗传图解各画一遍，标清每一步的场所与产物。"],
      ["竞赛入门", "联赛初赛真题里遗传计算占比最高，先攻这块；分子生物学部分按课内进度走。"],
      ["强基计划", "生物很少单独成科，多归在医学类强基；先确认目标专业是否要求生物。"],
      ["大学先修", "《普通生物学》细胞与遗传两章，重点看减数分裂与基因表达的联系。"],
    ],
    weak: [
      ["概念记混", "同化异化、有氧无氧常混：做成一张对照表，按「场所 / 原料 / 产物 / 能量」四列比。"],
      ["图表读不出", "曲线题看不懂：先看横纵坐标含义，再找起点、拐点、终点三个位置。"],
      ["实验设计缺对照", "答题漏对照组：任何实验设计先写「自变量、因变量、无关变量、对照」四项。"],
    ],
  },
  politics: {
    name: "政治",
    short: "政",
    color: "#B4531F",
    ladder: [
      ["课内拔高", "每单元画「概念—原理—时政」三列笔记，答题时先定位是哪一列的知识。"],
      ["竞赛入门", "没有学科竞赛，改走模拟政协、时政评论；练的是材料归纳与观点表达。"],
      ["强基计划", "文科强基很少，主要看面试；准备两三个能讲透的社会议题。"],
      ["大学先修", "《政治学原理》导论部分，重点看国家、权力、制度三个基础概念。"],
    ],
    weak: [
      ["答题口语化", "不会用术语：把「政府要管」改成「政府履行经济调节与市场监管职能」。"],
      ["材料没用上", "答案与材料两张皮：每答一点，先引材料原句，再写对应原理。"],
      ["范围答偏", "设问主体看错：先圈出「党 / 政府 / 人大 / 公民」，再决定用哪套知识。"],
    ],
  },
  history: {
    name: "历史",
    short: "史",
    color: "#8C5A2B",
    ladder: [
      ["课内拔高", "每个事件写「背景—经过—影响」三行，再串成时间轴，横向比同期中外。"],
      ["竞赛入门", "没有学科竞赛，改走史学阅读：《万历十五年》《中国历代政治得失》各读一半。"],
      ["强基计划", "历史强基集中在少数高校（古文字、考古方向），先查有没有对应专业。"],
      ["大学先修", "中国大学 MOOC《中国通史》先秦到秦汉部分，重点看史料怎么被使用。"],
    ],
    weak: [
      ["时间线混乱", "朝代顺序记不住：先背朝代歌，再把每个制度放到朝代里，不孤立背制度。"],
      ["影响答不深", "只会写「促进发展」：按「政治 / 经济 / 文化 / 对外」四个面拆开写。"],
      ["材料题跑题", "不看清材料出处：先看作者与年代，再判断这段话站在谁的立场。"],
    ],
  },
  geography: {
    name: "地理",
    short: "地",
    color: "#C9A227",
    ladder: [
      ["课内拔高", "区域地理按「位置—地形—气候—水文—人文」五步过一遍，每步只记一条主线。"],
      ["竞赛入门", "地理奥赛偏重野外与图表分析，先练等值线图与剖面图的读法。"],
      ["强基计划", "地理很少单独设强基，多在地球科学类；确认目标专业是否要求地理。"],
      ["大学先修", "《自然地理学》大气与水文两章，重点看气候成因的定量解释。"],
    ],
    weak: [
      ["图表读反", "等值线看错：先找数值递变方向，再判断是凸高为低还是凸低为高。"],
      ["成因答单因素", "只写一个原因：自然因素按「纬度 / 海陆 / 地形 / 洋流」逐条排查。"],
      ["区域定位错", "经纬度记不住：先看海陆轮廓与河流走向，再用经纬度确认。"],
    ],
  },
  technology: {
    name: "技术",
    short: "技",
    color: "#5B5BD6",
    ladder: [
      ["课内拔高", "信息技术与通用技术两本分开过；编程题不抄答案，手写一遍再上机验证。"],
      ["竞赛入门", "信息学奥赛 CSP-J/S 第一轮是笔试，先做两套真题判断要不要走这条路。"],
      ["强基计划", "信息学一般不作强基笔试科目，但竞赛奖项在综合评价里有用。"],
      ["大学先修", "《Python 程序设计》前六章，重点看列表、字典与函数的组合用法。"],
    ],
    weak: [
      ["概念与实操脱节", "会背不会做：每个知识点配一个 20 行以内的小程序，跑通再往下。"],
      ["读程序题靠猜", "不会跟变量：拿纸把每一行的变量值列出来，逐行推。"],
      ["设计题没结构", "流程图想到哪画到哪：先写输入、处理、输出三段，再补判断与循环。"],
    ],
  },
};

const ORDER = ["physics", "chemistry", "biology", "politics", "history", "geography", "technology"];
const STRONG_LINE = 62;
const WEAK_LINE = 42;

/** 演示用样例画像（明确标注，不冒充真实测评）。 */
const DEMO = {
  province: "江苏",
  subjects: { physics: 78, chemistry: 71, biology: 58, politics: 46, history: 39, geography: 52, technology: 0 },
};

const el = (id) => document.getElementById(id);
const fmt = (value) => Math.round(Number(value) || 0);

function readReport() {
  try {
    const raw = window.sessionStorage.getItem(REPORT_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    const report = saved && saved.report;
    if (!report || !report.profile || !report.profile.subject) return null;
    return {
      province: saved.province || report.province || "",
      subjects: report.profile.subject,
      combos: Array.isArray(report.combos) ? report.combos : [],
    };
  } catch {
    return null;
  }
}

function pickSource() {
  const demo = new URLSearchParams(window.location.search).get("demo");
  if (demo === "1") return { data: DEMO, demo: true };
  const report = readReport();
  if (report) return { data: report, demo: false };
  return { data: DEMO, demo: true, empty: true };
}

function renderChart(subjects, demo) {
  const box = el("gr-chart");
  box.innerHTML = "";
  // 0 分表示这套选科规则下没有这门（例如江苏没选技术），不画出来免得误导
  const visible = ORDER.filter((key) => Number(subjects[key]) > 0);
  const max = Math.max(...visible.map((key) => Number(subjects[key]) || 0), 1);
  for (const key of visible) {
    const meta = SUBJECTS[key];
    const value = Number(subjects[key]) || 0;
    const width = Math.max(2, Math.round((value / max) * 100));
    const row = document.createElement("div");
    row.className = "gr-bar";
    row.dataset.level = value >= STRONG_LINE ? "strong" : value <= WEAK_LINE ? "weak" : "mid";
    row.innerHTML = `
      <span class="gr-bar-name">${meta.name}</span>
      <span class="gr-bar-track"><i style="width:${width}%;background:${meta.color}"></i></span>
      <span class="gr-bar-value">${fmt(value)}</span>
    `;
    box.appendChild(row);
  }
  if (demo) {
    const hint = document.createElement("p");
    hint.className = "gr-chart-note";
    hint.textContent = "当前展示的是样例画像（江苏 · 物理向）。做完测评后这里会换成你自己的分数。";
    box.appendChild(hint);
  }
}

function ladderCard(key, score) {
  const meta = SUBJECTS[key];
  const steps = meta.ladder
    .map(
      (item, index) => `
      <li class="gr-step">
        <span class="gr-step-no">${index + 1}</span>
        <div>
          <p class="gr-step-title">${item[0]}</p>
          <p class="gr-step-text">${item[1]}</p>
        </div>
      </li>`,
    )
    .join("");
  return `
    <article class="gr-card gr-card--strong">
      <header class="gr-card-head">
        <span class="gr-dot" style="background:${meta.color}"></span>
        <h3>${meta.name}</h3>
        <span class="gr-score">${fmt(score)}</span>
      </header>
      <p class="gr-card-note">按顺序走，别一次上四级。</p>
      <ol class="gr-steps">${steps}</ol>
    </article>`;
}

function weakCard(key, score) {
  const meta = SUBJECTS[key];
  const items = meta.weak
    .map(
      (item) => `
      <li class="gr-weak-item">
        <p class="gr-weak-title">${item[0]}</p>
        <p class="gr-weak-text">${item[1]}</p>
      </li>`,
    )
    .join("");
  return `
    <article class="gr-card gr-card--weak">
      <header class="gr-card-head">
        <span class="gr-dot" style="background:${meta.color}"></span>
        <h3>${meta.name}</h3>
        <span class="gr-score">${fmt(score)}</span>
      </header>
      <p class="gr-card-note">先对号入座，再决定补哪一块。</p>
      <ul class="gr-weak-list">${items}</ul>
    </article>`;
}

function split(subjects) {
  const rows = ORDER.filter((key) => Number(subjects[key]) > 0).map((key) => ({ key, score: Number(subjects[key]) || 0 }));
  const strong = rows.filter((row) => row.score >= STRONG_LINE).sort((a, b) => b.score - a.score);
  const weak = rows.filter((row) => row.score > 0 && row.score <= WEAK_LINE).sort((a, b) => a.score - b.score);
  const mid = rows.filter((row) => !strong.includes(row) && !weak.includes(row));
  // 一个都不达标时，至少给最高和最低各一张卡，避免页面空着
  if (!strong.length && rows.length) strong.push([...rows].sort((a, b) => b.score - a.score)[0]);
  if (!weak.length && rows.length) {
    const lowest = [...rows].sort((a, b) => a.score - b.score)[0];
    if (!strong.some((row) => row.key === lowest.key)) weak.push(lowest);
  }
  return { strong, weak, mid };
}

function render(source) {
  const { data, demo, empty } = source;
  const subjects = data.subjects || {};
  const { strong, weak, mid } = split(subjects);

  el("gr-source-tag").textContent = demo
    ? empty
      ? "没找到你的测评结果 · 下面是样例"
      : "样例数据 · 从 ?demo=1 进入"
    : `基于 ${data.province || "你的省份"} 的测评结果`;

  renderChart(subjects, demo);

  el("gr-strong").innerHTML = strong.length
    ? strong.map((row) => ladderCard(row.key, row.score)).join("")
    : `<p class="gr-empty">这次没有明显优势科目，先把最高的一门稳住。</p>`;

  el("gr-weak").innerHTML = weak.length
    ? weak.map((row) => weakCard(row.key, row.score)).join("")
    : `<p class="gr-empty">没有明显短板，把时间放回优势科目上。</p>`;

  el("gr-mid").innerHTML = mid.length
    ? mid
        .map(
          (row) =>
            `<li><span class="gr-dot" style="background:${SUBJECTS[row.key].color}"></span>${SUBJECTS[row.key].name}<b>${fmt(row.score)}</b><em>保持课堂节奏，不额外加练</em></li>`,
        )
        .join("")
    : `<li class="gr-empty">七门都在优势或待补里，按上面的卡片走就行。</li>`;
}

function toast(text) {
  const node = el("gr-toast");
  node.textContent = text;
  node.hidden = false;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => {
    node.hidden = true;
  }, 2600);
}

function bindShell() {
  const burger = el("gr-burger");
  const nav = el("gr-nav");
  if (burger && nav) {
    burger.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      burger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.addEventListener("click", (event) => {
      if (event.target.closest("a")) nav.classList.remove("is-open");
    });
  }

  import("./login-modal.js")
    .then(({ mountLoginButton }) => {
      mountLoginButton({ slot: document.querySelector("[data-login-slot]") });
    })
    .catch(() => {});

  const aiOpen = el("gr-ai-open");
  if (aiOpen) {
    aiOpen.addEventListener("click", () => {
      window.location.href = "./ai-setup.html";
    });
  }
}

function init() {
  bindShell();
  try {
    render(pickSource());
  } catch (error) {
    el("gr-chart").innerHTML = `<p class="gr-empty">页面渲染出错：${error.message}</p>`;
  }
  // AI 配置只用来判断是否已接模型，本页不调用模型
  try {
    if (window.localStorage.getItem(AI_KEY)) el("gr-ai-open").textContent = "AI 已连接";
  } catch {
    /* 隐私模式下忽略 */
  }
}

init();
