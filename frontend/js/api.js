/** Thin wrapper around the JSON API. */

const BASE = "";

/** 登录页地址，带回当前页面，登录后原地返回。 */
function loginUrl() {
  const next = window.location.pathname + window.location.search;
  const suffix = next && next !== "/" && next !== "/index.html" ? `?next=${encodeURIComponent(next)}` : "";
  return `/login.html${suffix}`;
}

async function request(path, options = {}) {
  // silent401: 只探测用（门户首页问「现在登录了吗」），401 时不要把人踢去登录页
  const { silent401 = false, ...init } = options;
  let response;
  try {
    response = await fetch(BASE + path, { credentials: "same-origin", ...init });
  } catch {
    throw new Error("网络连接中断，请检查网络后重试");
  }
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    /* empty body */
  }
  // 会话过期：除了登录/注册接口本身，其余一律送回登录页
  if (response.status === 401 && !silent401 && !path.startsWith("/api/auth/")) {
    window.location.href = loginUrl();
    const error = new Error("登录已过期，请重新登录");
    error.status = 401;
    throw error;
  }
  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.error || `请求失败（${response.status}）`);
    error.status = response.status;
    error.code = payload.code || "";
    throw error;
  }
  return payload.data;
}

export const api = {
  me() {
    return request("/api/auth/me");
  },

  login(email, password) {
    return request("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  },

  register(email, password) {
    return request("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  },

  logout() {
    return request("/api/auth/logout", { method: "POST" });
  },

  meta(silent401 = false) {
    return request("/api/meta", { silent401 });
  },

  predict({ province, track, score, rank, tier, college }) {
    const body = { province, track };
    if (score !== null && score !== undefined && score !== "") body.score = Number(score);
    if (rank !== null && rank !== undefined && rank !== "") body.rank = Number(rank);
    if (tier) body.tier = tier;
    if (college) body.college = college; // 只看一所学校时传 college_id
    body.limit = 200; // 与后端上限一致；再大也会被夹回 200
    return request("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  college(collegeId, province, track) {
    const params = new URLSearchParams({ province, track });
    return request(`/api/college/${encodeURIComponent(collegeId)}?${params}`);
  },

  colleges({ q, province, track, limit = 8 }) {
    const params = new URLSearchParams({ q, province, track, limit: String(limit) });
    return request(`/api/colleges?${params}`);
  },

  plan({ province, track, score, rank, chong, wen, bao, mode }) {
    const body = { province, track };
    if (score !== null && score !== undefined && score !== "") body.score = Number(score);
    if (rank !== null && rank !== undefined && rank !== "") body.rank = Number(rank);
    for (const [key, value] of Object.entries({ chong, wen, bao })) {
      if (value !== null && value !== undefined && value !== "") body[key] = Number(value);
    }
    if (mode && mode !== "auto") body.mode = mode;
    return request("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  curve({ province, track, score, rank }) {
    const params = new URLSearchParams({ province, track });
    if (score !== null && score !== undefined && score !== "") params.set("score", String(score));
    if (rank !== null && rank !== undefined && rank !== "") params.set("rank", String(rank));
    return request(`/api/curve?${params}`);
  },
  mooc(major, limit = 6) {
    const params = new URLSearchParams({ major, limit: String(limit) });
    return request(`/api/mooc?${params}`);
  },

  moocMajors() {
    return request("/api/mooc/majors");
  },

  /** 专业目录：门类树 */
  majorMeta() {
    return request("/api/major/meta");
  },

  /** 专业列表，q / category / group 都可选 */
  majors({ q, category, group, limit = 60 } = {}) {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    if (group) params.set("group", group);
    params.set("limit", String(limit));
    return request(`/api/majors?${params}`);
  },

  /** 单专业详情（含分省规模、中位分、先导课分支） */
  majorDetail(name) {
    const params = new URLSearchParams({ name });
    return request(`/api/major/detail?${params}`);
  },

  /** 专业趋势预警：有多少年算多少年，缺的年份在返回里标出来 */
  majorTrend(name) {
    const params = new URLSearchParams({ name });
    return request(`/api/major/trend?${params}`);
  },

  /** 专业前景：学什么、毕业时的市场、要付的代价、四年怎么走 */
  majorOutlook(name) {
    const params = new URLSearchParams({ name });
    return request(`/api/major/outlook?${params}`);
  },

  /** 结构化画像：课程、职业、考公考研、创业五维、六维雷达分 */
  majorProfile(name) {
    const params = new URLSearchParams({ name });
    return request(`/api/major/profile?${params}`);
  },

  /** 专业对比：2–4 个专业，返回雷达图直接可用的结构 */
  majorCompare(names) {
    const params = new URLSearchParams();
    names.forEach((name) => params.append("name", name));
    return request(`/api/major/compare?${params}`);
  },

  quiz() {
    return request("/api/quiz");
  },

  quizSpec(key) {
    return request(`/api/quiz/${encodeURIComponent(key)}`);
  },

  match({ spec, answers, limit }) {
    const body = { spec, answers };
    if (limit) body.limit = Number(limit);
    return request("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  // -- 选科向导 ---------------------------------------------------------
  // 向导页未登录也能用，所以这里探测会话必须带 silent401，避免一进页面就被踢去登录
  session() {
    return request("/api/auth/me", { silent401: true });
  },

  /** 省份、科目、专业类要求、问卷元信息（题库本体在 /api/choice/quiz） */
  choiceMeta() {
    return request("/api/choice/meta");
  },

  /** 两版题库（simple 23 题 / deep 56 题），只给题干与选项，不含计分权重 */
  choiceQuiz(edition = "simple") {
    const params = new URLSearchParams({ edition });
    return request(`/api/choice/quiz?${params}`);
  },

  /** 某省的全部选科组合，用于第 1 步解释「你们省有几种选法」 */
  choiceCombos(province) {
    const params = new URLSearchParams({ province });
    return request(`/api/choice/combos?${params}`);
  },

  /** 规则引擎出报告；top_combos 取 1–6，换一批就靠它多要几组 */
  choiceReport({ province, answers, topCombos = 3, topMajors = 12, edition = "simple" }) {
    return request("/api/choice/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        province,
        answers,
        edition,
        top_combos: Number(topCombos),
        top_majors: Number(topMajors),
      }),
    });
  },

  // 课程库按账号开放；未登录返回 401，由页面自己给登录引导而不是整页跳转
  choiceMooc({ major, limit = 4 } = {}) {
    const params = new URLSearchParams();
    if (major) params.set("major", major);
    if (limit) params.set("limit", String(limit));
    return request(`/api/mooc?${params}`, { silent401: true });
  },

  /** 专业对应的院校优势；接口未上线时页面要能降级，不要静默卡住 */
  majorColleges({ name, province, track, limit = 20 } = {}) {
    const params = new URLSearchParams({ name });
    if (province) params.set("province", province);
    if (track) params.set("track", track);
    if (limit) params.set("limit", String(limit));
    return request(`/api/major/colleges?${params}`, { silent401: true });
  },

  /** AI 厂商目录是公开的，配置弹窗打开时就能拉 */
  aiProviders() {
    return request("/api/ai/providers");
  },

  /** Key 随请求体一次性传给后端，不落盘；json=true 时要求模型只吐 JSON */
  aiChat({ ai, messages, json = false }) {
    // 向导页自己处理未登录：弹登录而不是整页跳转，所以这里必须 silent401
    return request("/api/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ai, messages, json: Boolean(json) }),
      silent401: true,
    });
  },

  aiPing({ ai }) {
    return request("/api/ai/ping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ai }),
      silent401: true,
    });
  },
};
