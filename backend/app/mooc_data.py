"""专业 MOOC 先导课目录与推荐（功能 04）。

两套课程来源：
1. 人工整理的 40 门口碑课（平台名真实、链接指向平台搜索页，不会 404），
   有评分和学习人数；
2. 从 736 个专业画像的主干课反推出来的课程目录（course_catalog.json），
   覆盖全部专业，带学科通用知识点。

推荐分两段：先列本专业的主干课（学什么），再补平台口碑课（去哪学）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

DATA = Path(__file__).resolve().parent.parent / "data"
CATALOG_PATH = DATA / "course_catalog.json"

PLATFORMS = {
    "中国大学MOOC": "https://www.icourse163.org/search.htm?search=",
    "学堂在线": "https://www.xuetangx.com/search?query=",
    "B站": "https://search.bilibili.com/all?keyword=",
    "网易公开课": "https://open.163.com/search?keyword=",
}

# 每个专业方向的关键词，用于标题/标签的模糊命中
MAJOR_KEYWORDS = {
    "计算机科学与技术": ["编程", "Python", "算法", "数据结构", "代码"],
    "软件工程": ["编程", "软件", "工程化", "项目", "代码"],
    "电子信息类": ["电路", "信号", "电子", "通信", "硬件"],
    "自动化类": ["控制", "自动化", "机器人", "嵌入式"],
    "临床医学": ["医学", "解剖", "生理", "临床", "诊断"],
    "口腔医学": ["口腔", "牙", "医学", "解剖"],
    "金融学类": ["金融", "投资", "货币", "银行", "财务"],
    "经济学类": ["经济", "微观", "宏观", "市场"],
    "数学类": ["数学", "分析", "代数", "概率", "统计"],
    "建筑类": ["建筑", "设计", "图纸", "空间", "结构"],
    "机械类": ["机械", "制图", "制造", "力学"],
    "能源动力类": ["能源", "热力", "动力", "新能源"],
    "汉语言文学": ["文学", "写作", "古诗", "汉语", "文本"],
    "法学": ["法律", "法理", "民法", "刑法", "案例"],
    "新闻传播学类": ["新闻", "传播", "写作", "媒体", "采访"],
    "英语": ["英语", "口语", "翻译", "听力", "外语"],
    "历史学类": ["历史", "史料", "古代", "文明"],
    "行政管理": ["管理", "行政", "公共", "组织"],
    "社会学类": ["社会", "调查", "社会学", "田野"],
    "教育学类": ["教育", "教学", "心理", "课程"],
    "会计学": ["会计", "财务", "报表", "审计"],
}

_COURSE_ROWS = [
    # title, platform, provider, weeks, level, rating, learners, category, tags, majors, desc
    ("Python 语言程序设计", "中国大学MOOC", "北京理工大学", 8, "入门", 4.8, "38.2万", "计算机",
     ["编程", "Python", "代码"], ["计算机科学与技术", "软件工程", "数据科学与大数据技术"], "从零写出第一行代码，结课能独立做一个小项目。"),
    ("数据结构与算法基础", "中国大学MOOC", "浙江大学", 10, "进阶", 4.9, "26.7万", "计算机",
     ["算法", "数据结构", "编程"], ["计算机科学与技术", "软件工程", "人工智能"], "把「会写代码」升级成「写得快、写得对」。"),
    ("计算机网络", "学堂在线", "清华大学", 8, "进阶", 4.7, "18.4万", "计算机",
     ["网络", "协议", "通信"], ["计算机科学与技术", "软件工程", "电子信息类"], "从一根网线讲到一次网页请求的完整旅程。"),
    ("数据库系统概论", "中国大学MOOC", "中国人民大学", 9, "进阶", 4.7, "15.9万", "计算机",
     ["数据库", "SQL", "数据"], ["计算机科学与技术", "软件工程", "信息管理与信息系统"], "学会用 SQL 把数据真正管起来。"),
    ("人工智能导论", "学堂在线", "清华大学", 6, "入门", 4.8, "21.3万", "计算机",
     ["人工智能", "机器学习", "算法"], ["计算机科学与技术", "自动化类", "人工智能"], "不写公式，先建立对 AI 的整体直觉。"),
    ("电路原理", "中国大学MOOC", "清华大学", 12, "入门", 4.7, "22.6万", "电子信息",
     ["电路", "电子", "硬件"], ["电子信息类", "自动化类", "电气工程"], "硬件人的第一门硬课，也是后面所有课的地基。"),
    ("模拟电子技术基础", "中国大学MOOC", "华中科技大学", 10, "进阶", 4.6, "14.2万", "电子信息",
     ["电子", "电路", "信号"], ["电子信息类", "自动化类", "通信工程"], "从二极管到运放，看懂电路图背后的逻辑。"),
    ("信号与系统", "学堂在线", "清华大学", 9, "进阶", 4.7, "11.8万", "电子信息",
     ["信号", "系统", "通信"], ["电子信息类", "通信工程", "自动化类"], "通信与控制的共同语言，早学早轻松。"),
    ("自动控制原理", "中国大学MOOC", "哈尔滨工业大学", 10, "进阶", 4.8, "13.5万", "自动化",
     ["控制", "自动化", "系统"], ["自动化类", "机器人工程", "电气工程"], "让系统按你的想法稳定运行的理论底座。"),
    ("机器人学基础", "B站", "上海交通大学", 8, "入门", 4.6, "9.1万", "自动化",
     ["机器人", "控制", "嵌入式"], ["自动化类", "机械类", "人工智能"], "看机器人怎么「看见—思考—动手」。"),
    ("人体解剖学", "中国大学MOOC", "北京大学医学部", 12, "入门", 4.9, "31.7万", "医学",
     ["医学", "解剖", "临床"], ["临床医学", "口腔医学", "麻醉学"], "医学院的第一课，认识你自己。"),
    ("生理学", "中国大学MOOC", "复旦大学上海医学院", 10, "进阶", 4.8, "17.6万", "医学",
     ["医学", "生理", "诊断"], ["临床医学", "口腔医学", "护理学"], "身体是怎么运转的，生病时又是哪一步出了错。"),
    ("口腔医学导论", "B站", "四川大学华西口腔", 6, "入门", 4.6, "5.8万", "医学",
     ["口腔", "牙", "医学"], ["口腔医学"], "口腔专业到底学什么、以后做什么，先听一节课。"),
    ("微观经济学", "中国大学MOOC", "北京大学", 8, "入门", 4.8, "29.4万", "经济金融",
     ["经济", "微观", "市场"], ["经济学类", "金融学类", "会计学"], "用几个模型解释身边的价格与选择。"),
    ("金融学基础", "学堂在线", "清华大学五道口金融学院", 8, "入门", 4.7, "19.2万", "经济金融",
     ["金融", "投资", "货币"], ["金融学类", "经济学类", "会计学"], "利率、汇率、资产定价，一次讲明白。"),
    ("会计学原理", "中国大学MOOC", "厦门大学", 7, "入门", 4.7, "16.3万", "经济金融",
     ["会计", "财务", "报表"], ["会计学", "金融学类", "工商管理"], "看懂一张资产负债表，是商科生的基本功。"),
    ("高等数学（上）", "中国大学MOOC", "同济大学", 12, "入门", 4.9, "45.1万", "数学",
     ["数学", "分析", "微积分"], ["数学类", "计算机科学与技术", "电子信息类", "经济学类"], "大学第一道坎，提前预习能省一半力气。"),
    ("概率论与数理统计", "学堂在线", "清华大学", 9, "进阶", 4.8, "23.9万", "数学",
     ["概率", "统计", "数学"], ["数学类", "计算机科学与技术", "金融学类"], "不确定性的语言，AI 和数据课的必备前置。"),
    ("线性代数", "中国大学MOOC", "清华大学", 8, "入门", 4.8, "34.6万", "数学",
     ["数学", "代数", "矩阵"], ["数学类", "计算机科学与技术", "自动化类"], "矩阵不只是算题，它是机器学习的语法。"),
    ("建筑学概论", "中国大学MOOC", "同济大学", 6, "入门", 4.6, "8.7万", "建筑",
     ["建筑", "设计", "空间"], ["建筑类", "城乡规划", "风景园林"], "建筑学到底学什么，先看一节再决定要不要熬夜。"),
    ("建筑制图与识图", "B站", "东南大学", 8, "入门", 4.5, "4.2万", "建筑",
     ["图纸", "制图", "结构"], ["建筑类", "土木工程"], "看懂图纸，是设计和施工之间唯一的桥。"),
    ("机械原理", "中国大学MOOC", "哈尔滨工业大学", 10, "进阶", 4.7, "10.4万", "机械",
     ["机械", "机构", "力学"], ["机械类", "车辆工程", "自动化类"], "从连杆到齿轮，理解机械为什么能动。"),
    ("工程制图", "中国大学MOOC", "天津大学", 8, "入门", 4.6, "12.1万", "机械",
     ["制图", "机械", "图纸"], ["机械类", "建筑类", "工业设计"], "工科生的通用语言，第一周就要用。"),
    ("能源与动力工程导论", "中国大学MOOC", "西安交通大学", 6, "入门", 4.5, "5.6万", "能源",
     ["能源", "动力", "热力"], ["能源动力类", "新能源科学与工程"], "从锅炉到电池，能源专业到底在做什么。"),
    ("中国古代文学史", "中国大学MOOC", "北京大学", 10, "入门", 4.8, "14.8万", "人文",
     ["文学", "古诗", "历史"], ["汉语言文学", "历史学类", "新闻传播学类"], "从《诗经》读到明清小说，建立自己的文学地图。"),
    ("写作与沟通", "学堂在线", "清华大学", 6, "入门", 4.7, "20.5万", "人文",
     ["写作", "表达", "文本"], ["汉语言文学", "新闻传播学类", "法学", "行政管理"], "大学里最被低估的能力：把话说清楚。"),
    ("法理学导论", "中国大学MOOC", "中国政法大学", 8, "入门", 4.7, "13.2万", "法学",
     ["法律", "法理", "案例"], ["法学", "行政管理", "社会学类"], "法律人第一课，理解规则背后的道理。"),
    ("民法总论", "B站", "中国人民大学", 10, "进阶", 4.6, "9.8万", "法学",
     ["民法", "法律", "案例"], ["法学"], "从「人」和「物」开始，搭起民法体系。"),
    ("新闻采访与写作", "中国大学MOOC", "中国人民大学", 6, "入门", 4.6, "7.4万", "新闻传播",
     ["新闻", "采访", "写作"], ["新闻传播学类", "汉语言文学", "广播电视学"], "怎么问出一个好问题，怎么写出一个好故事。"),
    ("传播学概论", "学堂在线", "复旦大学", 6, "入门", 4.5, "6.9万", "新闻传播",
     ["传播", "媒体", "社会"], ["新闻传播学类", "社会学类", "广告学"], "理解信息如何影响人，也理解自己如何被影响。"),
    ("大学英语听说", "中国大学MOOC", "上海外国语大学", 8, "入门", 4.6, "25.3万", "外语",
     ["英语", "听说", "口语"], ["英语", "翻译", "国际经济与贸易"], "摆脱哑巴英语，从敢开口开始。"),
    ("英汉翻译基础", "B站", "北京外国语大学", 6, "进阶", 4.5, "8.1万", "外语",
     ["翻译", "英语", "写作"], ["英语", "翻译"], "翻译不是换词，是换一种思维方式。"),
    ("中国近代史纲要", "中国大学MOOC", "清华大学", 6, "入门", 4.5, "18.6万", "人文",
     ["历史", "近代", "史料"], ["历史学类", "汉语言文学", "思想政治教育"], "把碎片化的历史知识串成一条线。"),
    ("社会学概论", "学堂在线", "北京大学", 6, "入门", 4.6, "9.3万", "人文",
     ["社会", "社会学", "调查"], ["社会学类", "行政管理", "新闻传播学类"], "用社会学的眼睛重新看日常生活。"),
    ("公共管理学", "中国大学MOOC", "中山大学", 8, "入门", 4.5, "6.2万", "管理",
     ["管理", "公共", "行政"], ["行政管理", "公共事业管理", "社会学类"], "政府和社会组织是怎么运转的。"),
    ("教育学原理", "中国大学MOOC", "北京师范大学", 8, "入门", 4.7, "11.7万", "教育",
     ["教育", "教学", "课程"], ["教育学类", "学前教育", "小学教育"], "想当老师，先理解「人是怎么学会的」。"),
    # 通识
    ("如何高效学习", "中国大学MOOC", "浙江大学", 4, "通识", 4.7, "42.8万", "通识",
     ["学习方法", "效率", "大学"], [], "大学和高中最大的差别：没人再盯着你学了。"),
    ("时间管理与自我规划", "B站", "清华大学", 3, "通识", 4.5, "28.6万", "通识",
     ["时间管理", "规划", "大学"], [], "开学第一周就建立自己的节奏。"),
    ("演讲与表达", "学堂在线", "中国传媒大学", 4, "通识", 4.6, "15.4万", "通识",
     ["演讲", "表达", "沟通"], [], "从自我介绍到课堂展示，都能用得上。"),
    ("文献检索与论文写作", "中国大学MOOC", "武汉大学", 5, "通识", 4.6, "19.1万", "通识",
     ["论文", "检索", "科研"], [], "大一就学会查文献，四年都受益。"),
]


def _build_courses() -> tuple[dict, ...]:
    courses = []
    for index, row in enumerate(_COURSE_ROWS, start=1):
        title, platform, provider, weeks, level, rating, learners, category, tags, majors, desc = row
        courses.append(
            {
                "id": f"k{index:02d}",
                "title": title,
                "platform": platform,
                "provider": provider,
                "url": PLATFORMS[platform] + quote(title),
                "weeks": weeks,
                "level": level,
                "rating": rating,
                "learners": learners,
                "category": category,
                "tags": tags,
                "majors": majors,
                "desc": desc,
            }
        )
    return tuple(courses)


COURSES = _build_courses()


@lru_cache(maxsize=1)
def _catalog() -> dict:
    """读课程目录。文件不存在时退回空目录，页面仍可用（只剩 40 门精品课）。"""
    if not CATALOG_PATH.exists():
        return {"courses": [], "total": 0, "verified": 0}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _backbone(major: str, limit: int = 8) -> list[dict]:
    """这个专业的主干课，按课表里的自然顺序排（基础课在前），最多 8 门。"""
    rows = [c for c in _catalog()["courses"] if major in c["majors"]]
    rows.sort(key=lambda c: (c.get("position", 99), -c["count"], c["name"]))
    rows = rows[:limit]
    return [
        {
            "id": f"b{index:02d}",
            "title": row["name"],
            "platform": row["platform"],
            "url": row["url"],
            "category": row["category"],
            "desc": row["desc"],
            "points": row["points"],
            "points_verified": row["points_verified"],
            "count": row["count"],
            "source": "backbone",
        }
        for index, row in enumerate(rows, start=1)
    ]


def majors() -> list[str]:
    seen: set[str] = set()
    for course in COURSES:
        seen.update(course["majors"])
    for course in _catalog()["courses"]:
        seen.update(course["majors"])
    return sorted(seen)


def recommend(major: str, limit: int = 6) -> dict:
    query = (major or "").strip()
    limit = 6 if limit is None else int(limit)
    limit = max(1, min(limit, 12))
    if not query:
        raise ValueError("请填写专业名称")

    keywords = _keywords_for(query)
    scored: list[tuple[float, dict, str]] = []

    for course in COURSES:
        score, reason = _score_course(course, query, keywords)
        if score > 0:
            scored.append((score, course, reason))

    scored.sort(key=lambda row: (-row[0], -row[1]["rating"]))

    # 只推「真的相关」的课；不够数时用通识课补位，并在前端标成「通识补充」，
    # 而不是把解剖学、高等数学硬塞给法学。
    chosen = list(scored[:limit])
    if len(chosen) < limit:
        picked = {course["id"] for _, course, _ in chosen}
        fillers = [c for c in COURSES if c["category"] == "通识" and c["id"] not in picked]
        fillers.sort(key=lambda c: -c["rating"])
        for course in fillers[: limit - len(chosen)]:
            chosen.append((0.0, course, "开学通识课，先适应大学节奏"))

    items = []
    for score, course, reason in chosen:
        items.append(
            {
                **course,
                "match": round(min(score / 14, 1.0) * 100),
                "reason": reason,
            }
        )

    matched = sum(1 for score, _, _ in chosen if score > 0)
    backbone = _backbone(query)
    tip = "链接跳到对应平台的搜索结果，具体课程以平台为准；建议先挑一门 4–6 周的入门课试听。"
    if not backbone:
        tip = f"专业目录里没有「{query}」的主干课，下面是平台口碑课。换个写法再试，比如去掉括号里的方向。"
    elif matched < len(items):
        tip = "这个专业的可直接对口课程不多，后面几门是通识补充。"
    catalog = _catalog()
    return {
        "major": query,
        "total": len(items),
        "matched": matched,
        "items": items,
        "backbone": backbone,
        "catalog": {"total": catalog.get("total", 0), "verified": catalog.get("verified", 0)},
        "tip": tip,
    }


def _keywords_for(major: str) -> list[str]:
    hits: list[str] = []
    for name, words in MAJOR_KEYWORDS.items():
        if name == major or name in major or major in name:
            hits.extend(words)
    if not hits:
        hits = [major[:2], major[:3]]
    return list(dict.fromkeys(hits))


def _score_course(course: dict, query: str, keywords: list[str]) -> tuple[float, str]:
    score = 0.0
    reason = ""

    if query in course["majors"]:
        score += 6
        reason = f"与「{query}」直接对应"
    else:
        for name in course["majors"]:
            if name in query or query in name:
                score += 3
                reason = reason or f"面向「{name}」方向"
                break

    keyword_hits = 0
    for word in keywords:
        if word in course["title"]:
            score += 2.0
            keyword_hits += 1
        elif any(word in tag or tag in word for tag in course["tags"]):
            score += 1.2
            keyword_hits += 1
    if keyword_hits and not reason:
        reason = "覆盖 " + "、".join(course["tags"][:2])
    score += min(keyword_hits, 3) * 0.4

    if score == 0:
        # 完全无关的课直接不推，避免「法学 → 人体解剖学」这种填充。
        return 0.0, ""

    # 评分与入门难度只做同一相关度下的排序微调，不决定是否推荐。
    score += (course["rating"] - 4.4) * 0.3
    if course["level"] == "入门":
        score += 0.2

    reason = reason or f"{course['category']}方向的高口碑课"
    return score, reason
