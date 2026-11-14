"""功能 01-B：专业方向细分（把「计算机类」落到「计算机科学与技术 / 软件工程 / 信息安全」）。

问卷的大类得分只能回答"哪一类适合你"，回答不了"这一类里该学哪个"。
这里补一层方向坐标：

    6 个方向轴（动手实作 / 代码与系统 / 探究原理 / 与人打交道 / 规则与细节 / 创作表达）
    ↓ 方向题 d01–d06（五级量表，只加在标准与深度两套卷子里）
    考生的方向向量
    ↓ 与每个具体专业的方向向量做余弦
    方向匹配度 0–1
    ↓ 大类得分 × (0.6 + 0.4 × 方向匹配度)
    具体专业的细分得分

专业方向向量用两级拼装，保证 855 个专业一个不漏：

    第一级  GROUP_DIRECTIONS   56 个专业类各给一个基准向量（覆盖率 100%）
    第二级  KEYWORD_SHIFTS     按专业名关键词做类内修正（软件偏工程、安全偏规则…）

只用手工维护 21 个大类的方向画像（`PROFILE_TO_GROUP`），再借专业类基准向量扩散，
比逐个手写 855 条省事得多，而且新增专业名会自动落到对应专业类上。
"""

from __future__ import annotations

from functools import lru_cache

from . import major_catalog

# --------------------------------------------------------------------------
# 方向轴
# --------------------------------------------------------------------------
DIRECTION_AXES = {
    "build": "动手实作",
    "code": "代码与系统",
    "theory": "探究原理",
    "people": "与人打交道",
    "rule": "规则与细节",
    "create": "创作表达",
}

# 方向题的题号前缀，matcher 用它区分方向题与兴趣题
QUESTION_PREFIX = "d"

# --------------------------------------------------------------------------
# 方向题：五级量表，只加在 standard / deep 末尾
# --------------------------------------------------------------------------
# 权重落在方向轴上，reverse=True 表示越认同越不偏这个方向。
DIRECTION_QUESTIONS = (
    {
        "id": "d01",
        "text": "比起在纸上推演，我更愿意亲手把东西做出来、让它真的跑起来。",
        "w": {"build": 0.8, "code": 0.4},
    },
    {
        "id": "d02",
        "text": "我愿意花很长时间跟代码、系统、数据打交道，把想法变成能用的程序。",
        "w": {"code": 0.9, "theory": 0.3},
    },
    {
        "id": "d03",
        "text": "一个结论如果说不清来龙去脉，我会不放心，非要查清背后的原理。",
        "w": {"theory": 0.9, "code": 0.2},
    },
    {
        "id": "d04",
        "text": "我更喜欢和人一起把事情推动起来，而不是一个人闷头做。",
        "w": {"people": 0.9, "create": 0.2},
    },
    {
        "id": "d05",
        "text": "我喜欢规则清楚、能按流程一条条核对的工作，讨厌含糊。",
        "w": {"rule": 0.9},
    },
    {
        "id": "d06",
        "text": "我希望工作里需要一点审美和表达，而不只是照流程办事。",
        "w": {"create": 0.9, "people": 0.2},
    },
)


# --------------------------------------------------------------------------
# 21 个大类 → 专业目录里的专业类 id
# --------------------------------------------------------------------------
# 问卷的 MAJOR_PROFILES 用 21 个方向做画像，专业目录用 56 个专业类，
# 这张表把两边接上（计算机科学与技术、软件工程都落在「计算机类」）。
PROFILE_TO_GROUP = {
    "计算机科学与技术": "计算机",
    "软件工程": "计算机",
    "电子信息类": "电子信息",
    "自动化类": "自动化",
    "机械类": "机械",
    "能源动力类": "能源动力",
    "建筑类": "土木建筑",
    "数学类": "数学",
    "临床医学": "临床医学",
    "口腔医学": "口腔医学",
    "金融学类": "金融",
    "经济学类": "经济学",
    "会计学": "会计财务",
    "法学": "法学",
    "汉语言文学": "中文",
    "新闻传播学类": "新闻传播",
    "英语": "外语",
    "历史学类": "历史学",
    "教育学类": "教育学",
    "行政管理": "公共管理",
    "社会学类": "社会学",
}


# --------------------------------------------------------------------------
# 专业类基准向量（0–1，不必归一化，余弦会处理）
# --------------------------------------------------------------------------
GROUP_DIRECTIONS = {
    # 工学
    "计算机": {"code": 1.0, "theory": 0.55, "rule": 0.3},
    "航空航天交通": {"build": 0.95, "theory": 0.45, "code": 0.3},
    "自动化": {"build": 0.85, "code": 0.7, "theory": 0.4},
    "电子信息": {"code": 0.75, "build": 0.7, "theory": 0.6},
    "土木建筑": {"build": 0.9, "create": 0.55},
    "材料": {"build": 0.7, "theory": 0.75},
    "能源动力": {"build": 0.9, "theory": 0.4},
    "机械": {"build": 1.0, "code": 0.3},
    "化工制药": {"build": 0.6, "theory": 0.7, "rule": 0.35},
    "食品轻工": {"build": 0.5, "rule": 0.5, "theory": 0.4},
    "环境安全": {"rule": 0.7, "theory": 0.5, "build": 0.4},
    "资源矿业": {"build": 0.95, "theory": 0.3},
    "生医工程": {"build": 0.7, "theory": 0.7, "people": 0.35},
    "电气": {"build": 0.9, "code": 0.4, "theory": 0.4},
    # 理学
    "地理": {"theory": 0.85, "build": 0.3},
    "生物": {"theory": 0.95, "build": 0.4},
    "数学": {"theory": 1.0, "code": 0.4},
    "化学": {"theory": 0.9, "build": 0.5},
    "物理": {"theory": 1.0, "build": 0.4},
    "心理学": {"people": 0.8, "theory": 0.75},
    "力学": {"theory": 0.95, "build": 0.5},
    # 医学
    "护理康复": {"people": 0.9, "rule": 0.6},
    "临床医学": {"people": 0.75, "rule": 0.65, "theory": 0.4},
    "中医学": {"people": 0.7, "theory": 0.55, "rule": 0.4},
    "药学": {"theory": 0.7, "rule": 0.6, "build": 0.3},
    "公卫医技": {"rule": 0.75, "theory": 0.5},
    "口腔医学": {"build": 0.6, "people": 0.6, "rule": 0.5},
    "基础医学": {"theory": 0.95},
    # 经济学
    "金融": {"rule": 0.7, "people": 0.6, "theory": 0.45},
    "经济学": {"theory": 0.85, "rule": 0.5, "people": 0.4},
    "经贸": {"people": 0.75, "rule": 0.5, "theory": 0.3},
    "财政税收": {"rule": 0.9, "theory": 0.45},
    # 管理学
    "公共管理": {"people": 0.85, "rule": 0.6},
    "物流电商": {"rule": 0.6, "people": 0.5, "code": 0.45},
    "会计财务": {"rule": 1.0, "theory": 0.3},
    "工商管理": {"people": 0.9, "rule": 0.4},
    "信管": {"code": 0.75, "rule": 0.6, "people": 0.4},
    "旅游服务": {"people": 1.0, "create": 0.3},
    # 文学
    "外语": {"people": 0.7, "create": 0.65},
    "新闻传播": {"create": 0.9, "people": 0.7},
    "中文": {"create": 0.9, "theory": 0.5},
    # 法学
    "政治思政": {"rule": 0.7, "theory": 0.65, "people": 0.5},
    "法学": {"rule": 1.0, "people": 0.5},
    "社会学": {"people": 0.85, "theory": 0.7},
    # 教育学
    "教育学": {"people": 1.0, "create": 0.4},
    "体育": {"people": 0.8, "build": 0.45},
    # 历史学·哲学
    "历史学": {"theory": 0.85, "create": 0.6},
    "哲学": {"theory": 1.0, "create": 0.5},
    # 农学
    "农林": {"build": 0.6, "theory": 0.6},
    "农业工程": {"build": 0.75, "code": 0.3, "theory": 0.4},
    # 艺术学
    "音乐表演": {"create": 1.0, "people": 0.5},
    "艺术设计": {"create": 1.0, "build": 0.4},
    "美术": {"create": 1.0},
    "艺术管理": {"create": 0.6, "people": 0.7},
    # 其他 / 试验班：不知道学什么，给一个弱中性向量，靠大类得分决定排序
    "other": {"theory": 0.4, "people": 0.4},
    "trial": {"theory": 0.4, "code": 0.3},
}

# 目录里没登记的专业类，退回这个中性向量
_NEUTRAL = {"theory": 0.4, "people": 0.4}


# --------------------------------------------------------------------------
# 类内修正：专业名关键词 → 方向轴加减
# --------------------------------------------------------------------------
# 顺序有意义：先匹配更长的词（「信息安全」要在「信息」之前），命中即叠加。
KEYWORD_SHIFTS = (
    ("中外合作", {"people": 0.05}),
    ("试验班", {"theory": 0.2, "code": 0.15}),
    ("信息安全", {"rule": 0.35, "code": 0.1}),
    ("网络空间安全", {"rule": 0.35, "code": 0.1}),
    ("人工智能", {"theory": 0.3, "code": 0.15}),
    ("数据科学", {"rule": 0.2, "code": 0.2, "theory": 0.1}),
    ("大数据", {"rule": 0.2, "code": 0.2}),
    ("软件", {"code": 0.25, "build": 0.1}),
    ("物联网", {"build": 0.2, "code": 0.15}),
    ("智能", {"code": 0.15, "theory": 0.15}),
    ("机器人", {"build": 0.25, "code": 0.15}),
    ("芯片", {"theory": 0.2, "build": 0.15}),
    ("集成电路", {"theory": 0.2, "build": 0.2}),
    ("通信", {"code": 0.15, "build": 0.15}),
    ("土木", {"build": 0.2}),
    ("建筑", {"create": 0.2, "build": 0.1}),
    ("城乡规划", {"create": 0.25, "people": 0.2}),
    ("风景园林", {"create": 0.3}),
    ("工业设计", {"create": 0.3, "build": 0.15}),
    ("设计", {"create": 0.25}),
    ("会计", {"rule": 0.3}),
    ("审计", {"rule": 0.35}),
    ("财务", {"rule": 0.3}),
    ("税收", {"rule": 0.3}),
    ("统计", {"theory": 0.25, "code": 0.15}),
    ("经济", {"theory": 0.15, "rule": 0.1}),
    ("金融", {"rule": 0.1, "people": 0.1}),
    ("管理", {"people": 0.2, "rule": 0.1}),
    ("市场营销", {"people": 0.3}),
    ("人力资源", {"people": 0.35}),
    ("教育", {"people": 0.25}),
    ("心理", {"people": 0.2, "theory": 0.15}),
    ("护理", {"people": 0.25}),
    ("康复", {"people": 0.2, "build": 0.1}),
    ("法", {"rule": 0.2}),
    ("新闻", {"create": 0.25, "people": 0.15}),
    ("传播", {"create": 0.2, "people": 0.15}),
    ("汉语言", {"create": 0.25, "theory": 0.15}),
    ("历史", {"theory": 0.2, "create": 0.15}),
    ("哲学", {"theory": 0.25}),
    ("数学", {"theory": 0.3}),
    ("物理", {"theory": 0.3}),
    ("化学", {"theory": 0.25, "build": 0.1}),
    ("生物", {"theory": 0.25}),
    ("地理", {"theory": 0.2}),
    ("环境", {"rule": 0.15, "theory": 0.1}),
    ("食品", {"rule": 0.15, "build": 0.1}),
    ("能源", {"build": 0.2}),
    ("电气", {"build": 0.25}),
    ("机械", {"build": 0.25}),
    ("材料", {"build": 0.15, "theory": 0.1}),
    ("化工", {"theory": 0.15, "build": 0.1}),
    ("制药", {"theory": 0.15, "rule": 0.15}),
    ("口腔", {"build": 0.15, "people": 0.1}),
    ("中医", {"theory": 0.15, "people": 0.1}),
    ("临床", {"people": 0.15, "rule": 0.1}),
    ("药学", {"theory": 0.15, "rule": 0.15}),
    ("体育", {"build": 0.15, "people": 0.15}),
    ("音乐", {"create": 0.3}),
    ("美术", {"create": 0.3}),
    ("表演", {"create": 0.3, "people": 0.15}),
    ("农林", {"build": 0.1, "theory": 0.1}),
    ("动物", {"build": 0.15, "theory": 0.1}),
    ("植物", {"theory": 0.15, "build": 0.1}),
    ("工程", {"build": 0.12}),
    ("科学", {"theory": 0.12}),
    ("技术", {"build": 0.08, "code": 0.08}),
)

# 常见专业的一句话补充（结果卡片上多一句人话，缺失不报错）
MAJOR_NOTES = {
    "计算机科学与技术": "偏底层原理与系统，读研面最宽，也能直接就业。",
    "软件工程": "偏工程交付，代码量大、项目多，考研可选面略窄于计科。",
    "信息安全": "偏攻防与合规，进安全岗、政企信息部门更对口。",
    "人工智能": "偏算法与模型，本科阶段数学要求高，读研比例高。",
    "数据科学与大数据技术": "偏数据链路与业务分析，统计和工程都要碰。",
    "电子信息工程": "硬件与信号为主，通信、芯片、嵌入式都能走。",
    "自动化": "控制理论与嵌入式结合，工业现场和机器人方向都吃。",
    "机械设计制造及其自动化": "结构设计、工艺和产线，动手与制图能力吃重。",
    "土木工程": "结构、施工与管理，项目周期长、出差多。",
    "电气工程及其自动化": "电力系统与强电方向，电网、能源企业是主要去处。",
    "临床医学": "五年起步加规培，职业确定性强，但时间成本高。",
    "口腔医学": "手上功夫与医学知识并重，就业和收入都比较稳。",
    "护理学": "临床一线为主，倒班多，需求量大。",
    "药学": "研发、注册、临床监查三条路，本科研发岗偏少。",
    "金融学": "看学校与地域，投研、银行、券商分层明显。",
    "经济学": "偏理论，读研后进研究机构、政策部门更常见。",
    "会计学": "规则清晰、路径明确，考证是绕不开的一关。",
    "法学": "背得多、写得多，法考和实习决定起点。",
    "汉语言文学": "读书写作是日常，考编、媒体、教育都能走。",
    "新闻传播学": "采访、拍摄、运营并重，节奏快、看作品。",
    "英语": "语言是工具，配上另一门技能才好用。",
    "教育学": "跟人打交道为主，稳定、有寒暑假是主要吸引力。",
    "行政管理": "偏公共事务，考公考编的对口面比较宽。",
    "社会学": "做调研、看社会，继续深造的比例不低。",
    "心理学": "咨询、用户研究、教育都需要，读研比例高。",
    "数学与应用数学": "纯理论训练，转金融、算法、科研都留了后路。",
    "历史学": "大量阅读与史料整理，读研和考编是常见去向。",
}


# --------------------------------------------------------------------------
# 对外函数
# --------------------------------------------------------------------------
def questions() -> tuple[dict, ...]:
    """方向题题库（quiz_data 拼装问卷时用）。"""
    return DIRECTION_QUESTIONS


def axes_table() -> list[dict]:
    return [{"key": key, "label": label} for key, label in DIRECTION_AXES.items()]


def group_direction(group_id: str) -> dict[str, float]:
    """专业类基准向量。未知专业类退回中性向量。"""
    base = GROUP_DIRECTIONS.get(group_id)
    if base is None:
        base = _NEUTRAL
    return dict(base)


@lru_cache(maxsize=2048)
def direction_of(major: str, group_id: str) -> tuple[tuple[str, float], ...]:
    """一个专业的方向向量：专业类基准 + 专业名关键词修正。

    返回元组而不是 dict，是为了配合 lru_cache（dict 不可哈希）。
    """
    vector = group_direction(group_id)
    name = major or ""
    for keyword, shifts in KEYWORD_SHIFTS:
        if keyword and keyword in name:
            for axis, delta in shifts.items():
                vector[axis] = vector.get(axis, 0.0) + delta
    # 夹到 0–1.2：关键词叠加可能把某个轴推到 1 以上，留一点空间给余弦
    cleaned = {axis: round(max(0.0, min(value, 1.2)), 4) for axis, value in vector.items()}
    return tuple(sorted(cleaned.items()))


def vector_of(major: str, group_id: str) -> dict[str, float]:
    return dict(direction_of(major, group_id))


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    """方向向量余弦，落在 0–1。任一向量为空时返回 0。"""
    keys = set(left) | set(right)
    dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in keys)
    norm_left = sum(value * value for value in left.values()) ** 0.5
    norm_right = sum(value * value for value in right.values()) ** 0.5
    if norm_left <= 1e-9 or norm_right <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_left * norm_right)))


def score_answers(answers: dict) -> dict | None:
    """把方向题答案折成考生方向向量。

    返回 {"vector": {...}, "answered": n, "peak": 轴名}；一题没答或全部选「说不好」时返回 None。
    """
    totals = {key: 0.0 for key in DIRECTION_AXES}
    answered = 0
    for question in DIRECTION_QUESTIONS:
        raw = answers.get(question["id"])
        value = _level(raw)
        if value is None:
            continue
        answered += 1
        delta = (value - 3) / 2.0
        if question.get("reverse"):
            delta = -delta
        for axis, weight in question.get("w", {}).items():
            totals[axis] += weight * delta

    positive = {key: max(0.0, value) for key, value in totals.items()}
    peak_value = max(positive.values()) if positive else 0.0
    if peak_value <= 1e-6:
        return None
    return {
        "vector": {key: round(value / peak_value, 4) for key, value in positive.items()},
        "answered": answered,
        "peak": max(positive, key=lambda key: positive[key]),
    }


def diff_note(major: str, group_id: str, group_name: str = "") -> str:
    """这个专业比它所在的专业类「更偏哪一侧」，用于结果页的差异说明。"""
    base = group_direction(group_id)
    vector = vector_of(major, group_id)
    deltas = [
        (vector.get(axis, 0.0) - base.get(axis, 0.0), axis)
        for axis in DIRECTION_AXES
    ]
    deltas.sort(reverse=True)
    best_delta, best_axis = deltas[0]
    label = DIRECTION_AXES[best_axis]
    scope = f"「{group_name}」" if group_name else "同类专业"
    if best_delta <= 0.02:
        # 类内差异不明显，就说它最突出的一面
        top_axis = max(DIRECTION_AXES, key=lambda axis: vector.get(axis, 0.0))
        return f"方向和{scope}整体基本一致，更看重「{DIRECTION_AXES[top_axis]}」。"
    return f"比{scope}整体更偏「{label}」这一侧。"


def majors_in_group(group_id: str, limit: int = 60, collapse_variants: bool = True) -> list[dict]:
    """专业类下的具体专业（按招生规模降序）。

    collapse_variants：投档表里同时存在「软件工程」和「软件工程技术」（职业本科）这类
    同根变体，在这里把带后缀的重复项折掉，免得结果页第一名是个没人听说的变体名。
    """
    try:
        result = major_catalog.search(group=group_id, limit=limit)
    except Exception:
        return []
    items = result["items"]
    # 专业类本身（「计算机类」「自动化类」）也会作为条目出现在投档表里，它不是专业
    items = [item for item in items if not item.get("is_group")]
    if collapse_variants:
        names = {item["name"] for item in items}
        items = [
            item
            for item in items
            if not is_variant(item["name"], names)
            # 投档表还混了职业本科/专科的专业名（现代通信工程、物联网应用技术、
            # 航空智能制造技术…）：名字以「技术/工程」结尾且招生单元很少。
            # 本科专业里以这两个词结尾的（计算机科学与技术、密码科学与技术）
            # 招生规模都远大于这个门槛，所以不会误伤。
            and not (item["count"] < 40 and item["name"].endswith(("技术", "工程")))
        ]
    return items


VARIANT_SUFFIXES = ("技术", "工程")


def is_variant(name: str, siblings: set[str]) -> bool:
    """「软件工程技术」这类变体：去掉尾部两个字后同组里已经有同名专业。"""
    if len(name) <= 4:
        return False
    for suffix in VARIANT_SUFFIXES:
        if name.endswith(suffix) and name[: -len(suffix)] in siblings:
            return True
    return False


def note_of(major: str) -> str:
    return MAJOR_NOTES.get(major, "")


def _level(raw) -> int | None:
    """答案归一成 1–5；越界或非数字当成没答。"""
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if 1 <= value <= 5:
        return value
    return None
