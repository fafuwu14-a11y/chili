"""选科 / 院校 / AI 路由的 HTTP 层测试。

起一个真的 ThreadingHTTPServer（端口 0 让系统分配），用 urllib 打过去，
验证的是「路由接线、状态码、响应外壳」，不重复引擎的数值断言。
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import auth as auth_module  # noqa: E402
from backend.app import choice_quiz, server  # noqa: E402


def _answers() -> dict:
    picks = {}
    for question in choice_quiz.QUESTIONS:
        picks[question["id"]] = 3 if question["kind"] == "scale" else "a"
    return picks


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="chili-http-"))
        dataset = server.build_dataset_for("real")
        store = auth_module.AuthStore(cls.tmp / "auth.db")
        service = auth_module.AuthService(store)
        handler = type("Handler", (server.ApiHandler,), {
            "dataset": dataset,
            "frontend_dir": ROOT / "frontend",
            "auth": service,
            "secure_cookie": False,
        })
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.httpd.daemon_threads = True
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.service = service

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- 工具 ---------------------------------------------------------
    def get(self, path: str, cookie: str = ""):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        if cookie:
            request.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def post(self, path: str, payload: dict, cookie: str = ""):
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body, method="POST",
            headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}"},
        )
        if cookie:
            request.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))


class ChoiceRouteTest(ServerCase):
    def test_meta_汇总省份题库与专业数(self):
        status, body = self.get("/api/choice/meta")
        self.assertEqual(status, 200)
        data = body["data"]
        self.assertEqual(len(data["provinces"]), 31)
        self.assertEqual(len(data["groups"]), 92)
        self.assertEqual(data["quiz"]["count"], 23)
        self.assertGreaterEqual(data["majors_total"], 800)

    def test_题库不下发权重(self):
        status, body = self.get("/api/choice/quiz")
        self.assertEqual(status, 200)
        questions = body["data"]["items"]
        self.assertEqual(len(questions), 23)
        for question in questions:
            self.assertNotIn("scores", question)
            if question["kind"] == "scale":
                self.assertNotIn("options", question)
                continue
            for option in question["options"]:
                self.assertEqual(set(option), {"id", "text"})

    def test_组合数量随省份模式变化(self):
        for province, expected in (("江苏", 12), ("浙江", 35), ("上海", 20)):
            status, body = self.get("/api/choice/combos?province=%s" % urllib.parse.quote(province))
            self.assertEqual(status, 200, province)
            self.assertEqual(len(body["data"]["combos"]), expected, province)

    def test_未知省份报错(self):
        status, body = self.get("/api/choice/combos?province=%s" % urllib.parse.quote("火星"))
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

    def test_report返回推荐组合与专业(self):
        status, body = self.post("/api/choice/report", {"answers": _answers(), "province": "江苏"})
        self.assertEqual(status, 200)
        data = body["data"]
        self.assertTrue(data["combos"])
        self.assertTrue(data["majors"])
        self.assertIn("profile", data)

    def test_report缺答案报错(self):
        status, body = self.post("/api/choice/report", {"province": "江苏"})
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])


class CollegeRouteTest(ServerCase):
    def test_计算机专业返回院校名单(self):
        status, body = self.get("/api/major/colleges?name=%s&province=%s" % (urllib.parse.quote("计算机科学与技术"), urllib.parse.quote("江苏")))
        self.assertEqual(status, 200)
        data = body["data"]
        self.assertIn(data["granularity"], ("major", "cross_province", "nationwide"))
        self.assertTrue(data["items"])
        self.assertGreaterEqual(len(data["items"]), 5)

    def test_院校名不重复(self):
        status, body = self.get("/api/major/colleges?name=%s&limit=50" % urllib.parse.quote("计算机科学与技术"))
        self.assertEqual(status, 200)
        names = [item["college"] for item in body["data"]["items"]]
        self.assertEqual(len(names), len(set(names)))

    def test_未知专业返回400(self):
        status, body = self.get("/api/major/colleges?name=%s" % urllib.parse.quote("完全不存在专业"))
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])


class RetestRouteTest(ServerCase):
    def test_拿题目不需要登录(self):
        status, body = self.get("/api/mooc/retest?major=%s" % urllib.parse.quote("计算机科学与技术"))
        self.assertEqual(status, 200)
        self.assertEqual(len(body["data"]["questions"]), 3)
        self.assertEqual(len(body["data"]["scale"]), 5)

    def test_提交答案得到判定(self):
        status, body = self.post("/api/mooc/retest", {
            "major": "计算机科学与技术",
            "answers": {"invest": 5, "curiosity": 4, "resist": 4},
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["verdict"], "deep")

    def test_漏题返回400(self):
        status, body = self.post("/api/mooc/retest", {"major": "法学", "answers": {"invest": 3}})
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])


class AiRouteTest(ServerCase):
    def test_厂商列表免登录(self):
        status, body = self.get("/api/ai/providers")
        self.assertEqual(status, 200)
        providers = body["data"]["providers"]
        self.assertGreaterEqual(len(providers), 13)
        for provider in providers:
            self.assertNotIn("api_key", provider)
            self.assertNotIn("console", provider)

    def test_对话接口必须登录(self):
        status, body = self.post("/api/ai/chat", {"ai": {"provider": "deepseek"}, "messages": []})
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "login_required")

    def test_登录后未知厂商报错(self):
        self.service.register("ai-probe@example.com", "RitA2024x", ip="10.9.9.9")
        token, _expires, _user = self.service.login("ai-probe@example.com", "RitA2024x", ip="10.9.9.9")
        cookie = f"chili_session={token}"
        status, body = self.post(
            "/api/ai/chat",
            {"ai": {"provider": "不存在的厂商", "key": "sk-x"}, "messages": [{"role": "user", "content": "hi"}]},
            cookie=cookie,
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["code"], "provider_unknown")

    def test_专业顾问必须登录(self):
        status, body = self.post("/api/ai/major", {"ai": {"provider": "deepseek"}, "major": "法学"})
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "login_required")

    def test_专业顾问缺专业名报错(self):
        self.service.register("ai-major@example.com", "RitA2024x", ip="10.9.9.9")
        token, _expires, _user = self.service.login("ai-major@example.com", "RitA2024x", ip="10.9.9.9")
        status, body = self.post(
            "/api/ai/major",
            {"ai": {"provider": "deepseek", "key": "sk-x"}, "major": "  "},
            cookie=f"chili_session={token}",
        )
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])


if __name__ == "__main__":
    unittest.main()
