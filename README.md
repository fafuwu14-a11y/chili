# 赤鲤 · 高一选科 → 专业推荐 → 优势院校 → 先导课

> 面向**高一学生**的选科规划工具。不是「输入分数查能上哪」，而是「先想清楚读什么，再决定选哪三门」。

五步一条线，同一份画像贯穿：

1. **选科** —— 定省份（全国 31 个省级行政区，4 套规则）→ 23 道情境题 → 规则引擎给出 3 个候选组合 + 可报专业覆盖率
2. **专业** —— 按画像排出 821 个本科专业里的前 12 个，每个都能点开看「学什么、毕业去哪、要付什么代价」
3. **院校** —— 某个专业在哪些学校强：按真实投档位次排序，右侧抽屉展示（480px）
4. **先导课** —— 该专业的主干课先看几门，判断自己是不是真喜欢
5. **复测** —— 3 道题问自己还想不想继续，均分 <2 建议换方向

AI 的位置很明确：**选科那一步不是 AI 的主场**（92 个专业类的选科要求是公开规则，模型只能润色），
**选专业才是**——专业解读、适不适合我、和隔壁专业差在哪，这些没有标准答案，接的是大模型。

## 快速开始

```bash
cd gaokao-platform
python run.py                # 默认 8000 端口，自动开浏览器
python run.py --port 8080 --no-open
```

* 后端 Python 3.10+，**只用标准库**（无 FastAPI / 无第三方依赖）
* 前端原生 ES Module + CSS，**免构建**，同一个 Python 进程托管
* 演示账号：`demo@chili.dev` / `chili2026`（登录弹窗里有一键填入）
* 不登录也能走完选科问卷和专业库；登录是为了保存结果、用 AI（防陌生人拿站点当免费 API 代理）

## 数据规模

| 维度 | 数量 | 来源 |
|-|-|-|
| 省级行政区 | 31（3+1+2 共 23 省 / 3+3 共 6 省市，浙江 7 选 3 单列 / 西藏新疆老高考过渡） | 各省教育考试院公开文件 |
| 专业类 | 92 | 教育部本科专业目录 |
| 本科专业 | 821 | 同上 |
| 投档数据 | 104,115 个招生单元 / 8 省 / 2024–2026 | 江苏、广东、湖北、山西（院校专业组）+ 辽宁、浙江、山东、河北（专业+学校） |
| 先导课 | 40 门口碑课，覆盖全部专业 | 中国大学 MOOC 等公开课 |
| AI 厂商 | 13 家 | OpenAI 兼容协议 |

**投档数据的粒度不统一**，这一点会直接显示在页面上：辽宁/浙江/山东/河北是**专业级**（能查到「某校某专业」的位次）；
江苏/广东/湖北/山西只有**专业组**（「09 专业组」），反推不出具体专业。所以江苏学生查某专业时，
系统会回退到 4 个专业级省份的数据，并在抽屉里写清楚「这是跨省参考，不是你们省的线」。

## 目录结构

```
gaokao-platform/
├─ run.py                     # 启动入口（找空闲端口、开浏览器、起服务）
├─ start.bat                  # Windows 双击启动
├─ backend/
│  ├─ app/
│  │  ├─ subjects.py          # 31 省规则 + 92 专业类的选科要求 + 组合枚举 + 覆盖率
│  │  ├─ subject_map.py       # 821 个专业名 → 92 个专业类（精确表 + 关键词规则 + lru_cache）
│  │  ├─ choice_quiz.py       # 23 题问卷（16 单选 + 7 五级量表），权重留服务端
│  │  ├─ choice_engine.py     # 推荐引擎：组合评分、专业排序、霍兰德六型、文理倾向
│  │  ├─ major_colleges.py    # 专业 → 优势院校（按校名聚合，跨省去重，位次归一）
│  │  ├─ mooc_retest.py       # 兴趣复测：3 题 → deep / trial / switch
│  │  ├─ ai_providers.py      # 13 家厂商注册表
│  │  ├─ ai_client.py         # 统一 chat / interview / report / major_advisor / ping
│  │  ├─ major_catalog.py     # 专业目录与检索
│  │  ├─ major_profile.py     # 专业画像（课程、职业、六维雷达）
│  │  ├─ major_outlook.py     # 专业前景（学什么、市场、代价、四年路线）
│  │  ├─ mooc_data.py         # 课程目录 + 按专业打分
│  │  ├─ auth.py              # 账号：注册 / 登录 / 会话 / 限流 / 密码哈希
│  │  ├─ server.py            # 标准库 HTTP：JSON API + 静态文件
│  │  ├─ predictor.py         # 旧功能：位次法 / 线差法（保留在「高三工具」里）
│  │  ├─ planner.py           # 旧功能：冲稳保志愿表
│  │  └─ matcher.py           # 旧功能：18/34/48 题兴趣测评
│  ├─ data/                   # 12MB：专业目录、专业画像、课程库、8 省 CSV、账号库
│  └─ tests/                  # 372 个单元测试（unittest，无需 pytest）
└─ frontend/
   ├─ index.html              # 门户首页
   ├─ wizard.html             # 五步向导（主线）
   ├─ major.html              # 专业库：详情 + 优势院校抽屉 + AI 顾问抽屉
   ├─ ai-setup.html           # 接入 AI：13 家厂商 + 逐家教程
   ├─ mooc.html               # 课程库
   ├─ quiz.html               # 旧版兴趣测评
   ├─ predict.html / plan.html / curve.html / compare.html   # 高三工具
   ├─ about / help / privacy / terms / error / login
   ├─ css/                    # app.css 变量：--red #E60012 / --gold #C9A227 / --ink #241A1B
   └─ js/                     # 原生 ES Module，无打包步骤
```

## 组合评分怎么算

```
总分 = 0.45 × 学科契合 + 0.35 × 专业簇契合 + 0.20 × 覆盖率
覆盖率得分 = 100 × √(可报专业占比)        // 开根号，避免「多报一个专业」被过度奖励
簇契合 = 0.6 × 可达最强簇 + 0.4 × 前三簇均值  // 防止被大量 0 分专业稀释
```

两个额外结论：

* **文理倾向** = 物理/化学/生物/技术 加权 − 历史/政治/地理 加权；|差值| <8 算均衡，≥18 算明显。3+1+2 的 23 个省，学生第一个要拍板的就是「物理还是历史」，这个结论单独给。
* **霍兰德六型（RIASEC）** = 12 个专业簇加权投影到 R/I/A/S/E/C，按最大值拉满 100。**这是簇的投影，不是标准霍兰德量表**——页面上写清楚了，别当成心理测量工具。

## 接入 AI

13 家：DeepSeek / 通义千问 / 豆包 / Kimi / 智谱 / 文心 / 讯飞星火 / 腾讯混元 / MiniMax / 阶跃 / 硅基流动 / OpenRouter / 本地 Ollama。
全部走 OpenAI 兼容的 `POST {base_url}/chat/completions`，纯 `urllib`，不需要装 SDK。

**Key 只存在浏览器 `localStorage["chili.ai.config"]`**，每次请求放在 body 的 `ai` 对象里传给后端一次性代理，
不落库、不写日志、不回显；后端只做转发与结构校验。

详细开通步骤（每家从注册到拿到 Key 的完整路径、常见报错对照表）见 [`docs/AI接入指南.md`](docs/AI接入指南.md)，
页面内的版本是 `ai-setup.html`。

## API

全部 `{"ok":true,"data":...}` 包装；错误是 `{"ok":false,"error":"中文","code":"码"}`。

| 方法 | 路径 | 登录 | 说明 |
|-|-|-|-|
| GET | `/api/choice/meta` | 否 | 省份、科目、专业类要求、问卷元信息 |
| GET | `/api/choice/quiz` | 否 | 23 题（无计分权重） |
| GET | `/api/choice/combos?province=` | 否 | 该省全部组合 |
| POST | `/api/choice/report` | 否 | 画像 + 3 组合 + 12 专业 + `tendency` + `riasec` |
| GET | `/api/major/colleges?name=&province=` | 否 | 优势院校（参数名是 `name`） |
| GET/POST | `/api/mooc/retest` | 否 | 出题 / 判分 |
| GET | `/api/ai/providers` | 否 | 13 家厂商 |
| POST | `/api/ai/ping` `/chat` `/interview` `/report` | **是** | 连通性、对话、追问、整份报告解读 |
| POST | `/api/ai/major` | **是** | 单专业顾问：`{major, question, history, profile, combo}` → `{reply, level, points, probes}` |

`/api/ai/major` 的 `level` 四态：`match` 合适 / `caution` 有前提 / `mismatch` 不合适 / `unknown` 还没画像。
服务端会先把该专业的客观资料（学什么、就业口径、代价）拼进 context，压住模型瞎编排名和薪资。

## 测试

```bash
cd backend
python -X utf8 -m unittest discover -s tests      # 372 tests, OK
```

覆盖：选科规则、专业映射（覆盖率 100%）、推荐引擎、院校聚合、AI 客户端（全部 mock，不联网）、
HTTP 路由（起真服务器跑真请求）、账号与会话、旧功能回归。

## 数据声明

* 投档数据来自各省教育考试院公开发布的文件，只收录投档分数齐全的省份，缺数据的不占位
* 选科要求按 2024 版「物化捆绑」规则整理：理学（除地理科学类、心理学类）、工学（除建筑类）、农学、
  医学（除护理学类）要求物理 + 化学
* 专业画像、前景、课程库是编辑整理内容，不构成报考建议
* AI 输出的所有判断都可能错，最终以院校官网和当年招生计划为准
