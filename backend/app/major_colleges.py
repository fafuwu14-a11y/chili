"""功能 04：某专业在哪些学校更强 —— 用真实投档数据给院校排座次。

「优势」没法凭空编，这里用两个能查证的代理指标：

* ``best_rank``：该校该专业历史上最好的最低录取位次（数字越小越难考，
  市场认可度越高）。跨年份取最好值，避免某年断档把一所强校排到后面。
* ``depth``：出现在多少个招生年份里。只招过一年的学校，数据可信度低。

**数据粒度的坑**：8 个省里只有辽宁 / 浙江 / 山东 / 河北是「专业级」投档，
江苏 / 广东 / 湖北 / 山西 只有「XX专业组」，从专业组反推不出具体专业。
所以按专业查院校时只在专业级省份里找，并在返回里说明数据来自哪几个省，
不要拿江苏的考生基数去算别的省的位次百分位。
"""

from __future__ import annotations

import re

from . import subject_map

# dataset 不能哈希，用 id 做键；进程内只建一次索引（104k 条，约 0.1s）。
_INDEX_CACHE: dict[int, dict[str, list[dict]]] = {}

MAX_LIMIT = 50

# 真实数据里的院校名带「[公办]」「[民办]」后缀，展示时去掉
_BRACKET = re.compile(r"\s*\[[^\]]*\]\s*$")


def _clean(name: str) -> str:
    """去掉「(中外合作办学)」「（师范）」这类后缀，同一专业才能聚到一起。"""
    return subject_map.clean_name(name or "")


def _college_name(raw: str) -> str:
    return _BRACKET.sub("", raw or "").strip()


def _index(dataset) -> dict[str, list[dict]]:
    key = id(dataset)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    index: dict[str, list[dict]] = {}
    for program in dataset.programs:
        # 专业组（「09专业组」）不是一个具体专业，混进来会污染结果
        if program.get("kind") != "major":
            continue
        name = _clean(program.get("name", ""))
        if not name or name.endswith("专业组"):
            continue
        index.setdefault(name, []).append(program)
    _INDEX_CACHE[key] = index
    return index


def data_provinces(dataset) -> list[str]:
    """哪些省是专业级投档数据 —— 只有这些省能按专业查院校。"""
    seen: dict[str, int] = {}
    for program in dataset.programs:
        if program.get("kind") == "major":
            seen[program["province"]] = seen.get(program["province"], 0) + 1
    return [name for name, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def _resolve(name: str, index: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    """精确名优先；没有再按包含关系找（「计算机」能命中「计算机科学与技术」）。"""
    target = _clean(name)
    if not target:
        raise ValueError("请先选一个专业")
    hit = index.get(target)
    if hit:
        return target, hit

    candidates = [key for key in index if target in key or key in target]
    if not candidates:
        raise ValueError(f"招生数据里还没有「{target}」这个专业，换一个试试")
    # 「计算机类」是专业类不是专业；同名前缀下招生记录多的才是主专业名
    candidates.sort(key=lambda key: (
        key.endswith("类"),
        0 if key.startswith(target) else 1,
        -len(index[key]),
        len(key),
        key,
    ))
    best = candidates[0]
    return best, index[best]


def _candidates(dataset, province: str, track: str) -> int | None:
    info = dataset.province_info.get(province) or {}
    bucket = (info.get("tracks") or {}).get(track) or {}
    count = bucket.get("candidates")
    return int(count) if count else None


def advantage(
    dataset,
    name: str,
    *,
    province: str = "",
    track: str = "",
    limit: int = 20,
) -> dict:
    """返回某专业在各校的优势列表，按最好位次升序。"""
    index = _index(dataset)
    major, programs = _resolve(name, index)
    usable = data_provinces(dataset)

    province = (province or "").strip()
    track = (track or "").strip()

    def scope(prov: str, trk: str) -> list[dict]:
        return [
            p for p in programs
            if (not prov or p.get("province") == prov)
            and (not trk or p.get("track") == trk)
        ]

    scoped = scope(province, track)
    granularity = "major"
    note = ""

    if not scoped and province not in usable:
        # 江苏这类省份根本查不到专业级数据，不是「这个专业没人招」
        scoped = [p for p in programs if p.get("province") in usable]
        granularity = "cross_province"
        note = (
            f"{province}的投档数据只到「专业组」粒度，无法对应到具体专业；"
            f"下表按{'、'.join(usable)}的专业级数据排序，可用来比较院校强弱，"
            "但不是该校在你省的录取位次。"
        )
    elif not scoped:
        scoped = programs
        granularity = "nationwide"
        note = f"{province}·{track or '全部科类'}没有该专业的投档记录，已放宽到全国。"

    rows: dict[str, dict] = {}
    for program in scoped:
        stats = dataset.stats.get(program["id"]) or []
        if not stats:
            continue
        cid = program["college_id"]
        college = dataset.colleges.get(cid) or {}
        # 同一所学校在每省各存一份记录（id 带省前缀），按校名聚合才是「一所学校」
        name = _college_name(college.get("name", cid))
        row = rows.get(name)
        if row is None:
            row = {
                "college_id": cid,
                "college": name,
                "tags": list(college.get("tags") or []),
                "best_rank": None,
                "best_score": None,
                "best_year": None,
                "source_province": "",
                "source_track": "",
                "plan_total": 0,
                "years": set(),
                "programs": [],
            }
            rows[name] = row

        for stat in stats:
            rank = stat.get("min_rank")
            year = stat.get("year")
            if not rank:
                continue
            row["years"].add(year)
            if row["best_rank"] is None or rank < row["best_rank"]:
                row["best_rank"] = rank
                row["best_year"] = year
                row["best_score"] = stat.get("min_score")
                row["source_province"] = program.get("province", "")
                row["source_track"] = program.get("track", "")
            row["plan_total"] += int(stat.get("plan") or 0)
            if len(row["programs"]) < 6:
                row["programs"].append({
                    "program_id": program["id"],
                    "name": program["name"],
                    "province": program.get("province", ""),
                    "track": program.get("track", ""),
                    "requirement": program.get("requirement", ""),
                })

    items = [row for row in rows.values() if row["best_rank"]]
    items.sort(key=lambda row: (row["best_rank"], row["college"]))
    total = len(items)
    items = items[: max(1, min(int(limit or 20), MAX_LIMIT))]

    # 百分位必须用数据来源省的考生数算，跨省算出来的数字是假的
    for item in items:
        item["years"] = sorted(item["years"])
        item["depth"] = len(item["years"])
        count = _candidates(dataset, item["source_province"], item["source_track"])
        item["percentile"] = (
            round(100 * (1 - item["best_rank"] / count), 2)
            if count and item["best_rank"] else None
        )

    return {
        "major": major,
        "province": province,
        "track": track,
        "granularity": granularity,
        "data_provinces": usable,
        "total": total,
        "items": items,
        "note": note or (
            "位次来自各省考试院公布的投档数据，数字越小代表录取难度越高；"
            "同一专业在不同学校的培养方向差异很大，最终仍要看课程设置。"
        ),
    }
