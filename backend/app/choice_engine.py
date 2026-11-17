"""功能 02：选科推荐引擎 —— 问卷答案 → 学科画像 → 组合与专业推荐。

纯规则、零依赖、可单测。AI 不参与打分，只负责把结果讲成人话（见 ai_client）。

流程：

    answers ──score──> subject(7) / ability(6) / cluster(12) / value(4)
                            │
                            ├─ 候选组合 = subjects.combos(province)
                            │     ├─ 学科契合 = 三门学科分均值
                            │     ├─ 专业匹配 = 可报专业类的兴趣簇加权
                            │     └─ 覆盖率   = 该组合可报专业比例（开方压缩）
                            │
                            └─ 专业推荐 = 821 专业逐个打分（必须在该组合下可报）
"""

from __future__ import annotations

from . import choice_quiz, subject_map, subjects

# --------------------------------------------------------------------------
# 92 个专业类 → 12 个兴趣簇
# --------------------------------------------------------------------------
GROUP_CLUSTER: dict[str, str] = {
    # 信息与智能
    "computer": "tech", "electronics": "tech", "automation": "tech",
    "electrical": "tech", "instrument": "tech",
    # 工程与制造
    "mechanical": "eng", "mechanics": "eng", "material": "eng", "energy": "eng",
    "civil": "eng", "water": "eng", "survey": "eng", "chemical_eng": "eng",
    "geo_eng": "eng", "mining": "eng", "textile": "eng", "light_industry": "eng",
    "transport": "eng", "ocean_eng": "eng", "aerospace": "eng", "weapon": "eng",
    "nuclear": "eng", "agri_eng": "eng", "forestry_eng": "eng", "environment": "eng",
    "bme": "eng", "safety": "eng", "bio_eng": "eng",
    # 医学与健康
    "basic_med": "med", "clinical": "med", "stomatology": "med",
    "public_health": "med", "tcm": "med", "integrated_med": "med",
    "pharmacy": "med", "tcm_pharmacy": "med", "forensic": "med",
    "med_tech": "med", "nursing": "med",
    # 农林与食品
    "plant": "agri", "nature": "agri", "animal": "agri", "vet": "agri",
    "forestry": "agri", "fishery": "agri", "grass": "agri", "food": "agri",
    # 基础科学
    "math": "sci", "physics": "sci", "chemistry": "sci", "astronomy": "sci",
    "geo_science": "sci", "atmos": "sci", "ocean": "sci", "geophysics": "sci",
    "geology": "sci", "biology_sci": "sci", "psychology": "sci", "statistics": "sci",
    # 经济与管理
    "economics": "biz", "finance": "biz", "financial": "biz", "trade": "biz",
    "management_sci": "biz", "business": "biz", "agri_econ": "biz",
    "logistics": "biz", "industrial_eng": "biz", "ecommerce": "biz", "tourism": "biz",
    # 法学与公共事务
    "law": "law", "politics": "law", "public_admin": "law", "library": "law",
    # 公安与安全
    "public_security": "police", "police_tech": "police",
    # 社会与人际
    "sociology": "social", "ethnology": "social", "marxism": "social",
    # 教育与体育
    "education": "edu", "sports": "edu",
    # 人文与语言
    "chinese": "humanities", "foreign": "humanities", "journalism": "humanities",
    "history": "humanities", "philosophy": "humanities",
    # 艺术与设计
    "art_theory": "art", "music": "art", "drama": "art",
    "fine_arts": "art", "design": "art",
}

# 每个专业类强依赖的选考学科（用于「学科匹配度」加权，不是选科要求）
GROUP_SUBJECTS: dict[str, tuple[str, ...]] = {
    "computer": ("physics", "technology"), "electronics": ("physics",),
    "automation": ("physics",), "electrical": ("physics",),
    "mechanical": ("physics",), "material": ("chemistry", "physics"),
    "energy": ("physics", "chemistry"), "civil": ("physics",),
    "architecture": ("physics", "geography"), "survey": ("physics", "geography"),
    "chemical_eng": ("chemistry",), "mining": ("physics", "chemistry"),
    "transport": ("physics",), "aerospace": ("physics",), "nuclear": ("physics",),
    "environment": ("chemistry", "biology"), "bio_eng": ("biology", "chemistry"),
    "food": ("chemistry", "biology"), "agri_eng": ("physics", "biology"),
    "clinical": ("biology", "chemistry"), "stomatology": ("biology", "chemistry"),
    "pharmacy": ("chemistry", "biology"), "tcm": ("biology",),
    "public_health": ("biology",), "nursing": ("biology",),
    "med_tech": ("biology", "chemistry"), "basic_med": ("biology", "chemistry"),
    "plant": ("biology", "chemistry"), "animal": ("biology",),
    "vet": ("biology", "chemistry"), "forestry": ("biology", "geography"),
    "math": ("physics",), "physics": ("physics",), "chemistry": ("chemistry",),
    "biology_sci": ("biology",), "geo_science": ("geography",),
    "atmos": ("geography", "physics"), "ocean": ("geography", "biology"),
    "geology": ("geography", "chemistry"), "psychology": ("biology", "politics"),
    "statistics": ("physics",), "astronomy": ("physics",),
    "economics": ("politics",), "finance": ("politics",), "financial": ("politics",),
    "trade": ("politics", "geography"), "business": ("politics",),
    "law": ("politics", "history"), "politics": ("politics", "history"),
    "public_admin": ("politics",), "sociology": ("politics", "history"),
    "marxism": ("politics", "history"), "education": ("politics",),
    "sports": ("biology",), "chinese": ("history",), "foreign": ("history",),
    "journalism": ("politics", "history"), "history": ("history",),
    "philosophy": ("politics", "history"), "art_theory": ("history",),
}

# --------------------------------------------------------------------------
# 12 个兴趣簇 → 霍兰德 RIASEC 六型
#
# 学生和家长不一定看得懂「tech 簇 82 分」，但「你是 I 研究型 + R 现实型」
# 是招聘、生涯规划、大学专业介绍里通用的语言。这一层只做翻译，不新增题目。
# --------------------------------------------------------------------------
RIASEC_NAMES: dict[str, tuple[str, str]] = {
    "R": ("现实型", "喜欢动手、设备、户外与具体制造"),
    "I": ("研究型", "喜欢探究原理、做实验、推演规律"),
    "A": ("艺术型", "喜欢表达、创意、审美与非标准答案"),
    "S": ("社会型", "喜欢与人打交道、帮助、教学与协作"),
    "E": ("企业型", "喜欢影响他人、组织资源、争取结果"),
    "C": ("常规型", "喜欢规则清晰、数据准确、流程稳定"),
}

# 簇 → 六型权重。一个簇可以同时指向多型，权重和不必等于 1。
RIASEC_CLUSTERS: dict[str, dict[str, float]] = {
    "tech": {"I": 1.0, "R": 0.55, "C": 0.2},
    "eng": {"R": 1.0, "I": 0.6},
    "med": {"I": 0.9, "S": 0.7, "R": 0.3},
    "agri": {"R": 0.9, "I": 0.5},
    "sci": {"I": 1.0},
    "biz": {"E": 1.0, "C": 0.7},
    "law": {"E": 0.8, "S": 0.6, "I": 0.3},
    "police": {"R": 0.7, "E": 0.7, "S": 0.4},
    "social": {"S": 1.0},
    "edu": {"S": 0.9, "A": 0.3},
    "humanities": {"A": 0.8, "S": 0.6, "I": 0.3},
    "art": {"A": 1.0},
}

# 文理倾向：物理侧 / 历史侧各自由哪几门课构成。
# 权重不是拍脑袋——物理侧把数学能力最强的物理放最高，历史侧把阅读量最大的历史放最高。
TRACK_PHYSICS: tuple[tuple[str, float], ...] = (
    ("physics", 0.40), ("chemistry", 0.25), ("biology", 0.20), ("technology", 0.15),
)
TRACK_HISTORY: tuple[tuple[str, float], ...] = (
    ("history", 0.45), ("politics", 0.30), ("geography", 0.25),
)


# 组合强度的定性提示（我们没有实时选考人数，只给结构性风险）
COMBO_WATCH = {
    ("物理", "化学", "生物"): "学霸密度最高，赋分竞争最激烈；医学、生物类专业的通行证。",
    ("物理", "化学", "政治"): "覆盖面接近最大，且避开生物的高分内卷；考公、法学方向不吃亏。",
    ("物理", "化学", "地理"): "理工全覆盖，地理赋分相对友好；地质、测绘、气象的加分项。",
    ("物理", "化学", "技术"): "浙江等省专属，技术学科竞争小但可选专业窄。",
    ("历史", "政治", "地理"): "文科经典组合，赋分稳定；可报专业约两成，志愿填报要更精准。",
    ("历史", "政治", "生物"): "文科为主、保留少量医学护理口子；生物赋分通常不占优。",
    ("物理", "生物", "地理"): "避开化学后，多数化工、材料、医学类专业关闭，需提前确认目标专业。",
}


# --------------------------------------------------------------------------
# 归一化基准：每个维度理论上能拿到的最大原始分
# --------------------------------------------------------------------------
def _dimension_max(questions=None) -> dict[str, dict[str, float]]:
    maxima: dict[str, dict[str, float]] = {
        "subject": {}, "ability": {}, "cluster": {},
    }
    for q in (questions or choice_quiz.QUESTIONS):
        if q["kind"] == "single":
            for bucket in ("subject", "ability", "cluster"):
                best: dict[str, float] = {}
                for opt in q["options"]:
                    for key, val in opt["scores"].get(bucket, {}).items():
                        best[key] = max(best.get(key, 0), val)
                for key, val in best.items():
                    maxima[bucket][key] = maxima[bucket].get(key, 0) + val
        elif q["group"] == "ability":
            maxima["ability"][q["dim"]] = maxima["ability"].get(q["dim"], 0) + 4
    return maxima


_MAX_CACHE: dict[int, dict[str, dict[str, float]]] = {}


def _max_for(questions) -> dict[str, dict[str, float]]:
    """按题库缓存归一化基准：两版题量不同，不能用同一套最大值。"""
    key = id(questions)
    if key not in _MAX_CACHE:
        _MAX_CACHE[key] = _dimension_max(questions)
    return _MAX_CACHE[key]


_MAX = _max_for(choice_quiz.QUESTIONS)


def _normalise(raw: dict[str, float], maxima: dict[str, float]) -> dict[str, int]:
    return {
        key: int(round(raw.get(key, 0) / maxima[key] * 100)) if maxima.get(key) else 0
        for key in maxima
    }


def _riasec(clusters: dict[str, int]) -> dict[str, float]:
    """12 个兴趣簇 → 六型相对强度（最强项为 100）。

    这里**不做跨簇加权平均**：簇分本身已是「占该维度理论峰的百分比」，
    再平均会被人人都不选的簇稀释成个位数，六型全挤在 20 分附近看不出差异。
    改成加权求和后按最大值拉满，语义是「你最强的那一型」而不是「你绝对有多像」。
    """
    raw = {code: 0.0 for code in RIASEC_NAMES}
    for cluster, value in clusters.items():
        for code, weight in RIASEC_CLUSTERS.get(cluster, {}).items():
            raw[code] += value * weight
    peak = max(raw.values(), default=0.0)
    if peak <= 0:
        return {code: 0.0 for code in RIASEC_NAMES}
    return {code: round(value / peak * 100, 1) for code, value in raw.items()}


def _riasec_summary(scores: dict[str, float]) -> dict:
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top = [code for code, value in ranked[:2] if value > 0]
    label = "+".join(top) if top else ""
    names = [RIASEC_NAMES[c][0] for c in top]
    return {
        "code": label,
        "names": names,
        "title": "＋".join(names) if names else "尚未成形",
        "hint": RIASEC_NAMES[top[0]][1] if top else "答题太少，还看不出稳定的兴趣类型",
        "ranked": [{"code": c, "name": RIASEC_NAMES[c][0], "score": v} for c, v in ranked],
    }


def _tendency(subject_scores: dict[str, int], tech_allowed: bool | None = None) -> dict:
    """首选科目倾向：物理侧 vs 历史侧。

    高一最迟一个月内就要面对的第一个真实决策不是「三门怎么搭」，
    而是 3+1+2 里的那个「1」——物理还是历史。这里把它单独算出来。
    「技术」只有浙江能选，默认按有没有分数推断；调用方能给出确切省份就传
    ``tech_allowed``，避免「浙江学生技术考了 0 分」被误判成不可选。
    """
    if tech_allowed is None:
        tech_allowed = subject_scores.get("technology", 0) > 0
    physics_parts = [(k, w) for k, w in TRACK_PHYSICS if k != "technology" or tech_allowed]
    history_parts = list(TRACK_HISTORY)

    def blend(parts: list[tuple[str, float]]) -> float:
        total_w = sum(w for _, w in parts) or 1.0
        return sum(subject_scores.get(k, 0) * w for k, w in parts) / total_w

    physics = round(blend(physics_parts), 1)
    history = round(blend(history_parts), 1)
    diff = round(physics - history, 1)
    gap = abs(diff)

    if gap < 8:
        label, strength = "文理均衡", "不明显"
        note = "两边都不排斥，建议优先选物理——3+1+2 里选物理能报的专业是历史的 4 倍多。"
    elif diff > 0:
        label = "偏理科"
        strength = "明显" if gap >= 18 else "轻度"
        note = "物理侧更强，首选物理；再选两门建议在化学、生物、地理里挑你学得动且赋分不吃亏的。"
    else:
        label = "偏文科"
        strength = "明显" if gap >= 18 else "轻度"
        note = "历史侧更强，首选历史；但要提前接受可报专业面窄，志愿填报需要更精准。"

    return {
        "physics": physics,
        "history": history,
        "diff": diff,
        "label": label,
        "strength": strength,
        "note": note,
    }


def score(answers: dict, questions=None) -> dict:
    """问卷答案 → 四个维度的 0-100 画像。"""
    bank = questions or choice_quiz.QUESTIONS
    raw: dict[str, dict[str, float]] = {
        "subject": {}, "ability": {}, "cluster": {},
    }
    values: dict[str, float] = {k: 0.0 for k in choice_quiz.VALUE_KEYS}

    for q in bank:
        value = answers.get(q["id"])
        if value is None:
            continue
        if q["kind"] == "single":
            chosen = next((o for o in q["options"] if o["id"] == value), None)
            if not chosen:
                continue
            for bucket in ("subject", "ability", "cluster"):
                for key, val in chosen["scores"].get(bucket, {}).items():
                    raw[bucket][key] = raw[bucket].get(key, 0) + val
            for key, val in chosen["scores"].get("value", {}).items():
                values[key] = values.get(key, 0) + val * 10
        else:
            num = int(value)
            contribution = (num - 1) * 100 / 4  # 1→0, 5→100
            if q["group"] == "ability":
                raw["ability"][q["dim"]] = raw["ability"].get(q["dim"], 0) + (num - 1)
            elif q["group"] == "value":
                values[q["dim"]] = values.get(q["dim"], 0) + contribution

    maxima = _max_for(bank)
    profile = {
        "subject": _normalise(raw["subject"], maxima["subject"]),
        "ability": _normalise(raw["ability"], maxima["ability"]),
        "cluster": _normalise(raw["cluster"], maxima["cluster"]),
        "value": {k: int(round(min(100, v))) for k, v in values.items()},
    }
    profile["top_subjects"] = sorted(
        profile["subject"].items(), key=lambda kv: kv[1], reverse=True
    )
    profile["top_clusters"] = sorted(
        profile["cluster"].items(), key=lambda kv: kv[1], reverse=True
    )
    profile["riasec"] = _riasec(profile["cluster"])
    profile["riasec_summary"] = _riasec_summary(profile["riasec"])
    profile["tendency"] = _tendency(profile["subject"])
    return profile


# --------------------------------------------------------------------------
# 组合推荐
# --------------------------------------------------------------------------
def _cluster_fit(combo: list[str], clusters: dict[str, int], majors: list[dict]) -> float:
    """该组合通向学生兴趣方向的程度。

    不取所有可报专业的平均（会被大量兴趣为 0 的专业稀释），而是看
    「学生最感兴趣的 3 个方向，这个组合能接住几个」：

        fit = 0.6 × 可报方向里的最高簇分 + 0.4 × 可报方向里前 3 名的均值
    """
    reachable: list[int] = []
    for cluster, value in clusters.items():
        if value <= 0:
            continue
        hit = False
        for item in majors:
            gid = subject_map.group_of_major(item["name"], item.get("category", ""), item.get("group", ""))
            if gid == "other" or GROUP_CLUSTER.get(gid) != cluster:
                continue
            if subjects.group_eligible(gid, combo):
                hit = True
                break
        if hit:
            reachable.append(value)
    if not reachable:
        return 0.0
    reachable.sort(reverse=True)
    best = reachable[0]
    top3 = sum(reachable[:3]) / min(3, len(reachable))
    return round(0.6 * best + 0.4 * top3, 1)


def _subject_fit(combo: list[str], subject_scores: dict[str, int]) -> float:
    names = {v: k for k, v in choice_quiz.SUBJECT_NAMES.items()}
    keys = [names[s] for s in combo if s in names]
    if not keys:
        return 0.0
    return round(sum(subject_scores.get(k, 0) for k in keys) / len(keys), 1)


def _coverage_score(ratio: float) -> float:
    """开方压缩：69.5% → 83.4，21.4% → 46.3，避免覆盖率一票否决。"""
    return round(100 * (ratio ** 0.5), 1)


def recommend_combos(profile: dict, province: str, majors: list[dict], *, top: int = 3) -> list[dict]:
    """按省份合法组合逐一打分，返回 Top N。"""
    options = subjects.combos(province)
    subject_names = [c["subjects"] if isinstance(c, dict) else c for c in options]
    ranked: list[dict] = []

    for combo in subject_names:
        cov = subjects.coverage(list(combo), [m["name"] for m in majors])
        sfit = _subject_fit(list(combo), profile["subject"])
        cfit = _cluster_fit(list(combo), profile["cluster"], majors)
        cov_score = _coverage_score(cov["majors_ratio"])
        total = round(0.45 * sfit + 0.35 * cfit + 0.20 * cov_score, 1)
        ranked.append({
            "subjects": list(combo),
            "score": total,
            "subject_fit": sfit,
            "cluster_fit": cfit,
            "coverage_ratio": cov["majors_ratio"],
            "coverage_majors": cov["majors_ok"],
            "coverage_groups": cov["groups_total"],
            "watch": COMBO_WATCH.get(tuple(combo), ""),
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top]


# --------------------------------------------------------------------------
# 专业推荐
# --------------------------------------------------------------------------
def _major_score(item: dict, profile: dict) -> tuple[float, dict]:
    gid = subject_map.group_of_major(item["name"], item.get("category", ""), item.get("group", ""))
    cluster = GROUP_CLUSTER.get(gid, "eng")
    cluster_score = profile["cluster"].get(cluster, 0)

    keys = GROUP_SUBJECTS.get(gid, ())
    subj_score = (
        sum(profile["subject"].get(k, 0) for k in keys) / len(keys) if keys else 50.0
    )

    value = profile["value"]
    bonus = 0.0
    if value.get("stability", 0) >= 60 and gid in {"education", "clinical", "public_security", "public_admin", "nursing"}:
        bonus += 6
    if value.get("salary", 0) >= 60 and gid in {"computer", "financial", "electronics", "automation"}:
        bonus += 6
    if value.get("research", 0) >= 60 and gid in {"math", "physics", "chemistry", "biology_sci", "basic_med", "clinical"}:
        bonus += 5
    if value.get("interest", 0) >= 70 and cluster_score >= 60:
        bonus += 4

    total = round(0.55 * cluster_score + 0.35 * subj_score + bonus, 1)
    detail = {
        "group": subjects.GROUP_INDEX[gid]["name"] if gid in subjects.GROUP_INDEX else "其他",
        "cluster": cluster,
        "cluster_name": choice_quiz.CLUSTER_NAMES[cluster],
        "cluster_score": cluster_score,
        "subject_score": round(subj_score, 1),
    }
    return total, detail


def recommend_majors(
    profile: dict, combo: list[str], majors: list[dict], *, top: int = 12, per_group: int = 2,
) -> list[dict]:
    """在给定组合下可报的专业里，按「兴趣簇 + 学科匹配 + 价值取向」排序。

    同一个专业类最多出 ``per_group`` 个（否则 12 条推荐可能全是计算机类），
    试验班 / 预科班不出现在推荐里——它们不是可填报的具体专业。
    """
    picked: list[dict] = []
    for item in majors:
        name = item["name"]
        if subject_map.is_exempt(name):
            continue
        gid = subject_map.group_of_major(name, item.get("category", ""), item.get("group", ""))
        if gid == "other" or not subjects.group_eligible(gid, combo):
            continue
        total, detail = _major_score(item, profile)
        picked.append({"name": name, "group_id": gid, "score": total, **detail})
    picked.sort(key=lambda x: x["score"], reverse=True)

    result: list[dict] = []
    seen: dict[str, int] = {}
    for row in picked:
        count = seen.get(row["group_id"], 0)
        if count >= per_group:
            continue
        seen[row["group_id"]] = count + 1
        result.append(row)
        if len(result) >= top:
            break
    return result


# --------------------------------------------------------------------------
# 组合推荐理由
# --------------------------------------------------------------------------
def explain(profile: dict, combo: dict) -> dict:
    """为组合生成 why / 优势学科 / 风险，给 AI 报告的素材。"""
    names = combo["subjects"]
    ranked = profile["top_subjects"]
    strengths = [choice_quiz.SUBJECT_NAMES[k] for k, v in ranked if k in {_k for _k in choice_quiz.SUBJECT_NAMES} and v >= 60][:3]
    why = (
        f"这个组合里你的学科倾向是「{'、'.join(names)}」，"
        f"学科契合度 {combo['subject_fit']}/100，专业匹配度 {combo['cluster_fit']}/100，"
        f"全国可报 {combo['coverage_majors']} 个专业、覆盖 {combo['coverage_groups']} 个专业类。"
    )
    if strengths:
        why += f"你的相对优势学科是{'、'.join(strengths)}。"
    return {
        "why": why,
        "strengths": strengths,
        "risk": combo.get("watch") or "未发现结构性风险，注意确认目标院校的具体选科要求。",
    }


def _restrict_profile(profile: dict, province: str) -> dict:
    """把该省选不了的科目清零。

    7 门里「技术」只有浙江能选；江苏学生看到「技术 85 分」只会困惑，
    更糟的是会以为那是个可选项。画像按省裁剪后再展示 / 喂给 AI。
    """
    pool = {subjects.SUBJECTS[name]["key"] for name in subjects.province_pool(province)}
    cleaned = {
        key: (profile["subject"].get(key, 0) if key in pool else 0)
        for key in choice_quiz.SUBJECT_KEYS
    }
    profile = dict(profile)
    profile["subject"] = cleaned
    profile["top_subjects"] = sorted(cleaned.items(), key=lambda kv: kv[1], reverse=True)
    profile["tendency"] = _tendency(cleaned, "technology" in pool)
    return profile


def build_report(answers: dict, province: str, majors: list[dict], *, top_combos: int = 3, top_majors: int = 12, edition: str = "simple") -> dict:
    """一次给全：画像 + 组合 + 专业，前端和 AI 都吃这一份。"""
    bank = choice_quiz.questions_for(edition)
    errors = choice_quiz.validate(answers, edition)
    if errors:
        return {"ok": False, "errors": errors}
    if province not in subjects.PROVINCES:
        return {"ok": False, "errors": [f"未知省份 {province!r}"]}

    profile = _restrict_profile(score(answers, bank), province)
    combos = recommend_combos(profile, province, majors, top=top_combos)
    best = combos[0]
    majors_top = recommend_majors(profile, best["subjects"], majors, top=top_majors)
    return {
        "ok": True,
        "province": province,
        "mode": subjects.PROVINCES[province]["mode"],
        "profile": profile,
        "tendency": profile["tendency"],
        "riasec": profile["riasec_summary"],
        "combos": [dict(c, **explain(profile, c)) for c in combos],
        "majors": majors_top,
        "meta": {
            "combos_available": len(subjects.combos(province)),
            "majors_total": len(majors),
            "edition": edition,
            "answered": len(answers),
        },
    }
