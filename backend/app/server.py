"""A dependency-free HTTP server: JSON API + static frontend.

Only the Python standard library is used, so ``python run.py`` works on a
clean machine without pip. Routes:

    POST /api/auth/register      POST /api/auth/login
    POST /api/auth/logout        GET  /api/auth/me
    GET  /api/health
    GET  /api/meta
    POST /api/predict
    GET  /api/college/<college_id>?province=..&track=..
    GET  /api/colleges?province=..&track=..
    GET  /api/major/meta                      专业目录门类树
    GET  /api/majors?q=&category=&group=&limit=
    GET  /api/major/detail?name=
    GET  /api/major/trend?name=               专业趋势预警（缺年份会标出来）
    GET  /api/major/outlook?name=             专业前景（学什么 / 市场 / 代价 / 四年路线）
    GET  /api/choice/meta                     省份 / 科目 / 92 专业类 / 23 道题
    GET  /api/choice/combos?province=..       该省全部合法选科组合
    POST /api/choice/report                   问卷答案 -> 画像 + 组合 + 专业推荐
    GET  /api/ai/providers                    支持接入的 AI 厂商
    POST /api/ai/chat | ping | interview | report | major | coach
    GET  /*                       -> frontend/
"""

from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import socket
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import auth as auth_module
from . import ai_client, ai_providers
from . import choice_engine, choice_quiz
from . import major_catalog, major_colleges, major_outlook, major_profile, major_trend
from . import matcher, mooc_data, mooc_retest
from . import subjects, subject_map
from .planner import build_plan
from .predictor import Dataset

# AI 请求里带对话历史，64KB 装不下；静态资源不走这个上限。
MAX_BODY = 256 * 1024
JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}

# 需要登录才能访问的页面（静态资源不拦，否则登录页自己都加载不了）
# 门户首页不放进来：评委、招生老师第一次点开链接应该先看到产品是什么，
# 而不是一堵登录墙；要填分数或做测评时再登录。
PROTECTED_PAGES = {
    "/plan.html", "/quiz.html",
}

# 需要登录才能调用的接口
PROTECTED_APIS = ("/api/predict", "/api/plan", "/api/match", "/api/college/", "/api/colleges")
PROTECTED_EXACT = {
    "/api/predict",
    "/api/plan",
    "/api/match",
    "/api/colleges",
    "/api/quiz",
    "/api/curve",
    "/api/ai/chat",
    "/api/ai/ping",
    "/api/ai/interview",
    "/api/ai/report",
    "/api/ai/major",
    "/api/ai/coach",
}


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "ChiliGaokao/1.0"
    protocol_version = "HTTP/1.1"

    dataset: Dataset
    frontend_dir: Path
    auth: auth_module.AuthService
    secure_cookie: bool = False

    # -- plumbing --------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api("GET", parsed.path, parse_qs(parsed.query), None)
            else:
                self._serve_static(self.path)
        except Exception:  # pragma: no cover - last-resort guard
            self.log_error("%s", traceback.format_exc())
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "服务器内部错误"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "接口不存在"})
            return
        try:
            if not self._origin_allowed():
                self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "请求来源不被允许"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("请求体过大")
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(body, dict):
                raise ValueError("请求体必须是 JSON 对象")
            self._handle_api("POST", parsed.path, parse_qs(parsed.query), body)
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "JSON 格式不正确"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception:  # pragma: no cover
            self.log_error("%s", traceback.format_exc())
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "服务器内部错误"})

    def log_message(self, fmt: str, *args) -> None:  # keep the console readable
        print(f"  [{self.address_string()}] {fmt % args}")

    # -- API -------------------------------------------------------------
    def _handle_api(self, method: str, path: str, query: dict, body: dict | None) -> None:
        dataset = self.dataset
        try:
            token = auth_module.parse_cookie(self.headers.get("Cookie"))
            user = self.auth.current_user(token) if token else None

            # -- auth ----------------------------------------------------
            if path == "/api/auth/register":
                if method != "POST" or body is None:
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
                    return
                created = self.auth.register(
                    body.get("email"),
                    body.get("password"),
                    ip=self._client_ip(),
                    user_agent=self.headers.get("User-Agent") or "",
                )
                # 注册成功直接建会话，省得用户再输一次密码
                new_token, expires = self.auth.start_session(
                    created["id"], self._client_ip(), self.headers.get("User-Agent") or ""
                )
                self._send_json(
                    HTTPStatus.CREATED,
                    {"ok": True, "data": {"user": created, "expires_at": expires}},
                    cookie=auth_module.build_cookie(new_token, expires, secure=self.secure_cookie),
                )
                return

            if path == "/api/auth/login":
                if method != "POST" or body is None:
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
                    return
                new_token, expires, account = self.auth.login(
                    body.get("email"),
                    body.get("password"),
                    ip=self._client_ip(),
                    user_agent=self.headers.get("User-Agent") or "",
                )
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "data": {"user": account, "expires_at": expires}},
                    cookie=auth_module.build_cookie(new_token, expires, secure=self.secure_cookie),
                )
                return

            if path == "/api/auth/logout":
                if method != "POST":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
                    return
                self.auth.logout(token)
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "data": {"logged_out": True}},
                    cookie=auth_module.build_logout_cookie(secure=self.secure_cookie),
                )
                return

            if path == "/api/auth/me":
                if user is None:
                    self._send_json(
                        HTTPStatus.UNAUTHORIZED,
                        {"ok": False, "error": "请先登录", "code": "login_required"},
                    )
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "data": {"user": user}})
                return

            # -- everything below needs a signed-in user -----------------
            if self._needs_auth(path):
                if user is None:
                    self._send_json(
                        HTTPStatus.UNAUTHORIZED,
                        {"ok": False, "error": "登录已过期，请重新登录", "code": "login_required"},
                    )
                    return

            if path == "/api/health":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                # 之前这里写死了 "mock"，不管实际加载的是不是真实数据都报 mock，
                # 排查部署问题时会被误导；直接回数据集自己的 mode。
                self._send_json(HTTPStatus.OK, {"ok": True, "status": "up", "source": dataset.mode})
                return
            if path == "/api/meta":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "data": dataset.meta()})
                return

            if path == "/api/quiz":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "data": matcher.spec_list()})
                return

            if path.startswith("/api/quiz/"):
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                spec_key = unquote(path[len("/api/quiz/"):]).strip("/")
                self._send_json(HTTPStatus.OK, {"ok": True, "data": matcher.spec_detail(spec_key)})
                return

            if path == "/api/match":
                if method != "POST" or body is None:
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
                    return
                answers = body.get("answers") or {}
                result = matcher.match(
                    dataset,
                    spec_key=str(body.get("spec") or "deep"),
                    answers=answers,
                    limit=_limit(body.get("limit"), 6),
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            if path == "/api/predict":
                if method != "POST" or body is None:
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
                    return
                result = dataset.predict(
                    province=str(body.get("province", "")),
                    track=str(body.get("track", "")),
                    score=_optional_int(body.get("score"), "分数"),
                    rank=_optional_int(body.get("rank"), "位次"),
                    tier=body.get("tier") or None,
                    limit=_limit(body.get("limit"), 200),
                    college=str(body["college"]) if body.get("college") else None,
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            if path == "/api/plan":
                if method != "POST" or body is None:
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
                    return
                slots = {}
                for key, label in (("chong", "冲刺数量"), ("wen", "稳妥数量"), ("bao", "保底数量")):
                    value = _optional_int(body.get(key), label)
                    if value is not None:
                        slots[key] = value
                plan = build_plan(
                    dataset,
                    province=str(body.get("province", "")),
                    track=str(body.get("track", "")),
                    score=_optional_int(body.get("score"), "分数"),
                    rank=_optional_int(body.get("rank"), "位次"),
                    mode=str(body.get("mode") or "auto"),
                    **slots,
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "data": plan})
                return

            if path == "/api/curve":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                if dataset.mode != "real":
                    raise ValueError("一分一段查询需要真实数据，请用 python run.py --data real 启动")
                from .real_data import lookup_curve

                result = lookup_curve(
                    province=str(_first(query, "province") or ""),
                    track=str(_first(query, "track") or ""),
                    score=_optional_int(_first(query, "score"), "分数"),
                    rank=_optional_int(_first(query, "rank"), "位次"),
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return


            if path == "/api/mooc":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                major = _first(query, "major")
                limit = _limit(_first(query, "limit"), 6)
                self._send_json(HTTPStatus.OK, {"ok": True, "data": mooc_data.recommend(major, limit)})
                return

            if path == "/api/mooc/majors":
                names = {program["name"] for program in dataset.programs}
                names.update(mooc_data.majors())
                self._send_json(HTTPStatus.OK, {"ok": True, "data": sorted(names)})
                return

            if path == "/api/mooc/retest":
                # 二次检验是选科流程的收尾，不设登录门槛；规则在服务端，前端只负责收 3 个 1–5。
                if method == "GET":
                    major = _first(query, "major")
                    self._send_json(HTTPStatus.OK, {"ok": True, "data": {
                        "major": major.strip(),
                        "questions": mooc_retest.questions(major),
                        "scale": mooc_retest.SCALE,
                    }})
                    return
                if method == "POST":
                    body = body or {}
                    self._send_json(HTTPStatus.OK, {"ok": True, "data": mooc_retest.evaluate(
                        body.get("major") or "",
                        body.get("answers") or {},
                    )})
                    return
                self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET 或 POST"})
                return

            # -- 专业集合功能（目录浏览 / 搜索 / 详情）--------------------
            if path == "/api/major/meta":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "data": major_catalog.meta()})
                return

            if path == "/api/majors":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                result = major_catalog.search(
                    query=_first(query, "q"),
                    category=_first(query, "category"),
                    group=_first(query, "group"),
                    limit=_limit(_first(query, "limit"), 60),
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            if path == "/api/major/detail":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                result = major_catalog.detail(_first(query, "name"))
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            # 趋势预警：有多少年算多少年，缺的年份在返回里明确标出来。
            if path == "/api/major/trend":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                result = major_trend.trend(_first(query, "name"))
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            # 专业前景：学什么、毕业时市场什么样、代价在哪、四年怎么走。
            if path == "/api/major/outlook":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                result = major_outlook.build(_first(query, "name"))
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            # 结构化画像：课程、职业、考公考研、创业五维、六维雷达分。
            if path == "/api/major/profile":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                result = major_profile.get(_first(query, "name"))
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            # 专业对比：2–4 个专业，返回雷达图直接可用的结构。
            if path == "/api/major/compare":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                names = query.get("name") or []
                result = major_profile.compare(names)
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            # -- 选科测评（新主线）--------------------------------------
            if path == "/api/choice/meta":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                data = subjects.meta()
                edition = (_first(query, "edition") or "simple").strip()
                if edition not in ("simple", "deep"):
                    edition = "simple"
                data["quiz"] = choice_quiz.meta(edition)
                data["majors_total"] = len(_majors())
                self._send_json(HTTPStatus.OK, {"ok": True, "data": data})
                return

            if path == "/api/choice/quiz":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                edition = (_first(query, "edition") or "simple").strip()
                if edition not in ("simple", "deep"):
                    edition = "simple"
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "data": {
                        "edition": edition,
                        "items": choice_quiz.public_questions(edition),
                        "scale": choice_quiz.SCALE,
                    }},
                )
                return

            if path == "/api/choice/combos":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                province = _first(query, "province")
                if province not in subjects.PROVINCES:
                    raise ValueError("请先选一个省份，再查看可选组合")
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "data": {
                        "province": province,
                        "mode": subjects.province_mode(province),
                        "combos": subjects.combos(province),
                    }},
                )
                return

            if path == "/api/choice/report":
                if method != "POST" or body is None:
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
                    return
                answers = body.get("answers")
                if not isinstance(answers, dict):
                    raise ValueError("答案必须是对象")
                edition = str(body.get("edition") or "simple").strip()
                if edition not in ("simple", "deep"):
                    edition = "simple"
                result = choice_engine.build_report(
                    answers,
                    str(body.get("province") or "").strip(),
                    _majors(),
                    top_combos=_clamp(body.get("top_combos"), 3, 1, 6),
                    top_majors=_clamp(body.get("top_majors"), 12, 1, 40),
                    edition=edition,
                )
                if not result.get("ok"):
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"ok": False, "error": "还有题目没答完", "data": result},
                    )
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
                return

            # -- AI 接入口径统一走 _handle_ai -----------------------------
            if path == "/api/ai/providers":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {"ok": True, "data": {"providers": ai_providers.list_providers()}},
                )
                return

            if path.startswith("/api/ai/"):
                self._handle_ai(path[len("/api/ai/"):], method, body)
                return

            if path == "/api/major/colleges":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                self._send_json(HTTPStatus.OK, {"ok": True, "data": major_colleges.advantage(
                    dataset,
                    _first(query, "name"),
                    province=_first(query, "province"),
                    track=_first(query, "track"),
                    limit=_clamp(_first(query, "limit"), 20, 1, 50),
                )})
                return

            if path.startswith("/api/college/"):
                college_id = unquote(path[len("/api/college/"):]).strip("/")
                province = _first(query, "province")
                track = _first(query, "track")
                detail = dataset.college_detail(college_id, province, track)
                self._send_json(HTTPStatus.OK, {"ok": True, "data": detail})
                return

            if path == "/api/colleges":
                if method != "GET":
                    self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 GET"})
                    return
                province = _first(query, "province")
                track = _first(query, "track")
                keyword = _first(query, "q")
                if keyword:
                    rows = dataset.search_colleges(
                        keyword,
                        province=province,
                        track=track,
                        limit=_limit(_first(query, "limit"), 8),
                    )
                    self._send_json(HTTPStatus.OK, {"ok": True, "data": rows})
                    return
                rows = []
                for program in dataset.by_route.get((province, track), []):
                    college = dataset.colleges[program["college_id"]]
                    rows.append(
                        {
                            "college_id": college["id"],
                            "name": college["name"],
                            "city": college["city"],
                            "tags": college["tags"],
                            "program": program["name"],
                        }
                    )
                rows.sort(key=lambda r: r["name"])
                self._send_json(HTTPStatus.OK, {"ok": True, "data": rows})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "接口不存在"})
        except ai_client.AIError as exc:
            # AI 层的 status 就是它自己算好的 HTTP 码，直接透传
            self._send_json(exc.status, {"ok": False, "error": exc.message, "code": exc.code})
        except auth_module.AuthError as exc:
            self._send_json(
                exc.status,
                {"ok": False, "error": exc.message, "code": exc.code},
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except KeyError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc.args[0]) if exc.args else "未找到"})

    # -- AI --------------------------------------------------------------
    def _handle_ai(self, action: str, method: str, body: dict | None) -> None:
        """``/api/ai/*`` 统一入口：配置从请求体解析，Key 不落盘、不回显。"""
        if method != "POST" or body is None:
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "请使用 POST"})
            return
        config = _ai_config(body)
        timeout = _ai_timeout(body)

        if action == "chat":
            messages = body.get("messages")
            if not isinstance(messages, list):
                raise ValueError("messages 必须是数组")
            result = ai_client.chat(
                config, messages, json_mode=bool(body.get("json")), timeout=timeout
            )
            self._send_json(HTTPStatus.OK, {"ok": True, "data": {
                "content": result["content"],
                "usage": result["usage"],
                "provider": config.provider_id,
                "provider_name": config.provider_name,
                "model": config.model,
            }})
            return

        if action == "ping":
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "data": ai_client.ping(config, timeout=timeout or 20.0)},
            )
            return

        if action == "interview":
            self._send_json(HTTPStatus.OK, {"ok": True, "data": ai_client.interview(
                config,
                profile_summary=body.get("profile_summary") or "",
                history=body.get("history"),
                question=body.get("question") or "",
                step=_clamp(body.get("step"), 1, 1, 12),
            )})
            return

        if action == "report":
            answers = body.get("answers")
            if not isinstance(answers, dict):
                raise ValueError("答案必须是对象")
            base = choice_engine.build_report(
                answers,
                str(body.get("province") or "").strip(),
                _majors(),
                top_combos=3,
                top_majors=8,
            )
            if not base.get("ok"):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "还有题目没答完", "data": base},
                )
                return
            # AI 只做「把规则结果讲成人话」，分数仍以引擎为准，避免模型胡说
            self._send_json(HTTPStatus.OK, {"ok": True, "data": ai_client.report(
                config,
                profile=json.dumps(base["profile"], ensure_ascii=False),
                combos=[
                    {
                        "组合": subjects.combo_label(item["subjects"]),
                        "评分": item["score"],
                        "可报专业比例": f"{item['coverage_ratio']:.1%}",
                        "风险": item.get("watch", ""),
                    }
                    for item in base["combos"]
                ],
                majors=[
                    {"专业": item["name"], "专业类": item.get("group", ""),
                     "兴趣簇": item.get("cluster_name", ""), "匹配分": item["score"]}
                    for item in base["majors"]
                ],
            )})
            return

        if action == "major":
            name = str(body.get("major") or "").strip()
            if not name:
                raise ValueError("缺少专业名称 major")
            context = ""
            try:
                info = major_outlook.build(name)
            except ValueError:
                info = None
            if info:
                context = (
                    f"学什么：{info['what']}\n"
                    f"就业口径：{info['market']}\n"
                    f"代价：{info['risk']}\n"
                    f"四年路线：{'；'.join(info['path'])}\n"
                    f"综合判断：{info['verdict']}"
                )
            profile = body.get("profile")
            if isinstance(profile, dict):
                # 只喂 AI 用得上的维度，完整画像会把 4000 字上下文挤爆
                profile = {
                    "学科": profile.get("subject"),
                    "能力": profile.get("ability"),
                    "兴趣簇": profile.get("cluster"),
                    "霍兰德": (profile.get("riasec_summary") or {}).get("title", ""),
                    "文理倾向": profile.get("tendency"),
                    "优势学科": [k for k, v in (profile.get("top_subjects") or [])[:3]],
                }
            self._send_json(HTTPStatus.OK, {"ok": True, "data": ai_client.major_advisor(
                config,
                major=name,
                question=body.get("question") or "",
                history=body.get("history"),
                profile=profile,
                combo=body.get("combo"),
                context=context,
            )})
            return

        if action == "coach":
            raw_profile = body.get("profile")
            profile = None
            if isinstance(raw_profile, dict):
                profile = {
                    "学科": raw_profile.get("subject"),
                    "兴趣簇": raw_profile.get("cluster"),
                    "霍兰德": (raw_profile.get("riasec_summary") or {}).get("title", ""),
                    "文理倾向": raw_profile.get("tendency"),
                    "优势学科": [k for k, v in (raw_profile.get("top_subjects") or [])[:3]],
                }
            self._send_json(HTTPStatus.OK, {"ok": True, "data": ai_client.coach(
                config,
                history=body.get("history"),
                profile=profile,
                province=str(body.get("province") or "").strip(),
                turn=body.get("turn") or 0,
                timeout=_ai_timeout(body),
            )})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "接口不存在"})

    # -- static ----------------------------------------------------------
    def _serve_static(self, raw_path: str) -> None:
        root = self.frontend_dir.resolve()
        path = unquote(raw_path.split("?", 1)[0])
        if path in ("", "/"):
            # 首页是门户；带旧预测参数的链接（收藏、分享）直接送到预测页，不丢参数。
            query = raw_path.split("?", 1)[1] if "?" in raw_path else ""
            if any(key in query for key in ("province=", "track=", "score=", "rank=", "school=")):
                target = "/predict.html" + (f"?{query}" if query else "")
                if not self._logged_in():
                    self._redirect_to_login(target)
                    return
                self._redirect(target)
                return
            path = "/index.html"

        # 未登录时把受保护页面送回登录页，并把原地址带上，登录后能回到原地
        if path in PROTECTED_PAGES and not self._logged_in():
            self._redirect_to_login(raw_path)
            return

        # Normalise and keep the result inside frontend/.
        relative = posixpath.normpath(path).lstrip("/")
        target = (root / relative).resolve()
        inside = target == root or str(target).startswith(str(root) + os.sep)
        if not inside or not target.is_file():
            self._serve_not_found()
            return

        data = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _serve_not_found(self) -> None:
        """静态文件不存在时返回站点自己的 404 页，而不是裸 JSON。"""
        page = self.frontend_dir.resolve() / "error.html"
        if page.is_file():
            data = page.read_bytes()
            content_type = "text/html; charset=utf-8"
        else:
            data = "404".encode("utf-8")
            content_type = "text/plain; charset=utf-8"
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    # -- helpers ---------------------------------------------------------
    def _send_json(self, status: int, payload: dict, cookie: str | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for key, value in JSON_HEADERS.items():
            self.send_header(key, value)
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _cors(self) -> None:
        # 同源部署，不再回 Access-Control-Allow-Origin: *
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _origin_allowed(self) -> bool:
        """挡住跨站表单提交；命令行请求不带 Origin，直接放行。"""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host") or ""
        parsed = urlparse(origin)
        return parsed.netloc == host

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
        return (self.client_address[0] if self.client_address else "")[:64]

    def _logged_in(self) -> bool:
        token = auth_module.parse_cookie(self.headers.get("Cookie"))
        return bool(token) and self.auth.current_user(token) is not None

    def _redirect_to_login(self, raw_path: str) -> None:
        next_url = raw_path if raw_path.startswith("/") else "/"
        if next_url in ("/", "/index.html"):
            location = "/login.html"
        else:
            location = f"/login.html?next={quote(next_url, safe='')}"
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()

    @staticmethod
    def _needs_auth(path: str) -> bool:
        if path.startswith("/api/college/") or path.startswith("/api/quiz/"):
            return True
        return path in PROTECTED_EXACT

    def _redirect(self, location: str) -> None:
        """普通 302，用于把老链接送到新地址。"""
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()


def _first(query: dict, key: str) -> str:
    values = query.get(key) or [""]
    return str(values[0])


_MAJORS_CACHE: list[dict] | None = None


def _majors() -> list[dict]:
    """全部专业只读一次：821 条，选科引擎每个请求都要逐项打分。"""
    global _MAJORS_CACHE
    if _MAJORS_CACHE is None:
        _MAJORS_CACHE = major_catalog.all_majors()
    return _MAJORS_CACHE


def _clamp(value, default: int, low: int, high: int) -> int:
    parsed = _optional_int(value, "数量")
    if parsed is None:
        parsed = default
    return max(low, min(parsed, high))


_AI_FIELDS = (
    "provider", "provider_id", "vendor", "key", "api_key", "base_url", "baseUrl",
    "model", "model_id", "temperature", "max_tokens", "timeout",
)


def _ai_config(body: dict):
    """``{"ai": {...}}`` 或字段直接平铺，两种写法都收。"""
    raw = body.get("ai")
    if not isinstance(raw, dict):
        raw = {key: body[key] for key in _AI_FIELDS if key in body}
    return ai_client.AIConfig.from_mapping(raw)


def _ai_timeout(body: dict) -> float | None:
    parsed = _optional_int(body.get("timeout"), "超时时间")
    if parsed is None or parsed <= 0:
        return None
    return float(min(max(parsed, 5), 180))


def _optional_int(value, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label}格式不正确")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}格式不正确") from None
    # JSON 里允许 Infinity / 1e999，int() 会抛 OverflowError，这里一并当格式错误
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{label}格式不正确")
    try:
        return int(number)
    except (OverflowError, ValueError):
        raise ValueError(f"{label}格式不正确") from None


def _limit(value, default: int) -> int:
    """limit 为 0 时按 0 处理（不再被 `or` 吞成默认值），缺省才用 default。"""
    parsed = _optional_int(value, "数量")
    return default if parsed is None else parsed


def _display_hosts(host: str) -> list[str]:
    """Addresses to print in the banner; expands 0.0.0.0 to real LAN IPs."""
    if host not in ("0.0.0.0", "::"):
        return [host]
    hosts: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("127.") and addr not in hosts:
                hosts.append(addr)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("223.5.5.5", 53))  # no packet is sent for UDP
            addr = sock.getsockname()[0]
            if not addr.startswith("127."):
                if addr in hosts:
                    hosts.remove(addr)
                hosts.insert(0, addr)
    except OSError:
        pass
    return hosts or [host]


def build_dataset_for(source: str = "mock") -> Dataset:
    """``source`` is ``mock`` (synthetic demo) or ``real`` (Jiangsu 2026)."""
    if source == "real":
        from .real_data import build_real_dataset

        return Dataset(build_real_dataset())
    from .mock_data import build_dataset

    return Dataset(build_dataset())


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    frontend_dir: Path | None = None,
    source: str = "mock",
    db_path: Path | None = None,
) -> None:
    dataset = build_dataset_for(source)
    database = db_path or (Path(__file__).resolve().parents[1] / "data" / "app.db")
    store = auth_module.AuthStore(database)
    store.purge_expired()
    service = auth_module.AuthService(store)
    demo = service.ensure_demo()
    if demo["created"]:
        print(f"  演示账号已创建: {auth_module.DEMO_EMAIL} / {auth_module.DEMO_PASSWORD}")
    elif demo["reset"]:
        print(f"  演示账号密码已重置为: {auth_module.DEMO_PASSWORD}")
    handler = type("Handler", (ApiHandler,), {
        "dataset": dataset,
        "frontend_dir": frontend_dir or Path(__file__).resolve().parents[2] / "frontend",
        "auth": service,
        "secure_cookie": False,
    })
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    print(
        f"  数据源: {dataset.mode} | 院校 {len(dataset.colleges)} 所 / "
        f"招生单元 {len(dataset.programs)} 个 / 年份 {dataset.years}"
    )
    counts = service.stats()
    print(f"  账号:  {database} | 已注册 {counts['users']} 人")
    addresses = _display_hosts(host)
    print(f"  接口:  http://{addresses[0]}:{port}/api/meta")
    for addr in addresses:
        print(f"  页面:  http://{addr}:{port}/")
    if host in ("0.0.0.0", "::"):
        print("  手机连同一个 Wi-Fi，用上面「页面」里的局域网地址打开")
    print("  按 Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
    finally:
        httpd.server_close()
