"""专业趋势预警：某个专业在不同省份的招生规模与热度，跨年怎么变。

设计前提（重要）：我们手里的投档表**不是每省每年都齐**，所以这里的原则是
「有多少年算多少年，缺哪年就明说」，绝不靠插值假装四年数据都在。

数据现状（2026-11 盘点）：

* 只有「专业(类)+学校」模式的省份在投档表里带 ``unit_name``（专业名）：
  辽宁、浙江、山东、河北。
* 江苏、广东、湖北、山西按**院校专业组**公布，表里只有组号没有专业名，
  算不了专业级趋势，这里明确返回 ``unsupported`` 并说明原因。
* 年份：辽宁有 2024 与 2026（**缺 2025**）；浙江、山东、河北只有 2026。
  所以当前唯一能算真同比的是辽宁，其余只能给当年画像。

热度用「位次所占考生池比例」衡量，而不是裸分：不同年份题目难度不同，
分数直接相减没有意义，位次（经一分一段表换算）才能跨年比较。

对外只有一个入口 :func:`trend`，返回结构见函数 docstring。
"""

from __future__ import annotations

import csv
import re
import statistics
from functools import lru_cache

from . import major_catalog, real_data

# 与 tmp_build_catalog.py 保持一致的清洗规则：去掉括号说明与空白/间隔号，
# 这样投档表里的 ``计算机科学与技术(卓越班)`` 能和目录里的 ``计算机科学与技术`` 对上。
BRACKETS = re.compile(r"[（(\[【][^）)\]】]*[）)\]】]")
CLEAN = re.compile(r"[\s·]+")

# 「专业组」模式：投档单位是院校专业组，表里没有专业名。
GROUP_UNIT_NOTE = "该省按院校专业组公布投档，表里没有专业名，暂时算不了专业级预警。"
# 单年数据的说明。
SINGLE_YEAR_NOTE = "只采到 {year} 一年，看不了同比；补到往年数据后这里会自动出现变化。"
# 缺年份说明。
MISSING_NOTE = "缺 {years} 年的投档表，下面比的是 {first} 与 {last}。"


def strip_brackets(text: str) -> str:
    """去掉括号及其中的说明，允许嵌套，也容忍多余的右括号。

    与 tmp_build_catalog.py 同一套规则：「专业类[具体专业(方向)]」要整段剥掉，
    正则做不到（会残留一个 ``]``），所以用计数法。
    """
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch in "（([【":
            depth += 1
        elif ch in "）)]】":
            if depth > 0:
                depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def normalise(raw: str) -> str:
    """把投档表里的专业名洗成和目录一致的样子。"""
    return CLEAN.sub("", strip_brackets(raw or "").strip())


def _major_known(name: str) -> bool:
    """目录里有没有这个专业（不存在就抛 MajorError，交给 server 转 400）。"""
    major_catalog.detail(name)
    return True


@lru_cache(maxsize=256)
def _rows(name: str) -> tuple:
    """扫一遍投档表，只留下这个专业的行。

    返回 ``((省, 科类, 年份, 院校, 分数, 计划数), ...)`` 的元组，方便 lru_cache 缓存。
    同一专业第二次请求时直接命中，不再读文件。
    """
    out: list[tuple] = []
    for province, conf in real_data.PROVINCES.items():
        if not conf.get("available") or conf.get("unit") != "major":
            continue
        folder = real_data.DATA_DIR / real_data.PROVINCE_CODES[province]
        for track, track_conf in conf["tracks"].items():
            slug = track_conf["key"]
            for year in sorted(track_conf["lines"]):
                path = folder / f"toudang_{year}_{slug}.csv"
                if not path.exists():
                    continue
                with path.open(encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        if normalise(row.get("unit_name", "")) != name:
                            continue
                        try:
                            score = int(row.get("score") or 0)
                        except ValueError:
                            score = 0
                        plan_raw = (row.get("plan") or "").strip()
                        plan = int(plan_raw) if plan_raw.isdigit() else None
                        out.append(
                            (province, track, year, row.get("college", ""), score, plan)
                        )
    return tuple(out)


def _rank_share(province: str, track: str, year: int, score: float) -> float | None:
    """把中位分换算成「位次占考生池的比例」，用来跨年比较热度。

    比例越小说明越靠前、越热门；比裸分可靠得多。
    """
    if not score:
        return None
    table = _curve(province, track).get(year)
    if not table or not table.candidates:
        return None
    return min(1.0, max(0.0, table.rank(score) / table.candidates))


@lru_cache(maxsize=32)
def _curve(province: str, track: str) -> dict:
    """一分一段表（带缓存），``{年份: RankTable}``。"""
    return real_data.curve_series(province, track)


def _year_stats(rows: list[tuple]) -> dict:
    """把同一 (省, 科类, 年) 的行压成一条统计。

    行结构固定为 ``(省, 科类, 年, 院校, 分数, 计划数)``，所以按下标取，别用星号解包——
    ``for _, x, *_ in rows`` 拿到的是科类而不是院校，很容易错。
    """
    scores = [row[4] for row in rows if row[4]]
    plans = [row[5] for row in rows if row[5]]
    return {
        "units": len(rows),
        "colleges": len({row[3] for row in rows}),
        "median": round(statistics.median(scores), 1) if scores else None,
        "plan": sum(plans) if plans else None,
    }


def _scale_level(pct: float | None) -> str:
    """招生单元规模的变化档位。"""
    if pct is None:
        return "数据不足"
    if pct >= 15:
        return "明显扩张"
    if pct >= 5:
        return "小幅扩张"
    if pct <= -15:
        return "明显收缩"
    if pct <= -5:
        return "小幅收缩"
    return "基本持平"


def _heat_level(delta_pp: float | None) -> str:
    """热度档位：位次占比变动的百分点（负数 = 位次前移 = 变热）。"""
    if delta_pp is None:
        return "数据不足"
    if delta_pp <= -1.5:
        return "升温"
    if delta_pp <= -0.4:
        return "略升"
    if delta_pp >= 1.5:
        return "降温"
    if delta_pp >= 0.4:
        return "略降"
    return "稳定"


def _pct(first: float, last: float) -> float | None:
    """涨跌幅，first 为 0 时给 None（没法算百分比）。"""
    if not first:
        return None
    return round((last - first) / first * 100, 1)


def _track_block(province: str, track: str, rows: list[tuple]) -> dict:
    """一个省一个科类的多年序列 + 结论。"""
    by_year: dict[int, list[tuple]] = {}
    for row in rows:
        by_year.setdefault(row[2], []).append(row)

    years = []
    for year in sorted(by_year):
        stats = _year_stats(by_year[year])
        share = _rank_share(province, track, year, stats["median"] or 0)
        years.append(
            {
                "year": year,
                **stats,
                # 中位分对应的位次与占比，跨年比较看占比而不是分数
                "rank_share": round(share * 100, 2) if share is not None else None,
            }
        )

    block = {
        "province": province,
        "track": _track_name(province, track),
        "years": years,
        "first": years[0]["year"] if years else None,
        "last": years[-1]["year"] if years else None,
        "span": len(years),
        "missing_years": _missing_years(province, track, [y["year"] for y in years]),
    }

    if len(years) < 2:
        block.update(
            {
                "status": "single",
                "scale_level": "数据不足",
                "heat_level": "数据不足",
                "note": SINGLE_YEAR_NOTE.format(year=years[0]["year"]) if years else "",
            }
        )
        return block

    first, last = years[0], years[-1]
    scale_pct = _pct(first["units"], last["units"])
    college_pct = _pct(first["colleges"], last["colleges"])
    share_delta = None
    if first["rank_share"] is not None and last["rank_share"] is not None:
        share_delta = round(last["rank_share"] - first["rank_share"], 2)

    block.update(
        {
            "status": "ok",
            "units_pct": scale_pct,
            "colleges_pct": college_pct,
            "share_delta": share_delta,
            "scale_level": _scale_level(scale_pct),
            "heat_level": _heat_level(share_delta),
            "signals": _signals(first, last, scale_pct, college_pct, share_delta),
            "note": MISSING_NOTE.format(
                years="、".join(str(y) for y in block["missing_years"]) or "—",
                first=first["year"],
                last=last["year"],
            )
            if block["missing_years"]
            else "",
        }
    )
    return block


def _signals(first: dict, last: dict, scale_pct, college_pct, share_delta) -> list[dict]:
    """把三个指标翻成一句句人话，前端直接列出来。"""
    out = []
    if scale_pct is not None:
        out.append(
            {
                "key": "scale",
                "level": _scale_level(scale_pct),
                "text": f"招生单元 {first['units']} → {last['units']}（{scale_pct:+.1f}%）",
            }
        )
    if college_pct is not None:
        out.append(
            {
                "key": "colleges",
                "level": _scale_level(college_pct),
                "text": f"开设院校 {first['colleges']} → {last['colleges']}（{college_pct:+.1f}%）",
            }
        )
    if share_delta is not None:
        # 位次占比变小 = 录取位置前移 = 更热门
        out.append(
            {
                "key": "heat",
                "level": _heat_level(share_delta),
                "text": (
                    f"中位位次占比 {first['rank_share']}% → {last['rank_share']}%"
                    f"（{share_delta:+.2f} 个百分点）"
                ),
            }
        )
    return out


def _missing_years(province: str, track: str, have: list[int]) -> list[int]:
    """按省份配置里登记的年份，算出哪些年缺表。"""
    conf = real_data.PROVINCES.get(province, {})
    known = conf.get("tracks", {}).get(track, {}).get("lines", {})
    return sorted(y for y in known if y not in have)


def _track_name(province: str, track: str) -> str:
    """科类中文名（浙江/山东叫「综合改革」，前端要按人话展示）。"""
    if track == "综合改革":
        return "综合改革"
    return track


def _unsupported_block(province: str, conf: dict) -> dict:
    """专业组制省份：老实说算不了。"""
    return {
        "province": province,
        "track": "",
        "years": [],
        "status": "unsupported",
        "scale_level": "无法计算",
        "heat_level": "无法计算",
        "note": GROUP_UNIT_NOTE,
    }


def cover() -> dict:
    """数据覆盖说明，给页面头部的「数据到哪一步」用。"""
    majors, single, group = [], [], []
    for province, conf in real_data.PROVINCES.items():
        if not conf.get("available"):
            continue
        if conf.get("unit") != "major":
            group.append({"province": province, "unit": conf.get("unit")})
            continue
        # 按真实存在的文件算年份，而不是按配置里的本科线年份——这两者不全等（辽宁配了 2025 但没有 2025 的表）。
        folder = real_data.DATA_DIR / real_data.PROVINCE_CODES[province]
        years = sorted(
            {
                year
                for track_conf in conf["tracks"].values()
                for year in track_conf["lines"]
                if (folder / f"toudang_{year}_{track_conf['key']}.csv").exists()
            }
        )
        item = {"province": province, "years": years, "tracks": list(conf["tracks"])}
        if len(years) >= 2:
            majors.append(item)
        else:
            single.append(item)
    return {
        "trendable": majors,
        "single_year": single,
        "group_mode": group,
        "note": (
            "只有「专业(类)+学校」的省份能按专业算趋势；"
            "能跨年比较的目前只有 "
            + "、".join(f"{m['province']}（{'、'.join(map(str, m['years']))}）" for m in majors)
            + "。"
        )
        if majors
        else "目前没有两个年份都带专业名的投档表，趋势算不出来。",
    }


def trend(name: str) -> dict:
    """某个专业的趋势预警。

    返回::

        {
          "major": "计算机科学与技术",
          "category": "工学", "group": "计算机",
          "cover": {...},                  # 数据覆盖说明
          "provinces": [                   # 只有真的采到数据的省
            {
              "province": "辽宁", "tracks": [
                {"track": "物理类", "status": "ok", "years": [...],
                 "scale_level": "明显扩张", "heat_level": "略升",
                 "signals": [{"key","level","text"}], "note": "缺 2025 年..."}
              ]
            }
          ],
          "unsupported": ["江苏", ...],    # 专业组制，算不了
          "summary": "一句话结论",
          "has_trend": True                # 至少有一个省能算同比
        }
    """
    _major_known(name)
    detail = major_catalog.detail(name)
    rows = _rows(name)

    grouped: dict[str, list[tuple]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)

    provinces = []
    for province in grouped:
        conf = real_data.PROVINCES[province]
        tracks = [
            _track_block(province, track, [r for r in grouped[province] if r[1] == track])
            for track in conf["tracks"]
            if any(r[1] == track for r in grouped[province])
        ]
        provinces.append({"province": province, "tracks": tracks})

    unsupported = [
        p
        for p, conf in real_data.PROVINCES.items()
        if conf.get("available") and conf.get("unit") != "major"
    ]

    ok = [
        (p["province"], t)
        for p in provinces
        for t in p["tracks"]
        if t["status"] == "ok"
    ]
    has_trend = bool(ok)

    return {
        "major": name,
        "category": detail.get("category_name") or "",
        "group": detail.get("group") or "",
        "cover": cover(),
        "provinces": provinces,
        "unsupported": unsupported,
        "has_trend": has_trend,
        "summary": _summary(name, ok, provinces),
    }


def _summary(name: str, ok: list[tuple], provinces: list[dict]) -> str:
    """整个专业的一句话结论。"""
    if ok:
        parts = []
        for province, block in ok:
            parts.append(
                f"{province}（{block['track']}）招生{block['scale_level']}、热度{block['heat_level']}"
            )
        return f"{name}：" + "；".join(parts) + "。"
    if provinces:
        return f"{name}：只采到单年数据，还看不出趋势。"
    return f"{name}：暂时没有可用的投档数据。"
