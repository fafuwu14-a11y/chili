"""Admission-probability model.

Two modes share the same ``Dataset`` shell:

**mock** — the original demo model, kept so the UI and tests run without any
real data:

1.  For every program take its last three years of minimum admitted rank.
2.  Weight the recent years more, then extrapolate the linear trend by one
    year to get a predicted minimum rank for the target year.
3.  Turn (user rank - predicted rank) into a probability with a logistic
    curve whose width comes from the program's own historical volatility.
4.  Do the same in score space against the predicted minimum score.
5.  Blend 75% rank + 25% score and cut the result into 冲 / 稳 / 保 tiers.

**real** — the model that survived the 2025→2026 backtest (see
``realdata/REPORT.md``):

1.  Take the latest year's admitted rank for the program.
2.  Multiply by the candidate-pool scale, add the measured drift.
3.  Probability = logistic((predicted rank - user rank) / sigma), with
    ``sigma = max(predicted rank * 0.075, 1200)``.

Three-year trend extrapolation is deliberately *not* used in real mode: the
backtest showed it adds noise rather than signal.
"""

from __future__ import annotations

import math
import statistics

from . import mock_data
from .real_data import SIGMA_FACTOR, SIGMA_FLOOR

TIER_CHONG = "冲"
TIER_WEN = "稳"
TIER_BAO = "保"

YEAR_WEIGHTS = (0.2, 0.3, 0.5)


class Dataset:
    def __init__(self, raw: dict):
        self.raw = raw
        self.mode = raw.get("mode", "mock")
        self.years = list(raw.get("years", mock_data.YEARS))
        self.province_info = raw.get("provinces") or mock_data.PROVINCES
        self.scale = raw.get("scale", 1.0)
        self.drift = raw.get("drift", 0)
        self.curves = raw.get("curves") or {}
        self.colleges: dict[str, dict] = {c["id"]: c for c in raw["colleges"]}
        self.programs: list[dict] = raw["programs"]
        self.stats: dict[str, list[dict]] = {}
        for row in raw["stats"]:
            self.stats.setdefault(row["program_id"], []).append(row)
        for rows in self.stats.values():
            rows.sort(key=lambda r: r["year"])

        self.by_route: dict[tuple[str, str], list[dict]] = {}
        for program in self.programs:
            self.by_route.setdefault((program["province"], program["track"]), []).append(program)

    # -- lookups ---------------------------------------------------------
    def study_years(self) -> list[int]:
        return list(self.years)

    def program_history(self, program_id: str) -> list[dict]:
        return self.stats.get(program_id, [])

    def curve_for(self, province: str, track: str):
        if self.mode == "real":
            table = self.curves.get((province, track))
            if table is None:
                raise ValueError(f"{province} · {track} 暂无一分一段数据")
            return table
        return mock_data.curve_for(province, track)

    def meta(self) -> dict:
        provinces = {}
        for name, data in self.province_info.items():
            tracks = data.get("tracks") or {}
            provinces[name] = {
                "available": bool(data.get("available", True)),
                "unit": data.get("unit", "group"),
                "slots_max": int(data.get("slots_max") or 45),
                "tracks": list(tracks.keys()),
                "candidates": {t: v["candidates"] for t, v in tracks.items()},
                "line": {t: v["line"] for t, v in tracks.items()},
            }
        return {
            "source": self.raw.get("source", mock_data.DATA_SOURCE),
            "mode": self.mode,
            "target_year": self.raw.get("target_year", mock_data.TARGET_YEAR),
            "years": self.years,
            "provinces": provinces,
            "college_count": len(self.colleges),
            "program_count": len(self.programs),
            "stat_count": sum(len(v) for v in self.stats.values()),
            "scale": round(self.scale, 4),
            "drift": self.drift,
            "recent_scale": self.raw.get("recent_scale"),
            "recent_drift": self.raw.get("recent_drift"),
            "notice": self.raw.get("notice", ""),
        }

    def search_colleges(
        self,
        query: str,
        province: str | None = None,
        track: str | None = None,
        limit: int = 8,
    ) -> list[dict]:
        """按校名找学校：先精确，再前缀，再包含，最后才算城市。

        只返回当前省/科类真的有招生单位的学校——否则点进去是空列表，
        用户会以为搜错了。
        """
        q = (query or "").strip().lower()
        if not q:
            return []

        programs = self.by_route.get((province, track), []) if province and track else []
        counts: dict[str, int] = {}
        for program in programs:
            counts[program["college_id"]] = counts.get(program["college_id"], 0) + 1

        rows: list[tuple[int, int, dict]] = []
        for college in self.colleges.values():
            if province and track and not counts.get(college["id"]):
                continue
            name = college.get("name", "")
            low = name.lower()
            if q in low:
                rank = 3 if low == q else 2 if low.startswith(q) else 1
            elif q in str(college.get("city", "")).lower():
                rank = 0
            else:
                continue
            rows.append((rank, len(low), counts.get(college["id"], 0), college))

        # 同档匹配里，名字短的更可能是用户要的那所（搜「东南」先出东南大学，
        # 而不是「东南大学成贤学院」）。
        rows.sort(key=lambda r: (-r[0], r[1], -r[2], r[3].get("name", "")))
        return [
            {
                "id": college["id"],
                "name": college.get("name", ""),
                "city": college.get("city", ""),
                "tags": list(college.get("tags") or []),
                "program_count": count,
            }
            for _, _, count, college in rows[: max(1, min(int(limit or 8), 30))]
        ]

    # -- prediction ------------------------------------------------------
    def predict(
        self,
        province: str,
        track: str,
        score: int | None = None,
        rank: int | None = None,
        tier: str | None = None,
        limit: int = 200,
        college: str | None = None,
    ) -> dict:
        self._validate_route(province, track)
        curve = self.curve_for(province, track)
        info = self.province_info[province]["tracks"][track]

        if score is None and rank is None:
            raise ValueError("请至少提供分数或位次")
        if score is not None and not 0 <= score <= 750:
            raise ValueError("分数需要在 0 ~ 750 之间")
        if rank is not None and not 1 <= rank <= info["candidates"]:
            raise ValueError(f"位次需要在 1 ~ {info['candidates']} 之间")

        if rank is None:
            rank = curve.rank(score)  # type: ignore[arg-type]
        if score is None:
            score = curve.score(rank)

        items = []
        for program in self.by_route[(province, track)]:
            if college and program["college_id"] != college:
                continue
            history = self.program_history(program["id"])
            if not history:
                continue
            if self.mode == "real":
                item = self._score_program_real(program, history, curve, score, rank)
            else:
                if len(history) < 2:
                    continue
                item = self._score_program(program, history, curve, score, rank)
            items.append(item)

        # Real data has thousands of groups per province, so probability-first
        # ordering would fill the page with 99% 保底 schools. Order by how close
        # the program sits to the user's rank instead — that's what "matching"
        # means to a candidate.
        if college:
            # 只看一所学校时，按往年录取线从高到低排，读起来就是「这校从难到易」。
            items.sort(key=lambda x: (-x["predicted_score"], x["name"]))
        elif self.mode == "real":
            items.sort(key=lambda x: (abs(x["rank_gap"]), -x["probability"]))
        else:
            items.sort(key=lambda x: x["probability"], reverse=True)
        if tier in (TIER_CHONG, TIER_WEN, TIER_BAO):
            items = [x for x in items if x["tier"] == tier]

        counts = {TIER_CHONG: 0, TIER_WEN: 0, TIER_BAO: 0}
        for item in items:
            counts[item["tier"]] += 1
        total_all = len(items)

        # ``limit=0``（或 None）表示不截断：冲稳保方案要把全量候选挑一遍，
        # 只拿前 200 条「匹配度最高」的会让保底档直接空掉（前 200 条里没有
        # 位次差很远的保底校）。看单所学校时同理，一校几十个专业都要列全。
        if limit and not college:
            items = items[: max(1, min(int(limit), 200))]

        return {
            "input": {
                "province": province,
                "track": track,
                "score": score,
                "rank": rank,
                "year": self.raw.get("target_year", mock_data.TARGET_YEAR),
                "candidates": info["candidates"],
                "line": info["line"],
                "percentile": round(rank / info["candidates"] * 100, 2),
            },
            "summary": {
                "total": total_all,
                "listed": len(items),
                "chong": counts[TIER_CHONG],
                "wen": counts[TIER_WEN],
                "bao": counts[TIER_BAO],
                "college": college,
            },
            "items": items,
            "source": self.raw.get("source", mock_data.DATA_SOURCE),
        }

    def _score_program_real(
        self,
        program: dict,
        history: list[dict],
        curve,
        user_score: int,
        user_rank: int,
    ) -> dict:
        """Rank-equivalence model: latest rank × scale + drift."""
        latest = history[-1]
        base = latest["min_rank"] * self.scale + self.drift
        predicted_rank = max(20.0, base)

        sigma = max(predicted_rank * SIGMA_FACTOR, SIGMA_FLOOR)
        probability = _logistic((predicted_rank - user_rank) / sigma)
        probability = max(0.01, min(0.99, probability))

        predicted_score = curve.score(predicted_rank)
        rank_gap = int(round(predicted_rank - user_rank))

        ranks = [row["min_rank"] for row in history]
        if len(ranks) >= 2:
            volatility = statistics.pstdev(ranks)
            cv = volatility / max(predicted_rank, 1)
            confidence_score = max(30, min(96, int(round(94 - cv * 220))))
        else:
            confidence_score = 62  # only one year of history
        if self.drift:
            confidence_score = max(20, confidence_score - 6)
        confidence_level = "高" if confidence_score >= 80 else ("中" if confidence_score >= 60 else "低")

        college = self.colleges[program["college_id"]]
        tier = _tier(probability)

        return {
            "program_id": program["id"],
            "college": college,
            "name": program["name"],
            "kind": program.get("kind", "group"),
            "unit_code": program.get("unit_code", ""),
            "requirement": program["requirement"],
            "heat": program["heat"],
            "plan": latest.get("plan", 0),
            "tier": tier,
            "probability": round(probability, 4),
            "predicted_rank": int(round(predicted_rank)),
            "predicted_score": predicted_score,
            "rank_gap": rank_gap,
            "score_gap": user_score - predicted_score,
            "confidence": {"level": confidence_level, "score": confidence_score},
            "history": [
                {
                    "year": row["year"],
                    "min_score": row["min_score"],
                    "min_rank": row["min_rank"],
                    "plan": row.get("plan", 0),
                    "line": row["line"],
                }
                for row in history
            ],
            "advice": _advice(tier, rank_gap),
        }

    def _score_program(
        self,
        program: dict,
        history: list[dict],
        curve: mock_data.ScoreCurve,
        user_score: int,
        user_rank: int,
    ) -> dict:
        ranks = [row["min_rank"] for row in history]
        weights = YEAR_WEIGHTS[-len(ranks):]
        total_weight = sum(weights)
        base = sum(w * r for w, r in zip(weights, ranks)) / total_weight

        slope = (ranks[-1] - ranks[0]) / max(1, len(ranks) - 1)
        slope = max(min(slope, base * 0.15), -base * 0.15)
        predicted_rank = max(20.0, base + slope)

        volatility = statistics.pstdev(ranks) if len(ranks) > 1 else base * 0.05
        scale = max(volatility * 2.0, predicted_rank * 0.30, 800)

        z_rank = (predicted_rank - user_rank) / scale
        p_rank = _logistic(z_rank, steepness=1.0)

        predicted_score = curve.score(predicted_rank)
        points_per_rank = max(1.0, abs(curve.score(predicted_rank * 0.93) - curve.score(predicted_rank * 1.07)))
        score_scale = max(2.5, points_per_rank / 2)
        p_score = _logistic((user_score - predicted_score) / score_scale, steepness=1.0)

        probability = 0.75 * p_rank + 0.25 * p_score
        probability = max(0.01, min(0.99, probability))

        tier = _tier(probability)
        cv = volatility / max(predicted_rank, 1)
        confidence_score = max(35, min(97, int(round(96 - cv * 260))))
        confidence_level = "高" if confidence_score >= 80 else ("中" if confidence_score >= 60 else "低")

        college = self.colleges[program["college_id"]]
        rank_gap = int(round(predicted_rank - user_rank))
        score_gap = user_score - predicted_score

        return {
            "program_id": program["id"],
            "college": college,
            "name": program["name"],
            "requirement": program["requirement"],
            "heat": program["heat"],
            "plan": history[-1]["plan"],
            "tier": tier,
            "probability": round(probability, 4),
            "predicted_rank": int(round(predicted_rank)),
            "predicted_score": predicted_score,
            "rank_gap": rank_gap,
            "score_gap": score_gap,
            "confidence": {"level": confidence_level, "score": confidence_score},
            "history": [
                {
                    "year": row["year"],
                    "min_score": row["min_score"],
                    "min_rank": row["min_rank"],
                    "plan": row["plan"],
                    "line": row["line"],
                }
                for row in history
            ],
            "advice": _advice(tier, rank_gap, program.get("kind", "group")),
        }

    # -- detail ----------------------------------------------------------
    def college_detail(self, college_id: str, province: str, track: str) -> dict:
        self._validate_route(province, track)
        college = self.colleges.get(college_id)
        if not college:
            raise KeyError("院校不存在")
        programs = [
            p for p in self.by_route[(province, track)] if p["college_id"] == college_id
        ]
        rows = []
        for program in programs:
            rows.append(
                {
                    "program_id": program["id"],
                    "name": program["name"],
                    "requirement": program["requirement"],
                    "heat": program["heat"],
                    "history": [
                        {
                            "year": r["year"],
                            "min_score": r["min_score"],
                            "min_rank": r["min_rank"],
                            "plan": r["plan"],
                            "line": r["line"],
                        }
                        for r in self.program_history(program["id"])
                    ],
                }
            )
        return {"college": college, "province": province, "track": track, "programs": rows}

    def _validate_route(self, province: str, track: str) -> None:
        if province not in self.province_info:
            raise ValueError(f"暂不支持该省份：{province}")
        if track not in self.province_info[province]["tracks"]:
            raise ValueError(f"{province} 不支持该科类：{track}")


def _logistic(x: float, steepness: float = 1.0) -> float:
    value = max(-40.0, min(40.0, steepness * x))
    return 1.0 / (1.0 + math.exp(-value))


def _tier(probability: float) -> str:
    if probability >= 0.85:
        return TIER_BAO
    if probability >= 0.45:
        return TIER_WEN
    return TIER_CHONG


def _advice(tier: str, rank_gap: int, kind: str = "group") -> str:
    gap = abs(rank_gap)
    if gap < 30:
        return "你的位次和它往年的录取线几乎重合，属于典型的「擦线」位置，建议放在志愿表中段，前后都要有保底。"
    if tier == TIER_CHONG:
        return f"你的位次比它往年的录取线靠后约 {gap:,} 名，属于要冲一冲的位置，建议放在志愿表前段，并搭配稳、保志愿。"
    if tier == TIER_WEN:
        if kind == "major":
            return f"你的位次与往年录取线相差约 {gap:,} 名，可作为主力志愿，注意该专业是否有单科要求或体检限制。"
        return f"你的位次与往年录取线相差约 {gap:,} 名，可作为主力志愿，注意专业组内调剂风险。"
    return f"你的位次领先往年录取线约 {gap:,} 名，录取把握较大，建议作为保底志愿。"
