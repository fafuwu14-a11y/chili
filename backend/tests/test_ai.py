"""AI 接入层的单元测试：厂商表、请求体、错误文案、JSON 解析、Key 脱敏。

全部用假响应把 ``urllib.request.urlopen`` 打掉，**不联网**；
只用标准库（unittest / io / email.message），不依赖 pytest。

跑法::

    python -m unittest discover -s backend/tests -p "test_ai.py" -v
"""

from __future__ import annotations

import email.message
import io
import json
import socket
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai_client, ai_providers  # noqa: E402

API = "https://api.deepseek.com/v1/chat/completions"
SECRET = "sk-test-secret-123456"


# ---------------------------------------------------------------- 假对象


class FakeResponse:
    """冒充 ``http.client.HTTPResponse``：只要 read / status / 上下文协议就够。"""

    def __init__(self, payload, status: int = 200):
        if isinstance(payload, bytes):
            self._body = payload
        else:
            self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status = status
        self.headers = email.message.Message()
        self.headers["Content-Type"] = "application/json"

    def read(self, *args, **kwargs) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def fake_error(status: int, payload, url: str = API) -> urllib.error.HTTPError:
    """构造一个带 JSON body 的 HTTPError，``read()`` 能读到错误详情。"""
    body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urllib.error.HTTPError(url, status, "error", email.message.Message(), io.BytesIO(body))


def openai_reply(content: str, **extra) -> dict:
    data = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "deepseek-chat",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    data.update(extra)
    return data


class PatchedUrlopen:
    """把 urlopen 换成可编程假函数，同时记下每次请求，方便断言请求体。"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self._patcher = None

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError("假 urlopen 被多调用了一次")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def __enter__(self):
        self._patcher = mock.patch("urllib.request.urlopen", self)
        self._patcher.start()
        return self

    def __exit__(self, *exc_info):
        self._patcher.stop()
        return False

    # -- 断言辅助 --------------------------------------------------

    @property
    def last_body(self) -> dict:
        request, _ = self.requests[-1]
        return json.loads(request.data.decode("utf-8"))

    @property
    def last_request(self):
        return self.requests[-1][0]


# ---------------------------------------------------------------- 厂商表


class ProviderTests(unittest.TestCase):
    def test_covers_thirteen_providers_in_order(self):
        self.assertEqual(len(ai_providers.PROVIDERS), 13)
        self.assertEqual(
            ai_providers.provider_ids(),
            [
                "deepseek", "qwen", "doubao", "kimi", "zhipu", "ernie", "spark",
                "hunyuan", "minimax", "stepfun", "siliconflow", "openrouter", "local",
            ],
        )

    def test_every_provider_has_required_fields(self):
        for provider in ai_providers.PROVIDERS:
            with self.subTest(provider=provider["id"]):
                for key in ("id", "name", "base_url", "models", "free", "signup", "docs", "notes", "vision"):
                    self.assertIn(key, provider)
                self.assertTrue(provider["base_url"].startswith("http"))
                self.assertFalse(provider["base_url"].rstrip("/").endswith("/chat/completions"))
                self.assertTrue(provider["models"])
                self.assertIsInstance(provider["free"], bool)
                self.assertIsInstance(provider["vision"], bool)
                self.assertTrue(provider["signup"].startswith("https://"))
                self.assertTrue(provider["docs"].startswith("https://"))
                if provider["id"] != "local":  # 本地模型不涉及价格
                    self.assertIn("以官网为准", provider["notes"])

    def test_expected_base_urls(self):
        expected = {
            "deepseek": "https://api.deepseek.com/v1",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "doubao": "https://ark.cn-beijing.volces.com/api/v3",
            "kimi": "https://api.moonshot.cn/v1",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "ernie": "https://qianfan.baidubce.com/v2",
            "spark": "https://spark-api-open.xf-yun.com/v1",
            "hunyuan": "https://api.hunyuan.cloud.tencent.com/v1",
            "minimax": "https://api.minimax.chat/v1",
            "stepfun": "https://api.stepfun.com/v1",
            "siliconflow": "https://api.siliconflow.cn/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "local": "http://127.0.0.1:11434/v1",
        }
        self.assertEqual({p["id"]: p["base_url"] for p in ai_providers.PROVIDERS}, expected)

    def test_expected_default_models(self):
        expected = {
            "deepseek": "deepseek-chat",
            "qwen": "qwen-plus",
            "kimi": "kimi-k2-0905-preview",
            "zhipu": "glm-4-plus",
            "ernie": "ernie-4.5-turbo-128k",
            "spark": "generalv3.5",
            "hunyuan": "hunyuan-turbos-latest",
            "minimax": "MiniMax-Text-01",
            "stepfun": "step-2-16k",
            "siliconflow": "Qwen/Qwen2.5-7B-Instruct",
        }
        actual = {p["id"]: p["models"][0] for p in ai_providers.PROVIDERS}
        for provider_id, model in expected.items():
            with self.subTest(provider=provider_id):
                self.assertEqual(actual[provider_id], model)

    def test_default_provider_is_deepseek(self):
        provider = ai_providers.default_provider()
        self.assertEqual(provider["id"], "deepseek")
        self.assertEqual(provider["models"][0], "deepseek-chat")
        # 返回的是副本，改它不会污染注册表
        provider["models"].append("fake-model")
        self.assertNotIn("fake-model", ai_providers.get_provider("deepseek")["models"])

    def test_list_providers_hides_internal_fields(self):
        items = ai_providers.list_providers()
        self.assertEqual(len(items), 13)
        for item in items:
            with self.subTest(provider=item["id"]):
                self.assertNotIn("console", item)
                self.assertNotIn("key_hint", item)
                self.assertEqual(item["default_model"], item["models"][0])

    def test_get_provider_unknown_raises(self):
        with self.assertRaises(ai_providers.AIError) as ctx:
            ai_providers.get_provider("gpt-9000")
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "provider_unknown")
        self.assertIn("gpt-9000", ctx.exception.message)

    def test_get_provider_rejects_blank(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                with self.assertRaises(ai_providers.AIError) as ctx:
                    ai_providers.get_provider(value)
                self.assertEqual(ctx.exception.code, "provider_required")

    def test_get_provider_accepts_aliases(self):
        self.assertEqual(ai_providers.get_provider("Moonshot")["id"], "kimi")
        self.assertEqual(ai_providers.get_provider("qianfan")["id"], "ernie")
        self.assertEqual(ai_providers.get_provider("Ollama")["id"], "local")
        self.assertEqual(ai_providers.get_provider("  DeepSeek  ")["id"], "deepseek")

    def test_resolve_model(self):
        provider = ai_providers.get_provider("deepseek")
        self.assertEqual(ai_providers.resolve_model(provider, ""), "deepseek-chat")
        self.assertEqual(ai_providers.resolve_model(provider, "  "), "deepseek-chat")
        self.assertEqual(ai_providers.resolve_model(provider, "deepseek-reasoner"), "deepseek-reasoner")
        self.assertEqual(ai_providers.resolve_model("qwen", None), "qwen-plus")


# ---------------------------------------------------------------- 工具函数


class MaskKeyTests(unittest.TestCase):
    def test_masks_long_key(self):
        self.assertEqual(ai_client.mask_key(SECRET), "sk-t****")

    def test_masks_short_or_empty(self):
        self.assertEqual(ai_client.mask_key("short"), "****")
        self.assertEqual(ai_client.mask_key(""), "")
        self.assertEqual(ai_client.mask_key(None), "")

    def test_never_contains_full_key(self):
        masked = ai_client.mask_key(SECRET)
        self.assertNotIn(SECRET, masked)
        self.assertLess(len(masked), len(SECRET))


class ExtractJsonTests(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(ai_client.extract_json('{"a": 1}'), {"a": 1})

    def test_strips_json_fence(self):
        text = '好的，结果如下：\n```json\n{"question": "你更喜欢哪门课？", "tags": ["兴趣"]}\n```\n希望有用'
        self.assertEqual(
            ai_client.extract_json(text),
            {"question": "你更喜欢哪门课？", "tags": ["兴趣"]},
        )

    def test_strips_bare_fence(self):
        self.assertEqual(ai_client.extract_json("```\n{\"x\": [1, 2]}\n```"), {"x": [1, 2]})

    def test_extracts_object_from_chatter(self):
        self.assertEqual(ai_client.extract_json('前缀 {"b": true} 后缀'), {"b": True})

    def test_rejects_non_object(self):
        self.assertIsNone(ai_client.extract_json("[1, 2, 3]"))
        self.assertIsNone(ai_client.extract_json("就是一段普通文字"))
        self.assertIsNone(ai_client.extract_json(""))
        self.assertIsNone(ai_client.extract_json(None))


# ---------------------------------------------------------------- 配置


class AIConfigTests(unittest.TestCase):
    def test_defaults_come_from_provider(self):
        config = ai_client.AIConfig(provider_id="qwen", api_key=SECRET)
        self.assertEqual(config.model, "qwen-plus")
        self.assertEqual(config.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(config.endpoint(), "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")

    def test_explicit_values_win(self):
        config = ai_client.AIConfig(
            provider_id="kimi",
            model="moonshot-v1-8k",
            base_url="https://proxy.example.com/v1/",
            api_key=SECRET,
        )
        self.assertEqual(config.model, "moonshot-v1-8k")
        self.assertEqual(config.base_url, "https://proxy.example.com/v1")

    def test_strips_chat_completions_suffix(self):
        config = ai_client.AIConfig(provider_id="deepseek", base_url="https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(config.endpoint(), API)

    def test_clamps_temperature_and_tokens(self):
        config = ai_client.AIConfig(provider_id="deepseek", temperature=9, max_tokens=999999)
        self.assertEqual(config.temperature, 2.0)
        self.assertEqual(config.max_tokens, ai_client.MAX_TOKENS_LIMIT)
        config = ai_client.AIConfig(provider_id="deepseek", temperature=-3, max_tokens=0, timeout=1)
        self.assertEqual(config.temperature, 0.0)
        self.assertEqual(config.max_tokens, 1)
        self.assertEqual(config.timeout, 5.0)

    def test_unknown_provider_raises_early(self):
        with self.assertRaises(ai_providers.AIError):
            ai_client.AIConfig(provider_id="not-a-provider")

    def test_from_mapping_accepts_aliases(self):
        config = ai_client.AIConfig.from_mapping(
            {"provider": "moonshot", "key": SECRET, "model_id": "moonshot-v1-32k", "timeout": "30"}
        )
        self.assertEqual(config.provider_id, "kimi")
        self.assertEqual(config.api_key, SECRET)
        self.assertEqual(config.model, "moonshot-v1-32k")
        self.assertEqual(config.timeout, 30.0)
        self.assertEqual(ai_client.AIConfig.from_mapping(None).provider_id, "deepseek")

    def test_key_masked_property(self):
        config = ai_client.AIConfig(provider_id="deepseek", api_key=SECRET)
        self.assertEqual(config.key_masked, "sk-t****")


# ---------------------------------------------------------------- chat


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.config = ai_client.AIConfig(provider_id="deepseek", api_key=SECRET, timeout=20)

    def test_success_returns_content_usage_raw(self):
        with PatchedUrlopen(FakeResponse(openai_reply("你好，我是赤鲤"))) as fake:
            result = ai_client.chat(self.config, [{"role": "user", "content": "在吗"}])

        self.assertEqual(result["content"], "你好，我是赤鲤")
        self.assertEqual(result["usage"]["total_tokens"], 15)
        self.assertEqual(result["raw"]["model"], "deepseek-chat")
        self.assertEqual(fake.requests[0][0].full_url, API)
        self.assertEqual(fake.requests[0][1], 20)
        self.assertEqual(fake.last_request.get_header("Authorization"), f"Bearer {SECRET}")
        self.assertEqual(fake.last_request.get_header("Content-type"), "application/json")
        body = fake.last_body
        self.assertEqual(body["model"], "deepseek-chat")
        self.assertEqual(body["messages"], [{"role": "user", "content": "在吗"}])
        self.assertFalse(body["stream"])
        self.assertNotIn("response_format", body)

    def test_json_mode_sets_response_format(self):
        with PatchedUrlopen(FakeResponse(openai_reply('{"ok": true}'))) as fake:
            ai_client.chat(self.config, [{"role": "user", "content": "给个 JSON"}], json_mode=True)
        self.assertEqual(fake.last_body["response_format"], {"type": "json_object"})

    def test_json_mode_falls_back_when_provider_rejects_format(self):
        rejected = fake_error(400, {"error": {"message": "response_format is not supported by this model"}})
        with PatchedUrlopen(rejected, FakeResponse(openai_reply('{"ok": true}'))) as fake:
            result = ai_client.chat(self.config, [{"role": "user", "content": "给个 JSON"}], json_mode=True)
        self.assertEqual(result["content"], '{"ok": true}')
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.last_body["messages"][0]["content"], "给个 JSON")
        self.assertNotIn("response_format", fake.last_body)
        # 第一次请求是带 response_format 的，被拒后才降级
        first = json.loads(fake.requests[0][0].data.decode("utf-8"))
        self.assertIn("response_format", first)

    def test_rejects_empty_messages(self):
        with self.assertRaises(ai_providers.AIError) as ctx:
            ai_client.chat(self.config, [])
        self.assertEqual(ctx.exception.code, "ai_messages_empty")

    def test_401_message_points_to_console(self):
        error = fake_error(401, {"error": {"message": "Authentication Fails, Your api key is invalid"}})
        with PatchedUrlopen(error):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        exc = ctx.exception
        self.assertEqual(exc.status, 401)
        self.assertEqual(exc.code, "ai_unauthorized")
        self.assertIn("API Key 无效或已过期", exc.message)
        self.assertIn("DeepSeek 开放平台", exc.message)
        self.assertIn("sk-t****", exc.message)
        self.assertNotIn(SECRET, exc.message)

    def test_429_message_mentions_rate_limit_and_balance(self):
        error = fake_error(429, {"error": {"message": "Rate limit reached"}})
        with PatchedUrlopen(error):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.status, 429)
        self.assertIn("触发限流或余额不足", ctx.exception.message)

    def test_404_message_mentions_base_url_and_model(self):
        error = fake_error(404, {"error": {"message": "model not found"}})
        with PatchedUrlopen(error):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        message = ctx.exception.message
        self.assertEqual(ctx.exception.status, 404)
        self.assertIn("接口地址或模型 id 不对", message)
        self.assertIn("https://api.deepseek.com/v1", message)
        self.assertIn("deepseek-chat", message)

    def test_403_message_mentions_permission(self):
        with PatchedUrlopen(fake_error(403, {"error": {"message": "forbidden"}})):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("没有调用权限", ctx.exception.message)

    def test_timeout_message_includes_seconds(self):
        with PatchedUrlopen(TimeoutError("timed out")):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.status, 504)
        self.assertEqual(ctx.exception.code, "ai_timeout")
        self.assertIn("请求超时", ctx.exception.message)
        self.assertIn("20s", ctx.exception.message)

    def test_urlopen_timeout_reason_is_recognised(self):
        error = urllib.error.URLError(socket.timeout("timed out"))
        with PatchedUrlopen(error):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.code, "ai_timeout")

    def test_connection_error_suggests_ollama(self):
        config = ai_client.AIConfig(provider_id="local", api_key="local", timeout=10)
        error = urllib.error.URLError(ConnectionRefusedError(10061, "拒绝连接"))
        with PatchedUrlopen(error):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.status, 502)
        self.assertIn("连不上", ctx.exception.message)
        self.assertIn("127.0.0.1:11434", ctx.exception.message)
        self.assertIn("Ollama", ctx.exception.message)

    def test_non_json_response_is_explained(self):
        with PatchedUrlopen(FakeResponse(b"<html>404 Not Found</html>")):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.code, "ai_bad_response")
        self.assertIn("不是 JSON", ctx.exception.message)

    def test_empty_content_is_explained(self):
        with PatchedUrlopen(FakeResponse(openai_reply("   "))):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.code, "ai_empty")

    def test_missing_choices_is_explained(self):
        with PatchedUrlopen(FakeResponse({"error": {"message": "model not exist"}})):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.code, "ai_bad_response")
        self.assertIn("model not exist", ctx.exception.message)

    def test_logs_never_contain_raw_key(self):
        with self.assertLogs("app.ai_client", level="INFO") as logs:
            with PatchedUrlopen(FakeResponse(openai_reply("好的"))):
                ai_client.chat(self.config, [{"role": "user", "content": "hi"}])
        text = "\n".join(logs.output)
        self.assertNotIn(SECRET, text)
        self.assertIn("sk-t****", text)


# ---------------------------------------------------------------- interview


class InterviewTests(unittest.TestCase):
    def setUp(self):
        self.config = ai_client.AIConfig(provider_id="deepseek", api_key=SECRET)

    def test_returns_question_hint_tags(self):
        payload = {
            "question": "你平时做物理题是觉得有意思，还是纯粹为了分数？",
            "hint": "没有对错，按真实感受说就行",
            "tags": ["兴趣", "物理"],
        }
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))):
            result = ai_client.interview(
                self.config,
                profile_summary={"province": "江苏", "likes": ["物理"]},
                history=[{"role": "assistant", "content": "你喜欢哪门课？"}, {"role": "user", "content": "物理"}],
                question="物理",
                step=2,
            )
        self.assertEqual(result["question"], payload["question"])
        self.assertEqual(result["hint"], payload["hint"])
        self.assertEqual(result["tags"], ["兴趣", "物理"])

    def test_prompt_is_chinese_and_forbids_self_intro(self):
        with PatchedUrlopen(FakeResponse(openai_reply('{"question": "然后呢", "hint": "", "tags": []}'))) as fake:
            ai_client.interview(self.config, profile_summary="江苏高一", question="喜欢物理", step=1)
        body = fake.last_body
        self.assertEqual(body["messages"][0]["role"], "system")
        system = body["messages"][0]["content"]
        self.assertIn("高一选科", system)
        self.assertIn("一次只问一个问题", system)
        self.assertIn("不要提「我是 AI」", system)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertIn("第 1 轮", body["messages"][1]["content"])

    def test_degrades_to_plain_text_instead_of_failing(self):
        with PatchedUrlopen(FakeResponse(openai_reply("那数学呢？你平时数学能考多少分？"))):
            result = ai_client.interview(self.config, profile_summary="", question="", step=1)
        self.assertIn("数学", result["question"])
        self.assertEqual(result["hint"], "")
        self.assertEqual(result["tags"], [])


# ---------------------------------------------------------------- report


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.config = ai_client.AIConfig(provider_id="deepseek", api_key=SECRET)

    def test_returns_full_structure(self):
        payload = {
            "headline": "物理化学是你的主场",
            "summary": "你理科兴趣明显，物理化学组合覆盖 96% 的理工专业。",
            "combo_fit": [
                {"combo": "物理+化学+生物", "why": "覆盖医学与工科", "watch": "生物高二背诵量陡增"},
                {"combo": "物理+化学+地理", "why": "地理赋分相对友好", "watch": "部分医学专业要求生物"},
            ],
            "risk": ["生物学科竞争激烈", "地理高二自然地理偏难"],
            "next": ["这学期把化学必修二吃透", "找两节医学导论慕课试听"],
        }
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))) as fake:
            result = ai_client.report(
                self.config,
                profile={"province": "江苏", "interest": "物理"},
                combos=["物理+化学+生物", "物理+化学+地理"],
                majors=["临床医学", "计算机科学与技术"],
            )
        self.assertEqual(result["headline"], payload["headline"])
        self.assertEqual(len(result["combo_fit"]), 2)
        self.assertEqual(result["combo_fit"][0]["combo"], "物理+化学+生物")
        self.assertEqual(result["risk"], payload["risk"])
        self.assertEqual(result["next"], payload["next"])
        body = fake.last_body
        self.assertEqual(body["response_format"], {"type": "json_object"})
        user_prompt = body["messages"][1]["content"]
        self.assertIn("临床医学", user_prompt)
        self.assertIn("物理+化学+生物", user_prompt)

    def test_non_json_raises_actionable_error(self):
        with PatchedUrlopen(FakeResponse(openai_reply("抱歉，我无法生成报告。"))):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.report(self.config, profile={"a": 1}, combos=["物理+化学+生物"])
        self.assertEqual(ctx.exception.code, "ai_bad_json")
        self.assertIn("模型没有按 JSON 返回", ctx.exception.message)

    def test_missing_fields_are_filled(self):
        with PatchedUrlopen(FakeResponse(openai_reply('{"headline": "就选物化生" }'))):
            result = ai_client.report(self.config, profile={}, combos=[])
        self.assertEqual(result["headline"], "就选物化生")
        self.assertEqual(result["summary"], "")
        self.assertEqual(result["combo_fit"], [])
        self.assertEqual(result["risk"], [])
        self.assertEqual(result["next"], [])

    def test_empty_json_raises(self):
        with PatchedUrlopen(FakeResponse(openai_reply("{}"))):
            with self.assertRaises(ai_providers.AIError) as ctx:
                ai_client.report(self.config, profile={}, combos=[])
        self.assertEqual(ctx.exception.code, "ai_bad_json")


class MajorAdvisorTests(unittest.TestCase):
    """选专业顾问：AI 接入的重点场景是「这个专业我该不该选」。"""

    def setUp(self):
        self.config = ai_client.AIConfig(provider_id="deepseek", api_key=SECRET)

    def test_returns_reply_level_points_probes(self):
        payload = {
            "reply": "计算机科学与技术的主干课是数据结构、操作系统、计算机网络、编译原理。你现在数学和物理都不弱，学起来不会太吃力，但要有心理准备：大二要写很多代码。",
            "level": "match",
            "points": ["数学要求高", "就业面宽", "需要长期自学"],
            "probes": ["和软件工程有什么区别？", "不擅长数学能学吗？"],
        }
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))) as fake:
            result = ai_client.major_advisor(
                self.config,
                major="计算机科学与技术",
                question="这个专业学什么？",
                profile={"subject": {"physics": 88}},
                combo="物理+化学+生物",
                context="学什么：数据结构与算法",
            )
        self.assertEqual(result["reply"], payload["reply"])
        self.assertEqual(result["level"], "match")
        self.assertEqual(result["points"], payload["points"])
        self.assertEqual(result["probes"], payload["probes"])
        body = fake.last_body
        self.assertEqual(body["response_format"], {"type": "json_object"})
        prompt = body["messages"][1]["content"]
        self.assertIn("计算机科学与技术", prompt)
        self.assertIn("数据结构与算法", prompt)
        self.assertIn("物理+化学+生物", prompt)
        self.assertIn("这个专业学什么", prompt)

    def test_default_question_when_empty(self):
        with PatchedUrlopen(FakeResponse(openai_reply('{"reply": "先看课程"}'))) as fake:
            ai_client.major_advisor(self.config, major="法学")
        self.assertIn("这个专业到底学什么", fake.last_body["messages"][1]["content"])

    def test_non_json_degrades_to_plain_text(self):
        # 对话断了比格式不完美更糟：解析失败不抛错，把原文当回答
        with PatchedUrlopen(FakeResponse(openai_reply("这个专业主要学数据结构。"))):
            result = ai_client.major_advisor(self.config, major="计算机科学与技术")
        self.assertEqual(result["reply"], "这个专业主要学数据结构。")
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["points"], [])

    def test_unknown_level_falls_back(self):
        with PatchedUrlopen(FakeResponse(openai_reply('{"reply": "还行", "level": "great"}'))) as fake:
            result = ai_client.major_advisor(self.config, major="法学")
        self.assertEqual(result["level"], "unknown")

    def test_empty_reply_gets_default(self):
        with PatchedUrlopen(FakeResponse(openai_reply('{"level": "caution"}'))):
            result = ai_client.major_advisor(self.config, major="法学")
        self.assertTrue(result["reply"])
        self.assertEqual(result["level"], "caution")

    def test_missing_major_raises(self):
        with self.assertRaises(ai_providers.AIError) as ctx:
            ai_client.major_advisor(self.config, major="   ")
        self.assertEqual(ctx.exception.code, "major_required")

    def test_points_and_probes_are_capped(self):
        payload = {
            "reply": "可以",
            "level": "caution",
            "points": ["一", "二", "三", "四", "五"],
            "probes": ["甲", "乙", "丙", "丁"],
        }
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))):
            result = ai_client.major_advisor(self.config, major="会计学")
        self.assertEqual(len(result["points"]), 4)
        self.assertEqual(len(result["probes"]), 3)


# ---------------------------------------------------------------- ping


class PingTests(unittest.TestCase):
    def test_ping_reports_latency_and_model(self):
        with PatchedUrlopen(FakeResponse(openai_reply("收到"))):
            result = ai_client.ping(ai_client.AIConfig(provider_id="deepseek", api_key=SECRET))
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["model"], "deepseek-chat")
        self.assertEqual(result["reply"], "收到")
        self.assertIsInstance(result["latency_ms"], int)


class CoachTests(unittest.TestCase):
    """引导式对话：AI 主动提问，学生回答，最后收敛出方向。"""

    def setUp(self):
        self.config = ai_client.AIConfig(provider_id="deepseek", api_key=SECRET)

    def test_returns_say_ask_options_stage(self):
        payload = {
            "say": "好，先不聊专业名字。",
            "ask": "最近一个月，你在什么事上不知不觉花了两小时？",
            "options": ["拆装电脑", "看小说", "打球"],
            "stage": "interest",
            "done": False,
        }
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))) as fake:
            result = ai_client.coach(self.config, province="江苏", turn=0)
        self.assertEqual(result["say"], payload["say"])
        self.assertEqual(result["ask"], payload["ask"])
        self.assertEqual(result["options"], payload["options"])
        self.assertEqual(result["stage"], "interest")
        self.assertFalse(result["done"])
        body = fake.last_body
        self.assertEqual(body["response_format"], {"type": "json_object"})
        prompt = body["messages"][1]["content"]
        self.assertIn("江苏", prompt)
        self.assertIn("第 1 轮", prompt)

    def test_first_turn_says_not_chatted_yet(self):
        with PatchedUrlopen(FakeResponse(openai_reply('{"say":"好","ask":"你最近在忙什么？"}'))) as fake:
            ai_client.coach(self.config)
        self.assertIn("第一轮", fake.last_body["messages"][1]["content"])

    def test_close_stage_marks_done_and_keeps_suggestion(self):
        payload = {
            "say": "行，我大概有数了。",
            "ask": "",
            "options": [],
            "stage": "close",
            "done": True,
            "suggestion": {
                "directions": ["电子信息类", "自动化类", "计算机类"],
                "why": "你更愿意把问题弄明白。",
            },
        }
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))):
            result = ai_client.coach(self.config, turn=5)
        self.assertTrue(result["done"])
        self.assertEqual(result["ask"], "")
        self.assertEqual(result["suggestion"]["directions"], payload["suggestion"]["directions"])
        self.assertEqual(result["suggestion"]["why"], payload["suggestion"]["why"])

    def test_turn_six_forces_done_even_if_model_asks_again(self):
        # 模型忘了收敛时，用轮次兜底，别让学生一直答下去
        payload = {"say": "再问一个", "ask": "还有呢？", "stage": "reality", "done": False}
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))):
            result = ai_client.coach(self.config, turn=6)
        self.assertTrue(result["done"])
        self.assertEqual(result["ask"], "")

    def test_non_json_degrades_to_fallback_question(self):
        with PatchedUrlopen(FakeResponse(openai_reply("先说个大概吧。"))):
            result = ai_client.coach(self.config)
        self.assertEqual(result["say"], "先说个大概吧。")
        self.assertTrue(result["ask"])
        self.assertEqual(result["stage"], "interest")
        self.assertFalse(result["done"])
        self.assertIsNone(result["suggestion"])

    def test_limits_directions_to_three_and_options_to_four(self):
        payload = {
            "say": "聊聊",
            "ask": "选一个",
            "options": ["a", "b", "c", "d", "e"],
            "stage": "ability",
            "done": True,
            "suggestion": {"directions": ["一", "二", "三", "四"], "why": "理由"},
        }
        with PatchedUrlopen(FakeResponse(openai_reply(json.dumps(payload, ensure_ascii=False)))):
            result = ai_client.coach(self.config, turn=3)
        self.assertEqual(len(result["options"]), 4)
        self.assertEqual(len(result["suggestion"]["directions"]), 3)


if __name__ == "__main__":
    unittest.main()
