# 赤鲤 · 工作日志

> 倒序排列，最新在最上面。一条 = 一次可验收的交付，不是「改了点什么」的流水账。
> 新对话接手时：**先读 [`NEXT.md`](NEXT.md) 看下一步**，再翻这里最近 3 条了解上下文。
> 写日志的规矩：改动写文件路径，验证写命令和结果，遗留写清楚卡在哪、等谁。

---

## 2026-11-15 12:52 · 课程推荐扩到「专业—课程—知识点」三级

**状态**：完成，235 测试全绿

**背景**：申报书承诺课程推荐做到「专业—课程—知识点」三级、覆盖全部专业；原实现只有 40 门口碑课、覆盖 44 个专业，知识点一层是空的。用户：「扩大,扩大到申报书承诺的那种」。

**改动**
- 新建 `backend/data/course_catalog.json`：**614 门课**，其中 **270 门手写知识点**（`points_verified: true`）、344 门按课程类型归类；每门课带 3–6 个知识点、平台、平台搜索链接、覆盖专业数、全量关联专业列表。
- 新建 `tmp_build_courses.py`（项目根）：从 736 条画像的主干课累计词频反推课程目录，`POINTS` 手写 270 门课的知识点（工科基础 / 计算机 / 经管 / 外语 / 法学 / 新闻 / 设计 / 医学 / 文史 / 教育 / 物理……），`GENERIC_RULES` 按课程名尾巴兜底；`position` 记课程在专业课表里的平均位置，用于把基础课排前面。
- 改 `tmp_build_profile.py`：新增 `FALLBACK_COURSES`（12 个门类各 8 门兜底课表）、`NAME_FALLBACK`（56 个只剩占位名的长尾专业逐个给真实课表）、「工业设计」关键词覆盖；重建后仍是 736 条。
- 改 `backend/app/mooc_data.py`：`_catalog()` / `_backbone()`；`recommend()` 新增返回 `backbone`（本专业主干课，按课表顺序、最多 8 门）与 `catalog`；`majors()` 覆盖 **749 个专业**；专业目录里查不到时 `tip` 明确说「目录里没有这个专业的主干课」。
- 改 `frontend/mooc.html`：新增「这个专业要上的课」区块 + 「平台上的口碑课」小标题。
- 改 `frontend/js/mooc.js`：`renderBackbone()` / `backboneCard()`（平台标签、共学专业数、知识点 chips、「搜这门课」外链）；`courseCard()` 兼容 provider / rating / learners 为空。
- 改 `frontend/css/app.css`：`.backbone*`、`.course-section-title`、`.course-platform.is-smartedu`，760px 单列。花括号 934/934。

**验证**
- `PYTHONIOENCODING=utf-8 python realdata/tmp_run_tests.py` → 235 tests OK。
- `node --check frontend/js/mooc.js` 通过。
- HTTP（port 8152，demo 账号）：`/api/mooc?major=` 对 计算机科学与技术 / 临床医学 / 法学 / 汉语言文学 / 工业设计 都返回 8 门主干课，手写知识点分别为 8 / 7 / 8 / 8 / 5；`catalog` 614 门 / 270 门；`/mooc.html` 200。
- 空结果：查「视觉传达设计」（不在目录里）→ `backbone` 为空，tip 提示换写法。

**遗留**
- 344 门课的知识点是按课程类型归类的通用表述（如「实验目的与安全规范」），不是课程大纲；页面按 `points_verified` 区分文案。
- **没有编「第几讲」**——讲次只有课程主页才有，编出来就是假数据。申报书里「精确到第几分钟」这条在 `docs/PLAN-cup-2027.md` 里已主动降级为「第几讲」。
- 主干课区块仍未做浏览器视觉验证（无 Playwright），需本地 `python run.py --data real` 打开 `/mooc.html` 看排版。

---

## 2026-11-15 12:36 · 专业画像扩到全部 736 个专业

**状态**：完成，235 测试全绿

**背景**：用户「直接推」。100 条试水后把画像推到目录里的全部专业。实际可生成的是 **736 个**（`is_group == false`），821 是 `total_majors`，含 56 个专业类条目。

**改动**
- `tmp_build_profile.py`：`GROUPS` 模板覆盖 55 个专业类 + `other` / `trial`；`OTHER_ROUTES` 把 238 个长尾专业（海洋、小语种、影视、烹饪……）按名字路由到最接近的模板，课程和岗位不再全是「专业导论、学科基础课」。
- `profile_group` 字段：路由后的类名单独存，`group` 仍保持 catalog 原值，避免与 `major_catalog` 打架；前端可优先显示 `profile_group`。
- `GROUP_DEGREES`（按专业类定学位）+ `NAME_DEGREE_RULES`（杂类按名字兜底），学位从笼统的「学士」细化到文学 / 工学 / 农学 / 医学 / 艺术学等，剩余「学士」为 0。
- 修 `_resolve_group()`：`other` 本身也是 `GROUPS` 的键，原先 `group_id in GROUPS` 直接命中，路由永远走不到。
- 补 `GROUPS` 里 `civil.units` 不足 3 个的模板（艺术管理、other）；`trial` 的 industries 补到 3 个。
- `电影` / `戏剧` 关键词覆盖：电影学不再上「设计素描、色彩构成」。

**验证**
- `PYTHONIOENCODING=utf-8 python tmp_build_profile.py --limit 0` → 736 条（733 推算 / 3 人工），覆盖 55 个专业类。
- `PYTHONIOENCODING=utf-8 python realdata/tmp_run_tests.py` → 235 tests OK。
- 抽检 10 个长尾专业：意大利语 → 外国语言文学类 · 文学学士，量子信息科学 → 物理类 · 理学学士，茶学 → 植物与动物类 · 农学学士，海洋技术 → 资源与矿业类 · 工学学士，电影学 → 艺术设计类 · 艺术学学士。
- HTTP（port 8151）：`/api/major/profile` 200、`/api/major/compare` 200（3 项 6 轴）、`/api/majors` total 821、`/compare.html` 与 `/major.html` 200。

**遗留**
- 56 个长尾专业仍显示 `group="其他"`（有 `profile_group` 时可显示路由后的类名）。
- 238 条 `estimated: true` 的区间是专业类推算，答辩时不能说成统计数据。

---

## 2026-11-15 12:32 · 专业画像批量扩到 100 条

**状态**：完成，235 测试全绿；821 条全量还没跑

**背景**：NEXT 队列任务 5。3 条手写样例证明了 schema，但 821 条逐条手写写不完，同组内也必然写出自相矛盾的课程。先做 100 条试水：按招生规模取前 100（覆盖 39 个专业类），抽检质量再决定要不要推到 821。

**改动**
- 新建 `tmp_build_profile.py`（项目根，和 `tmp_build_catalog.py` 同级）：39 个专业类的模板（课程 8 门 / 岗位 6 个 / 行业 / 考公 / 考研 / 三段区间），40 条关键词覆盖（人工智能、软件工程、大数据、网络空间安全……）按专业名给细分方向换专业课和岗位。`_too_similar()` 只认包含关系，避免「前端开发工程师 / 后端开发工程师」被当成同一个岗位。
- 数据现实写进生成器：就业率 / 升学率 / 起薪给的是**专业类通用区间**，打 `estimated: true`，note 里写明「按 X 类推算，不是本专业单独统计」；三条人工样例保持 `estimated: false`，批量不覆盖。
- `backend/app/major_quant.py`：中文类起薪分 1 → 2（汉语言文学 4500–8500，比哲学/历史高）。
- `_startup_for()` 由六维分推创业五维并夹到 1–5，保证和雷达图不打架。

**验证**
- `PYTHONIOENCODING=utf-8 python tmp_build_profile.py --limit 100` → 写入 100 条（97 推算 / 3 人工），覆盖 39 个专业类。
- `python -m unittest tests.test_major_profile tests.test_major_quant` → 32 tests OK。
- `PYTHONIOENCODING=utf-8 python realdata/tmp_run_tests.py` → 235 tests OK。
- HTTP 探针（port 8146，demo 账号）：随机抽 8 条 `/api/major/profile` 全 200，课程 8 / 岗位 6 / 技能 4；`/api/major/compare` 200；未知专业 400「专业画像里没有『纯属虚构专业』，目前收了 100 个专业」。
- 抽检修掉的问题：俄语课表里出现「英语听力」（外语组模板改成「基础外语 / 对象国文学」）；「外贸业务员 / 外贸业务」重复；金融学「银行客户经理 / 银行柜员与客户经理」重复；大数据管理与应用等三个计算机细分方向课表与计算机科学与技术一字不差（补了关键词覆盖）。

**遗留**
- 只做了前 100 条，剩余 721 个专业没有画像，`/api/major/profile` 对它们返回 400。
- `estimated: true` 的条目**不能当统计数据引用**，答辩时要说清是专业类推算。
- 机械设计制造及其自动化在 catalog 里归到「自动化」类，课表混了机械与自控，属于 P0 分类遗留。

---

## 2026-11-15 12:14 · 六维量化 + 专业对比页（雷达图）

**状态**：完成，235 测试全绿

**背景**：NEXT 队列任务 3（56 个专业类六维量化）与任务 4（雷达图组件 + 对比 demo）。画像单条能看，但要说服人还得把几个专业摆在一起。

**改动**
- 新建 `backend/app/major_quant.py`：`GROUP_SCORES` 覆盖 56 个专业类（键与 `major_catalog.meta()` 的 group id 精确一致），每类六维 1–5 分；`KEYWORD_SCORES` 处理同组内明显偏离的细分方向（人工智能考研必要 +1、软件工程 −1、口腔医学起薪/创业 +1 等），按关键词长度倒序匹配、命中累加、最后夹到 1–5；`scores_for(name, group_id)` 出分，`explain()` 把每维翻译成「最重 / 较宽 / 几乎必需」这类人话。
- `backend/app/major_profile.py:compare()`：返回项补充 `postgrad`、`courses[:6]`、`civil`，一次请求就够画图和列表，不用前端再发 N 个请求。
- `backend/app/server.py:52`：`PROTECTED_PAGES` 加 `/compare.html`；:370 起两个只读路由 `/api/major/profile`、`/api/major/compare`（GET-only）。
- 新建 `frontend/compare.html` + `frontend/js/compare.js`：搜索选 2–4 个专业（默认放三个示例），手写 SVG 六维雷达（5 圈网格 + 6 轴 + 最多 4 条半透明多边形），下方图例标出每个专业最强的一维，再往下是逐项对照表（学制学位 / 就业率 / 升学率 / 起薪 / 考公类别 / 对口职业 / 核心课程）。深链 `?name=A&name=B` 可直达；从专业详情页点「加入专业对比」只带一个名字，页面提示再选一个。
- `frontend/js/api.js:159`：新增 `majorProfile(name)`、`majorCompare(names)`。
- `frontend/js/major.js`：详情里新增「和其他专业比一比」块，链到 `compare.html?name=`。
- 11 个页面的「更多」下拉加「专业对比」入口（`major.html` 用的是 `is-active` 变体，单独手改）。
- `frontend/css/app.css:2636` 起追加 feature 09 段（约 210 行）：`.compare-suggest` 下拉、`.compare-chip--1..4` 与 `.compare-legend-item--1..4` 共用 `--series` 变量、`.radar-ring/--spoke/--label/--area/--line/--dot`、`.compare-table`、1024 / 760 两档断点（雷达与图例改上下排、图例转横排再转纵排、表格缩字号）。花括号 913/913。

**验证**
- `python -m unittest tests.test_major_quant -v` → 11 tests OK（56 类全覆盖、无多余键、每维 1–5、**三条样例画像与量化规则分数完全一致**、关键词修正方向、未知专业类回落 other、explain 六条规则）。
- `PYTHONIOENCODING=utf-8 python realdata/tmp_run_tests.py` → **235 tests OK**。
- `node --check` 通过 `compare.js`、`major.js`、`api.js`；`compare.html` 的 id 集合与 `compare.js` 的 `getElementById` 集合完全相等。
- HTTP 探针（port 8141，`--data real`）：demo 登录 200 → `/api/major/compare?name=计算机科学与技术&name=临床医学&name=社会工作` 200，courses 各 6 条、postgrad 上限 40/60/32；`/compare.html` 登录后 200（6818B）；匿名 302 → `/login.html?next=%2Fcompare.html`（用不跟随重定向的 opener 验证）；`/api/health` → `source: real`。

**遗留**
- 雷达图只做了代码与接口验证，**没有真浏览器视觉确认**（环境无 Playwright）。760px 下是否横向溢出靠 CSS 断点保证，建议本地打开 `compare.html` 拖窄窗口看一眼。
- 只有 3 条画像，对比页目前只能比这三个；821 条批量生成是队列任务 5，规则要复用 `major_quant.scores_for()`，否则又会跟样例打架。

---

## 2026-11-15 12:10 · 专业画像 schema + 3 条样例 + 演示账号

**状态**：完成，224 测试全绿

**背景**：NEXT 队列任务 1（画像 schema + 3 条样例）与任务 2（演示账号），为 P2 画像一期打地基。

**改动**
- 新建 `backend/data/major_profile.json`：schema v1，先收 3 条标杆画像（计算机科学与技术 / 临床医学 / 社会工作）。字段为学制学位、主干课程 6–10 门、核心能力 4–6、对口职业 5–10、行业 3–5、区域、就业率区间、升学率区间、起薪区间（三条区间都带 `note` + `source`）、考公类别与单位、考研学科与评估档、创业五维、六维雷达分。
- 新建 `backend/app/major_profile.py`：`check()` 结构校验（字段齐全、列表长度上下限、区间 low<high、带来源、1–5 分越界）、`_payload()` 整体加载校验（任何一条不合格直接 `MajorError`）、`get()` / `names()` / `stats()` / `compare(2–4 个专业)`。复用 `major_catalog.MajorError`（继承 `ValueError` → server 转 400）。
- `backend/app/server.py:35`：导入 `major_profile`；`PROTECTED_EXACT` 加 `/api/major/profile`、`/api/major/compare`；:370 起两个 GET-only 路由。
- 新建 `backend/tests/test_major_profile.py`（21 用例）：样例齐全、逐条过 `check`、名字与目录一致、分类字段与目录一致、列表长度、起薪必须是区间、六维在 1–5、临床医学考研必要 5 / 创业友好 ≤2 等现实性断言、`get` 空值与未知专业抛错、`MajorError` 是 `ValueError`、`stats` 计数、`compare` 参数边界、以及 5 个篡改合法画像的负面用例（删课程、删来源、区间倒置、分数越界）。
- 演示账号：`demo@chili.local`（users id=11），12 位随机密码，供评委直接体验。

**验证**
- `cd backend && python -m unittest tests.test_major_profile -v` → 21 tests OK。
- `PYTHONIOENCODING=utf-8 python realdata/tmp_run_tests.py`（工作区根）→ **224 tests OK**。
- HTTP 探针（`--data real`，port 8140）：demo 登录 200；`/api/major/profile?name=计算机科学与技术` 200、10 门课程；`/api/major/compare?name=计算机科学与技术&name=临床医学` 200、6 轴 2 项；只传 1 个专业 400「对比至少选 2 个专业」；未知专业 400「专业画像里没有…，目前收了 3 个专业」。

**遗留**
- 只灌了 3 条样例，821 条要等六维量化规则定稿后批量生成（队列任务 3、5）。
- 六维分目前是人工判断，批量前需要把「专业类基准分 + 关键词修正」的推导规则写成代码，否则 821 条会出现同类专业分数互斥。
- 前端还没接画像页和雷达图（队列任务 4）。

**演示账号**：`demo@chili.local` / `ZHAwSRJFpw6J`

---

## 2026-11-14 23:50 · 部署体检：修 health 假报 mock + 首页登录墙

**状态**：完成，203 测试全绿

**背景**：用户把系统部署到 `https://jacket-valuation-positioning-paste.trycloudflare.com/`，手机可访问；实测发现两个问题。

**改动**
- `backend/app/server.py:210`：`/api/health` 的 `source` 原来硬编码 `"mock"`，改用 `dataset.mode`。之前不管加载什么数据都报 mock，排查部署会被误导。
- `backend/app/server.py:49`：`PROTECTED_PAGES` 移除 `/index.html`。门户页现在匿名可看，评委点链接第一眼不再是登录墙。
- `frontend/js/api.js:12`：`request()` 新增 `silent401` 选项，只探测登录态的请求不把人踢去登录页；`api.meta(silent401)` 透传。
- `frontend/js/portal.js`：`api.meta(true)`；401 时提示「登录后可以按分数直达预测」而不是「连不上服务」；`onSubmit` 在 `meta` 为空时提示先登录。

**验证**
- 本地 `--data real` 起服务：`/api/health` → `source: real`；`--data mock` → `source: mock`。
- 匿名访问：`/` 200 门户页、`/index.html` 200、`/about.html` 200；`/predict.html`、`/major.html` 跳登录。
- `PYTHONIOENCODING=utf-8 python realdata/tmp_run_tests.py` → **203 tests OK**。
- 线上实例实测（登录后）：`/api/meta` → `source: real-js`、8 省齐全；`/api/major/meta` → 821 专业；`/api/major/trend` → 计算机辽宁「明显扩张、热度降温」；`/api/major/outlook` → 专业类画像、path 4 条。

**遗留**
- 线上实例还在跑旧代码，**需要重启** `python run.py --data real` 才生效。
- 移动端只做了静态检查（13 页面都有 viewport、CSS 有 760px 断点），没有真浏览器。

---

## 2026-11-14 23:44 · 孵化计划成文

**状态**：完成

**产出**：[`PLAN-cup-2027.md`](PLAN-cup-2027.md)——现状盘点、差距清单、六个阶段（P1 答辩收口 / P2 画像一期 / P3 课程地图 / P4 培优一期 / P5 扩省 / P6 试点结题）、两档经费（2000 / 5000）、三处建议主动降级的承诺。

**关键判断**
- 800 道题审校和 168 门课程核对是真正的工作量，不是写页面。
- 培优只做数学高一，九科一年做不完。
- 就业率/起薪只写区间 + 来源年份，不写单点数字。

---

## 2026-11-13 18:06 · 参赛收口：删三省 + exe 重打包

**状态**：完成

**改动**
- 删重庆、四川、河南：`backend/data/cq/` 整目录、`real_data.py` 的 `PROVINCES`/`PROVINCE_CODES`/占位分支、`mock_data.py` 改成江苏 + 广东。
- `major_catalog.json` 重建：821 专业 / 94,790 招生单元，`by_province` 只剩浙鲁冀辽。
- `build_exe.py` 打包时排除 `app.db` 和 `*.bak.json`，避免把用户账号库打进安装包。
- 前端 14 个文件的「九省」文案统一改成八省；`app.js`/`curve.js`/`plan.js` 删掉「数据整理中」死代码。
- 清库：删掉 3 个测试账号，保留用户本人账号。

**验证**：203 tests OK；`dist/chili.exe` 11.8MB，包内 55 个数据条目、无 `app.db`/`bak`/`cq`。

**遗留**：exe 只验证了包内容，没在干净机器上真跑（沙箱不允许创建临时目录）。

---

## 2026-11-11 · P0 + P1 全部完成

**状态**：完成

详见 [`HANDOVER-2026-11-11.md`](HANDOVER-2026-11-11.md)。

- P0：专业集合（三路由 + major.html/major.js + 样式 + 17 用例）
- P1-A：方向细分（六轴方向题 + 56 专业类画像 + matcher 输出具体专业 + 28 用例）
- P1-B：趋势预警（major_trend.py，有多少年算多少年，显式标记缺失 + 24 用例）
- P1-C：专业前景（major_outlook.py，56 类手写判断 + 关键词细分 + 15 用例）
- 脏专业名修复：`strip_brackets` 栈式解析，0 残留
