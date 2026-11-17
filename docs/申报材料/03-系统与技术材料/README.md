# 03 · 系统与技术材料

对应《申报书》第六部分（三）「系统与技术材料」。

## 一、技术栈与运行方式

| 项 | 说明 |
| --- | --- |
| 后端 | Python 3.10+ 标准库（`http.server` + `sqlite3` + `json`），**零第三方依赖** |
| 前端 | 原生 ES Module + CSS，**无构建步骤**，直接由后端托管 |
| 数据 | 8 省投档表 CSV（`backend/data/`）、专业目录 JSON、SQLite 账号库 |
| 启动 | `python run.py --port 8000`，或双击 `start.bat` |
| 离线包 | `dist/chili.exe`（PyInstaller 打包，双击即用，不需要装 Python） |
| 测试 | `python -m unittest discover -s tests`，378 个用例 |

选择零依赖的理由：中学机房、评审核验电脑往往没有管理员权限，装不了 Node 和 pip 包。整个系统拷过去就能跑。

## 二、源码

源码目录：`E:\大肥鱼工作区\gaokao-platform\`

```
gaokao-platform/
├─ run.py                  启动入口
├─ start.bat               Windows 一键启动
├─ build_exe.py            打包成免安装 exe
├─ backend/
│  ├─ app/                 业务模块（20 个）
│  │  ├─ server.py         路由与静态托管
│  │  ├─ auth.py           账号、会话、限流
│  │  ├─ subjects.py       31 省选科规则 + 92 专业类要求
│  │  ├─ subject_map.py    821 专业 → 92 专业类映射
│  │  ├─ choice_quiz.py    23 题题库
│  │  ├─ choice_engine.py  组合 / 专业推荐引擎
│  │  ├─ major_colleges.py 院校优势（按投档位次）
│  │  ├─ major_outlook.py  就业画像
│  │  ├─ mooc_data.py      先导课
│  │  ├─ mooc_retest.py    二次检验
│  │  ├─ ai_providers.py   13 家厂商注册表
│  │  └─ ai_client.py      AI 调用与降级（含引导式对话）
│  ├─ data/                投档表、专业目录、课程库
│  └─ tests/               19 个测试文件
├─ frontend/               15 个页面 + 12 个 CSS 文件
├─ docs/                   方案、指南、申报材料
└─ dist/                   免安装 exe
```

源码压缩包：`源码_赤鲤_2026-11-17.zip`（同目录），SHA256 见 `源码校验.txt`。解压后按 README 启动即可复现截图里的全部界面。

## 三、单元测试用例清单

**378 个用例全部通过**，命令：

```bash
cd backend
python -X utf8 -m unittest discover -s tests
# Ran 378 tests in ~23s
# OK
```

| 测试文件 | 用例数 | 覆盖对象 |
| --- | ---: | --- |
| `test_ai.py` | 55 | 13 家厂商注册表、Key 脱敏、JSON 提取、对话、报告、**专业顾问**、超时与错误码 |
| `test_auth.py` | 53 | 密码哈希（PBKDF2 60 万轮）、会话、限流、注册登录、演示账号、SQL 注入防护 |
| `test_choice.py` | 33 | 23 题题库结构、答案校验、六维打分、组合推荐、专业推荐、专业映射 |
| `test_quiz.py` | 31 | 兴趣量表计分、约束校验 |
| `test_major_direction.py` | 28 | 专业方向问答与打分 |
| `test_major_trend.py` | 24 | 录取趋势、年份统计、缺口处理 |
| `test_major_profile.py` | 21 | 六维画像、对比、字段校验 |
| `test_major_catalog.py` | 18 | 821 专业目录完整性、分组、检索 |
| `test_server_routes.py` | 17 | HTTP 层：选科、组合、报告、院校、AI 路由、鉴权、错误码 |
| `test_predictor.py` | 15 | 位次换算、一分一段、录取概率、院校检索 |
| `test_major_colleges.py` | 15 | 院校优势：索引、跨省去重、位次排序、百分位、降级说明、真实数据冒烟 |
| `test_major_outlook.py` | 14 | 就业画像字段与覆盖 |
| `test_planner.py` | 14 | 冲稳保方案生成 |
| `test_mooc_retest.py` | 13 | 二次检验出题与判分、三档结论 |
| `test_major_quant.py` | 11 | 专业量化指标 |
| `test_mooc.py` | 10 | 先导课匹配与兜底 |

测试全部使用 `unittest` 标准库，不依赖 pytest；AI 相关用例用 mock 替换 `urllib`，**测试过程不联网、不消耗任何 API 额度**。

## 四、多设备兼容性测试记录

实测环境（2026-11-17，Windows 11 + Microsoft Edge 无头模式，通过 CDP 控制）：

| 场景 | 视口 | 结果 | 证据 |
| --- | --- | --- | --- |
| 桌面宽屏 | 1440 × 1000 | 通过 | 01–13 号截图全部在此视口 |
| 桌面长页 | 1440 × 1100 | 通过 | 就业画像、院校抽屉、AI 顾问 |
| 手机竖屏 | 390 × 844 | 通过 | 14、15 号截图（汉堡菜单收起、卡片单列、按钮不溢出） |

已知边界：

- CSS 断点在 560px（抽屉全宽）、900px（两栏转单栏）、1100px（导航收起为汉堡菜单）
- 未在 Firefox / Safari 上实测；系统只用了 CSS 变量、Grid、Flex 与 `backdrop-filter`，均为 Chromium 与 Firefox 共同支持的属性
- 移动端未做原生 App，走同一套响应式页面

## 五、离线包

本目录内的 `chili.exe`（与 `dist/chili.exe` 同一份，12 MB）：单文件免安装，双击后自动开浏览器，账号库写在 exe 同级的 `data/app.db`。

- 体积约 12 MB
- 首次启动 3–5 秒（解压内置数据）
- 不需要 Python，不需要联网（AI 增强功能需要用户自己填 Key）
- PyInstaller 打包，个别杀毒软件会误报，选「允许运行」即可

`dist/使用说明.txt` 是给最终用户的一页说明。
