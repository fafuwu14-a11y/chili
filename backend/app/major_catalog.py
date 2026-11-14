"""专业目录（门类 → 专业类 → 具体专业）。

数据来自八省 2026 年投档表里的专业名：去掉「（中外合作办学）」这类括号后缀后去重，
出现次数 ≥5 的进目录（855 个），再按关键词归到 12 个学科门类下的 56 个专业类。

用途：给「专业」这个集合功能提供浏览、搜索与详情数据，并把先导课作为专业的一个分支。
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from . import mooc_data

_DATA_ROOT = Path(
    os.environ.get("CHILI_DATA_DIR") or Path(__file__).resolve().parent.parent / "data"
)
CATALOG_PATH = _DATA_ROOT / "major_catalog.json"

# 门类排序：工学在前，其它按考生关注度
CATEGORY_ORDER = [
    "eng", "sci", "med", "eco", "mgt", "lit", "law", "edu", "his", "agr", "art", "other",
]


class MajorError(ValueError):
    """专业查询参数不合法。"""


@lru_cache(maxsize=1)
def _catalog() -> dict:
    if not CATALOG_PATH.exists():
        raise MajorError("专业目录还没生成，先运行 tmp_build_catalog.py")
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _major_index() -> dict[str, dict]:
    return {item["name"]: item for item in _catalog()["majors"]}


@lru_cache(maxsize=1)
def _category_names() -> dict[str, str]:
    """门类 id → 中文名。majors 里只存了 id，展示用名字要从 categories 取。"""
    return {item["id"]: item["name"] for item in _catalog()["categories"]}


def _category_name(item: dict) -> str:
    return item.get("category_name") or _category_names().get(item["category"], "")


def meta() -> dict:
    data = _catalog()
    return {
        "total_majors": data["total_majors"],
        "total_rows": data["total_rows"],
        "source": data["source"],
        "categories": [
            {"id": item["id"], "name": item["name"], "groups": item["groups"]}
            for item in data["categories"]
        ],
    }


def _brief(item: dict) -> dict:
    return {
        "name": item["name"],
        "category": item["category"],
        "category_name": _category_name(item),
        "group": item["group"],
        "group_id": item["group_id"],
        "count": item["count"],
        "provinces": item["provinces"],
        "score_median": item["score_median"],
        "is_group": item["is_group"],
    }


def search(
    query: str | None = None,
    category: str | None = None,
    group: str | None = None,
    limit: int = 60,
) -> dict:
    """按关键词 / 门类 / 专业类筛选专业，按招生单元数量降序。"""
    data = _catalog()
    keyword = (query or "").strip()
    items = data["majors"]

    if category:
        items = [item for item in items if item["category"] == category]
    if group:
        items = [item for item in items if item["group_id"] == group]
    if keyword:
        matched = [
            item
            for item in items
            if keyword in item["name"] or keyword in item["group"]
        ]
        # 完全相等 / 前缀优先，其次按出现次数
        matched.sort(
            key=lambda item: (
                0 if item["name"] == keyword else 1,
                0 if item["name"].startswith(keyword) else 1,
                -item["count"],
            )
        )
        items = matched
    else:
        items = sorted(items, key=lambda item: (-item["count"], item["name"]))

    total = len(items)
    if limit:
        items = items[: max(1, min(int(limit), 400))]
    return {"total": total, "listed": len(items), "items": [_brief(item) for item in items]}


def detail(name: str) -> dict:
    """一个专业的完整信息：分省招生规模与分数，附先导课分支。"""
    target = (name or "").strip()
    if not target:
        raise MajorError("请先选一个专业")
    item = _major_index().get(target)
    if item is None:
        raise MajorError(f"专业目录里没有「{target}」，换个说法试试")

    provinces = []
    for key, bucket in sorted(item["by_province"].items(), key=lambda kv: -kv[1]["count"]):
        provinces.append(
            {
                "key": key,
                "count": bucket["count"],
                "median": bucket["median"],
            }
        )

    courses = []
    try:
        courses = mooc_data.recommend(target, 4)["items"]
    except Exception:  # 课程库挂了不该拖垮专业详情
        courses = []

    return {
        "name": item["name"],
        "category": item["category"],
        "category_name": _category_name(item),
        "group": item["group"],
        "group_id": item["group_id"],
        "count": item["count"],
        "provinces": item["provinces"],
        "score_min": item["score_min"],
        "score_max": item["score_max"],
        "score_median": item["score_median"],
        "is_group": item["is_group"],
        "by_province": provinces,
        "courses": courses,
    }
