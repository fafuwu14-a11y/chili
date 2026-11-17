"""OpenAI 兼容协议的调用封装：只用 ``urllib.request``，零第三方依赖。

整个 AI 层只有这一处会发网络请求，其他模块（server、前端）都通过这里的
:func:`chat` / :func:`interview` / :func:`report` 走，好处是超时、重试、
错误文案、Key 脱敏只在一个地方维护。

**Key 不落盘**：``api_key`` 只活在 :class:`AIConfig` 对象里，日志里一律走
:func:`mask_key`。这不是可选项——``docs/选科改版方案.md`` 第 3.6 节写死了
「后端不落盘、不进日志」。

错误分层：所有异常统一收敛成 :class:`app.ai_providers.AIError`，``status``
是建议的 HTTP 码、``code`` 给前端做分支（比如 ``ai_timeout`` 就提示换模型）。
文案原则是**能指导用户下一步点哪里**，不是把服务端英文原文甩给高中生。
"""

from __future__ import annotations

import json
import logging
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from .ai_providers import (
    DEFAULT_PROVIDER_ID,
    AIError,
    get_provider,
    normalise_id,
    resolve_model,
)

__all__ = [
    "AIConfig",
    "AIError",
    "mask_key",
    "extract_json",
    "chat",
    "interview",
    "report",
    "ping",
]

logger = logging.getLogger(__name__)

# 单次对话的硬上限，防止前端传个离谱的 max_tokens 把账单打爆
MAX_TOKENS_LIMIT = 8000
# 送进 prompt 的历史条数上限（选科追问用不到更多）
HISTORY_LIMIT = 8
# 画像/组合这类结构化内容序列化后的字符上限，超了截断，避免撑爆上下文
CONTEXT_CHARS_LIMIT = 4000

# 匹配 ```json ... ``` 或 ``` ... ``` 围栏，模型很爱加这个
_FENCE_RE = re.compile(r"```[ \t]*(?:json|JSON)?[ \t]*\r?\n?(.*?)```", re.S)
# HTTP 400 里出现这些字样，说明是「不支持 JSON 模式」，可以去掉 response_format 重试
_FORMAT_HINTS = ("response_format", "json_object", "json mode", "json_mode")


# ---------------------------------------------------------------- 小工具


def mask_key(key: Any) -> str:
    """日志里用的脱敏形式：``sk-1234****``。空值返回空串。"""
    if not key:
        return ""
    text = str(key).strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return text[:4] + "****"


def extract_json(text: Any) -> dict[str, Any] | None:
    """从模型回复里抠出一个 JSON 对象，抠不出来返回 ``None``。

    依次尝试：```json 围栏内的内容 → 整段原文 → 第一个 ``{`` 到最后一个 ``}``。
    只在结果**是对象**时返回；数组或纯文本一律 ``None``，交给调用方决定怎么办。
    """
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None

    candidates: list[str] = []
    fenced = _FENCE_RE.search(raw)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _as_text(value: Any, limit: int = CONTEXT_CHARS_LIMIT) -> str:
    """把 dict / list / str 统一变成一段紧凑中文文本，并截断。"""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            text = str(value)
    if len(text) > limit:
        text = text[:limit] + f"…（已截断，原长 {len(text)} 字）"
    return text


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 配置


@dataclass
class AIConfig:
    """一次调用需要的全部参数；``base_url`` / ``model`` 没填就从厂商表取默认。"""

    provider_id: str = DEFAULT_PROVIDER_ID
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.6
    timeout: float = 60.0
    max_tokens: int = 1600

    def __post_init__(self) -> None:
        self.provider_id = normalise_id(self.provider_id) or DEFAULT_PROVIDER_ID
        provider = get_provider(self.provider_id)  # 未知 id 在这里就抛，早失败
        self.model = resolve_model(provider, self.model)
        base_url = (self.base_url or provider["base_url"]).strip()
        # 允许用户手滑把 /chat/completions 一起粘进来
        base_url = re.sub(r"/chat/completions/?$", "", base_url.rstrip("/"))
        self.base_url = base_url.rstrip("/")
        self.temperature = min(2.0, max(0.0, _as_float(self.temperature, 0.6)))
        self.timeout = max(5.0, _as_float(self.timeout, 60.0))
        self.max_tokens = min(MAX_TOKENS_LIMIT, max(1, _as_int(self.max_tokens, 1600)))

    # -- 便捷构造 --------------------------------------------------

    @classmethod
    def from_mapping(cls, data: Any = None) -> "AIConfig":
        """从 dict（比如前端 ``X-AI-*`` 头组装出来的）构造，字段名尽量宽容。"""
        if not isinstance(data, dict):
            return cls()
        provider = (
            data.get("provider_id")
            or data.get("provider")
            or data.get("vendor")
            or DEFAULT_PROVIDER_ID
        )
        return cls(
            provider_id=provider,
            model=data.get("model") or data.get("model_id") or "",
            api_key=data.get("api_key") or data.get("key") or data.get("apikey") or "",
            base_url=data.get("base_url") or data.get("baseUrl") or data.get("host") or "",
            temperature=data.get("temperature", 0.6),
            timeout=data.get("timeout", 60.0),
            max_tokens=data.get("max_tokens", 1600),
        )

    @property
    def provider_name(self) -> str:
        return str(get_provider(self.provider_id).get("name") or self.provider_id)

    @property
    def console_name(self) -> str:
        """厂商控制台的中文名，401 文案里让用户知道去哪儿复制 Key。"""
        return str(get_provider(self.provider_id).get("console") or self.provider_name)

    @property
    def key_masked(self) -> str:
        return mask_key(self.api_key)

    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"


# ---------------------------------------------------------------- 单次调用


def chat(
    config: AIConfig,
    messages: Iterable[dict[str, Any]],
    *,
    json_mode: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    """POST ``{base_url}/chat/completions``，返回 ``{"content", "usage", "raw"}``。

    ``json_mode=True`` 时带上 ``response_format={"type":"json_object"}``；个别
    厂商不认这个字段，会在 400 里明说，这里自动去掉重试一次，不打扰用户。
    """
    if not isinstance(config, AIConfig):
        raise AIError("内部错误：AI 配置类型不对", 500, "ai_config_invalid")
    norm_messages = _normalise_messages(messages)
    if not norm_messages:
        raise AIError("对话内容不能为空", 400, "ai_messages_empty")

    payload: dict[str, Any] = {
        "model": config.model,
        "messages": norm_messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    timeout_s = max(5.0, _as_float(timeout if timeout is not None else config.timeout, 60.0))
    url = config.endpoint()

    logger.info(
        "AI 请求 provider=%s model=%s key=%s json=%s timeout=%ss",
        config.provider_id,
        config.model,
        config.key_masked,
        json_mode,
        timeout_s,
    )
    started = time.monotonic()
    provider = get_provider(config.provider_id)
    try:
        data = _post(url, payload, config.api_key, timeout_s, provider)
    except AIError as exc:
        # 只有「不支持 JSON 模式」才降级重试；Key 错/限流/404 直接抛，别重试浪费用户时间
        if json_mode and exc.code == "ai_bad_request" and _mentions_format_mode(exc.message):
            payload.pop("response_format", None)
            logger.warning("该厂商不支持 JSON 模式，已改为普通模式重试：%s", config.provider_id)
            data = _post(url, payload, config.api_key, timeout_s, provider)
        else:
            raise
    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info("AI 返回 provider=%s 用时=%sms", config.provider_id, elapsed_ms)

    choice = _first_choice(data)
    message = choice.get("message") if isinstance(choice, dict) else None
    content = ""
    if isinstance(message, dict):
        content = message.get("content") or ""
    if not isinstance(content, str):
        content = str(content)
    if not content.strip():
        raise AIError(
            f"{config.provider_name} 返回了空内容，可能是模型不支持该参数，换默认模型再试",
            502,
            "ai_empty",
        )
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {"content": content, "usage": usage, "raw": data}


def _normalise_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """只保留 role/content，顺手把 role 规整成协议认的三个值。"""
    result: list[dict[str, str]] = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip().lower()
        if role not in ("system", "user", "assistant"):
            role = "user"
        content = item.get("content")
        if content is None:
            continue
        if not isinstance(content, str):
            content = _as_text(content)
        if not content.strip():
            continue
        result.append({"role": role, "content": content})
    return result


def _first_choice(data: Any) -> dict[str, Any]:
    """取 ``choices[0]``，结构不对就抛可读错误。"""
    if not isinstance(data, dict):
        raise AIError("AI 接口返回的不是 JSON 对象，检查 base_url 是否指向了网页而不是 API", 502, "ai_bad_response")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        # 有的厂商出错时也返回 200，把错误塞在 error 字段里
        error = data.get("error")
        if error:
            raise AIError(f"AI 接口报错：{_error_detail(error)}", 502, "ai_bad_response")
        raise AIError("AI 接口没有返回 choices，可能是模型 id 写错了", 502, "ai_bad_response")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise AIError("AI 接口返回结构异常（choices[0] 不是对象）", 502, "ai_bad_response")
    return choice


def _post(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout_s: float,
    provider: dict[str, Any],
) -> dict[str, Any]:
    """真正发请求的地方；所有网络异常在这里翻译成中文 AIError。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        # 不设 User-Agent 有些网关会直接 403
        "User-Agent": "chili-gaokao/1.0 (+python-urllib)",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:  # 必须先于 URLError，它是子类
        raise _http_error(exc, url, payload, provider, api_key) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise _timeout_error(timeout_s) from exc
        raise AIError(
            f"连不上 {url.split('/v1')[0]}，检查网络或代理设置；"
            "用本地模型的话，先确认 Ollama 已经启动（ollama serve）",
            502,
            "ai_unreachable",
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise _timeout_error(timeout_s) from exc
    except OSError as exc:
        raise AIError(f"网络异常：{exc}，检查网络后重试", 502, "ai_network") from exc

    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError) as exc:
        preview = raw[:120].decode("utf-8", "replace").replace("\n", " ")
        raise AIError(
            f"接口返回的不是 JSON（开头是「{preview}」），base_url 可能填成了网页地址",
            502,
            "ai_bad_response",
        ) from exc
    return data


def _http_error(
    exc: urllib.error.HTTPError,
    url: str,
    payload: dict[str, Any],
    provider: dict[str, Any],
    api_key: str,
) -> AIError:
    """把 HTTP 状态码翻译成用户能照着做的一句话。"""
    status = int(getattr(exc, "code", 0) or 0)
    detail = _read_error_body(exc)
    console = str(provider.get("console") or provider.get("name") or "厂商控制台")
    model = payload.get("model", "")
    base_url = url[: -len("/chat/completions")] if url.endswith("/chat/completions") else url

    if status == 401:
        shown = mask_key(api_key) or "空的"
        return AIError(
            f"API Key 无效或已过期，请到{console}重新复制（当前填的是 {shown}）",
            401,
            "ai_unauthorized",
        )
    if status == 403:
        return AIError(
            f"这个 Key 没有调用权限：可能没实名认证、没开通该模型，或 Key 被限制。"
            f"到{console}开通后重试",
            403,
            "ai_forbidden",
        )
    if status == 404:
        return AIError(
            f"接口地址或模型 id 不对：base_url={base_url}，model={model}。"
            "base_url 要填到 /v1 或 /v4 这一级，模型名照抄厂商文档",
            404,
            "ai_not_found",
        )
    if status == 429:
        return AIError(
            f"触发限流或余额不足：等 1~2 分钟再试；一直这样就到{console}看余额/免费额度是否用完",
            429,
            "ai_rate_limited",
        )
    if status in (400, 422):
        return AIError(
            f"请求参数被拒绝（HTTP {status}）：{detail or '可能是模型不支持该参数，或 max_tokens 超限'}",
            400,
            "ai_bad_request",
        )
    if status in (500, 502, 503, 504):
        return AIError(
            f"{provider.get('name', '厂商')} 服务端出错（HTTP {status}），歇一会儿重试，"
            "或者先换个厂商/模型",
            502,
            "ai_upstream",
        )
    return AIError(
        f"调用失败（HTTP {status}）：{detail or '没有更多信息'}",
        400 if status < 500 else 502,
        "ai_http_error",
    )


def _timeout_error(timeout_s: float) -> AIError:
    return AIError(
        f"请求超时（{timeout_s:g}s），可换更快的模型（比如 flash/turbo 系列）或调大超时",
        504,
        "ai_timeout",
    )


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    """从错误响应里抠一句人话，抠不到返回空串。"""
    try:
        raw = exc.read()
    except Exception:  # noqa: BLE001 - 读不到就算了，不能因为这个再抛一次
        return ""
    if not raw:
        return ""
    text = raw[:2000].decode("utf-8", "replace").strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return text[:160].replace("\n", " ")
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return _error_detail(error)
        if isinstance(error, str):
            return error[:160]
        for key in ("message", "msg", "detail", "error_msg"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value[:160]
    return text[:160].replace("\n", " ")


def _error_detail(error: Any) -> str:
    if isinstance(error, dict):
        for key in ("message", "msg", "detail", "code"):
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                return value[:160]
    return str(error)[:160]


def _mentions_format_mode(detail: str) -> bool:
    low = (detail or "").lower()
    return any(hint in low for hint in _FORMAT_HINTS)


# ---------------------------------------------------------------- 业务入口

INTERVIEW_SYSTEM_PROMPT = """你是一名高一选科规划助手，正在通过对话帮学生确定「3+1+2」或「3+3」的选科组合。

说话要求：
1. 一次只问一个问题，问题要短（30 字以内）、口语化，像学长聊天，不要书面腔。
2. 必须结合学生已经答过的内容追问，不要重复问过的信息；他答得含糊就往下挖一层。
3. 不要评价学生「对/错」，不要急着给结论，你只负责把情况问清楚。
4. 只输出内容本身，不要自我介绍，不要提「我是 AI」「作为语言模型」之类的话。

输出一个 JSON 对象，不要 markdown 代码块：
{"question": "下一个要问的问题", "hint": "一句给学生的提示或备选答案", "tags": ["本题涉及的维度，如 兴趣/能力/专业倾向"]}"""


def interview(
    config: AIConfig,
    *,
    profile_summary: Any = "",
    history: Any = None,
    question: str = "",
    step: int = 1,
) -> dict[str, Any]:
    """选科 AI 追问的统一入口，返回 ``{"question", "hint", "tags"}``。

    模型偶尔不按 JSON 返回，这里**不报错**：把纯文本当问题用，追问流程不能断。
    """
    history_text = _history_text(history)
    user_parts = [
        f"【学生画像】{_as_text(profile_summary) or '（还没填，先问基本信息）'}",
        f"【当前是第 {max(1, _as_int(step, 1))} 轮追问】",
    ]
    if history_text:
        user_parts.append(f"【已经聊过的内容】\n{history_text}")
    if question:
        user_parts.append(f"【他刚才的回答】{_as_text(question, 800)}")
    user_parts.append("请给出下一个问题，只输出 JSON。")

    result = chat(
        config,
        [
            {"role": "system", "content": INTERVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        json_mode=True,
    )
    parsed = extract_json(result["content"])
    if parsed is None:
        logger.warning("interview 未按 JSON 返回，已退化为纯文本：%s", mask_key(config.api_key))
        return {
            "question": _strip_noise(result["content"]),
            "hint": "",
            "tags": [],
            "usage": result["usage"],
        }

    return {
        "question": _clean_str(parsed.get("question")) or "再具体说说你的想法？",
        "hint": _clean_str(parsed.get("hint")),
        "tags": _clean_tags(parsed.get("tags")),
        "usage": result["usage"],
    }


REPORT_SYSTEM_PROMPT = """你是一名高考选科与专业规划顾问，服务对象是高一学生和他的家长。请基于给定画像和候选组合，写一份可以直接展示在页面上的个性化解读。

要求：
1. 全部用中文，语气务实、具体，像有经验的班主任；不夸张、不空泛、不堆术语。
2. combo_fit 必须覆盖给出的每一个组合：why 说「为什么适合他」（结合兴趣/能力/硬条件），watch 说「选这个要注意什么」（哪门课会变难、哪些专业报不了）。
3. risk 写 2-4 条真实风险，next 写 2-4 条这学期就能动手做的事。
4. 不要提「我是 AI」「作为语言模型」，不要输出解释性前言。

只输出一个 JSON 对象（不要 markdown 代码块），结构如下：
{"headline": "一句话结论，20 字以内", "summary": "150 字以内的整体解读", "combo_fit": [{"combo": "组合名", "why": "为什么适合", "watch": "要注意什么"}], "risk": ["..."], "next": ["..."]}"""


def report(
    config: AIConfig,
    *,
    profile: Any,
    combos: Any,
    majors: Any = None,
) -> dict[str, Any]:
    """生成个性化解读，返回 ``{"headline","summary","combo_fit","risk","next"}``。

    这里和 :func:`interview` 相反：JSON 解析失败必须抛错——报告是最终产物，
    纯文本塞不进页面结构，硬塞只会显示成一段乱码。
    """
    user_parts = [f"【学生画像】\n{_as_text(profile)}", f"【候选组合】\n{_as_text(combos)}"]
    if majors:
        user_parts.append(f"【可能感兴趣的专业】\n{_as_text(majors)}")
    user_parts.append("请按约定的 JSON 结构输出解读。")

    result = chat(
        config,
        [
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        json_mode=True,
    )
    parsed = extract_json(result["content"])
    if parsed is None:
        preview = result["content"].strip()[:60].replace("\n", " ")
        raise AIError(
            f"模型没有按 JSON 返回，无法生成解读（它返回的开头是「{preview}…」）。"
            "换一个模型（如 deepseek-chat / qwen-plus）或重试一次",
            502,
            "ai_bad_json",
        )
    if not any(parsed.get(key) for key in ("headline", "summary", "combo_fit", "risk", "next")):
        raise AIError("模型返回了空 JSON，重试一次或换个模型", 502, "ai_bad_json")

    return {
        "headline": _clean_str(parsed.get("headline")),
        "summary": _clean_str(parsed.get("summary")),
        "combo_fit": _clean_combo_fit(parsed.get("combo_fit")),
        "risk": _clean_list(parsed.get("risk")),
        "next": _clean_list(parsed.get("next")),
        "usage": result["usage"],
    }


MAJOR_SYSTEM_PROMPT = """你是一名专业选择顾问，坐在对面的是一位高一学生和他的家长。他们正在看一个具体专业的介绍页，想弄清楚「这个专业到底学什么、我该不该选」。

说话要求：
1. 全部用中文，像一个带过很多届毕业班的老师：具体、诚实、有分寸。不写招生宣传语。
2. 只讲你能确定的事。不要编造排名、薪资数字、招生计划、就业率；不确定就明说「这个要看具体学校」。
3. 学生画像和该专业的差距要直说，不要为了让对方高兴而含糊。但语气是建议，不是审判。
4. 讲到课程就说真实的主干课名字，讲到就业就说真实岗位类型；家长听得懂比术语准确更重要。
5. 不要提「我是 AI」「作为语言模型」，不要输出前言和总结套话。

只输出一个 JSON 对象（不要 markdown 代码块）：
{"reply": "120-200 字的回答，先直接回答他问的问题", "level": "match 或 caution 或 mismatch 或 unknown", "points": ["2-4 条关键判断依据，每条 20 字以内"], "probes": ["2-3 个他接着可以问的问题"]}

level 的含义：结合画像看，这个专业对他 match（合适）/ caution（要谨慎、有明确前提）/ mismatch（明显不合适）/ unknown（还没拿到画像，判断不了）。"""


def major_advisor(
    config: AIConfig,
    *,
    major: str,
    question: str = "",
    history: Any = None,
    profile: Any = None,
    combo: Any = None,
    context: Any = None,
) -> dict[str, Any]:
    """单专业顾问对话，返回 ``{"reply","level","points","probes"}``。

    和 :func:`report` 的分工：report 解读「整份选科报告」，这里只回答
    「这个专业我到底该不该选」。JSON 解析失败时退化为纯文本 reply——
    对话断了比格式不完美更糟。
    """
    name = _as_text(major, 60)
    if not name:
        raise AIError("缺少专业名称", 400, "major_required")

    user_parts = [f"【当前专业】{name}"]
    if profile:
        user_parts.append(f"【学生画像】\\n{_as_text(profile)}")
    if combo:
        user_parts.append(f"【他目前的选科组合】{_as_text(combo, 200)}")
    if context:
        user_parts.append(f"【这个专业的客观资料（以此为准，不要与之矛盾）】\\n{_as_text(context)}")
    history_text = _history_text(history)
    if history_text:
        user_parts.append(f"【之前聊过的】\\n{history_text}")
    user_parts.append(f"【他现在问】{_as_text(question, 600) or '这个专业到底学什么？我适合吗？'}")
    user_parts.append("请按约定的 JSON 结构回答。")

    result = chat(
        config,
        [
            {"role": "system", "content": MAJOR_SYSTEM_PROMPT},
            {"role": "user", "content": "\\n\\n".join(user_parts)},
        ],
        json_mode=True,
    )
    parsed = extract_json(result["content"])
    if parsed is None:
        logger.warning("major_advisor 未按 JSON 返回，已退化为纯文本：%s", mask_key(config.api_key))
        return {
            "reply": _strip_noise(result["content"]),
            "level": "unknown",
            "points": [],
            "probes": [],
            "usage": result["usage"],
        }

    level = _clean_str(parsed.get("level")).lower()
    if level not in {"match", "caution", "mismatch", "unknown"}:
        level = "unknown"
    return {
        "reply": _clean_str(parsed.get("reply")) or "这个问题我暂时答不上来，换个问法再试试。",
        "level": level,
        "points": _clean_list(parsed.get("points"))[:4],
        "probes": _clean_list(parsed.get("probes"))[:3],
        "usage": result["usage"],
    }


COACH_SYSTEM_PROMPT = """你是「赤鲤」的选科顾问，正在和一个高一学生面对面聊天。

你的任务不是回答问题，是**通过提问弄清楚他适合什么**。

硬性要求：
1. 每次回复只做两件事：先用一句人话回应他刚说的（不超过 40 字），再问**一个**问题。
2. 问题必须具体、可回答，不要问「你的兴趣是什么」这种空问题。
3. 每轮给 2-4 个候选答案（options），让他可以点选，也可以自己打字。
4. 不要给专业排名、薪资数字、录取分数——你手上没有这些数据，编一个就是害人。
5. 他说「不知道」时，换一个更小的角度问，不要重复原问题。
6. 最多 8 轮，到第 6 轮必须收敛。

按顺序推进，每轮只走一步：
- interest：他愿意在什么事上花时间
- ability：他做什么比同学轻松
- value：稳定 / 收入 / 兴趣 / 研究，更看重哪个
- reality：家里倾向、身体条件、地域偏好
- close：给出 2-3 个方向 + 一句为什么

输出 JSON：
{"say":"回应上一条","ask":"下一个问题","options":["选项1","选项2"],"stage":"interest|ability|value|reality|close","done":false,"suggestion":{"directions":["方向1","方向2"],"why":"一句话理由"}}
"""


def coach(
    config: AIConfig,
    *,
    history: Any = None,
    profile: Any = None,
    province: str = "",
    turn: int = 0,
    timeout: float | None = None,
) -> dict[str, Any]:
    """AI 主导的引导式对话：AI 提问、学生回答、AI 追问，最后收敛出方向。

    和 :func:`major_advisor` 的分工：那个是学生问、AI 答；这里是 AI 问、
    学生答。JSON 解析失败时退化成「说 + 一个兜底问题」，不中断对话。
    """
    try:
        turn = max(0, int(turn))
    except (TypeError, ValueError):
        turn = 0

    parts: list[str] = []
    if province:
        parts.append(f"【他在哪个省考试】{_as_text(province, 20)}")
    if profile:
        parts.append(f"【已有画像（来自 23 题测评，可能为空）】\n{_as_text(profile)}")
    history_text = _history_text(history)
    if history_text:
        parts.append(f"【已经聊过的】\n{history_text}")
    else:
        parts.append("【这是第一轮，还没有聊过。先用一句短话开场，然后问他第一个问题。】")
    parts.append(f"【现在是第 {turn + 1} 轮，最多 8 轮】")
    if turn >= 6:
        parts.append("【已经问够了，这一轮必须 done=true，直接给方向，不要再提问】")
    elif turn >= 4:
        parts.append("【快问完了，这一轮之后准备收敛】")
    parts.append("请按约定的 JSON 结构回答。")

    result = chat(
        config,
        [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        json_mode=True,
        timeout=timeout,
    )
    parsed = extract_json(result["content"])
    if parsed is None:
        logger.warning("coach 未按 JSON 返回，已退化为纯文本：%s", mask_key(config.api_key))
        return {
            "say": _strip_noise(result["content"]) or "我在，我们慢慢聊。",
            "ask": "最近一个月，你在什么事上不知不觉花了两小时？",
            "options": [],
            "stage": "interest",
            "done": False,
            "suggestion": None,
            "turn": turn,
            "usage": result["usage"],
        }

    stage = _clean_str(parsed.get("stage")).lower()
    if stage not in {"interest", "ability", "value", "reality", "close"}:
        stage = "interest"
    done = parsed.get("done") is True or stage == "close" or turn >= 6
    suggestion = parsed.get("suggestion")
    if not isinstance(suggestion, dict):
        suggestion = None
    else:
        suggestion = {
            "directions": _clean_list(suggestion.get("directions"))[:3],
            "why": _clean_str(suggestion.get("why"))[:200],
        }
    ask = _clean_str(parsed.get("ask"))
    if not done and not ask:
        ask = "最近一个月，你在什么事上不知不觉花了两小时？"
    return {
        "say": _clean_str(parsed.get("say")) or "嗯，我在听。",
        "ask": "" if done else ask,
        "options": _clean_list(parsed.get("options"))[:4],
        "stage": stage,
        "done": bool(done),
        "suggestion": suggestion,
        "turn": turn,
        "usage": result["usage"],
    }


def ping(config: AIConfig, *, timeout: float = 20.0) -> dict[str, Any]:
    """「一键测试」用：发一句最短的话，确认 Key、地址、模型三者都对。"""
    started = time.monotonic()
    result = chat(
        config,
        [{"role": "user", "content": "请只回复两个字：收到"}],
        timeout=timeout,
    )
    return {
        "ok": True,
        "provider": config.provider_id,
        "provider_name": config.provider_name,
        "model": config.model,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "reply": _strip_noise(result["content"])[:80],
        "usage": result["usage"],
    }


# ---------------------------------------------------------------- 输出清洗


def _clean_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().strip("`").strip()


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _clean_str(item if isinstance(item, str) else _as_text(item, 300))
        if text:
            result.append(text)
    return result


def _clean_tags(value: Any) -> list[str]:
    return [tag for tag in _clean_list(value) if len(tag) <= 12][:6]


def _clean_combo_fit(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        combo = _clean_str(item.get("combo") or item.get("name"))
        why = _clean_str(item.get("why") or item.get("reason"))
        watch = _clean_str(item.get("watch") or item.get("risk"))
        if combo or why:
            result.append({"combo": combo, "why": why, "watch": watch})
    return result


def _history_text(history: Any) -> str:
    """把对话历史压成「学生：… / 你：…」的短文本，最多留最近 8 条。"""
    if not history:
        return ""
    if isinstance(history, str):
        return _as_text(history, 1200)
    if not isinstance(history, list):
        return ""
    lines: list[str] = []
    for item in history[-HISTORY_LIMIT:]:
        if isinstance(item, dict):
            role = str(item.get("role") or "user").lower()
            content = _clean_str(item.get("content") or item.get("answer") or item.get("question"))
            if not content:
                continue
            speaker = "你" if role == "assistant" else "学生"
            lines.append(f"{speaker}：{_as_text(content, 300)}")
        elif isinstance(item, str) and item.strip():
            lines.append(f"学生：{_as_text(item, 300)}")
    return "\n".join(lines)


def _strip_noise(text: str) -> str:
    """去掉模型爱加的开场白和代码围栏，留下能直接展示的一句话。"""
    value = (text or "").strip()
    value = _FENCE_RE.sub(lambda m: m.group(1), value).strip()
    for prefix in ("好的，", "好的！", "当然，", "当然！", "以下是", "这是"):
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
    return value.strip().strip('"“”')
