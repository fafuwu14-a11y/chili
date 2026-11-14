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
from . import major_catalog, major_outlook, major_trend
from . import matcher, mooc_data
from .planner import build_plan
from .predictor import Dataset

MAX_BODY = 64 * 1024
JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}

# 需要登录才能访问的页面（静态资源不拦，否则登录页自己都加载不了）
PROTECTED_PAGES = {
    "/index.html", "/predict.html", "/plan.html", "/mooc.html", "/quiz.html", "/major.html",
}

# 需要登录才能调用的接口
PROTECTED_APIS = ("/api/predict", "/api/plan", "/api/match", "/api/college/", "/api/colleges")
PROTECTED_EXACT = {
    "/api/meta",
    "/api/predict",
    "/api/plan",
    "/api/match",
    "/api/colleges",
    "/api/quiz",
    "/api/mooc",
    "/api/mooc/majors",
    "/api/curve",
    "/api/major/meta",
    "/api/majors",
    "/api/major/detail",
    "/api/major/trend",
    "/api/major/outlook",
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
                self._send_json(HTTPStatus.OK, {"ok": True, "status": "up", "source": "mock"})
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
                    spec_key=str(body.get("spec") or "standard"),
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
        except auth_module.AuthError as exc:
            self._send_json(
                exc.status,
                {"ok": False, "error": exc.message, "code": exc.code},
            )
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except KeyError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc.args[0]) if exc.args else "未找到"})

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
