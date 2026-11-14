"""Deterministic mock dataset for the "admission probability" demo.

All numbers here are synthetic. They are generated from a fixed seed so the
API, the tests and the UI always agree, and are shaped so that they behave
like a real province-level score/rank distribution (a monotone "一分一段"
curve plus per-program volatility and trend).

Nothing in this module is real admission data.
"""

from __future__ import annotations

import math
import random

YEARS = (2023, 2024, 2025)
TARGET_YEAR = 2026
DATA_SOURCE = "mock"

# --------------------------------------------------------------------------
# Provinces / tracks
# --------------------------------------------------------------------------
PROVINCES: dict[str, dict] = {
    "江苏": {
        "tracks": {
            "物理类": {"candidates": 258_000, "line": 448},
            "历史类": {"candidates": 118_000, "line": 474},
        },
    },
    "广东": {
        "tracks": {
            "物理类": {"candidates": 400_000, "line": 425},
            "历史类": {"candidates": 260_000, "line": 440},
        },
    },
}

# (points above the batch line, cumulative share of all candidates)
# Log-linear interpolation between anchors; this is the fake "一分一段表".
_CURVE_ANCHORS = (
    (-90, 0.9600),
    (-40, 0.8500),
    (0, 0.6200),
    (30, 0.2000),
    (60, 0.1150),
    (90, 0.0750),
    (120, 0.0450),
    (150, 0.0250),
    (180, 0.0125),
    (210, 0.0055),
    (240, 0.0022),
    (270, 0.0008),
    (300, 0.0002),
)


class ScoreCurve:
    """A synthetic score <-> rank conversion table for one province/year."""

    def __init__(self, line: int, candidates: int):
        self.line = line
        self.candidates = candidates

    def share(self, score: float) -> float:
        delta = max(min(score - self.line, 300), -90)
        anchors = _CURVE_ANCHORS
        idx = 0
        while idx < len(anchors) - 1 and anchors[idx + 1][0] <= delta:
            idx += 1
        d0, f0 = anchors[idx]
        d1, f1 = anchors[min(idx + 1, len(anchors) - 1)]
        if d0 == d1:
            return f0
        ratio = (delta - d0) / (d1 - d0)
        return math.exp(math.log(f0) + (math.log(f1) - math.log(f0)) * ratio)

    def rank(self, score: float) -> int:
        return max(1, int(round(self.share(score) * self.candidates)))

    def score(self, rank: float) -> int:
        """Smallest score whose cumulative rank is still <= ``rank``."""
        share = max(min(rank / self.candidates, 0.999), 1e-6)
        lo, hi = self.line - 90, 750
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.share(mid) >= share:
                lo = mid
            else:
                hi = mid - 1
        return int(lo)


# --------------------------------------------------------------------------
# Colleges (names are real, every statistic below is fabricated)
# --------------------------------------------------------------------------
# base_frac: roughly the share of candidates that reaches this college.
COLLEGES: tuple[dict, ...] = (
    {"id": "c01", "name": "清华大学", "city": "北京", "tags": ["985", "211", "双一流"], "base_frac": 0.0006},
    {"id": "c02", "name": "北京大学", "city": "北京", "tags": ["985", "211", "双一流"], "base_frac": 0.0009},
    {"id": "c03", "name": "上海交通大学", "city": "上海", "tags": ["985", "211", "双一流"], "base_frac": 0.0022},
    {"id": "c04", "name": "复旦大学", "city": "上海", "tags": ["985", "211", "双一流"], "base_frac": 0.0028},
    {"id": "c05", "name": "浙江大学", "city": "杭州", "tags": ["985", "211", "双一流"], "base_frac": 0.0038},
    {"id": "c06", "name": "中国科学技术大学", "city": "合肥", "tags": ["985", "211", "双一流"], "base_frac": 0.0046},
    {"id": "c07", "name": "南京大学", "city": "南京", "tags": ["985", "211", "双一流"], "base_frac": 0.0060},
    {"id": "c08", "name": "中国人民大学", "city": "北京", "tags": ["985", "211", "双一流"], "base_frac": 0.0072},
    {"id": "c09", "name": "同济大学", "city": "上海", "tags": ["985", "211", "双一流"], "base_frac": 0.0100},
    {"id": "c10", "name": "北京航空航天大学", "city": "北京", "tags": ["985", "211", "双一流"], "base_frac": 0.0125},
    {"id": "c11", "name": "武汉大学", "city": "武汉", "tags": ["985", "211", "双一流"], "base_frac": 0.0180},
    {"id": "c12", "name": "华中科技大学", "city": "武汉", "tags": ["985", "211", "双一流"], "base_frac": 0.0205},
    {"id": "c13", "name": "东南大学", "city": "南京", "tags": ["985", "211", "双一流"], "base_frac": 0.0240},
    {"id": "c14", "name": "中山大学", "city": "广州", "tags": ["985", "211", "双一流"], "base_frac": 0.0300},
    {"id": "c15", "name": "哈尔滨工业大学", "city": "哈尔滨", "tags": ["985", "211", "双一流"], "base_frac": 0.0330},
    {"id": "c16", "name": "西安交通大学", "city": "西安", "tags": ["985", "211", "双一流"], "base_frac": 0.0380},
    {"id": "c17", "name": "厦门大学", "city": "厦门", "tags": ["985", "211", "双一流"], "base_frac": 0.0450},
    {"id": "c18", "name": "天津大学", "city": "天津", "tags": ["985", "211", "双一流"], "base_frac": 0.0500},
    {"id": "c19", "name": "北京理工大学", "city": "北京", "tags": ["985", "211", "双一流"], "base_frac": 0.0560},
    {"id": "c20", "name": "华东师范大学", "city": "上海", "tags": ["985", "211", "双一流"], "base_frac": 0.0620},
    {"id": "c21", "name": "电子科技大学", "city": "成都", "tags": ["985", "211", "双一流"], "base_frac": 0.0700},
    {"id": "c22", "name": "四川大学", "city": "成都", "tags": ["985", "211", "双一流"], "base_frac": 0.0780},
    {"id": "c23", "name": "华南理工大学", "city": "广州", "tags": ["985", "211", "双一流"], "base_frac": 0.0850},
    {"id": "c24", "name": "中南大学", "city": "长沙", "tags": ["985", "211", "双一流"], "base_frac": 0.0950},
    {"id": "c25", "name": "大连理工大学", "city": "大连", "tags": ["985", "211", "双一流"], "base_frac": 0.1050},
    {"id": "c26", "name": "湖南大学", "city": "长沙", "tags": ["985", "211", "双一流"], "base_frac": 0.1150},
    {"id": "c27", "name": "重庆大学", "city": "重庆", "tags": ["985", "211", "双一流"], "base_frac": 0.1250},
    {"id": "c28", "name": "兰州大学", "city": "兰州", "tags": ["985", "211", "双一流"], "base_frac": 0.1500},
    {"id": "c29", "name": "南京理工大学", "city": "南京", "tags": ["211", "双一流"], "base_frac": 0.1350},
    {"id": "c30", "name": "苏州大学", "city": "苏州", "tags": ["211", "双一流"], "base_frac": 0.1450},
    {"id": "c31", "name": "郑州大学", "city": "郑州", "tags": ["211", "双一流"], "base_frac": 0.1800},
    {"id": "c32", "name": "西南大学", "city": "重庆", "tags": ["211", "双一流"], "base_frac": 0.2000},
    {"id": "c33", "name": "江苏大学", "city": "镇江", "tags": ["省重点"], "base_frac": 0.2400},
    {"id": "c34", "name": "扬州大学", "city": "扬州", "tags": ["省重点"], "base_frac": 0.3000},
    {"id": "c35", "name": "南通大学", "city": "南通", "tags": ["省重点"], "base_frac": 0.3600},
    {"id": "c36", "name": "河南理工大学", "city": "焦作", "tags": ["省重点"], "base_frac": 0.4000},
    {"id": "c37", "name": "常州大学", "city": "常州", "tags": ["省重点"], "base_frac": 0.4300},
    {"id": "c38", "name": "江苏科技大学", "city": "镇江", "tags": ["省重点"], "base_frac": 0.4700},
    {"id": "c39", "name": "河南工业大学", "city": "郑州", "tags": ["省重点"], "base_frac": 0.5000},
    {"id": "c40", "name": "西华大学", "city": "成都", "tags": ["省属本科"], "base_frac": 0.4200},
    {"id": "c41", "name": "四川轻化工大学", "city": "自贡", "tags": ["省属本科"], "base_frac": 0.4400},
    {"id": "c42", "name": "盐城工学院", "city": "盐城", "tags": ["省属本科"], "base_frac": 0.4600},
    {"id": "c43", "name": "中原工学院", "city": "郑州", "tags": ["省属本科"], "base_frac": 0.4800},
    {"id": "c44", "name": "淮阴工学院", "city": "淮安", "tags": ["省属本科"], "base_frac": 0.5000},
    {"id": "c45", "name": "黄淮学院", "city": "驻马店", "tags": ["省属本科"], "base_frac": 0.5200},
)

PHYSICS_MAJORS = (
    ("计算机科学与技术", 0.72, "物理+化学"),
    ("电子信息类", 0.80, "物理+化学"),
    ("自动化类", 0.95, "物理+化学"),
    ("临床医学", 0.78, "物理+化学"),
    ("软件工程", 0.85, "物理+化学"),
    ("金融学类", 0.90, "物理+不限"),
    ("数学类", 0.92, "物理+化学"),
    ("建筑类", 1.05, "物理+不限"),
    ("机械类", 1.10, "物理+化学"),
    ("能源动力类", 1.15, "物理+化学"),
    ("口腔医学", 0.75, "物理+化学"),
    ("经济学类", 0.98, "物理+不限"),
)

HISTORY_MAJORS = (
    ("汉语言文学", 0.85, "历史+不限"),
    ("法学", 0.80, "历史+不限"),
    ("新闻传播学类", 1.00, "历史+不限"),
    ("英语", 1.05, "历史+不限"),
    ("历史学类", 1.10, "历史+不限"),
    ("经济学类", 0.95, "历史+不限"),
    ("行政管理", 1.15, "历史+不限"),
    ("社会学类", 1.20, "历史+不限"),
    ("教育学类", 1.12, "历史+不限"),
    ("会计学", 0.92, "历史+不限"),
)


def curve_for(province: str, track: str, year: int = 2025) -> ScoreCurve:
    info = PROVINCES[province]["tracks"][track]
    line = info["line"] + (year - 2024) * 2
    return ScoreCurve(line=line, candidates=info["candidates"])


# 少数专业只在这类院校开设，避免出现「哈工大口腔医学」这种明显穿帮的组合。
MED_COLLEGES = frozenset(
    {"c02", "c03", "c04", "c05", "c07", "c11", "c12", "c14", "c16", "c17",
     "c22", "c24", "c28", "c30", "c31", "c33", "c34", "c35"}
)
ARCH_COLLEGES = frozenset(
    {"c01", "c03", "c05", "c07", "c09", "c11", "c12", "c13", "c15", "c16",
     "c17", "c18", "c22", "c23", "c24", "c26", "c27"}
)
MAJOR_ALLOWED = {
    "临床医学": MED_COLLEGES,
    "口腔医学": MED_COLLEGES,
    "建筑类": ARCH_COLLEGES,
}


def _major_pool(majors, college_id: str):
    allowed = tuple(
        m for m in majors
        if m[0] not in MAJOR_ALLOWED or college_id in MAJOR_ALLOWED[m[0]]
    )
    return allowed if len(allowed) >= 3 else majors


def build_dataset() -> dict:
    """Build every college/program/stat row from the fixed seed."""
    colleges = []
    programs = []
    stats = []

    for college in COLLEGES:
        colleges.append(
            {
                "id": college["id"],
                "name": college["name"],
                "city": college["city"],
                "tags": list(college["tags"]),
                "intro": _intro(college),
            }
        )

        for province, pdata in PROVINCES.items():
            for track in pdata["tracks"]:
                curve = curve_for(province, track)
                majors = _major_pool(PHYSICS_MAJORS if track == "物理类" else HISTORY_MAJORS, college["id"])
                rng = random.Random(f"{college['id']}|{province}|{track}")
                chosen = rng.sample(majors, 3)
                drift = rng.uniform(-0.05, 0.05)

                for major_index, (major, factor, requirement) in enumerate(chosen):
                    pid = f"{college['id']}-{_slug(province)}-{_slug(track)}-{major_index}"
                    base_rank = max(20.0, college["base_frac"] * curve.candidates * factor)
                    heat = int(round(58 + (1.4 - factor) * 45 + rng.uniform(-8, 8)))
                    heat = max(35, min(99, heat))
                    programs.append(
                        {
                            "id": pid,
                            "college_id": college["id"],
                            "name": major,
                            "province": province,
                            "track": track,
                            "requirement": requirement,
                            "heat": heat,
                        }
                    )

                    for year in YEARS:
                        year_rng = random.Random(f"{pid}|{year}")
                        noise = year_rng.uniform(-0.035, 0.035)
                        trend = drift * (year - 2024)
                        line = PROVINCES[province]["tracks"][track]["line"] + (year - 2024) * 2
                        rank = max(20, int(round(base_rank * (1 + noise + trend))))
                        # Never place a program below the undergraduate line.
                        rank = min(rank, curve.rank(curve.line + 2))
                        score = curve.score(rank)
                        plan = 6 + year_rng.randrange(0, 9) * 4
                        stats.append(
                            {
                                "program_id": pid,
                                "year": year,
                                "min_score": score,
                                "min_rank": rank,
                                "plan": plan,
                                "line": line,
                            }
                        )

    stats.sort(key=lambda s: (s["program_id"], s["year"]))
    return {"colleges": colleges, "programs": programs, "stats": stats, "years": list(YEARS)}


def _slug(text: str) -> str:
    table = {
        "江苏": "js", "广东": "gd",
        "物理类": "phys", "历史类": "hist",
    }
    if text in table:
        return table[text]
    # stable short hash for major names
    return "m%02d" % (sum(ord(ch) for ch in text) % 97)


def _intro(college: dict) -> str:
    tags = "、".join(college["tags"])
    return f"{tags}高校，位于{college['city']}。演示数据，非真实录取信息。"
