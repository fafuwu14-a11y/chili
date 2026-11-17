"""AI 厂商注册表：纯数据 + 查询函数，不联网、不读环境变量、不碰任何 Key。

为什么要这张表：国内能用的「OpenAI 兼容」接口有十几家，地址、模型名、控制台
各不相同。前端「AI 接入向导」直接拿 :func:`list_providers` 的结果渲染卡片，
用户选一家、点「去申请」、把 Key 粘进来就能用，不用自己查文档。

三条硬约束（改这个文件前先读）：

1. **不存 Key**。Key 只存在用户浏览器的 ``localStorage['chili.ai.config']``，
   请求时由前端放进 ``X-AI-Key`` 头临时带给后端代理，后端不落盘、不进日志。
2. **纯标准库**。整个项目零第三方依赖，这里连 ``requests`` 都不许出现。
3. ``base_url`` 是 **OpenAI 兼容根地址**，不带 ``/chat/completions``；
   调用方统一拼 ``{base_url}/chat/completions``（见 :mod:`app.ai_client`）。

``PROVIDERS`` 里比前端多两个字段（``console``、``key_hint``），属于内部字段，
:func:`list_providers` 会剔掉，别把控制台文案漏给前端。
"""

from __future__ import annotations

import copy
from typing import Any

# ---------------------------------------------------------------- 异常


class AIError(Exception):
    """AI 层的统一错误，``status`` 直接当 HTTP 状态码用，风格照抄 ``auth.AuthError``。"""

    def __init__(self, message: str, status: int = 400, code: str = "ai_error"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


# ---------------------------------------------------------------- 数据

# 价格只是量级，用来让用户有心理预期；真实计费一律以厂商官网为准。
# ``free`` 的含义是「有长期免费额度或免费模型，适合先白嫖试试」，不是「永久免费」。
PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "name": "DeepSeek（深度求索）",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "free": False,
        "signup": "https://platform.deepseek.com/sign_up",
        "docs": "https://api-docs.deepseek.com/zh-cn/",
        "notes": "国内直连最省事，中文好；deepseek-chat 约 ¥2/百万 tokens 量级，充值 10 元能用很久（以官网为准）",
        "vision": False,
        "console": "DeepSeek 开放平台",
        "key_hint": "sk- 开头",
    },
    {
        "id": "qwen",
        "name": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-vl-plus"],
        "free": True,
        "signup": "https://bailian.console.aliyun.com/",
        "docs": "https://help.aliyun.com/zh/model-studio/",
        "notes": "新用户每个模型有免费 token 额度；qwen-plus 约 ¥0.8/百万输入，qwen-max 贵一倍多（以官网为准）",
        "vision": True,
        "console": "阿里云百炼控制台",
        "key_hint": "sk- 开头",
    },
    {
        "id": "doubao",
        "name": "豆包（火山方舟 / 字节跳动）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [
            "doubao-1-5-pro-32k-250115",
            "doubao-seed-1-6-250615",
            "doubao-1-5-vision-pro-32k-250115",
        ],
        "free": True,
        "signup": "https://console.volcengine.com/ark",
        "docs": "https://www.volcengine.com/docs/82379",
        "notes": "注册送 50 万 tokens 免费额度，便宜；**模型 id 以火山方舟控制台「在线推理」里显示的为准**，可能带日期后缀，价格也以官网为准",
        "vision": True,
        "console": "火山方舟控制台",
        "key_hint": "一串 UUID 样式的字符",
    },
    {
        "id": "kimi",
        "name": "Kimi（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k2-0905-preview", "moonshot-v1-8k", "moonshot-v1-32k"],
        "free": False,
        "signup": "https://platform.moonshot.cn/console/api-keys",
        "docs": "https://platform.moonshot.cn/docs",
        "notes": "长文本是强项，kimi-k2 约 ¥4/百万输入、¥16/百万输出；moonshot-v1-8k 更便宜（以官网为准）",
        "vision": False,
        "console": "Moonshot 开放平台",
        "key_hint": "sk- 开头",
    },
    {
        "id": "zhipu",
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4v-plus"],
        "free": True,
        "signup": "https://open.bigmodel.cn/usercenter/apikeys",
        "docs": "https://open.bigmodel.cn/dev/api",
        "notes": "glm-4-flash 长期免费（够写选科追问）；glm-4-plus 效果更好但要钱，约几十元/百万 tokens（以官网为准）",
        "vision": True,
        "console": "智谱开放平台",
        "key_hint": "形如 xxxx.xxxx 的两段式",
    },
    {
        "id": "ernie",
        "name": "文心一言（百度千帆）",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-4.5-turbo-128k", "ernie-4.5-8k-preview"],
        "free": True,
        "signup": "https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application",
        "docs": "https://cloud.baidu.com/doc/qianfan-api/index.html",
        "notes": "千帆 v2 已兼容 OpenAI 协议；新用户有免费额度，ernie-4.5-turbo 约 ¥0.8/百万输入（以官网为准）",
        "vision": False,
        "console": "百度智能云千帆控制台",
        "key_hint": "bce-v3/ 开头或一串字符",
    },
    {
        "id": "spark",
        "name": "讯飞星火",
        "base_url": "https://spark-api-open.xf-yun.com/v1",
        "models": ["generalv3.5", "4.0Ultra"],
        "free": True,
        "signup": "https://console.xfyun.cn/services/bm35",
        "docs": "https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html",
        "notes": "Spark Lite 免费；generalv3.5 约 ¥20/百万 tokens 量级，模型名要填控制台里的「套餐名」（以官网为准）",
        "vision": False,
        "console": "讯飞开放平台控制台",
        "key_hint": "APIPassword，32 位字母数字",
    },
    {
        "id": "hunyuan",
        "name": "腾讯混元",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": ["hunyuan-turbos-latest", "hunyuan-lite", "hunyuan-vision"],
        "free": True,
        "signup": "https://console.cloud.tencent.com/hunyuan/api-key",
        "docs": "https://cloud.tencent.com/document/product/1729",
        "notes": "hunyuan-lite 免费；turbos 约 ¥0.8/百万输入，需在控制台先开通模型服务（以官网为准）",
        "vision": True,
        "console": "腾讯云混元控制台",
        "key_hint": "sk- 开头",
    },
    {
        "id": "minimax",
        "name": "MiniMax（稀宇科技）",
        "base_url": "https://api.minimax.chat/v1",
        "models": ["MiniMax-Text-01", "abab6.5s-chat"],
        "free": False,
        "signup": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        "docs": "https://platform.minimaxi.com/document",
        "notes": "Text-01 约 ¥1/百万输入；国内域名有时是 api.minimaxi.com，连不上就换（以官网为准）",
        "vision": False,
        "console": "MiniMax 开放平台",
        "key_hint": "eyJ 开头的长串 JWT",
    },
    {
        "id": "stepfun",
        "name": "阶跃星辰 StepFun",
        "base_url": "https://api.stepfun.com/v1",
        "models": ["step-2-16k", "step-1v-8k"],
        "free": False,
        "signup": "https://platform.stepfun.com/interface-key",
        "docs": "https://platform.stepfun.com/docs",
        "notes": "step-2 是万亿参数大模型，贵（约 ¥38/百万输入）；step-1v-8k 能看图，适合读题（以官网为准）",
        "vision": True,
        "console": "阶跃星辰开放平台",
        "key_hint": "sk- 开头",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 SiliconFlow（聚合）",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            "Qwen/Qwen2.5-7B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-VL-72B-Instruct",
        ],
        "free": True,
        "signup": "https://cloud.siliconflow.cn/account/ak",
        "docs": "https://docs.siliconflow.cn",
        "notes": "一个 Key 调十几家开源模型，注册送额度；7B 小模型约 ¥0.35/百万，部分模型标着免费（以官网为准）",
        "vision": True,
        "console": "硅基流动控制台",
        "key_hint": "sk- 开头",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter（海外聚合）",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "deepseek/deepseek-chat",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-001",
        ],
        "free": True,
        "signup": "https://openrouter.ai/keys",
        "docs": "https://openrouter.ai/docs",
        "notes": "模型最全，带 :free 后缀的有免费额度；**国内需要能访问外网**，且要绑卡才能用付费模型（以官网为准）",
        "vision": True,
        "console": "OpenRouter 控制台",
        "key_hint": "sk-or-v1- 开头",
    },
    {
        "id": "local",
        "name": "本地模型（Ollama / vLLM / LM Studio）",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen2.5:7b", "qwen2.5:14b", "qwen2.5vl:7b", "llama3.1:8b"],
        "free": True,
        "signup": "https://ollama.com/download",
        "docs": "https://github.com/ollama/ollama/blob/main/docs/openai.md",
        "notes": "完全免费、数据不出本机；先 `ollama run qwen2.5:7b` 拉模型，8G 内存跑 7B 够用，第一次下载约 5GB",
        "vision": True,
        "console": "本地 Ollama 服务",
        "key_hint": "本地模型不用填，随便写 local 也行",
    },
]

# 只给后端自己用的字段，不下发前端（前端不需要知道控制台叫啥、Key 长啥样）。
INTERNAL_FIELDS: tuple[str, ...] = ("console", "key_hint")

# 前端可能传过来的口语化写法 → 标准 id，做一层容错。
ALIASES: dict[str, str] = {
    "deep-seek": "deepseek",
    "深度求索": "deepseek",
    "qwen": "qwen",
    "tongyi": "qwen",
    "dashscope": "qwen",
    "通义": "qwen",
    "通义千问": "qwen",
    "doubao": "doubao",
    "ark": "doubao",
    "volcengine": "doubao",
    "豆包": "doubao",
    "kimi": "kimi",
    "moonshot": "kimi",
    "月之暗面": "kimi",
    "zhipu": "zhipu",
    "glm": "zhipu",
    "智谱": "zhipu",
    "ernie": "ernie",
    "wenxin": "ernie",
    "qianfan": "ernie",
    "文心": "ernie",
    "文心一言": "ernie",
    "spark": "spark",
    "xfyun": "spark",
    "星火": "spark",
    "hunyuan": "hunyuan",
    "混元": "hunyuan",
    "minimax": "minimax",
    "stepfun": "stepfun",
    "step": "stepfun",
    "阶跃": "stepfun",
    "siliconflow": "siliconflow",
    "silicon": "siliconflow",
    "硅基流动": "siliconflow",
    "openrouter": "openrouter",
    "local": "local",
    "ollama": "local",
    "本地": "local",
}

DEFAULT_PROVIDER_ID = "deepseek"

_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in PROVIDERS}


# ---------------------------------------------------------------- 查询


def normalise_id(provider_id: Any) -> str:
    """把用户/前端传来的厂商名规整成标准 id，认不出来就原样小写返回。"""
    if not isinstance(provider_id, str):
        return ""
    value = provider_id.strip().lower()
    if value in _BY_ID:
        return value
    return ALIASES.get(value, value)


def get_provider(provider_id: Any) -> dict[str, Any]:
    """按 id 取一家厂商的**完整**记录（含内部字段）；取不到抛 :class:`AIError`。"""
    if provider_id is None or (isinstance(provider_id, str) and not provider_id.strip()):
        raise AIError("请先选择 AI 厂商", 400, "provider_required")
    key = normalise_id(provider_id)
    provider = _BY_ID.get(key)
    if provider is None:
        names = "、".join(p["id"] for p in PROVIDERS)
        raise AIError(f"不认识的 AI 厂商「{provider_id}」，可选：{names}", 400, "provider_unknown")
    return provider


def default_provider() -> dict[str, Any]:
    """默认厂商（DeepSeek）的完整记录，给没选厂商的场景兜底。

    返回深拷贝：调用方改了 ``models`` 也不会污染注册表。
    """
    return copy.deepcopy(_BY_ID[DEFAULT_PROVIDER_ID])


def list_providers() -> list[dict[str, Any]]:
    """给前端的精简清单，按国内普及度排序，已剔除内部字段。"""
    result: list[dict[str, Any]] = []
    for provider in PROVIDERS:
        item = {k: v for k, v in provider.items() if k not in INTERNAL_FIELDS}
        item["models"] = list(provider["models"])
        # 第一个模型就是默认模型，前端不用再猜
        item["default_model"] = provider["models"][0]
        result.append(item)
    return result


def provider_ids() -> list[str]:
    """全部标准 id，测试和文档生成用。"""
    return [p["id"] for p in PROVIDERS]


def resolve_model(provider: dict[str, Any] | str, model: Any = "") -> str:
    """模型没填（或填了空白）就用该厂商的默认模型；填了就尊重用户。"""
    if isinstance(provider, str):
        provider = get_provider(provider)
    if isinstance(model, str) and model.strip():
        return model.strip()
    models = provider.get("models") or []
    if not models:
        raise AIError(f"{provider.get('name', '该厂商')} 没有配置可用模型", 500, "model_missing")
    return models[0]


def describe(provider_id: Any) -> str:
    """一行人类可读的说明，日志和错误文案里用，例如「DeepSeek（深度求索）」。"""
    try:
        return str(get_provider(provider_id).get("name") or provider_id)
    except AIError:
        return str(provider_id)
