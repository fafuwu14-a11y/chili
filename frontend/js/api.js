/** Thin wrapper around the JSON API. */

const BASE = "";

/** 登录页地址，带回当前页面，登录后原地返回。 */
function loginUrl() {
  const next = window.location.pathname + window.location.search;
  const suffix = next && next !== "/" && next !== "/index.html" ? `?next=${encodeURIComponent(next)}` : "";
  return `/login.html${suffix}`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(BASE + path, { credentials: "same-origin", ...options });
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
  if (response.status === 401 && !path.startsWith("/api/auth/")) {
    window.location.href = loginUrl();
    throw new Error("登录已过期，请重新登录");
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

  meta() {
    return request("/api/meta");
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
};
