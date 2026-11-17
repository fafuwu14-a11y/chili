# 下一步 · 断点指引

> **新对话接手先读这一页。** 读完就知道项目在哪、怎么跑、从哪继续。
> 详细历史看 [`WORKLOG.md`](WORKLOG.md)，长周期规划看 [`PLAN-cup-2027.md`](PLAN-cup-2027.md)，早期技术细节看 [`HANDOVER-2026-11-11.md`](HANDOVER-2026-11-11.md)。

**最后更新**：2026-11-15 12:40

---

## 一句话现状

赤鲤平台（高考志愿 + 专业画像 + 课程推荐）已到可演示状态：8 省真实数据、821 个专业条目、**736 个专业有结构化画像**、**614 门课含 270 门手写知识点**、专业对比页、235 个测试全绿、Windows 单文件 exe 可打包。下一阶段：把画像里的「推算区间」换成有出处的数据，然后做培优模块。

---

## 环境事实（照着敲就行）

| 项 | 值 |
| --- | --- |
| 项目根 | `E:\大肥鱼工作区\gaokao-platform` |
| 跑测试 | `cd "E:\大肥鱼工作区" && PYTHONIOENCODING=utf-8 python realdata/tmp_run_tests.py`（**脚本在项目外**，chdir 到 backend 跑） |
| 起服务 | `cd gaokao-platform && python run.py --data real [--port 8123] [--no-open]` |
| 打包 exe | `cd gaokao-platform && python build_exe.py`（沙箱里需要 `danger-full-access`，PyInstaller 要建管道） |
| Node（做 JS 语法检查） | `C:\Users\零下80s\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe`，PATH 里没有 |
| 登录账号 | `f79639802022@163.com` / `Chili2026`（用户本人，users id=3） |
| 演示账号 | `demo@chili.local` / `ZHAwSRJFpw6J`（users id=11，给评委用） |
| 数据 | `backend/data/` 八省目录 + `major_catalog.json`（821 专业 / 94,790 单元）+ `major_profile.json`（**736 条画像**，733 推算 / 3 人工） |
| 测试数 | 235（auth 49 / catalog 18 / direction 28 / outlook 14 / trend 24 / profile 21 / quant 11 / mooc 10 / planner 14 / predictor 15 / quiz 31） |
| 版本控制 | **项目不是 git 仓库**，改坏了只能靠 `scratch/backup-gaokao-20261113.zip` 回滚 |
| 线上演示 | `https://jacket-valuation-positioning-paste.trycloudflare.com/`（临时隧道，会变，用完要关） |

### 不可违反的约定

1. 纯标准库后端，**不加任何第三方依赖**
2. 原生 ES Module 前端，**不加构建步骤**、不引框架
3. 中文注释
4. 接口失败返回 `400` + `{"ok": false, "error": "..."}`（**不是** 200，`api.js` 靠 `ok === false` 判错、靠 401 跳登录）
5. 样式只用 `css/app.css` 里的 CSS 变量，不写死颜色
6. 数据「缺不占位」：缺省份/年份就明说，不硬凑

---

## 明天（2026-11-15）任务队列

按顺序做，**每完成一项立刻往 `WORKLOG.md` 顶部写一条**，然后从这里划掉。

| # | 任务 | 验收标准 | 预计 | 依赖 |
| --- | --- | --- | --- | --- |
| ~~1~~ | ~~**专业画像 schema + 3 条样例**~~ ✅ 2026-11-15 12:10 | `major_profile.py` + 3 条样例 + 21 测试 + 两个只读接口 | 2h | — |
| ~~2~~ | ~~**演示账号**~~ ✅ 2026-11-15 12:10 | `demo@chili.local` 登录 200，密码 `ZHAwSRJFpw6J` | 20min | — |
| ~~3~~ | ~~**六维量化（56 个专业类）**~~ ✅ 12:14 | `major_quant.py`：56 类基准分 + 关键词修正 + explain() | 1.5h | 1 的字段定义 |
| ~~4~~ | ~~**雷达图组件 + 对比 demo**~~ ✅ 12:14 | `compare.html` + `compare.js` 手写 SVG；`/api/major/compare`；未做真浏览器验证 | 2.5h | 3 |
| ~~5~~ | ~~**821 条批量生成（先跑 100 条试水）**~~ ✅ 12:36 | 已推到全部 **736 个专业**（55 个专业类全覆盖），抽检 10 条长尾专业；`estimated` 标记与来源写在数据里 | 2h | 1、3 |
| 6 | **收尾** | `WORKLOG.md` 写完、本文件更新、测试重跑 | 20min | 全部 |

**画像覆盖**：`backend/data/major_profile.json` 现有 **736 条**（733 条推算 / 3 条人工），覆盖目录里全部非专业类条目；55 个专业类全有模板。
**质量口径**：`employment` / `postgrad` / `salary` 三段区间，733 条是 `estimated: true`（按专业类通用区间推算，note 里点名「不是本专业单独统计」），只有 3 条人工样例 `estimated: false`。答辩时不能说成统计数据。

**合格线**：做完 1–4 = 今天合格；只做完 1–2 = 也算（地基比数量重要）。
**不要做**：exe 真机验证（等用户）、扩省数据下载（要联网抓）、培优题库（重，排到后面）。

---

## 已确认的坑（别重复踩）

1. `realdata/tmp_run_tests.py` **不在项目内**，在工作区根 `E:\大肥鱼工作区\realdata\`。
2. PATH 里的 `python` 不是项目用的那个；用 DSH 的 bundled python（`C:/Users/零下80s/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe`）。
3. 改 `major_catalog.json` 后必须重跑 `python tmp_build_catalog.py`，且 catalog 与 `major_trend.py` 的 `normalise` 规则要一致（都是 `strip_brackets` 栈式解析）。
4. 匹配题量硬编码在多处：`quiz_data.SPECS`（18/40/54）、`test_quiz.py` 的 `test_spec_counts` 与 `test_specs_are_nested_prefixes`。改一处必须改三处。
5. `major_catalog.meta()` 的 `groups` 嵌在 `categories[].groups` 里，**没有顶层 groups**。
6. 专业目录只有浙、鲁、冀、辽四省有专业级分数（其余省是院校专业组制，表里没专业名）。
7. `api.js` 的 401 跳转对 `/api/auth/` 前缀豁免，其余全跳登录；需要静默探测时传 `silent401`。
8. 沙箱里跑 PyInstaller 会 `PermissionError: [WinError 5]`，要 `sandbox_permissions: danger-full-access`。

---

## 当前数据事实

| 项 | 值 |
| --- | --- |
| 省份 | 江苏、广东、湖北、山西、辽宁、浙江、山东、河北（8 省，无占位） |
| 年份 | 江苏/广东 2024–2026；山西 2025–2026；辽宁 2024+2026（缺 2025）；湖北/河北/浙江/山东只有 2026 |
| 专业 | 821 个，12 门类、56 个专业类 |
| 专业级分数 | 只有浙、鲁、冀、辽四省（`by_province` = he/ln/sd/zj） |
| 趋势可比 | 只有辽宁能做 2024→2026 同比 |
| 回测 | 江苏全量：中位误差 8.0 分，≤5 分 29.9%，≤10 分 60.2% |

---

## 一页架构

```
backend/app/
  server.py        646  路由与静态服务，链式 if
  auth.py          674  PBKDF2 口令、会话、限流、CSRF
  real_data.py     533  八省数据装配，PROVINCES / PROVINCE_CODES
  predictor.py     437  位次等值法预测
  planner.py       201  冲稳保志愿表
  quiz_data.py     294  18/40/54 三档题库 + 21 条大类画像
  matcher.py       554  六维余弦匹配 + 方向细分 + 硬条件惩罚
  major_catalog.py 159  821 专业检索
  major_direction.py 452 六轴方向题 + 56 类方向画像
  major_trend.py   425  招生规模/热度同比（有多少年算多少年）
  major_outlook.py 1044 专业前景：56 类画像 + 关键词细分 + 4 条路径
  mooc_data.py     320  课程推荐：40 门口碑课 + 614 门主干课（读 course_catalog.json）

frontend/  13 个页面 + 12 个 ES Module
  页面：index / predict / plan / quiz / major / mooc / curve / about / help / login / privacy / terms / error
```

---

## 下一个大目标的起点

P2 画像一期、P3 课程地图都已完成（`major_profile.py` + `major_quant.py` + `course_catalog.json`）。下一步是 **P4 培优模块**，申报书里承诺的是「诊断—归因—训练—反馈」四段 + 优势科目四级路径 + 弱势科目按知识点组卷 + 知识点映射到课程片段。

**必须先降级再做**：只做**数学·高一**一个学科。理由写在 `docs/PLAN-cup-2027.md`：九科题库做不完，一科做扎实反而能在答辩时讲清楚。入口建议 `backend/app/tutor_data.py`（知识点树 + 题目）+ `backend/app/tutor.py`（诊断与组卷），数据从人教版高中数学必修一/二的知识点开始。

做之前先确认两件事：题库从哪来（自编 or 公开教辅）、错题推送要做到什么粒度。不要先写前端。
