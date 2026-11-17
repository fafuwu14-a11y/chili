"""专业画像：把 major_outlook 的口语化判断，落成可直接渲染和对比的结构化字段。

一份画像回答了六个问题：学什么（courses）、练什么能力（skills）、
出去干什么（jobs / industries / regions）、值不值（employment / postgrad / salary）、
能不能考公考研（civil / exam）、适不适合创业（startup / scores）。

数据里的就业率、起薪一律是区间加来源，不写单点数字——口径不统一时，
单点数字只是看起来精确。

只依赖标准库，与 major_catalog 共用同一份专业名。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .major_catalog import MajorError

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "major_profile.json"

# 一条画像必须具备的文本字段：少任何一个，前端就会渲染出空白。
REQUIRED_TEXT = (
    "name",
    "category",
    "category_name",
    "group",
    "group_id",
    "degree",
    "source",
    "updated",
)
# 列表字段的最少条数：低于这个数量，画像就没有信息量。
MIN_LIST = {
    "courses": 6,
    "skills": 4,
    "jobs": 5,
    "industries": 3,
    "regions": 2,
}
MAX_LIST = {
    "courses": 10,
    "skills": 6,
    "jobs": 10,
    "industries": 5,
    "regions": 8,
}
# 区间字段：low < high，且必须带 note 与 source。
RANGE_FIELDS = ("employment", "postgrad", "salary")
SCORE_FIELDS = (
    "course_load",
    "job_width",
    "salary",
    "exam_need",
    "civil_fit",
    "startup_fit",
)
STARTUP_FIELDS = ("barrier", "license", "capital", "team", "risk")

# 六维雷达图的展示口径，前端按这个顺序画。
SCORE_LABELS = (
    ("course_load", "课业强度"),
    ("job_width", "就业面"),
    ("salary", "起薪"),
    ("exam_need", "考研必要"),
    ("civil_fit", "考公适配"),
    ("startup_fit", "创业友好"),
)


def check(item: dict) -> list[str]:
    """检查一条画像，返回问题列表；空列表表示通过。

    这里只管「结构对不对」，不管文案好不好——文案质量靠人工抽检，
    结构错误却会让前端直接崩，所以必须机器挡。
    """
    problems: list[str] = []
    if not isinstance(item, dict):
        return ["画像不是对象"]

    name = item.get("name") or "（无名）"

    for key in REQUIRED_TEXT:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{name}：缺少文本字段 {key}")

    years = item.get("years")
    if not isinstance(years, int) or not 2 <= years <= 8:
        problems.append(f"{name}：years 必须是 2–8 的整数")

    for key, low in MIN_LIST.items():
        values = item.get(key)
        if not isinstance(values, list):
            problems.append(f"{name}：{key} 必须是列表")
            continue
        if len(values) < low:
            problems.append(f"{name}：{key} 至少 {low} 条，现在 {len(values)} 条")
        if len(values) > MAX_LIST[key]:
            problems.append(f"{name}：{key} 最多 {MAX_LIST[key]} 条，现在 {len(values)} 条")
        if any(not isinstance(x, str) or not x.strip() for x in values):
            problems.append(f"{name}：{key} 里有空条目")
        if len(set(values)) != len(values):
            problems.append(f"{name}：{key} 有重复条目")

    for key in RANGE_FIELDS:
        block = item.get(key)
        if not isinstance(block, dict):
            problems.append(f"{name}：{key} 必须是对象")
            continue
        low, high = block.get("low"), block.get("high")
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            problems.append(f"{name}：{key} 的 low/high 必须是数字")
        elif not 0 <= low < high:
            problems.append(f"{name}：{key} 要满足 0 <= low < high")
        for field in ("note", "source"):
            if not isinstance(block.get(field), str) or not block[field].strip():
                problems.append(f"{name}：{key} 缺少 {field}")

    civil = item.get("civil")
    if not isinstance(civil, dict):
        problems.append(f"{name}：civil 必须是对象")
    else:
        if not isinstance(civil.get("categories"), list) or not civil["categories"]:
            problems.append(f"{name}：civil.categories 不能为空")
        if not isinstance(civil.get("units"), list) or len(civil["units"]) < 3:
            problems.append(f"{name}：civil.units 至少 3 个")
        if not isinstance(civil.get("note"), str) or not civil["note"].strip():
            problems.append(f"{name}：civil 缺少 note")

    exam = item.get("exam")
    if not isinstance(exam, dict):
        problems.append(f"{name}：exam 必须是对象")
    else:
        for field in ("subject", "grade", "note"):
            if not isinstance(exam.get(field), str) or not exam[field].strip():
                problems.append(f"{name}：exam 缺少 {field}")

    startup = item.get("startup")
    if not isinstance(startup, dict):
        problems.append(f"{name}：startup 必须是对象")
    else:
        for field in STARTUP_FIELDS:
            value = startup.get(field)
            if not isinstance(value, int) or not 1 <= value <= 5:
                problems.append(f"{name}：startup.{field} 必须是 1–5 的整数")

    scores = item.get("scores")
    if not isinstance(scores, dict):
        problems.append(f"{name}：scores 必须是对象")
    else:
        for field in SCORE_FIELDS:
            value = scores.get(field)
            if not isinstance(value, int) or not 1 <= value <= 5:
                problems.append(f"{name}：scores.{field} 必须是 1–5 的整数")

    return problems


@lru_cache(maxsize=1)
def _payload() -> dict:
    """读取并整体校验画像文件；任何一条不合格都直接报错，不让脏数据进前端。"""
    if not DATA_PATH.exists():
        raise MajorError("专业画像数据还没生成")
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    items = payload.get("majors")
    if not isinstance(items, list) or not items:
        raise MajorError("专业画像数据为空")

    problems: list[str] = []
    seen: set[str] = set()
    for item in items:
        problems.extend(check(item))
        name = item.get("name") if isinstance(item, dict) else None
        if name in seen:
            problems.append(f"{name}：重复出现")
        seen.add(name)
    if problems:
        raise MajorError("专业画像校验未通过：" + "；".join(problems[:5]))
    return payload


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    return {item["name"]: item for item in _payload()["majors"]}


def names() -> list[str]:
    """按专业名排序，便于测试与下拉框使用。"""
    return sorted(_index())


def get(name: str) -> dict:
    """取一条画像；不存在时抛 MajorError，由 server 统一转成 400。"""
    key = (name or "").strip()
    if not key:
        raise MajorError("请提供专业名")
    item = _index().get(key)
    if item is None:
        raise MajorError(f"专业画像里没有「{key}」，目前收了 {len(_index())} 个专业")
    return item


def stats() -> dict:
    """画像覆盖情况：总数与门类分布，供关于页与自检使用。"""
    items = _payload()["majors"]
    by_category: dict[str, int] = {}
    for item in items:
        by_category[item["category_name"]] = by_category.get(item["category_name"], 0) + 1
    return {
        "total": len(items),
        "by_category": by_category,
        "updated": _payload().get("updated", ""),
        "note": _payload().get("note", ""),
    }


def compare(major_names: list[str]) -> dict:
    """选 2–4 个专业做对比，返回雷达图直接可用的结构。

    六维分数取自已校验的 scores，所以不用再兜底；这里只负责选维度和排序。
    """
    cleaned = [name.strip() for name in major_names if name and name.strip()]
    if len(cleaned) < 2:
        raise MajorError("对比至少选 2 个专业")
    if len(cleaned) > 4:
        raise MajorError("对比最多选 4 个专业")
    if len(set(cleaned)) != len(cleaned):
        raise MajorError("对比的专业不能重复")

    items = [get(name) for name in cleaned]
    return {
        "axes": [{"key": key, "label": label} for key, label in SCORE_LABELS],
        "items": [
            {
                "name": item["name"],
                "group": item["group"],
                "degree": item["degree"],
                "years": item["years"],
                "scores": {key: item["scores"][key] for key, _ in SCORE_LABELS},
                "salary": item["salary"],
                "employment": item["employment"],
                "postgrad": item["postgrad"],
                "jobs": item["jobs"][:4],
                "courses": item["courses"][:6],
                "civil": item["civil"],
            }
            for item in items
        ],
    }
