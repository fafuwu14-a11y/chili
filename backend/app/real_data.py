"""Real dataset: undergraduate batch, three years, two tracks per province.

Data files live in ``backend/data/<province code>`` (江苏 ``js``, 广东 ``gd``)
and come from the official provincial examination authority releases:

* ``toudang_{year}_{track}.csv`` — 本科批平行志愿投档线
  (``院校代号, 院校, 专业组, 选科要求, 投档最低分``)
* ``curve_{year}_{track}.csv`` — 一分一段表 (``score, same, cumulative``)

2019 年的表格是官方 .xls，2025 / 2026 是 PDF 与图片；图片版由 ``realdata``
目录下的脚本 OCR 后用累计人数做锚点修复，六张表的底端分数与官方本科线
完全一致（物理 462 / 463 / 456，历史 478 / 482 / 484）。

预测口径仍是位次等值法：拿专业组最近一年的录取位次，按考生规模折算，再用
logistic 换成概率。回测（``realdata/REPORT.md``）表明三年趋势外推在这个场景
下不成立，所以 2024 年的数据只用于页面展示「近三年」，不参与外推。
"""

from __future__ import annotations

import csv
import os
import statistics
from pathlib import Path

# 打包成 exe 后模块位置会变，用环境变量指到解压出来的数据目录；源码运行时按相对路径找。
DATA_DIR = Path(os.environ.get("CHILI_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")

def _data_dir(province: str) -> Path:
    """每个省一个目录：广西/广东等用两字母代码，未登记的省退化为省名。"""
    return DATA_DIR / PROVINCE_CODES.get(province, province)

TARGET_YEAR = 2027
YEARS = (2024, 2025, 2026)
LATEST_YEAR = YEARS[-1]
PREVIOUS_YEAR = YEARS[-2]

# 每个省有哪些科类、对应哪份文件、各年本科线是多少。
# 只收录投档分数完整的省份：当年投档线与一分一段表齐全、科类齐全。
# 缺数据的省（如只有物理类、或完全没有投档表）不占位——宁可少一个省，
# 也不让用户点进去看到「数据整理中」。
PROVINCE_CODES = {
    "江苏": "js",
    "广东": "gd",
    "湖北": "hb",
    "山西": "sx",
    "辽宁": "ln",
    "浙江": "zj",
    "山东": "sd",
    "河北": "he",
}

# ``unit`` 说明这个省的投档单位是什么：
#   group = 院校专业组（江苏、广东、湖北、山西），一个组里含若干专业；
#   major = 专业（类）+ 学校（辽宁、浙江、山东、河北），投档单位就是具体专业。
PROVINCES: dict[str, dict] = {
    "江苏": {
        "available": True,
        "unit": "group",
        "slots_max": 40,
        "tracks": {
            "物理类": {"key": "physics", "lines": {2024: 462, 2025: 463, 2026: 456}},
            "历史类": {"key": "history", "lines": {2024: 478, 2025: 482, 2026: 484}},
        },
    },
    "广东": {
        "available": True,
        "unit": "group",
        "slots_max": 45,
        "tracks": {
            # 广东本科线：2024 物理 442 / 历史 428，2025 物理 436 / 历史 464，
            # 2026 物理 425 / 历史 440（广东省教育考试院录取最低分数线公告）。
            "物理类": {"key": "physics", "lines": {2024: 442, 2025: 436, 2026: 425}},
            "历史类": {"key": "history", "lines": {2024: 428, 2025: 464, 2026: 440}},
        },
    },
    "湖北": {
        "available": True,
        "unit": "group",
        "slots_max": 45,
        "tracks": {
            # 湖北本科线（省教育厅录取控制分数线通知）：2026 物理 435 / 历史 443；
            # 2025 物理 426 / 历史 442；2024 物理 437 / 历史 432。
            "物理类": {"key": "physics", "lines": {2026: 435}},
            "历史类": {"key": "history", "lines": {2026: 443}},
        },
    },
    "山西": {
        "available": True,
        "unit": "group",
        "slots_max": 45,
        "tracks": {
            # 山西 2025 年首次新高考（3+1+2），只有 2025/2026 两年数据。
            # 本科批录取最低控制分数线（省招考委公告）：2026 物理 401 / 历史 409；
            # 2025 物理 419 / 历史 443。
            "物理类": {"key": "physics", "lines": {2025: 419, 2026: 401}},
            "历史类": {"key": "history", "lines": {2025: 443, 2026: 409}},
        },
    },
    "辽宁": {
        "available": True,
        "unit": "major",
        "slots_max": 112,
        "tracks": {
            # 辽宁是「专业(类)+学校」模式，投档单位就是具体专业，没有专业组。
            # 本科线取自省招考办公告，与逐分段表的底端分数一致：
            # 2024 物理 368 / 历史 400，2025 物理 367 / 历史 437，2026 物理 344 / 历史 442。
            "物理类": {"key": "physics", "lines": {2024: 368, 2025: 367, 2026: 344}},
            "历史类": {"key": "history", "lines": {2024: 400, 2025: 437, 2026: 442}},
        },
    },
    "浙江": {
        "available": True,
        "unit": "major",
        "slots_max": 80,
        "tracks": {
            # 浙江是「专业(类)+学校」+ 综合改革，只有一个科类；一段线 2026 为 494。
            # 浙江这张投档表还带计划数和官方位次，所以 plan/rank 直接用原值。
            "综合改革": {"key": "zonghe", "lines": {2026: 494}},
        },
    },
    "山东": {
        "available": True,
        "unit": "major",
        "slots_max": 96,
        "tracks": {
            # 山东同样是「专业(类)+学校」+ 综合改革，一段线 2026 为 444。
            # 山东投档表只给最低位次、不给分数，分数由一分一段表反查。
            "综合改革": {"key": "zonghe", "lines": {2026: 444}},
        },
    },
    "河北": {
        "available": True,
        "unit": "major",
        "slots_max": 96,
        "tracks": {
            # 河北是「专业(类)+学校」，分物理/历史两个科目组合；本科线 2026 为
            # 物理 366 / 历史 432。投档表只给最低分，位次由一分一段表反查。
            "物理类": {"key": "physics", "lines": {2026: 366}},
            "历史类": {"key": "history", "lines": {2026: 432}},
        },
    },
}

# Tuned on the 2025 → 2026 backtest: sigma = max(predicted rank * 0.075, 1200)
# gives the best calibration (mean |model - actual| ≈ 0.029 across probability
# buckets), with 稳档 hitting its nominal value almost exactly.
SIGMA_FACTOR = 0.075
SIGMA_FLOOR = 1200.0


class RankTable:
    """A score ↔ cumulative-rank table (一分一段表)."""

    def __init__(self, rows: list[tuple[int, int]], line: int, candidates: int):
        self.line = line
        self.candidates = candidates
        self._table = {score: cumulative for score, cumulative in rows}
        self._scores = sorted(self._table)

    def rank(self, score: float) -> int:
        """Cumulative rank at ``score`` (lower score → larger rank)."""
        score = int(round(score))
        if score >= self._scores[-1]:
            return max(1, self._table[self._scores[-1]])
        if score <= self._scores[0]:
            return self.candidates
        if score in self._table:
            return self._table[score]
        # linear interpolation between neighbouring scores
        import bisect

        index = bisect.bisect_left(self._scores, score)
        low, high = self._scores[index - 1], self._scores[index]
        low_rank, high_rank = self._table[low], self._table[high]
        step = (score - low) / (high - low)
        return int(round(low_rank + (high_rank - low_rank) * step))

    def score(self, rank: float) -> int:
        """Inverse of :meth:`rank`.

        ``_table`` is keyed by ascending score, so cumulative counts descend
        from the batch line up to the top score. We therefore search the
        descending-score view, where cumulative counts ascend.
        """
        import bisect

        rank = max(1.0, min(float(rank), self.candidates))
        scores_desc = list(reversed(self._scores))
        cumulatives = [self._table[s] for s in scores_desc]  # ascending
        index = bisect.bisect_left(cumulatives, rank)
        if index <= 0:
            return scores_desc[0]
        if index >= len(scores_desc):
            return scores_desc[-1]
        # scores_desc[index - 1] > answer >= scores_desc[index]
        high, low = scores_desc[index - 1], scores_desc[index]
        high_rank, low_rank = cumulatives[index - 1], cumulatives[index]
        if low_rank == high_rank:
            return low
        step = (rank - high_rank) / (low_rank - high_rank)
        return int(round(high + (low - high) * step))


def _load_curve(name: str, line: int, province: str) -> RankTable | None:
    path = _data_dir(province) / name
    if not path.exists():
        return None
    rows = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append((int(row["score"]), int(row["cumulative"])))
    rows.sort()
    # rows are sorted by ascending score, so the first row (batch line) carries
    # the largest cumulative count: that is the whole candidate pool.
    candidates = rows[0][1] if rows else 0
    return RankTable(rows, line=line, candidates=candidates)


def _load_lines(name: str, province: str) -> dict[tuple[str, str], dict]:
    """Read one 投档线 CSV.

    Two formats coexist:

    * 院校专业组（江苏、广东、湖北、山西）：``code,college,group,requirement,score``
    * 专业(类)+学校（辽宁、浙江…）：``code,college,unit_code,unit_name,requirement,score``

    Both are normalised to a ``unit_code`` + ``name`` pair, so the rest of the
    pipeline does not care which province it is looking at.
    """
    path = _data_dir(province) / name
    if not path.exists():
        return {}
    table: dict[tuple[str, str], dict] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            unit_code = (row.get("unit_code") or row.get("group") or "").strip()
            unit_name = (row.get("unit_name") or "").strip()
            if not unit_code:
                continue
            plan_raw = (row.get("plan") or "").strip()
            rank_raw = (row.get("rank") or "").strip()
            table[(row["code"], unit_code)] = {
                "code": row["code"],
                "college": row["college"],
                "unit_code": unit_code,
                "unit_name": unit_name,
                "name": unit_name or f"{unit_code}专业组",
                "requirement": (row.get("requirement") or "").strip(),
                "score": int(row["score"]),
                # 有些省的表直接给计划数和官方位次（浙江），有就照抄，没有留空。
                "plan": int(plan_raw) if plan_raw.isdigit() else 0,
                "rank": int(rank_raw) if rank_raw.isdigit() else None,
            }
    return table


def _track_slug(province: str, track: str) -> str | None:
    conf = PROVINCES.get(province, {})
    track_conf = conf.get("tracks", {}).get(track)
    return track_conf["key"] if track_conf else None


def _measure_shift(
    lines_prev: dict[tuple[str, str], dict],
    lines_last: dict[tuple[str, str], dict],
    curve_prev: RankTable,
    curve_last: RankTable,
) -> tuple[float, int, int]:
    """Return (scale, drift, matched_count) for the last year-over-year step."""
    scale = curve_last.candidates / curve_prev.candidates if curve_prev.candidates else 1.0
    shifts = []
    for key, row_last in lines_last.items():
        row_prev = lines_prev.get(key)
        if not row_prev or row_prev["requirement"] != row_last["requirement"]:
            continue
        rank_prev = curve_prev.rank(row_prev["score"])
        rank_last = curve_last.rank(row_last["score"])
        shifts.append(rank_last - rank_prev * scale)
    drift = int(round(statistics.median(shifts))) if shifts else 0
    return scale, drift, len(shifts)


def build_real_dataset() -> dict:
    """Build a dataset that mirrors ``mock_data.build_dataset``'s shape."""
    colleges: dict[str, dict] = {}
    programs: list[dict] = []
    stats: list[dict] = []
    curves: dict[tuple[str, str], RankTable] = {}
    provinces_meta: dict[str, dict] = {}
    latest_lines: dict[tuple[str, str], dict] = {}
    recent: list[dict] = []

    for province, conf in PROVINCES.items():
        tracks_meta: dict[str, dict] = {}
        for track, track_conf in conf["tracks"].items():
            slug = track_conf["key"]
            lines = track_conf["lines"]
            # 有些省只采到最新一年（如湖北 2026 才首批），缺的年份直接跳过。
            years = [year for year in YEARS if year in lines]
            tables = {
                year: _load_curve(f"curve_{year}_{slug}.csv", lines[year], province)
                for year in years
            }
            toudang = {
                year: _load_lines(f"toudang_{year}_{slug}.csv", province) for year in years
            }
            if not tables[LATEST_YEAR] or not toudang[LATEST_YEAR]:
                continue

            curve_last = tables[LATEST_YEAR]
            curve_prev = tables.get(PREVIOUS_YEAR)
            curves[(province, track)] = curve_last

            scale, drift, matched = (1.0, 0, 0)
            if curve_prev:
                scale, drift, matched = _measure_shift(
                    toudang.get(PREVIOUS_YEAR) or {}, toudang[LATEST_YEAR], curve_prev, curve_last
                )
                recent.append(
                    {
                        "province": province,
                        "track": track,
                        "scale": round(scale, 4),
                        "drift": drift,
                        "matched": matched,
                    }
                )

            tracks_meta[track] = {
                "key": slug,
                "line": lines[LATEST_YEAR],
                "candidates": curve_last.candidates,
                "years": [year for year in years if tables.get(year)],
            }

            province_prefix = PROVINCE_CODES.get(province, province)
            unit_kind = conf.get("unit", "group")
            for (code, unit_code), row_last in toudang[LATEST_YEAR].items():
                # 院校代号只在同省同科类里稳定：山西有 97 个代号在两个科类下
                # 指向不同学校（1359 物理是锦州医科大学、历史是沈阳建筑大学），
                # 广东、湖北也有几十处。所以身份必须带上科类，否则会张冠李戴。
                college_id = f"{province_prefix}-{slug}-{code}"
                college = colleges.get(college_id)
                if college is None:
                    college = {
                        "id": college_id,
                        "name": row_last["college"],
                        "city": "",
                        "tags": [],
                        "intro": "",
                    }
                    colleges[college_id] = college

                program_id = f"{college_id}-{unit_code}"
                rank_last = curve_last.rank(row_last["score"])
                programs.append(
                    {
                        "id": program_id,
                        "college_id": college_id,
                        "name": row_last["name"],
                        "kind": unit_kind,
                        "unit_code": unit_code,
                        "province": province,
                        "track": track,
                        "requirement": row_last["requirement"],
                        "heat": _heat(rank_last, curve_last.candidates),
                    }
                )
                latest_lines[(province, track, code, unit_code)] = row_last

                for year in years:
                    row = toudang.get(year, {}).get((code, unit_code))
                    table = tables.get(year)
                    if not row or not table:
                        continue
                    # A program group whose subject requirement changed is not a
                    # comparable series, so it is left out of that year.
                    if year != LATEST_YEAR and row["requirement"] != row_last["requirement"]:
                        continue
                    stats.append(
                        {
                            "program_id": program_id,
                            "year": year,
                            "min_score": row["score"],
                            # 有的省（浙江）表里直接给官方位次，就不要再拿分数反算了；
                            # 没给的（江苏/广东/山西）再用一分一段表换算。
                            "min_rank": row.get("rank") or table.rank(row["score"]),
                            "plan": row.get("plan") or 0,
                            "line": lines.get(year, lines[LATEST_YEAR]),
                        }
                    )

        provinces_meta[province] = {
            "available": True,
            "unit": conf.get("unit", "group"),
            "slots_max": conf.get("slots_max"),
            "tracks": tracks_meta,
        }

    stats.sort(key=lambda row: (row["program_id"], row["year"]))

    total_candidates = sum(
        meta["candidates"] for conf in provinces_meta.values() for meta in conf["tracks"].values()
    )
    recent_drift = int(round(statistics.median([item["drift"] for item in recent]))) if recent else 0
    recent_scale = (
        round(statistics.mean([item["scale"] for item in recent]), 4) if recent else 1.0
    )

    return {
        "mode": "real",
        "source": "real-js",
        "target_year": TARGET_YEAR,
        "years": list(YEARS),
        # The shift is measured on 2025 → 2026. We do not carry it into the
        # 2027 forecast: an unknown next-year expansion would otherwise be
        # double-counted, and assuming "schools get easier" is the unsafe
        # direction for a 保底 recommendation.
        "scale": 1.0,
        "drift": 0,
        "recent_scale": recent_scale,
        "recent_drift": recent_drift,
        "curves": curves,
        "provinces": provinces_meta,
        "notice": (
            "数据来源：江苏、广东、湖北、山西、辽宁、浙江、山东、河北八省教育考试院"
            "公开发布的普通类本科批投档线与逐分段统计表，覆盖物理类、历史类"
            "（浙江、山东为综合改革，单科类；湖北、河北、浙江、山东目前只有最近一年）。"
            f"最近一年录取位次整体后移约 {recent_drift:,} 名，未计入 {TARGET_YEAR} 预测。"
            "结果为统计估算，不构成志愿填报建议。"
        ),
        "candidate_total": total_candidates,
        "colleges": list(colleges.values()),
        "programs": programs,
        "stats": stats,
    }


def _heat(rank: int, candidates: int) -> int:
    """Rough 'competition' score so the UI still has something to show."""
    share = max(0.0, min(1.0, rank / max(1, candidates)))
    return max(30, min(99, int(round(100 - 62 * share ** 0.5))))


def load_curves() -> dict[tuple[str, str], RankTable]:
    """Expose the score ↔ rank tables for the 一分一段 lookup page."""
    out: dict[tuple[str, str], RankTable] = {}
    for province, conf in PROVINCES.items():
        for track, track_conf in conf.get("tracks", {}).items():
            table = _load_curve(
                f"curve_{LATEST_YEAR}_{track_conf['key']}.csv",
                track_conf["lines"][LATEST_YEAR],
                province,
            )
            if table:
                out[(province, track)] = table
    return out


def curve_series(province: str, track: str) -> dict[int, RankTable]:
    """All available years of one (province, track) curve."""
    slug = _track_slug(province, track)
    if not slug:
        return {}
    conf = PROVINCES[province]["tracks"][track]
    out: dict[int, RankTable] = {}
    for year, line in conf["lines"].items():
        table = _load_curve(f"curve_{year}_{slug}.csv", line, province)
        if table:
            out[year] = table
    return out


def lookup_curve(province: str, track: str, score: int | None = None, rank: int | None = None) -> dict:
    """Score ↔ rank lookup across every year we have for one province/track."""
    if not province:
        raise ValueError("请先选择省份")
    if not track:
        raise ValueError("请先选择科类")
    if province not in PROVINCES:
        raise ValueError(
            f"暂不支持 {province}，目前覆盖的是江苏、广东、湖北、山西、辽宁、浙江、山东、河北"
        )
    conf = PROVINCES[province]
    if not conf.get("available") or track not in conf.get("tracks", {}):
        raise ValueError(f"{province} · {track} 的数据正在整理中")
    if score is None and rank is None:
        raise ValueError("请至少填写分数或位次")
    if score is not None and not (0 <= score <= 750):
        raise ValueError("分数需要在 0 ~ 750 之间")
    if rank is not None and rank < 1:
        raise ValueError("位次需要大于 0")

    series = curve_series(province, track)
    if not series:
        raise ValueError(f"{province} · {track} 的数据正在整理中")

    rows = []
    for year in sorted(series, reverse=True):
        table = series[year]
        if score is not None:
            value_rank = table.rank(score)
            value_score = int(score)
        else:
            value_rank = int(rank)
            value_score = table.score(rank)
        rows.append(
            {
                "year": year,
                "score": value_score,
                "rank": value_rank,
                "line": table.line,
                "candidates": table.candidates,
                "percentile": round(value_rank / max(1, table.candidates) * 100, 2),
                "above_line": value_score - table.line,
            }
        )

    top = series[max(series)]
    return {
        "province": province,
        "track": track,
        "input": {"score": score, "rank": rank},
        "years": sorted(series, reverse=True),
        "line": top.line,
        "candidates": top.candidates,
        "rows": rows,
        "note": (
            f"{province} · {track} 逐分段统计表 {min(series)}–{max(series)} 年，"
            f"表内覆盖 {top.line} 分以上考生，本科线 {top.line} 分。"
        ),
    }
