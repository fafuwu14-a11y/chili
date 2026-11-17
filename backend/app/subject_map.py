"""专业名 → 教育部 92 个专业类 的映射。

投档表里的专业名是院校自己写的（「计算机科学与技术」「工科试验班」「（中外合作办学）」），
本模块用「精确名 → 关键词规则 → 原目录大类兜底」三级匹配，把它们归到
``subjects.MAJOR_GROUPS`` 的 92 个专业类上，从而能判定选科要求。

映射质量直接影响覆盖率统计：``stats()`` 会给出未命中清单，改规则后跑一遍即可。
"""

from __future__ import annotations

import re
from functools import lru_cache

from . import subjects

# --------------------------------------------------------------------------
# 一级：精确名（高频专业名的权威归属，避免被泛关键词抢走）
# --------------------------------------------------------------------------
EXACT: dict[str, str] = {
    # 工学
    "计算机科学与技术": "computer", "软件工程": "computer", "网络工程": "computer",
    "信息安全": "computer", "物联网工程": "computer", "人工智能": "computer",
    "数据科学与大数据技术": "computer", "数字媒体技术": "computer",
    "智能科学与技术": "computer", "空间信息与数字技术": "computer",
    "电子与计算机工程": "computer", "区块链工程": "computer",
    "电子信息工程": "electronics", "通信工程": "electronics",
    "微电子科学与工程": "electronics", "集成电路设计与集成系统": "electronics",
    "电子科学与技术": "electronics", "光电信息科学与工程": "electronics",
    "信息工程": "electronics", "电磁场与无线技术": "electronics",
    "自动化": "automation", "机器人工程": "automation",
    "轨道交通信号与控制": "automation", "智能装备与系统": "automation",
    "电气工程及其自动化": "electrical", "电气工程与智能控制": "electrical",
    "机械设计制造及其自动化": "mechanical", "机械电子工程": "mechanical",
    "车辆工程": "mechanical", "智能制造工程": "mechanical",
    "工业设计": "mechanical", "过程装备与控制工程": "mechanical",
    "材料科学与工程": "material", "材料成型及控制工程": "material",
    "高分子材料与工程": "material", "冶金工程": "material",
    "无机非金属材料工程": "material", "复合材料与工程": "material",
    "新能源材料与器件": "material", "金属材料工程": "material",
    "能源与动力工程": "energy", "新能源科学与工程": "energy",
    "储能科学与工程": "energy", "建筑环境与能源应用工程": "civil",
    "土木工程": "civil", "城市地下空间工程": "civil",
    "道路桥梁与渡河工程": "civil", "给排水科学与工程": "civil",
    "建筑学": "architecture", "城乡规划": "architecture", "风景园林": "architecture",
    "历史建筑保护工程": "architecture",
    "水利水电工程": "water", "水文与水资源工程": "water", "港口航道与海岸工程": "water",
    "测绘工程": "survey", "遥感科学与技术": "survey", "导航工程": "survey",
    "化学工程与工艺": "chemical_eng", "制药工程": "chemical_eng",
    "资源循环科学与工程": "chemical_eng", "能源化学工程": "chemical_eng",
    "地质工程": "geo_eng", "勘查技术与工程": "geo_eng", "资源勘查工程": "geo_eng",
    "采矿工程": "mining", "石油工程": "mining", "矿物加工工程": "mining",
    "油气储运工程": "mining", "智能采矿工程": "mining",
    "纺织工程": "textile", "服装设计与工程": "textile", "非织造材料与工程": "textile",
    "轻化工程": "light_industry", "包装工程": "light_industry", "印刷工程": "light_industry",
    "交通运输": "transport", "交通工程": "transport", "飞行技术": "transport",
    "航海技术": "transport", "轮机工程": "transport",
    "船舶与海洋工程": "ocean_eng", "海洋资源开发技术": "ocean_eng",
    "航空航天工程": "aerospace", "飞行器设计与工程": "aerospace",
    "飞行器动力工程": "aerospace", "飞行器制造工程": "aerospace",
    "武器系统与工程": "weapon", "弹药工程与爆炸技术": "weapon",
    "核工程与核技术": "nuclear", "辐射防护与核安全": "nuclear",
    "农业机械化及其自动化": "agri_eng", "农业水利工程": "agri_eng",
    "木材科学与工程": "forestry_eng", "林产化工": "forestry_eng",
    "环境工程": "environment", "环境科学": "environment", "环保设备工程": "environment",
    "生物医学工程": "bme", "假肢矫形工程": "bme",
    "食品科学与工程": "food", "食品质量与安全": "food", "粮食工程": "food",
    "乳品工程": "food", "酿酒工程": "food",
    "安全工程": "safety", "应急技术与管理": "safety",
    "生物工程": "bio_eng", "生物制药": "bio_eng", "发酵工程": "bio_eng",
    "刑事科学技术": "police_tech", "消防工程": "police_tech",
    "交通管理工程": "police_tech", "网络安全与执法": "police_tech",
    "公安视听技术": "police_tech",

    # 理学
    "数学与应用数学": "math", "信息与计算科学": "math", "数理基础科学": "math",
    "物理学": "physics", "应用物理学": "physics", "声学": "physics",
    "化学": "chemistry", "应用化学": "chemistry", "化学生物学": "chemistry",
    "天文学": "astronomy",
    "地理科学": "geo_science", "自然地理与资源环境": "geo_science",
    "人文地理与城乡规划": "geo_science", "地理信息科学": "geo_science",
    "大气科学": "atmos", "应用气象学": "atmos",
    "海洋科学": "ocean", "海洋技术": "ocean", "军事海洋学": "ocean",
    "地球物理学": "geophysics",
    "地质学": "geology", "地球化学": "geology", "古生物学": "geology",
    "生物科学": "biology_sci", "生物技术": "biology_sci", "生物信息学": "biology_sci",
    "生态学": "biology_sci",
    "心理学": "psychology", "应用心理学": "psychology",
    "统计学": "statistics", "应用统计学": "statistics", "数据计算及应用": "statistics",

    # 医学
    "基础医学": "basic_med",
    "临床医学": "clinical", "麻醉学": "clinical", "医学影像学": "clinical",
    "眼视光医学": "clinical", "精神医学": "clinical", "儿科学": "clinical",
    "放射医学": "clinical",
    "口腔医学": "stomatology",
    "预防医学": "public_health", "食品卫生与营养学": "public_health",
    "妇幼保健医学": "public_health",
    "中医学": "tcm", "针灸推拿学": "tcm", "中医康复学": "tcm", "壮医学": "tcm",
    "中西医临床医学": "integrated_med",
    "药学": "pharmacy", "药物制剂": "pharmacy", "临床药学": "pharmacy",
    "药物分析": "pharmacy", "药事管理": "pharmacy",
    "中药学": "tcm_pharmacy", "中药资源与开发": "tcm_pharmacy",
    "法医学": "forensic",
    "医学检验技术": "med_tech", "医学影像技术": "med_tech", "康复治疗学": "med_tech",
    "口腔医学技术": "med_tech", "卫生检验与检疫": "med_tech", "智能医学工程": "med_tech",
    "护理学": "nursing", "助产学": "nursing",

    # 农学
    "农学": "plant", "园艺": "plant", "植物保护": "plant", "种子科学与工程": "plant",
    "茶学": "plant", "烟草": "plant", "设施农业科学与工程": "plant",
    "农业资源与环境": "nature", "水土保持与荒漠化防治": "nature",
    "野生动物与自然保护区管理": "nature",
    "动物科学": "animal", "蚕学": "animal",
    "动物医学": "vet", "动物药学": "vet", "动植物检疫": "vet",
    "林学": "forestry", "园林": "forestry", "森林保护": "forestry",
    "水产养殖学": "fishery", "海洋渔业科学与技术": "fishery",
    "草业科学": "grass",

    # 经济学
    "经济学": "economics", "数字经济": "economics", "能源经济": "economics",
    "国民经济管理": "economics", "商务经济学": "economics",
    "财政学": "finance", "税收学": "finance",
    "金融学": "financial", "金融工程": "financial", "保险学": "financial",
    "投资学": "financial", "金融科技": "financial", "精算学": "financial",
    "国际经济与贸易": "trade", "贸易经济": "trade",

    # 管理学
    "管理科学": "management_sci", "信息管理与信息系统": "management_sci",
    "工程管理": "management_sci", "工程造价": "management_sci",
    "大数据管理与应用": "management_sci", "房地产开发与管理": "management_sci",
    "工商管理": "business", "市场营销": "business", "会计学": "business",
    "财务管理": "business", "人力资源管理": "business", "审计学": "business",
    "资产评估": "business", "物业管理": "business", "文化产业管理": "business",
    "农林经济管理": "agri_econ", "农村区域发展": "agri_econ",
    "公共事业管理": "public_admin", "行政管理": "public_admin",
    "劳动与社会保障": "public_admin", "土地资源管理": "public_admin",
    "城市管理": "public_admin", "海关管理": "public_admin", "交通管理": "public_admin",
    "图书馆学": "library", "档案学": "library", "信息资源管理": "library",
    "物流管理": "logistics", "物流工程": "logistics", "供应链管理": "logistics",
    "工业工程": "industrial_eng", "标准化工程": "industrial_eng",
    "质量管理工程": "industrial_eng",
    "电子商务": "ecommerce", "跨境电子商务": "ecommerce",
    "旅游管理": "tourism", "酒店管理": "tourism", "会展经济与管理": "tourism",

    # 法学
    "法学": "law", "知识产权": "law", "监狱学": "law", "司法警察学": "law",
    "政治学与行政学": "politics", "国际政治": "politics", "外交学": "politics",
    "国际事务与国际关系": "politics",
    "社会学": "sociology", "社会工作": "sociology", "社会政策": "sociology",
    "民族学": "ethnology",
    "思想政治教育": "marxism", "马克思主义理论": "marxism", "中国共产党历史": "marxism",
    "治安学": "public_security", "侦查学": "public_security", "公安管理学": "public_security",
    "警务指挥与战术": "public_security", "涉外警务": "public_security",
    "犯罪学": "public_security", "公安情报学": "public_security",

    # 教育学
    "教育学": "education", "学前教育": "education", "小学教育": "education",
    "特殊教育": "education", "教育技术学": "education", "科学教育": "education",
    "人文教育": "education", "艺术教育": "education",
    "体育教育": "sports", "运动训练": "sports", "社会体育指导与管理": "sports",
    "运动人体科学": "sports", "武术与民族传统体育": "sports", "休闲体育": "sports",

    # 文学
    "汉语言文学": "chinese", "汉语言": "chinese", "汉语国际教育": "chinese",
    "秘书学": "chinese", "中国语言与文化": "chinese",
    "英语": "foreign", "日语": "foreign", "俄语": "foreign", "德语": "foreign",
    "法语": "foreign", "西班牙语": "foreign", "阿拉伯语": "foreign",
    "朝鲜语": "foreign", "翻译": "foreign", "商务英语": "foreign",
    "新闻学": "journalism", "传播学": "journalism", "广告学": "journalism",
    "网络与新媒体": "journalism", "编辑出版学": "journalism",
    "广播电视学": "journalism", "数字出版": "journalism",

    # 历史学 / 哲学
    "历史学": "history", "世界史": "history", "考古学": "history",
    "文物与博物馆学": "history",
    "哲学": "philosophy", "逻辑学": "philosophy", "宗教学": "philosophy",
    "伦理学": "philosophy",

    # 艺术学
    "艺术史论": "art_theory", "艺术管理": "art_theory", "非物质文化遗产保护": "art_theory",
    "音乐学": "music", "音乐表演": "music", "舞蹈学": "music", "舞蹈表演": "music",
    "作曲与作曲技术理论": "music", "舞蹈编导": "music",
    "表演": "drama", "戏剧影视文学": "drama", "广播电视编导": "drama",
    "播音与主持艺术": "drama", "动画": "drama", "影视摄影与制作": "drama",
    "戏剧影视导演": "drama", "录音艺术": "drama",
    "美术学": "fine_arts", "绘画": "fine_arts", "雕塑": "fine_arts",
    "摄影": "fine_arts", "书法学": "fine_arts", "中国画": "fine_arts",
    "视觉传达设计": "design", "环境设计": "design", "产品设计": "design",
    "服装与服饰设计": "design", "数字媒体艺术": "design", "公共艺术": "design",
    "工艺美术": "design", "艺术设计学": "design", "艺术与科技": "design",
}

# --------------------------------------------------------------------------
# 二级：关键词规则（按顺序匹配，越具体越靠前）
# --------------------------------------------------------------------------
# (关键词元组, 专业类 id)；任一关键词命中即归入该类。
RULES: list[tuple[tuple[str, ...], str]] = [
    # --- 计算机 / 电子 ---
    (("计算机", "软件工程", "软件", "物联网", "信息安全", "网络空间安全", "人工智能",
      "数据科学", "大数据", "智能科学", "数字媒体技术", "区块链"), "computer"),
    (("集成电路", "微电子", "电子科学", "电子信息", "通信工程", "通信", "光电信息",
      "信息工程", "电磁场", "电波传播"), "electronics"),
    (("自动化", "机器人", "轨道交通信号", "智能装备"), "automation"),
    (("电气工程", "电力系统", "智能电网"), "electrical"),
    (("机械", "车辆", "汽车服务", "智能制造", "机电", "过程装备", "工业设计",
      "材料成型"), "mechanical"),
    (("材料", "冶金", "高分子", "焊接", "复合材料", "无机非金属"), "material"),
    (("能源与动力", "能源动力", "新能源科学", "储能", "风能与动力"), "energy"),
    (("土木", "给排水", "道路桥梁", "城市地下空间", "建筑环境", "智能建造"), "civil"),
    (("建筑学", "城乡规划", "风景园林", "历史建筑"), "architecture"),
    (("水利", "水文", "港口航道", "水务工程"), "water"),
    (("测绘", "遥感", "导航工程", "地理空间信息"), "survey"),
    (("化学工程", "化工", "制药工程", "能源化学", "资源循环"), "chemical_eng"),
    (("勘查技术", "资源勘查", "地质工程", "地下水科学"), "geo_eng"),
    (("采矿", "石油工程", "矿物加工", "油气储运", "智能采矿"), "mining"),
    (("纺织", "服装设计与工程", "非织造"), "textile"),
    (("轻化工程", "包装工程", "印刷工程", "香料香精"), "light_industry"),
    (("交通运输", "交通工程", "飞行技术", "航海技术", "轮机工程", "交通设备"), "transport"),
    (("船舶与海洋", "海洋工程", "海洋资源开发"), "ocean_eng"),
    (("航空航天", "飞行器"), "aerospace"),
    (("武器", "弹药", "特种能源"), "weapon"),
    (("核工程", "核技术", "辐射防护"), "nuclear"),
    (("农业机械化", "农业水利", "农业工程"), "agri_eng"),
    (("木材科学", "林产化工", "林业工程"), "forestry_eng"),
    (("环境工程", "环境科学", "环境生态", "资源环境科学", "环保设备"), "environment"),
    (("生物医学工程", "假肢矫形", "智能医学工程"), "bme"),
    (("食品科学", "食品质量", "粮食工程", "乳品", "酿酒", "食品营养"), "food"),
    (("安全工程", "应急技术", "消防工程", "安全防范"), "safety"),
    (("生物工程", "生物制药", "发酵工程", "合成生物学"), "bio_eng"),
    (("刑事科学技术", "公安视听", "网络安全与执法", "交通管理工程"), "police_tech"),

    # --- 理学 ---
    (("数学", "信息与计算科学", "数理"), "math"),
    (("物理学", "应用物理", "声学"), "physics"),
    (("化学",), "chemistry"),
    (("天文",), "astronomy"),
    (("地理科学", "自然地理", "人文地理", "地理信息"), "geo_science"),
    (("大气科学", "气象"), "atmos"),
    (("海洋科学", "海洋技术", "军事海洋"), "ocean"),
    (("地球物理", "空间科学与技术"), "geophysics"),
    (("地质学", "地球化学", "古生物", "地球信息"), "geology"),
    (("生物科学", "生物技术", "生物信息", "生态学", "生物科学类"), "biology_sci"),
    (("心理学", "应用心理"), "psychology"),
    (("统计学", "应用统计", "数据计算"), "statistics"),

    # --- 医学 ---
    (("基础医学",), "basic_med"),
    (("临床医学", "麻醉", "医学影像学", "眼视光医学", "精神医学", "儿科学", "放射医学"), "clinical"),
    (("口腔医学",), "stomatology"),
    (("预防医学", "食品卫生与营养", "妇幼保健", "卫生监督"), "public_health"),
    (("中医学", "针灸推拿", "中医康复", "民族医学"), "tcm"),
    (("中西医",), "integrated_med"),
    (("药学", "药物制剂", "临床药学", "药物分析", "药事管理"), "pharmacy"),
    (("中药",), "tcm_pharmacy"),
    (("法医学",), "forensic"),
    (("医学检验", "医学影像技术", "康复治疗", "口腔医学技术", "卫生检验", "眼视光学"), "med_tech"),
    (("护理学", "助产", "护理"), "nursing"),

    # --- 农学 ---
    (("农学", "园艺", "植物保护", "种子科学", "茶学", "烟草", "设施农业", "智慧农业"), "plant"),
    (("农业资源", "水土保持", "自然保护区", "生态修复"), "nature"),
    (("动物科学", "蚕学", "蜂学", "经济动物"), "animal"),
    (("动物医学", "动物药学", "动植物检疫", "中兽医学"), "vet"),
    (("林学", "园林", "森林保护", "经济林"), "forestry"),
    (("水产", "海洋渔业"), "fishery"),
    (("草业", "草坪科学"), "grass"),

    # --- 经济 / 管理 ---
    (("经济学", "经济统计", "数字经济", "能源经济", "商务经济", "国民经济"), "economics"),
    (("财政学", "税收学", "税务"), "finance"),
    (("金融", "保险", "投资学", "精算", "信用管理"), "financial"),
    (("国际经济与贸易", "贸易经济", "国际商务"), "trade"),
    (("管理科学", "信息管理与信息系统", "工程管理", "工程造价", "大数据管理",
      "房地产开发", "应急管理"), "management_sci"),
    (("工商管理", "市场营销", "会计", "财务管理", "人力资源", "审计", "资产评估",
      "物业管理", "文化产业管理", "国际商务营销"), "business"),
    (("农林经济", "农村区域"), "agri_econ"),
    (("公共事业管理", "行政管理", "劳动与社会保障", "土地资源管理", "城市管理",
      "海关管理", "公共政策", "卫生事业管理"), "public_admin"),
    (("图书馆学", "档案学", "信息资源管理", "编辑出版"), "library"),
    (("物流", "供应链"), "logistics"),
    (("工业工程", "标准化工程", "质量管理"), "industrial_eng"),
    (("电子商务",), "ecommerce"),
    (("旅游管理", "酒店管理", "会展经济", "旅游"), "tourism"),

    # --- 法学 ---
    (("法学", "知识产权", "监狱学", "司法"), "law"),
    (("政治学", "国际政治", "外交学", "国际事务", "国际关系"), "politics"),
    (("社会学", "社会工作", "社会政策", "家政学"), "sociology"),
    (("民族学",), "ethnology"),
    (("思想政治教育", "马克思主义", "中国共产党历史", "科学社会主义"), "marxism"),
    (("治安学", "侦查", "公安管理", "警务", "涉外警务", "犯罪学", "公安情报",
      "禁毒", "警犬技术"), "public_security"),

    # --- 教育 ---
    (("教育学", "学前教育", "小学教育", "特殊教育", "教育技术", "科学教育",
      "人文教育", "艺术教育", "体育教育", "运动训练", "社会体育", "运动人体",
      "武术", "休闲体育", "运动康复", "体能训练"), "sports"),
    (("教育",), "education"),

    # --- 文学 / 历史 / 哲学 ---
    (("汉语言", "汉语国际", "秘书学", "中国语言"), "chinese"),
    (("英语", "日语", "俄语", "德语", "法语", "西班牙语", "阿拉伯语", "朝鲜语",
      "葡萄牙语", "意大利语", "翻译", "商务英语", "外国语言"), "foreign"),
    (("新闻", "传播", "广告", "网络与新媒体", "编辑出版", "广播电视学", "数字出版"), "journalism"),
    (("历史", "考古", "文物与博物馆", "世界史"), "history"),
    (("哲学", "逻辑学", "宗教学", "伦理学"), "philosophy"),

    # --- 艺术 ---
    (("艺术史论", "艺术管理", "非物质文化遗产"), "art_theory"),
    (("音乐", "舞蹈", "作曲"), "music"),
    (("表演", "戏剧", "影视", "播音", "主持", "广播电视编导", "动画", "录音艺术"), "drama"),
    (("美术", "绘画", "雕塑", "书法", "中国画", "摄影"), "fine_arts"),
    (("设计", "工艺美术", "公共艺术"), "design"),
]

# --------------------------------------------------------------------------
# 三级：原目录的 56 个自定义大类兜底（group 名 → 92 类 id）
# --------------------------------------------------------------------------
GROUP_HINTS: dict[str, str] = {
    "计算机类": "computer", "航空航天与交通类": "aerospace", "自动化类": "automation",
    "土木建筑类": "civil", "电子信息类": "electronics", "材料类": "material",
    "能源动力类": "energy", "机械类": "mechanical", "化工与制药类": "chemical_eng",
    "食品与轻工类": "food", "环境与安全类": "environment", "资源与矿业类": "mining",
    "生物医学工程类": "bme", "电气类": "electrical",
    "地理与大气类": "geo_science", "生物科学类": "biology_sci", "数学类": "math",
    "化学类": "chemistry", "物理类": "physics", "心理学类": "psychology",
    "力学类": "mechanics",
    "护理与康复类": "nursing", "临床医学类": "clinical", "中医学类": "tcm",
    "药学类": "pharmacy", "公共卫生与医学技术类": "public_health",
    "口腔医学类": "stomatology", "基础与法医学类": "basic_med",
    "金融学类": "financial", "经济学类": "economics", "经贸类": "trade",
    "财政与税收类": "finance",
    "公共管理类": "public_admin", "物流与电商类": "logistics",
    "会计与财务类": "business", "旅游与服务类": "tourism",
    "管理与信息系统类": "management_sci", "工商管理类": "business",
    "外国语言文学类": "foreign", "新闻传播类": "journalism", "中国语言文学类": "chinese",
    "政治学与思政类": "politics", "法学类": "law", "社会学类": "sociology",
    "教育学类": "education", "体育类": "sports",
    "历史学类": "history", "哲学类": "philosophy",
    "植物与动物类": "plant", "农业工程与食品类": "agri_eng",
    "音乐与表演类": "music", "艺术设计类": "design", "美术类": "fine_arts",
    "艺术管理类": "art_theory",
}

# 大类招生里带方向提示的名字（「工科试验班」「经济管理试验班」）
TRIAL_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("工科", "工程"), "computer"),
    (("理科", "自然科学"), "math"),
    (("医学",), "clinical"),
    (("经济", "管理", "商科"), "business"),
    (("人文", "文科"), "chinese"),
]

# --------------------------------------------------------------------------
# 补充规则：新工科 / 小语种 / 医学技术 / 专科专业名（2024 后大量新设）
# --------------------------------------------------------------------------
SUPPLEMENT: list[tuple[tuple[str, ...], str]] = [
    # 计算机 / 电子 / 自动化
    (("工业互联网", "云计算技术", "移动应用开发", "智能视觉", "具身智能"), "computer"),
    (("电子封装", "柔性电子", "水声", "大功率半导体", "光源与照明", "智能感知",
      "仪器类", "应用电子", "电信工程", "智能视听"), "electronics"),
    (("智能测控", "工业智能", "智能无人系统", "智能控制"), "automation"),
    (("电气类", "供用电技术"), "electrical"),
    (("装备智能化", "智能网联汽车", "汽车工程技术", "数控技术", "电梯工程",
      "仿生科学"), "mechanical"),
    # 土木 / 建筑 / 测绘 / 资源
    (("建筑工程", "建筑装饰", "道路与桥梁", "智慧建筑", "土地整治"), "civil"),
    (("建筑类",), "architecture"),
    (("智能地球探测",), "geo_eng"),
    (("矿业类", "海洋油气", "碳储科学"), "mining"),
    (("智慧城市", "城市设施智慧管理", "自然资源登记", "土地科学"), "public_admin"),
    (("国家公园",), "nature"),
    (("森林工程",), "forestry_eng"),
    (("水质科学", "环境监测", "碳中和科学"), "environment"),
    # 安全 / 兵器
    (("安全科学与", "应急装备", "安全生产监管", "职业卫生", "防灾减灾"), "safety"),
    (("兵器类", "信息对抗"), "weapon"),
    # 医学技术 / 护理 / 兽医
    (("医学技术类", "医学实验", "医学美容", "眼视光技术", "老年医学",
      "智能影像工程"), "med_tech"),
    (("医养照护", "安宁照护"), "nursing"),
    (("健康与医疗保障", "健康管理"), "public_health"),
    (("宠物医疗", "畜牧兽医", "兽医公共"), "vet"),
    (("实验动物", "动物生产", "马业科学", "智慧牧业", "饲料工程"), "animal"),
    (("水族科学",), "fishery"),
    (("婴幼儿发展",), "education"),
    # 农 / 食品 / 轻工
    (("生物农药", "菌物科学", "农药化肥", "中草药栽培", "植物生产",
      "植物科学"), "plant"),
    (("智慧林业",), "forestry"),
    (("生物质科学",), "agri_eng"),
    (("葡萄与葡萄酒", "中西面点", "西式烹饪"), "food"),
    (("化妆品", "轻工类", "数字化染整"), "light_industry"),
    (("服装工程",), "textile"),
    # 交通
    (("动车组", "高速铁路动车组", "空中乘务", "民航运输", "海事管理",
      "港口与航运", "智能交通管理"), "transport"),
    # 经济 / 管理 / 法
    (("企业数字化", "医疗产品管理", "商务数据分析"), "management_sci"),
    (("创业管理", "劳动关系"), "business"),
    (("国际税收",), "finance"),
    (("数字贸易", "关务与外贸"), "trade"),
    (("全媒体电商", "电商运营"), "ecommerce"),
    (("会展策划", "数字文旅", "国际邮轮"), "tourism"),
    (("慈善管理", "乡村治理", "社区管理", "公共关系学"), "public_admin"),
    (("女性学", "家政管理", "婚姻服务", "殡葬管理"), "sociology"),
    (("纪检监察", "国际法", "法律事务", "信用风险管理", "社区矫正",
      "海外利益安全"), "law"),
    (("国家安全学", "国际组织", "区域国别"), "politics"),
    (("海外安全管理", "航空安防"), "public_security"),
    # 人文 / 艺术 / 体育
    (("数字人文", "古典文献", "应用中文", "民族语言", "现代文秘"), "chinese"),
    (("新媒体技术", "文化创意", "公共文化服务"), "journalism"),
    (("电影学", "电影制作", "智能影像艺术", "动漫制作"), "drama"),
    (("艺术学理论", "文化遗产"), "art_theory"),
    (("电子竞技", "高尔夫"), "sports"),
    # 理学
    (("量子信息",), "physics"),
    (("行星科学",), "astronomy"),
    (("海洋资源与环境",), "ocean"),
    (("文化遗产",), "history"),
    # 收尾补漏
    (("无人机",), "aerospace"),
    (("农业电气化",), "agri_eng"),
    (("氢能",), "energy"),
    (("智能海洋装备",), "ocean_eng"),
    (("现代分析测试",), "electronics"),
    (("药品质量", "药品经营"), "pharmacy"),
]
# 单字/极短名单独处理：「法律」这类精确名
EXACT.setdefault("法律", "law")

# 预科班 / 实验班 / 学院名：没有明确专业指向，不计入覆盖率分母
EXEMPT_PATTERNS = ("预科班", "实验班", "试验班", "商学院", "健行学院")

_NORMALISE = re.compile(r"[（(].*?[）)]")


def clean_name(name: str) -> str:
    """去掉「（中外合作办学）」「（师范）」「(实验班)」这类括号后缀。"""
    return _NORMALISE.sub("", str(name or "")).strip()


def is_exempt(name: str) -> bool:
    """预科班 / 实验班 / 学院名：无专业指向，统计覆盖率时不计入分母。"""
    return any(p in str(name or "") for p in EXEMPT_PATTERNS)


@lru_cache(maxsize=4096)
def group_of_major(name: str, category: str = "", group: str = "") -> str:
    """专业名 → 专业类 id；匹配不上返回 ``other``。

    ``category`` / ``group`` 是 ``major_catalog.json`` 里已有的粗略归类，用于兜底。
    """
    raw = str(name or "").strip()
    if not raw:
        return "other"
    if raw in EXACT:
        return EXACT[raw]
    cleaned = clean_name(raw)
    if cleaned in EXACT:
        return EXACT[cleaned]

    probe = cleaned or raw
    for keywords, gid in RULES:
        if any(k in probe for k in keywords):
            return gid
    for keywords, gid in SUPPLEMENT:
        if any(k in probe for k in keywords):
            return gid

    # 泰语 / 匈牙利语 / 马来语…… 以「语」结尾的小语种名
    if clean_name(probe).endswith("语") and len(probe) <= 9:
        return "foreign"

    # 大类招生：「工科试验班」这类按方向提示猜一个
    if "试验班" in raw or "实验班" in raw or "大类" in raw:
        for keywords, gid in TRIAL_HINTS:
            if any(k in raw for k in keywords):
                return gid

    if group and group in GROUP_HINTS:
        return GROUP_HINTS[group]
    return "other"


def map_all(items: list[dict]) -> dict[str, str]:
    """批量映射，``items`` 是 ``major_catalog.json`` 的 majors 列表。"""
    return {
        item["name"]: group_of_major(item["name"], item.get("category", ""), item.get("group", ""))
        for item in items
    }


def stats(items: list[dict], *, limit: int = 40) -> dict:
    """覆盖率与未命中清单，用来调关键词规则。"""
    mapping = map_all(items)
    total = len(mapping)
    exempt = [name for name in mapping if is_exempt(name)]
    missed = [name for name, gid in mapping.items() if gid == "other" and name not in exempt]
    eligible = total - len(exempt)
    by_group: dict[str, int] = {}
    for gid in mapping.values():
        by_group[gid] = by_group.get(gid, 0) + 1
    return {
        "total": total,
        "exempt": len(exempt),
        "denominator": eligible,
        "mapped": eligible - len(missed),
        "ratio": round((eligible - len(missed)) / eligible, 4) if eligible else 0.0,
        "mapped_groups": len([g for g in by_group if g != "other"]),
        "total_groups": len(subjects.MAJOR_GROUPS),
        "by_group": by_group,
        "missed": missed[:limit],
        "missed_total": len(missed),
    }
