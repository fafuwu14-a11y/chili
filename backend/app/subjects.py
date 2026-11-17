"""选科数据层：全国 31 省选科模式 + 教育部 2024 版专业类选考科目要求。

三块内容，全部纯数据 + 纯函数，不联网、不依赖其它模块：

1. ``SUBJECTS``      —— 6+1 门选考科目（浙江多一门「技术」）；
2. ``PROVINCES``     —— 31 个省级行政区的选科模式（3+1+2 / 3+3 / 老文理）；
3. ``MAJOR_GROUPS``  —— 12 个学科门类下的 92 个专业类与选考要求。

数据依据：《普通高校本科招生专业选考科目要求指引（2024 年版）》对专业类的
通用要求，以及各省考试院已公布的实施方案。**专业类级别的「必选」是稳定的，
落实到具体院校、具体专业仍可能更严**，所以每个专业类都带 ``note``，
页面必须同时展示「以本省考试院当年公布的选考科目要求为准」。

核心政策是 2024 版起的「物化捆绑」：理学、工学（建筑类除外）、农学、
医学（护理学类除外）绝大多数专业类要求首选物理 + 再选化学。
"""

from __future__ import annotations

from itertools import combinations

# --------------------------------------------------------------------------
# 选考科目
# --------------------------------------------------------------------------
# order 用于页面稳定排序；short 是组合标签里的单字（物化生）。
SUBJECTS: dict[str, dict] = {
    "物理": {"key": "physics", "short": "物", "order": 1, "group": "首选", "color": "#E60012"},
    "历史": {"key": "history", "short": "史", "order": 2, "group": "首选", "color": "#B4531F"},
    "化学": {"key": "chemistry", "short": "化", "order": 3, "group": "再选", "color": "#1F7A8C"},
    "生物": {"key": "biology", "short": "生", "order": 4, "group": "再选", "color": "#2E8540"},
    "政治": {"key": "politics", "short": "政", "order": 5, "group": "再选", "color": "#8C1C4B"},
    "地理": {"key": "geography", "short": "地", "order": 6, "group": "再选", "color": "#A8761C"},
    "技术": {"key": "technology", "short": "技", "order": 7, "group": "再选", "color": "#5B5B8C"},
}

# 3+1+2：首选二选一，再选四选二
FIRST_CHOICE = ("物理", "历史")
SECOND_CHOICE = ("化学", "生物", "政治", "地理")
# 3+3：六选三（浙江七选三，多「技术」）
SIX_CHOOSE = ("物理", "化学", "生物", "政治", "历史", "地理")
SEVEN_CHOOSE = ("物理", "化学", "生物", "政治", "历史", "地理", "技术")

# --------------------------------------------------------------------------
# 31 个省级行政区
# --------------------------------------------------------------------------
# mode:  3+1+2 / 3+3 / old（老文理，过渡期）
# first: 该省新高考首考年份（老文理为 None）
# batch: 改革批次，用于首页分组展示
PROVINCES: dict[str, dict] = {
    # ---- 3+3 第二批（2020 首考）----
    "北京": {"mode": "3+3", "first": 2020, "batch": "第二批", "pool": 6},
    "天津": {"mode": "3+3", "first": 2020, "batch": "第二批", "pool": 6},
    "山东": {"mode": "3+3", "first": 2020, "batch": "第二批", "pool": 6},
    "海南": {"mode": "3+3", "first": 2020, "batch": "第二批", "pool": 6},
    # ---- 3+3 第一批（2017 首考）：浙江七选三 ----
    "上海": {"mode": "3+3", "first": 2017, "batch": "第一批", "pool": 6},
    "浙江": {"mode": "3+3", "first": 2017, "batch": "第一批", "pool": 7},
    # ---- 3+1+2 第三批（2021 首考）----
    "河北": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    "辽宁": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    "江苏": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    "福建": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    "湖北": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    "湖南": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    "广东": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    "重庆": {"mode": "3+1+2", "first": 2021, "batch": "第三批"},
    # ---- 3+1+2 第四批（2024 首考）----
    "甘肃": {"mode": "3+1+2", "first": 2024, "batch": "第四批"},
    "吉林": {"mode": "3+1+2", "first": 2024, "batch": "第四批"},
    "黑龙江": {"mode": "3+1+2", "first": 2024, "batch": "第四批"},
    "安徽": {"mode": "3+1+2", "first": 2024, "batch": "第四批"},
    "江西": {"mode": "3+1+2", "first": 2024, "batch": "第四批"},
    "贵州": {"mode": "3+1+2", "first": 2024, "batch": "第四批"},
    "广西": {"mode": "3+1+2", "first": 2024, "batch": "第四批"},
    # ---- 3+1+2 第五批（2025 首考）----
    "河南": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    "山西": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    "陕西": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    "内蒙古": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    "四川": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    "云南": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    "宁夏": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    "青海": {"mode": "3+1+2", "first": 2025, "batch": "第五批"},
    # ---- 过渡期：仍按文理分科（2028—2029 起转 3+1+2）----
    "西藏": {"mode": "old", "first": None, "batch": "过渡期"},
    "新疆": {"mode": "old", "first": None, "batch": "过渡期"},
}

MODE_LABELS = {
    "3+1+2": "3+1+2 模式",
    "3+3": "3+3 模式",
    "old": "文理分科（过渡期）",
}

MODE_DESC = {
    "3+1+2": "语文、数学、外语必考；首选科目物理、历史二选一；再选科目化学、生物、政治、地理四选二。",
    "3+3": "语文、数学、外语必考；从物理、化学、生物、政治、历史、地理（浙江含技术）中任选三门。",
    "old": "仍分文科、理科，尚未进入新高考；页面上按「文科 / 理科」折算组合。",
}

# --------------------------------------------------------------------------
# 92 个专业类 → 选考要求
# --------------------------------------------------------------------------
# required: 必须全部选考的科目
# any_of:   在其中至少选一门（为空表示无此约束）
# 判定：required ⊆ 组合 且（any_of 为空 或 any_of ∩ 组合 非空）
MAJOR_GROUPS: list[dict] = [
    # ---------------- 哲学 ----------------
    {"id": "philosophy", "name": "哲学类", "category": "哲学", "required": [],
     "note": "多数院校不限；少数要求思想政治或历史。"},

    # ---------------- 经济学 ----------------
    {"id": "economics", "name": "经济学类", "category": "经济学", "required": [],
     "note": "多数不限；部分院校要求物理。"},
    {"id": "finance", "name": "财政学类", "category": "经济学", "required": [],
     "note": "多数不限。"},
    {"id": "financial", "name": "金融学类", "category": "经济学", "required": [],
     "note": "多数不限；部分院校要求物理。"},
    {"id": "trade", "name": "经济与贸易类", "category": "经济学", "required": [],
     "note": "多数不限。"},

    # ---------------- 法学 ----------------
    {"id": "law", "name": "法学类", "category": "法学", "required": [],
     "note": "多数不限；部分政法类院校要求思想政治。"},
    {"id": "politics", "name": "政治学类", "category": "法学", "required": ["政治"],
     "note": "思想政治必选。"},
    {"id": "sociology", "name": "社会学类", "category": "法学", "required": [],
     "note": "多数不限。"},
    {"id": "ethnology", "name": "民族学类", "category": "法学", "required": [],
     "note": "多数不限。"},
    {"id": "marxism", "name": "马克思主义理论类", "category": "法学", "required": ["政治"],
     "note": "思想政治必选。"},
    {"id": "public_security", "name": "公安学类", "category": "法学", "required": ["政治"],
     "note": "思想政治必选；公安类院校另有体检与政审。"},

    # ---------------- 教育学 ----------------
    {"id": "education", "name": "教育学类", "category": "教育学", "required": [],
     "note": "多数不限；部分院校的数学/物理教育方向要求物理。"},
    {"id": "sports", "name": "体育学类", "category": "教育学", "required": [],
     "note": "多数不限；需参加体育专业测试。"},

    # ---------------- 文学 ----------------
    {"id": "chinese", "name": "中国语言文学类", "category": "文学", "required": [],
     "note": "多数不限；部分院校要求历史。"},
    {"id": "foreign", "name": "外国语言文学类", "category": "文学", "required": [],
     "note": "多数不限。"},
    {"id": "journalism", "name": "新闻传播学类", "category": "文学", "required": [],
     "note": "多数不限；部分院校要求政治或历史。"},

    # ---------------- 历史学 ----------------
    {"id": "history", "name": "历史学类", "category": "历史学", "required": ["历史"],
     "note": "历史必选；少数院校不限。"},

    # ---------------- 理学（12）----------------
    {"id": "math", "name": "数学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "physics", "name": "物理学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "chemistry", "name": "化学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "astronomy", "name": "天文学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "geo_science", "name": "地理科学类", "category": "理学", "required": ["物理"],
     "any_of": ["化学", "地理"], "note": "物理必选，另一门多要求化学或地理。"},
    {"id": "atmos", "name": "大气科学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "ocean", "name": "海洋科学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "geophysics", "name": "地球物理学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "geology", "name": "地质学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "biology_sci", "name": "生物科学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "psychology", "name": "心理学类", "category": "理学", "required": ["物理"],
     "any_of": ["化学", "生物"], "note": "物理必选；部分院校要求化学或生物。"},
    {"id": "statistics", "name": "统计学类", "category": "理学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选；部分院校只要求物理。"},

    # ---------------- 工学（31）----------------
    {"id": "mechanics", "name": "力学类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "mechanical", "name": "机械类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "instrument", "name": "仪器类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "material", "name": "材料类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "energy", "name": "能源动力类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "electrical", "name": "电气类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "electronics", "name": "电子信息类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "automation", "name": "自动化类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "computer", "name": "计算机类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "civil", "name": "土木类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "water", "name": "水利类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "survey", "name": "测绘类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "chemical_eng", "name": "化工与制药类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "geo_eng", "name": "地质类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "mining", "name": "矿业类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "textile", "name": "纺织类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "light_industry", "name": "轻工类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "transport", "name": "交通运输类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "ocean_eng", "name": "海洋工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "aerospace", "name": "航空航天类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "weapon", "name": "兵器类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "nuclear", "name": "核工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "agri_eng", "name": "农业工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "forestry_eng", "name": "林业工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "environment", "name": "环境科学与工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "bme", "name": "生物医学工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "food", "name": "食品科学与工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "architecture", "name": "建筑类", "category": "工学", "required": ["物理"],
     "note": "物理必选；建筑学、城乡规划多要求物理，风景园林部分不限。"},
    {"id": "safety", "name": "安全科学与工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "bio_eng", "name": "生物工程类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "police_tech", "name": "公安技术类", "category": "工学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选；部分公安类院校另要求政治。"},

    # ---------------- 农学（7）----------------
    {"id": "plant", "name": "植物生产类", "category": "农学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "nature", "name": "自然保护与环境生态类", "category": "农学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "animal", "name": "动物生产类", "category": "农学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "vet", "name": "动物医学类", "category": "农学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "forestry", "name": "林学类", "category": "农学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "fishery", "name": "水产类", "category": "农学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "grass", "name": "草学类", "category": "农学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},

    # ---------------- 医学（11）----------------
    {"id": "basic_med", "name": "基础医学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "clinical", "name": "临床医学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选；多为五年制及以上。"},
    {"id": "stomatology", "name": "口腔医学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "public_health", "name": "公共卫生与预防医学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "tcm", "name": "中医学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选（2024 版起）。"},
    {"id": "integrated_med", "name": "中西医结合类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "pharmacy", "name": "药学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "tcm_pharmacy", "name": "中药学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "forensic", "name": "法医学类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "med_tech", "name": "医学技术类", "category": "医学", "required": ["物理", "化学"],
     "note": "物理 + 化学必选。"},
    {"id": "nursing", "name": "护理学类", "category": "医学", "required": [],
     "any_of": ["化学", "生物"], "note": "多数不限；部分院校要求化学或生物。"},

    # ---------------- 管理学（9）----------------
    {"id": "management_sci", "name": "管理科学与工程类", "category": "管理学", "required": ["物理"],
     "note": "多数要求物理；信息管理与信息系统等方向尤其如此。"},
    {"id": "business", "name": "工商管理类", "category": "管理学", "required": [],
     "note": "多数不限。"},
    {"id": "agri_econ", "name": "农业经济管理类", "category": "管理学", "required": [],
     "note": "多数不限。"},
    {"id": "public_admin", "name": "公共管理类", "category": "管理学", "required": [],
     "note": "多数不限。"},
    {"id": "library", "name": "图书情报与档案管理类", "category": "管理学", "required": [],
     "note": "多数不限。"},
    {"id": "logistics", "name": "物流管理与工程类", "category": "管理学", "required": [],
     "note": "多数不限；部分要求物理。"},
    {"id": "industrial_eng", "name": "工业工程类", "category": "管理学", "required": ["物理"],
     "note": "多数要求物理。"},
    {"id": "ecommerce", "name": "电子商务类", "category": "管理学", "required": [],
     "note": "多数不限。"},
    {"id": "tourism", "name": "旅游管理类", "category": "管理学", "required": [],
     "note": "多数不限。"},

    # ---------------- 艺术学（5）----------------
    {"id": "art_theory", "name": "艺术学理论类", "category": "艺术学", "required": [],
     "note": "不限；需参加艺术类专业考试。"},
    {"id": "music", "name": "音乐与舞蹈学类", "category": "艺术学", "required": [],
     "note": "不限；需参加艺术类专业考试。"},
    {"id": "drama", "name": "戏剧与影视学类", "category": "艺术学", "required": [],
     "note": "不限；需参加艺术类专业考试。"},
    {"id": "fine_arts", "name": "美术学类", "category": "艺术学", "required": [],
     "note": "不限；需参加艺术类专业考试。"},
    {"id": "design", "name": "设计学类", "category": "艺术学", "required": [],
     "note": "不限；部分院校的设计类专业要求物理或历史。"},
]

CATEGORY_ORDER = ["理学", "工学", "医学", "经济学", "管理学", "法学", "文学",
                  "教育学", "历史学", "农学", "艺术学", "哲学"]

# 校验：92 个专业类，id 不重复
assert len(MAJOR_GROUPS) == 92, f"专业类应为 92 个，实际 {len(MAJOR_GROUPS)}"
assert len({g["id"] for g in MAJOR_GROUPS}) == 92, "专业类 id 有重复"

GROUP_INDEX: dict[str, dict] = {g["id"]: g for g in MAJOR_GROUPS}
GROUP_BY_NAME: dict[str, dict] = {g["name"]: g for g in MAJOR_GROUPS}


# --------------------------------------------------------------------------
# 组合
# --------------------------------------------------------------------------
def subject_order(name: str) -> int:
    return SUBJECTS.get(name, {}).get("order", 99)


def sort_subjects(subjects) -> list[str]:
    """按固定顺序排，保证「物化生」不会变成「生化物」。"""
    return sorted({s for s in subjects if s in SUBJECTS}, key=subject_order)


def combo_label(subjects) -> str:
    return "+".join(sort_subjects(subjects))


def combo_short(subjects) -> str:
    """组合标签：物化生 / 史政地。"""
    return "".join(SUBJECTS[s]["short"] for s in sort_subjects(subjects))


def province_mode(province: str) -> str:
    info = PROVINCES.get(province)
    if not info:
        raise ValueError(f"未收录的省份：{province}")
    return info["mode"]


def province_pool(province: str) -> tuple[str, ...]:
    """该省可选的全部选考科目。"""
    info = PROVINCES.get(province)
    if not info:
        raise ValueError(f"未收录的省份：{province}")
    mode = info["mode"]
    if mode == "3+1+2":
        return FIRST_CHOICE + SECOND_CHOICE
    if mode == "3+3":
        return SEVEN_CHOOSE if info.get("pool") == 7 else SIX_CHOOSE
    return SIX_CHOOSE  # old：文理各三门，虚拟组合


def combos(province: str) -> list[dict]:
    """枚举一个省的全部合法选科组合。

    3+1+2 12 种、六选三 20 种、浙江七选三 35 种、老文理 2 种。
    每个组合带 ``subjects``（有序列表）、``label``、``short``、``track``（老文理时的文/理）。
    """
    mode = province_mode(province)
    result: list[dict] = []
    if mode == "3+1+2":
        for first in FIRST_CHOICE:
            for rest in combinations(SECOND_CHOICE, 2):
                subs = sort_subjects([first, *rest])
                result.append({
                    "subjects": subs,
                    "label": combo_label(subs),
                    "short": combo_short(subs),
                    "first": [first],
                    "track": "物理类" if first == "物理" else "历史类",
                })
    elif mode == "3+3":
        for picked in combinations(province_pool(province), 3):
            subs = sort_subjects(picked)
            result.append({
                "subjects": subs,
                "label": combo_label(subs),
                "short": combo_short(subs),
                "first": [],
                "track": "",
            })
    else:  # old
        result.append({"subjects": ["物理", "化学", "生物"], "label": "理科（物化生）",
                       "short": "理", "first": [], "track": "理科"})
        result.append({"subjects": ["政治", "历史", "地理"], "label": "文科（政史地）",
                       "short": "文", "first": [], "track": "文科"})
    return result


def normalize_combo(province: str, subjects) -> list[str]:
    """把用户/前端传来的组合校验成该省合法的有序科目列表。

    支持传 `"物理+化学+生物"` 字符串。不合法时抛 ValueError，说明原因。
    """
    if isinstance(subjects, str):
        raw = [s.strip() for s in subjects.replace("＋", "+").split("+") if s.strip()]
    else:
        raw = [str(s).strip() for s in (subjects or [])]
    picked = sort_subjects(raw)
    if len(picked) != len({s for s in raw if s in SUBJECTS}):
        unknown = [s for s in raw if s not in SUBJECTS]
        raise ValueError(f"不认识的科目：{'、'.join(unknown)}")
    mode = province_mode(province)

    if mode == "3+1+2":
        if len(picked) != 3:
            raise ValueError("3+1+2 模式必须选 3 门（1 门首选 + 2 门再选）")
        firsts = [s for s in picked if s in FIRST_CHOICE]
        if len(firsts) != 1:
            raise ValueError("3+1+2 模式的首选科目必须且只能从物理、历史中选 1 门")
        for s in picked:
            if s not in FIRST_CHOICE and s not in SECOND_CHOICE:
                raise ValueError(f"「{s}」不是该省的再选科目")
        return picked

    if mode == "3+3":
        if len(picked) != 3:
            raise ValueError("3+3 模式必须选 3 门")
        pool = province_pool(province)
        for s in picked:
            if s not in pool:
                raise ValueError(f"「{s}」不在该省的可选科目里")
        return picked

    # old：只接受两种标准文理组合
    legacy = {("物理", "化学", "生物"): "理科", ("历史", "地理", "政治"): "文科"}
    for key in legacy:
        if tuple(picked) == tuple(sort_subjects(key)):
            return picked
    raise ValueError("该省仍按文理分科，请选择「理科（物化生）」或「文科（政史地）」")


# --------------------------------------------------------------------------
# 选考要求判定与覆盖率
# --------------------------------------------------------------------------
def group_eligible(group: dict | str, subjects) -> bool:
    """某专业类的选考要求，在给定组合下是否满足。"""
    if isinstance(group, str):
        group = GROUP_BY_NAME.get(group) or GROUP_INDEX.get(group)
        if group is None:
            raise ValueError(f"未收录的专业类：{group}")
    picked = set(sort_subjects(subjects))
    if not set(group.get("required", [])) <= picked:
        return False
    any_of = group.get("any_of") or []
    if any_of and not (set(any_of) & picked):
        return False
    return True


def requirement_text(group: dict) -> str:
    """把要求翻译成人话：物理+化学必选 / 不限 / 物理必选（化学或地理）。"""
    required = group.get("required") or []
    any_of = group.get("any_of") or []
    if not required and not any_of:
        return "不限"
    if not required and any_of:
        return "「" + "」或「".join(any_of) + "」选一门"
    head = "+".join(required) + "必选"
    if any_of:
        head += "（" + "或".join(any_of) + "）"
    return head


def missing_requirements(group: dict, subjects) -> list[str]:
    """报不了时，缺哪几门；用于给用户「想报这个专业，你需要补什么」。"""
    picked = set(sort_subjects(subjects))
    missing = [s for s in (group.get("required") or []) if s not in picked]
    any_of = group.get("any_of") or []
    if any_of and not (set(any_of) & picked):
        missing.append("或".join(any_of))
    return missing


def eligible_groups(subjects) -> list[dict]:
    return [g for g in MAJOR_GROUPS if group_eligible(g, subjects)]


def coverage(subjects, major_names: list[str] | None = None) -> dict:
    """一个组合能报多少。

    ``major_names`` 给了就按真实专业清单统计（需要上层先做专业 → 专业类映射），
    没给就按 92 个专业类统计。

    返回 ``{"groups": [...], "groups_ratio": 0.87, "by_category": {...}}``。
    """
    picked = sort_subjects(subjects)
    ok_groups = [g for g in MAJOR_GROUPS if group_eligible(g, picked)]
    by_category: dict[str, dict] = {}
    for g in MAJOR_GROUPS:
        row = by_category.setdefault(g["category"], {"total": 0, "ok": 0})
        row["total"] += 1
        if group_eligible(g, picked):
            row["ok"] += 1
    payload = {
        "groups": [g["name"] for g in ok_groups],
        "groups_total": len(ok_groups),
        "groups_ratio": round(len(ok_groups) / len(MAJOR_GROUPS), 4),
        "by_category": by_category,
    }
    if major_names:
        from .subject_map import group_of_major  # 延迟导入，避免循环

        hit = 0
        groups_hit: set[str] = set()
        for name in major_names:
            gid = group_of_major(name)
            group = GROUP_INDEX.get(gid)
            if group is not None and group_eligible(group, picked):
                hit += 1
                groups_hit.add(gid)
        payload["majors_total"] = len(major_names)
        payload["majors_ok"] = hit
        payload["majors_ratio"] = round(hit / len(major_names), 4) if major_names else 0.0
        payload["majors_groups"] = len(groups_hit)
    return payload


# --------------------------------------------------------------------------
# 给前端的元数据
# --------------------------------------------------------------------------
def meta() -> dict:
    """省份 / 科目 / 专业类的完整元数据，前端初始化一次即可。"""
    mode_counts: dict[str, int] = {}
    for info in PROVINCES.values():
        mode_counts[info["mode"]] = mode_counts.get(info["mode"], 0) + 1
    return {
        "subjects": [
            {"name": name, **{k: v for k, v in info.items() if k != "key"}, "key": info["key"]}
            for name, info in sorted(SUBJECTS.items(), key=lambda kv: kv[1]["order"])
        ],
        "provinces": [
            {"name": name, **info, "mode_label": MODE_LABELS[info["mode"]],
             "combo_count": len(combos(name))}
            for name, info in PROVINCES.items()
        ],
        "mode_counts": mode_counts,
        "mode_labels": MODE_LABELS,
        "mode_desc": MODE_DESC,
        "categories": CATEGORY_ORDER,
        "groups": [
            {"id": g["id"], "name": g["name"], "category": g["category"],
             "required": g.get("required", []), "any_of": g.get("any_of", []),
             "requirement": requirement_text(g), "note": g.get("note", "")}
            for g in MAJOR_GROUPS
        ],
        "source": "教育部《普通高校本科招生专业选考科目要求指引（2024 年版）》+ 各省考试院实施方案",
        "disclaimer": "专业类的必选科目是通用要求；具体院校、具体专业可能更严，"
                      "以本省考试院当年公布的《选考科目要求》为准。",
    }
