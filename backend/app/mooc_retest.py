"""专业的「二次检验」：试完先导课之后，用 3 道题判断还感不感兴趣。

这一步的逻辑很朴素 —— 先导课已经给出「这个专业到底学什么」，再用三道五级量表题
把「愿意投入 / 对内容好奇 / 抗劝退」三个信号量出来。均分 ≥4 建议深入，2–4 建议先
试课，<2 建议换专业。规则放在服务端，AI 只是把结论讲得更像人话。
"""

from __future__ import annotations

from . import mooc_data

SCALE = [
    {"value": 1, "label": "完全不是"},
    {"value": 2, "label": "基本不是"},
    {"value": 3, "label": "说不好"},
    {"value": 4, "label": "比较像"},
    {"value": 5, "label": "非常像"},
]

MIN = 1
MAX = 5


def _backbone_names(major: str) -> list[str]:
    try:
        backbone = mooc_data._backbone(major, limit=3)
    except Exception:  # 主干课缺失不该让整个二次检验挂掉
        return []
    names = []
    for course in backbone or []:
        name = course.get("name") or course.get("title") or ""
        if name and name not in names:
            names.append(name)
    return names


def questions(major: str) -> list[dict]:
    """三道题，题干里塞进这个专业真实的主干课名，避免空泛。"""
    name = (major or "").strip()
    if not name:
        raise ValueError("请先选一个专业")
    lessons = _backbone_names(name)
    sample = "、".join(f"《{item}》" for item in lessons[:2]) or "这个专业的入门课"
    return [
        {
            "id": "invest",
            "topic": "投入意愿",
            "title": f"如果周末空出两小时，我愿意用来弄懂「{name}」最基础的概念。",
            "hint": "想的是「我愿不愿意」，不是「我应不应该」。",
        },
        {
            "id": "curiosity",
            "topic": "内容好奇",
            "title": f"看到{sample}这样的课程名，我会想点进去看看它讲什么。",
            "hint": "先导课里哪一节让你走神了？回想那一节再打分。",
        },
        {
            "id": "resist",
            "topic": "抗劝退",
            "title": f"就算有人告诉我「{name}又难又不好找工作」，我还是想学。",
            "hint": "被劝退时还想学，才是真的想学。",
        },
    ]


def _pick(answers, key: str) -> int:
    value = answers.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"第「{key}」题需要一个 {MIN}–{MAX} 的整数")
    if value < MIN or value > MAX:
        raise ValueError(f"第「{key}」题的分数要在 {MIN}–{MAX} 之间")
    return int(round(value))


def evaluate(major: str, answers) -> dict:
    if not isinstance(answers, dict):
        raise ValueError("答案格式不对")
    name = (major or "").strip()
    if not name:
        raise ValueError("请先选一个专业")
    items = questions(name)
    scores = [(item, _pick(answers, item["id"])) for item in items]
    average = sum(score for _, score in scores) / len(scores)

    if average >= 4:
        verdict, title = "deep", "建议深入"
        advice = f"你对「{name}」的投入意愿和好奇心都在线。下一步别停在试听：找一门课完整跟完一周，再去看这个专业大二的核心课表。"
    elif average >= 2:
        verdict, title = "trial", "先试课"
        advice = f"兴趣有，但还没到「非它不可」。先按上面推荐的先导课完整听完一门（4–6 周），再回来重测一次。"
    else:
        verdict, title = "switch", "换个专业看看"
        advice = f"三道题都在低位，说明「{name}」更像是被名字吸引。回到专业列表，把相邻的两个专业各做一次二次检验。"

    weakest = min(scores, key=lambda pair: pair[1])
    return {
        "major": name,
        "score": round(average, 2),
        "verdict": verdict,
        "title": title,
        "advice": advice,
        "weakest": {"id": weakest[0]["id"], "topic": weakest[0]["topic"], "score": weakest[1]},
        "items": [
            {"id": item["id"], "topic": item["topic"], "title": item["title"], "score": score}
            for item, score in scores
        ],
        "scale": SCALE,
    }
