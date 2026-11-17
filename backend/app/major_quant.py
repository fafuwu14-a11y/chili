"""六维量化：给 56 个专业类各打一组 1–5 分，批量生成 821 条画像时用。

为什么要「量化」而不是逐条手填：821 个专业里，同一个专业类的几十个专业
课程结构、就业去向高度相似，逐条手填既写不完，也必然写出同一个专业类
两个专业分数打架这种硬伤。所以基准分按「专业类」给，只有明显偏离的
细分方向才用 KEYWORD_SCORES 修正。

六个维度都按 1–5 打，5 表示这一维最强：
- course_load 课业强度：课多、实验多、要背的多、学制长
- job_width   就业面：本科毕业能对口的岗位面有多宽
- salary      起薪：同届本科里的相对水位，不是绝对工资
- exam_need   考研必要：越高表示不读研越难走对口岗位
- civil_fit   考公适配：公务员招录里限这个专业的岗位多少
- startup_fit 创业友好：本科毕业创业或开店的现实可行度

分数是判断，不是统计。这里只是把判断显式化，让两条相似的专业不会给出
互相矛盾的分，也让人能指着某一维问「为什么是 4」。
"""

from __future__ import annotations

from .major_profile import SCORE_FIELDS, SCORE_LABELS

# 每个专业类的基准分。键是 major_catalog.meta() 里的 group id。
GROUP_SCORES: dict[str, dict[str, int]] = {
    "计算机": {"course_load": 4, "job_width": 5, "salary": 4, "exam_need": 4, "civil_fit": 4, "startup_fit": 4},
    "电子信息": {"course_load": 4, "job_width": 4, "salary": 4, "exam_need": 4, "civil_fit": 2, "startup_fit": 3},
    "自动化": {"course_load": 4, "job_width": 4, "salary": 4, "exam_need": 4, "civil_fit": 2, "startup_fit": 3},
    "电气": {"course_load": 4, "job_width": 4, "salary": 4, "exam_need": 3, "civil_fit": 3, "startup_fit": 2},
    "机械": {"course_load": 4, "job_width": 4, "salary": 3, "exam_need": 3, "civil_fit": 2, "startup_fit": 3},
    "土木建筑": {"course_load": 4, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 3, "startup_fit": 3},
    "材料": {"course_load": 4, "job_width": 3, "salary": 3, "exam_need": 5, "civil_fit": 1, "startup_fit": 2},
    "化工制药": {"course_load": 4, "job_width": 3, "salary": 2, "exam_need": 4, "civil_fit": 2, "startup_fit": 2},
    "能源动力": {"course_load": 4, "job_width": 4, "salary": 3, "exam_need": 3, "civil_fit": 2, "startup_fit": 2},
    "航空航天交通": {"course_load": 4, "job_width": 4, "salary": 4, "exam_need": 4, "civil_fit": 2, "startup_fit": 2},
    "环境安全": {"course_load": 3, "job_width": 2, "salary": 2, "exam_need": 4, "civil_fit": 3, "startup_fit": 2},
    "食品轻工": {"course_load": 3, "job_width": 3, "salary": 2, "exam_need": 3, "civil_fit": 2, "startup_fit": 4},
    "生医工程": {"course_load": 4, "job_width": 3, "salary": 3, "exam_need": 5, "civil_fit": 1, "startup_fit": 2},
    "资源矿业": {"course_load": 4, "job_width": 3, "salary": 4, "exam_need": 3, "civil_fit": 2, "startup_fit": 1},
    "农业工程": {"course_load": 3, "job_width": 3, "salary": 2, "exam_need": 4, "civil_fit": 2, "startup_fit": 3},
    "力学": {"course_load": 4, "job_width": 2, "salary": 3, "exam_need": 5, "civil_fit": 1, "startup_fit": 2},
    "数学": {"course_load": 4, "job_width": 2, "salary": 3, "exam_need": 5, "civil_fit": 2, "startup_fit": 2},
    "物理": {"course_load": 4, "job_width": 2, "salary": 2, "exam_need": 5, "civil_fit": 1, "startup_fit": 2},
    "化学": {"course_load": 4, "job_width": 2, "salary": 2, "exam_need": 5, "civil_fit": 2, "startup_fit": 2},
    "生物": {"course_load": 4, "job_width": 2, "salary": 2, "exam_need": 5, "civil_fit": 1, "startup_fit": 2},
    "地理": {"course_load": 3, "job_width": 2, "salary": 2, "exam_need": 4, "civil_fit": 2, "startup_fit": 2},
    "心理学": {"course_load": 3, "job_width": 2, "salary": 2, "exam_need": 4, "civil_fit": 2, "startup_fit": 3},
    "农林": {"course_load": 3, "job_width": 2, "salary": 2, "exam_need": 4, "civil_fit": 3, "startup_fit": 4},
    "临床医学": {"course_load": 5, "job_width": 3, "salary": 3, "exam_need": 5, "civil_fit": 3, "startup_fit": 1},
    "口腔医学": {"course_load": 5, "job_width": 3, "salary": 5, "exam_need": 4, "civil_fit": 2, "startup_fit": 5},
    "中医学": {"course_load": 4, "job_width": 3, "salary": 3, "exam_need": 4, "civil_fit": 3, "startup_fit": 3},
    "药学": {"course_load": 4, "job_width": 3, "salary": 3, "exam_need": 4, "civil_fit": 2, "startup_fit": 3},
    "护理康复": {"course_load": 3, "job_width": 4, "salary": 2, "exam_need": 3, "civil_fit": 3, "startup_fit": 2},
    "公卫医技": {"course_load": 3, "job_width": 3, "salary": 2, "exam_need": 3, "civil_fit": 4, "startup_fit": 2},
    "基础医学": {"course_load": 4, "job_width": 1, "salary": 2, "exam_need": 5, "civil_fit": 1, "startup_fit": 1},
    "金融": {"course_load": 3, "job_width": 4, "salary": 4, "exam_need": 4, "civil_fit": 3, "startup_fit": 3},
    "经济学": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 4, "civil_fit": 4, "startup_fit": 2},
    "经贸": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 3, "startup_fit": 3},
    "财政税收": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 5, "startup_fit": 2},
    "会计财务": {"course_load": 3, "job_width": 4, "salary": 3, "exam_need": 3, "civil_fit": 5, "startup_fit": 3},
    "工商管理": {"course_load": 2, "job_width": 3, "salary": 2, "exam_need": 3, "civil_fit": 3, "startup_fit": 3},
    "公共管理": {"course_load": 2, "job_width": 2, "salary": 2, "exam_need": 3, "civil_fit": 5, "startup_fit": 2},
    "信管": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 3, "startup_fit": 3},
    "物流电商": {"course_load": 3, "job_width": 4, "salary": 3, "exam_need": 3, "civil_fit": 2, "startup_fit": 4},
    "旅游服务": {"course_load": 2, "job_width": 3, "salary": 2, "exam_need": 2, "civil_fit": 2, "startup_fit": 4},
    "法学": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 4, "civil_fit": 5, "startup_fit": 3},
    "社会学": {"course_load": 2, "job_width": 3, "salary": 2, "exam_need": 3, "civil_fit": 4, "startup_fit": 3},
    "政治思政": {"course_load": 2, "job_width": 2, "salary": 2, "exam_need": 4, "civil_fit": 5, "startup_fit": 1},
    "中文": {"course_load": 2, "job_width": 2, "salary": 2, "exam_need": 4, "civil_fit": 5, "startup_fit": 2},
    "外语": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 2, "startup_fit": 2},
    "新闻传播": {"course_load": 2, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 3, "startup_fit": 3},
    "历史学": {"course_load": 2, "job_width": 1, "salary": 1, "exam_need": 4, "civil_fit": 4, "startup_fit": 1},
    "哲学": {"course_load": 2, "job_width": 1, "salary": 1, "exam_need": 4, "civil_fit": 3, "startup_fit": 1},
    "教育学": {"course_load": 2, "job_width": 3, "salary": 2, "exam_need": 3, "civil_fit": 5, "startup_fit": 2},
    "体育": {"course_load": 2, "job_width": 3, "salary": 2, "exam_need": 3, "civil_fit": 4, "startup_fit": 4},
    "音乐表演": {"course_load": 2, "job_width": 2, "salary": 2, "exam_need": 3, "civil_fit": 2, "startup_fit": 3},
    "艺术设计": {"course_load": 2, "job_width": 3, "salary": 3, "exam_need": 2, "civil_fit": 1, "startup_fit": 4},
    "美术": {"course_load": 2, "job_width": 2, "salary": 2, "exam_need": 3, "civil_fit": 1, "startup_fit": 4},
    "艺术管理": {"course_load": 2, "job_width": 2, "salary": 2, "exam_need": 3, "civil_fit": 2, "startup_fit": 3},
    "other": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 3, "startup_fit": 3},
    "trial": {"course_load": 3, "job_width": 3, "salary": 3, "exam_need": 3, "civil_fit": 3, "startup_fit": 3},
}

# 同一个专业类里，这几种细分方向和基准分明显不同，单独修正。
# 键是专业名里出现的关键词，按长度倒序匹配，命中即叠加（不是覆盖）。
KEYWORD_SCORES: dict[str, dict[str, int]] = {
    "人工智能": {"exam_need": 1},
    "信息安全": {"civil_fit": 1},
    "网络空间安全": {"civil_fit": 1},
    "软件工程": {"exam_need": -1},
    "数据科学": {"exam_need": 1},
    "物联网": {"exam_need": -1},
    "口腔医学": {"salary": 1, "startup_fit": 1},
    "麻醉学": {"salary": 1},
    "医学影像": {"salary": 1},
    "护理": {"exam_need": -1},
    "金融工程": {"exam_need": 1, "startup_fit": 1},
    "保险学": {"salary": -1},
    "会计学": {"civil_fit": 1},
    "审计学": {"civil_fit": 1},
    "财务管理": {"salary": -1},
    "汉语言文学": {"startup_fit": -1},
    "秘书学": {"civil_fit": 1},
    "英语": {"job_width": 1},
    "日语": {"job_width": -1},
    "建筑学": {"course_load": 1, "job_width": -1},
    "城乡规划": {"job_width": -1},
    "风景园林": {"startup_fit": 1},
    "车辆工程": {"salary": 1},
    "机器人工程": {"exam_need": 1},
    "智能制造": {"salary": 1},
    "集成电路": {"exam_need": 1, "salary": 1},
    "微电子": {"exam_need": 1, "salary": 1},
    "新能源": {"salary": 1},
}

# 分数到说法的映射，用于 explain()：让每个分数都能被翻译成一句人话。
_BANDS: dict[str, tuple[str, ...]] = {
    "course_load": ("很轻", "偏轻", "中等", "偏重", "最重"),
    "job_width": ("很窄", "偏窄", "中等", "较宽", "最宽"),
    "salary": ("最低", "偏低", "中等", "偏高", "最高"),
    "exam_need": ("不必要", "较宽松", "看情况", "较必要", "几乎必需"),
    "civil_fit": ("几乎无", "很少", "一般", "较多", "最多"),
    "startup_fit": ("不适合", "偏难", "一般", "较友好", "很友好"),
}

DEFAULT_GROUP = "other"


def _clamp(value: int) -> int:
    return max(1, min(5, value))


def keyword_bonus(name: str) -> dict[str, int]:
    """按关键词累加修正；长词优先，避免「计算机」先于「计算机科学与技术」命中。"""
    bonus: dict[str, int] = {}
    if not name:
        return bonus
    for keyword in sorted(KEYWORD_SCORES, key=len, reverse=True):
        if keyword in name:
            for key, delta in KEYWORD_SCORES[keyword].items():
                bonus[key] = bonus.get(key, 0) + delta
    return bonus


def scores_for(name: str, group_id: str) -> dict[str, int]:
    """一个专业的六维分 = 专业类基准分 + 关键词修正，最后夹到 1–5。"""
    base = GROUP_SCORES.get(group_id) or GROUP_SCORES[DEFAULT_GROUP]
    bonus = keyword_bonus(name)
    return {key: _clamp(base[key] + bonus.get(key, 0)) for key in SCORE_FIELDS}


def explain(name: str, group_id: str) -> dict:
    """把六维分翻译成人话，方便前端展示「为什么是这个分」。"""
    scores = scores_for(name, group_id)
    rules = []
    for key, label in SCORE_LABELS:
        score = scores[key]
        rules.append({"key": key, "label": label, "score": score, "text": _BANDS[key][score - 1]})
    return {
        "name": name,
        "group_id": group_id if group_id in GROUP_SCORES else DEFAULT_GROUP,
        "scores": scores,
        "rules": rules,
    }
