"""功能 01：问卷打分引擎（五级量表）。

输入是一份答案字典（题号 → 1–5），输出是 21 个专业的匹配度排序。
全程规则计算、没有随机数、没有外部调用，毫秒级返回，可以完整单测。

作答是 MBTI 那种五级量表：1 完全不认同 … 5 非常认同。每题落在六维兴趣向量上，
反向题（reverse）按负分计入，所以「一路选 5」不会把每个维度都点满。

打分由三块加权相加，再减去「硬条件」惩罚：

    兴趣契合 0.72   兴趣向量（负值截零后）与专业画像的余弦相似度
    能力契合 0.18   该专业门槛（如数学）与自评是否匹配
    偏好契合 0.10   看重的标签（高薪/稳定/…）与专业标签的加权重合度

惩罚项：长学制不接受、实验环境不接受、偏离偏好地域、学费生活费预算吃紧。
"""

from __future__ import annotations

import math

from . import major_direction, quiz_data
from .quiz_data import ABILITY_LABELS, DIM_LABELS, MAJOR_PROFILES, QUESTIONS, SCALE, SPECS
from .predictor import Dataset

SPEC_INDEX = {spec["key"]: spec for spec in SPECS}

W_INTEREST = 0.72
W_ABILITY = 0.18
W_PREF = 0.10

PENALTY_LONG = 0.26
PENALTY_LAB = 0.14
PENALTY_REGION = 0.05
PENALTY_BUDGET = 0.08
BONUS_REGION = 0.05

# 五级量表里的门槛：>=4 视为「认同」，<=2 视为「不认同」，3 视为没表态
AGREE = 4
DISAGREE = 2


class QuizError(ValueError):
    """问卷答案不合法（缺题、取值越界、未知规格）。"""


# --------------------------------------------------------------------------
# 规格与题目
# --------------------------------------------------------------------------
def spec_list() -> list[dict]:
    return [
        {
            "key": spec["key"],
            "name": spec["name"],
            "count": spec["count"],
            "minutes": spec["minutes"],
            "level": spec["level"],
            "desc": spec["desc"],
            "covers": list(spec["covers"]),
        }
        for spec in SPECS
        if not spec.get("hidden")
    ]


def spec_detail(spec_key: str) -> dict:
    spec = SPEC_INDEX.get(spec_key)
    if spec is None:
        raise QuizError(f"未知的问卷规格：{spec_key}")
    questions = [
        {
            "id": q["id"],
            "group": _group_of(q["id"]),
            "text": q["text"],
            "reverse": bool(q.get("reverse")),
            "scale": list(SCALE["labels"]),
        }
        for q in QUESTIONS[spec_key]
    ]
    return {
        "key": spec["key"],
        "name": spec["name"],
        "count": spec["count"],
        "minutes": spec["minutes"],
        "level": spec["level"],
        "desc": spec["desc"],
        "covers": list(spec["covers"]),
        "scale": {
            "min": SCALE["min"],
            "max": SCALE["max"],
            "labels": list(SCALE["labels"]),
            "hints": list(SCALE["hints"]),
        },
        "questions": questions,
    }


def _group_of(question_id: str) -> str:
    return {
        "i": "interest",
        "a": "ability",
        "p": "pref",
        "s": "style",
        "f": "fit",
        "d": "direction",
    }[question_id[0]]


# --------------------------------------------------------------------------
# 匹配
# --------------------------------------------------------------------------
def match(dataset: Dataset, spec_key: str, answers: dict, limit: int = 6) -> dict:
    spec = SPEC_INDEX.get(spec_key)
    if spec is None:
        raise QuizError(f"未知的问卷规格：{spec_key}")
    if not isinstance(answers, dict):
        raise QuizError("answers 需要是一个对象")
    if limit is None:
        limit = 6
    limit = max(1, min(int(limit), 21))

    questions = QUESTIONS[spec_key]
    interest = {key: 0.0 for key in DIM_LABELS}
    ability_sum: dict[str, float] = {}
    ability_cnt: dict[str, int] = {}
    prefs: dict[str, float] = {}
    picked_region: tuple[str, float] | None = None
    constraints: dict = {}
    answered = 0

    for question in questions:
        qid = question["id"]
        value = _as_level(answers.get(qid))
        if value is None:
            continue
        answered += 1
        group = _group_of(qid)
        delta = (value - SCALE["mid"]) / 2.0  # -1 … +1

        if group in ("interest", "style"):
            if question.get("reverse"):
                delta = -delta
            for dim, weight in question.get("w", {}).items():
                interest[dim] += weight * delta
        elif group == "ability":
            dim = question.get("ability")
            if dim:
                ability_sum[dim] = ability_sum.get(dim, 0.0) + (value - 1) / 4.0
                ability_cnt[dim] = ability_cnt.get(dim, 0) + 1
        elif group == "pref":
            tag = question.get("tag")
            if tag:
                strength = (value - 1) / 4.0
                prefs[tag] = max(prefs.get(tag, 0.0), strength)
        elif group == "direction":
            # 方向题不进兴趣向量，统一交给 major_direction 折成方向坐标
            continue
        else:
            kind = question.get("constraint")
            if kind == "long_ok" and value != SCALE["mid"]:
                constraints["long_ok"] = value >= AGREE
            elif kind == "lab_ok" and value != SCALE["mid"]:
                constraints["lab_ok"] = value >= AGREE
            elif kind == "budget" and value >= AGREE:
                constraints["budget"] = "low"
            elif kind == "region":
                strength = (value - 1) / 4.0
                if value >= AGREE and (picked_region is None or strength > picked_region[1]):
                    picked_region = (question["region"], strength)

    if picked_region:
        constraints["region"] = picked_region[0]

    # 负分截零：反对某个方向只是「不加分」，不该让它变成负数拖累所有专业
    positive = {key: max(0.0, value) for key, value in interest.items()}
    peak = max(positive.values()) if positive else 0.0
    if peak <= 1e-6:
        raise QuizError(
            "答案里看不出明显的兴趣倾向（大多是「说不好」或都不认同），"
            "请至少对几道题给出「比较认同」，再来一次。"
        )

    abilities = {
        dim: ability_sum[dim] / ability_cnt[dim]
        for dim in ability_sum
        if ability_cnt[dim]
    }
    pref_tags = [tag for tag, strength in prefs.items() if strength >= 0.5]

    interest_unit = _normalize(positive)
    uniformity = (sum(positive.values()) / len(positive) / peak) if peak else 0.0

    items = []
    for name, profile in MAJOR_PROFILES.items():
        colleges = _colleges_of(dataset, name)
        cosine = _cosine(interest_unit, _normalize(profile["dims"]))
        # 余弦落在 0.35~1.0 之间才说明「真的像」，再用指数放大差异，
        # 否则同属工科的五六个专业会全部挤在 87~88 分，看不出区别。
        ratio = _clamp((cosine - 0.35) / 0.65, 0.0, 1.0)
        interest_part = ratio**1.6

        ability_part, weak_gate = _ability_fit(profile.get("gate", {}), abilities)
        pref_part, matched_tags = _pref_fit(profile.get("tags", []), prefs)

        penalty, notes = _penalties(profile, colleges, constraints)

        score = W_INTEREST * interest_part + W_ABILITY * ability_part + W_PREF * pref_part - penalty
        if constraints.get("region") and _in_region(colleges, constraints["region"]):
            score += BONUS_REGION
        score = _clamp(score, 0.0, 1.0)
        # 高分端压缩，避免一屏五六个 99/100，也避免并列挤在一起。
        if score > 0.88:
            score = 0.88 + (score - 0.88) * 0.72

        items.append(
            {
                "major": name,
                "group_id": major_direction.PROFILE_TO_GROUP.get(name, ""),
                "match": int(round(score * 100)),
                "tags": list(profile.get("tags", [])),
                "blurb": profile.get("blurb", ""),
                "long": bool(profile.get("long")),
                "lab": bool(profile.get("lab")),
                "matched_tags": matched_tags,
                "dims": [
                    {
                        "key": key,
                        "label": DIM_LABELS[key],
                        "value": round(profile["dims"].get(key, 0.0), 2),
                        "yours": round(positive[key] / peak, 2) if peak else 0.0,
                    }
                    for key in sorted(profile["dims"], key=lambda k: profile["dims"][k], reverse=True)
                ],
                "colleges": colleges[:3],
                "reason": _reason(name, profile, positive, matched_tags, weak_gate, notes),
            }
        )

    items.sort(key=lambda item: (-item["match"], item["major"]))
    top = items[:limit]

    # ---- 方向细分：把大类落到具体专业 ----
    # 只有答过方向题（standard / deep）才算得出考生方向；快测一律走中性值，
    # 此时细分分 = 大类分 × 0.8，类内顺序退化成「按招生规模」，结果页会说明原因。
    direction_answers = major_direction.score_answers(answers)
    your_direction = direction_answers["vector"] if direction_answers else None

    flat: list[dict] = []
    seen: set[str] = set()
    for item in top:
        rows = _directions_of(item, your_direction)
        item["directions"] = rows
        for row in rows:
            if row["major"] in seen:
                continue
            seen.add(row["major"])
            flat.append(row)

    flat.sort(key=lambda row: (-row["match"], -row["count"], row["major"]))
    majors = flat[:6]

    return {
        "spec": {
            "key": spec["key"],
            "name": spec["name"],
            "count": spec["count"],
            "minutes": spec["minutes"],
            "level": spec["level"],
        },
        "answered": answered,
        "confidence": _confidence(answered, spec["count"]),
        "interest": _dim_rows(positive, peak),
        "ability": [
            {"key": key, "label": ABILITY_LABELS[key], "value": round(abilities[key], 2)}
            for key in ("math", "science", "language", "english")
            if key in abilities
        ],
        "prefs": pref_tags,
        "items": top,
        "majors": majors,
        "direction": _direction_block(direction_answers, your_direction, spec_key),
        "advice": _advice(top, peak, positive, uniformity),
        "next": {
            "plan": "plan.html",
            "predict": "predict.html",
            "mooc": f"mooc.html?major={top[0]['major']}" if top else "mooc.html",
        },
        "source": "规则打分 · 演示数据",
    }


# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------
def _as_level(raw) -> int | None:
    """把答案归一成 1–5；越界或非数字一律当成没答。"""
    if isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if SCALE["min"] <= value <= SCALE["max"]:
        return value
    return None


def _normalize(vector: dict[str, float]) -> dict[str, float]:
    length = math.sqrt(sum(value * value for value in vector.values()))
    if length <= 1e-9:
        return {key: 0.0 for key in vector}
    return {key: value / length for key, value in vector.items()}


def _cosine(u: dict[str, float], v: dict[str, float]) -> float:
    keys = set(u) | set(v)
    dot = sum(u.get(key, 0.0) * v.get(key, 0.0) for key in keys)
    return _clamp(dot, 0.0, 1.0)


def _ability_fit(gate: dict, abilities: dict[str, float]) -> tuple[float, str | None]:
    """门槛越高、自评越弱，扣得越多。没答能力题时给中性分，不奖不罚。"""
    if not gate:
        return 0.62, None
    if not abilities:
        return 0.62, None
    penalties = []
    weakest = None
    worst = 0.0
    for dim, need in gate.items():
        have = abilities.get(dim)
        if have is None:
            continue
        gap = max(0.0, need - have)
        penalties.append(gap / max(need, 1e-6))
        if gap > worst:
            worst = gap
            weakest = dim
    if not penalties:
        return 0.62, None
    fit = _clamp(1.0 - sum(penalties) / len(penalties) * 0.9, 0.0, 1.0)
    return fit, (weakest if worst > 0.12 else None)


def _pref_fit(tags: list[str], prefs: dict[str, float]) -> tuple[float, list[str]]:
    """看重的标签越强、专业标签越贴，得分越高；没答偏好题时给中间分。"""
    total = sum(prefs.values())
    if total <= 0:
        return 0.5, []
    hit = sum(strength for tag, strength in prefs.items() if tag in tags)
    matched = [tag for tag, strength in prefs.items() if tag in tags and strength >= 0.5]
    return _clamp(hit / total, 0.0, 1.0), matched


def _penalties(profile: dict, colleges: list[dict], constraints: dict) -> tuple[float, list[str]]:
    penalty = 0.0
    notes = []
    if profile.get("long") and constraints.get("long_ok") is False:
        penalty += PENALTY_LONG
        notes.append("长学制")
    if profile.get("lab") and constraints.get("lab_ok") is False:
        penalty += PENALTY_LAB
        notes.append("实验/车间环境")
    budget_tight = constraints.get("budget") == "low"
    if budget_tight and profile.get("long"):
        penalty += PENALTY_BUDGET
        notes.append("学制长、总花费高")
    region = constraints.get("region")
    if region and colleges and not _in_region(colleges, region):
        penalty += PENALTY_REGION
        notes.append(f"主要在{colleges[0]['city']}，不在{region}")
    return penalty, notes


def _in_region(colleges: list[dict], region: str) -> bool:
    return any(quiz_data.REGION_OF_CITY.get(college["city"]) == region for college in colleges)


def _colleges_of(dataset: Dataset, major: str) -> list[dict]:
    seen = set()
    rows = []
    for program in dataset.programs:
        if program["name"] != major:
            continue
        college = dataset.colleges.get(program["college_id"])
        if not college or college["id"] in seen:
            continue
        seen.add(college["id"])
        rows.append(
            {
                "id": college["id"],
                "name": college["name"],
                "city": college["city"],
                "tags": list(college["tags"]),
            }
        )
    return rows


def _dim_rows(interest: dict[str, float], peak: float) -> list[dict]:
    return [
        {
            "key": key,
            "label": DIM_LABELS[key],
            "value": round(interest[key] / peak, 2) if peak else 0.0,
        }
        for key in sorted(interest, key=lambda k: interest[k], reverse=True)
    ]


def _directions_of(item: dict, your_direction: dict | None, limit: int = 3) -> list[dict]:
    """一个大类下的具体专业，按「大类分 × (0.6 + 0.4 × 方向匹配度)」排序取前几个。"""
    group_id = item.get("group_id") or ""
    if not group_id:
        return []
    rows = []
    for major in major_direction.majors_in_group(group_id):
        vector = major_direction.vector_of(major["name"], group_id)
        # 没答方向题时给中性值 0.5：既不会把某一类顶上去，也不会打压
        fit = major_direction.cosine(your_direction, vector) if your_direction else 0.5
        score = item["match"] * (0.6 + 0.4 * fit)
        rows.append(
            {
                "major": major["name"],
                "group": major["group"],
                "group_id": group_id,
                "category": major["category"],
                "category_name": major["category_name"],
                "match": int(round(score)),
                "group_match": item["match"],
                "direction_fit": round(fit, 3),
                "count": major["count"],
                "note": major_direction.note_of(major["name"]),
                "diff": major_direction.diff_note(major["name"], group_id, major["group"]),
                "from": item["major"],
            }
        )
    rows.sort(key=lambda row: (-row["match"], -row["count"], row["major"]))

    # 「软件工程」这种本身就是专业的条目：把它自己提到第一位，否则用户会看到
    # 「你适合软件工程 → 推荐物联网工程」这种绕口的错位。
    own = item["major"]
    if not own.endswith("类"):
        for index, row in enumerate(rows):
            if row["major"] == own:
                row["match"] = item["match"]
                row["direction_fit"] = 1.0
                row["diff"] = ""
                rows.insert(0, rows.pop(index))
                break
    return rows[:limit]


def _direction_block(
    direction_answers: dict | None,
    vector: dict | None,
    spec_key: str,
) -> dict:
    """结果页顶部那块「你的方向」说明。"""
    total = len(quiz_data.DIRECTION_QUESTIONS)
    axes = [
        {
            "key": key,
            "label": label,
            "value": round((vector or {}).get(key, 0.0), 2),
        }
        for key, label in major_direction.DIRECTION_AXES.items()
    ]
    axes.sort(key=lambda row: -row["value"])

    if spec_key == "quick":
        return {
            "available": False,
            "answered": 0,
            "total": 0,
            "peak": "",
            "axes": axes,
            "note": "快测只到大类。用标准或深度问卷多答 6 道方向题，就能落到具体专业。",
        }
    if vector is None:
        return {
            "available": True,
            "answered": 0,
            "total": total,
            "peak": "",
            "axes": axes,
            "note": "方向题没答，下面的具体专业先按大类分和招生规模排；补答方向题会排得更准。",
        }
    tops = [row["label"] for row in axes[:2] if row["value"] > 0.15]
    note = "你更偏"
    note += "和".join(f"「{label}」" for label in tops) if tops else "中性"
    note += "，下面的具体专业已经按这个方向排过序。"
    return {
        "available": True,
        "answered": direction_answers["answered"] if direction_answers else 0,
        "total": total,
        "peak": tops[0] if tops else "",
        "axes": axes,
        "note": note,
    }


def _confidence(answered: int, total: int) -> dict:
    ratio = answered / total if total else 0.0
    if ratio >= 0.85:
        level, note = "高", "题目基本答完，结果可以直接当参考。"
    elif ratio >= 0.55:
        level, note = "中", "还有几题没答，结果方向大致可信。"
    else:
        level, note = "低", "只答了一部分，建议再补几题或换更长的问卷。"
    return {"level": level, "percent": int(round(ratio * 100)), "note": note}


def _reason(
    name: str,
    profile: dict,
    interest: dict[str, float],
    matched_tags: list[str],
    weak_gate: str | None,
    notes: list[str],
) -> str:
    dims = profile["dims"]
    scored = {key: interest.get(key, 0.0) * dims[key] for key in dims}
    top_dim = max(scored, key=lambda key: scored[key])
    label = DIM_LABELS[top_dim]
    text = f"你在「{label}」上的倾向和它最合拍"
    if matched_tags:
        text += f"，也符合你看重的「{'、'.join(matched_tags[:2])}」"
    text += "。"
    if weak_gate:
        text += f"不过{ABILITY_LABELS.get(weak_gate, weak_gate)}基础偏弱，学起来会更吃力。"
    if notes:
        detail = "、".join(dict.fromkeys(notes))
        text += f"硬条件上要留个心：{detail}。"
    return text


def _advice(items: list[dict], peak: float = 1.0, interest: dict[str, float] | None = None,
            uniformity: float = 0.0) -> str:
    if not items:
        return "没有算出结果，请检查答案后重试。"
    top = items[0]
    second = items[1]["major"] if len(items) > 1 else None
    text = ""
    if uniformity > 0.8:
        text += "你的兴趣分布比较平均，没有哪一个方向特别突出，分数也普遍不高——这属于「都可以试试」；"
    text += f"最贴合你的是「{top['major']}」，匹配度 {top['match']}%。"
    if second:
        text += f"次选「{second}」。"
    text += "建议再用录取预测看看这个专业在你能报的院校里处在什么位置。"
    return text


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
