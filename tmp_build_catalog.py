"""把八省真实投档表里的专业名，整理成「门类 → 专业类 → 具体专业」目录。

一次性构建脚本：读 backend/data/*/toudang_*.csv，归一化专业名，
按关键词归到 12 个学科门类下的专业类，输出 backend/data/major_catalog.json。

用法：python tmp_build_catalog.py
"""

from __future__ import annotations

import csv
import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "backend" / "data"
OUT = DATA / "major_catalog.json"

BRACKETS = re.compile(r"[（(\[【][^）)\]】]*[）)\]】]")
CLEAN = re.compile(r"[\s·]+")
# 「XX类」这种是专业类而不是具体专业，展示时降级
GROUPISH = re.compile(r"类$|试验班$|班$|学院$")

# 门类 → 专业类 → 关键词（按顺序匹配，越具体越靠前）
RULES: list[tuple[str, str, str, list[str]]] = [
    ("eng", "计算机类", "计算机", ["计算机", "软件工程", "软件", "人工智能", "数据科学", "大数据", "网络工程", "信息安全", "网络空间安全", "物联网", "数字媒体技术", "智能科学", "区块链", "密码"]),
    ("eng", "电子信息类", "电子信息", ["电子信息", "通信工程", "电子科学", "集成电路", "微电子", "光电信息", "电磁场", "电波传播", "信息工程"]),
    ("eng", "自动化类", "自动化", ["自动化", "机器人工程", "测控技术", "控制", "智能装备"]),
    ("eng", "机械类", "机械", ["机械", "车辆工程", "汽车服务", "工业设计", "过程装备", "材料成型"]),
    ("eng", "材料类", "材料", ["材料", "高分子", "金属材料", "无机非金属", "复合材料", "新能源材料"]),
    ("eng", "能源动力类", "能源动力", ["能源", "动力工程", "新能源科学", "储能", "核工程", "建筑环境与能源"]),
    ("eng", "电气类", "电气", ["电气工程", "智能电网", "电力"]),
    ("eng", "土木建筑类", "土木建筑", ["土木工程", "建筑学", "城乡规划", "风景园林", "智能建造", "给排水", "道路桥梁", "工程管理", "工程造价", "房地产", "测绘工程", "建筑环境"]),
    ("eng", "化工与制药类", "化工制药", ["化学工程", "化工", "制药工程", "生物制药", "精细化工", "能源化学工程"]),
    ("eng", "航空航天与交通类", "航空航天交通", ["航空航天", "飞行器", "交通运输", "交通工程", "船舶", "海洋工程", "车辆运用", "铁道", "航海", "轮机"]),
    ("eng", "环境与安全类", "环境安全", ["环境工程", "环境科学", "安全工程", "资源循环", "应急技术", "消防"]),
    ("eng", "食品与轻工类", "食品轻工", ["食品", "轻化工程", "纺织", "服装设计与工程", "包装工程", "印刷"]),
    ("eng", "生物医学工程类", "生医工程", ["生物医学工程", "医疗器械", "假肢", "康复工程"]),
    ("sci", "数学类", "数学", ["数学", "信息与计算科学", "统计学", "应用统计"]),
    ("sci", "物理类", "物理", ["物理学", "应用物理", "声学", "光学", "核物理"]),
    ("sci", "化学类", "化学", ["化学", "应用化学", "分子科学"]),
    ("sci", "生物科学类", "生物", ["生物科学", "生物技术", "生物信息", "生态学", "生物工程", "生命科学"]),
    ("sci", "地理与大气类", "地理", ["地理", "大气科学", "海洋科学", "地质", "地球物理", "测绘与地理"]),
    ("sci", "心理学类", "心理学", ["心理学"]),
    ("med", "临床医学类", "临床医学", ["临床医学", "麻醉", "医学影像", "眼视光医学", "精神医学", "儿科学", "放射医学"]),
    ("med", "口腔医学类", "口腔医学", ["口腔"]),
    ("med", "中医学类", "中医学", ["中医学", "针灸", "推拿", "中西医结合", "中药学", "中药"]),
    ("med", "护理与康复类", "护理康复", ["护理", "康复", "助产"]),
    ("med", "药学类", "药学", ["药学", "药物制剂", "临床药学", "药事管理"]),
    ("med", "公共卫生与医学技术类", "公卫医技", ["预防医学", "卫生检验", "医学检验", "食品卫生", "健康服务", "公共事业管理（卫生", "卫生监督"]),
    ("eco", "经济学类", "经济学", ["经济学", "经济统计", "数字经济", "劳动经济", "资源与环境经济"]),
    ("eco", "金融学类", "金融", ["金融", "投资", "保险", "信用管理", "金融科技", "精算"]),
    ("eco", "经贸类", "经贸", ["国际经济与贸易", "贸易经济", "国际商务", "跨境电商", "商务经济"]),
    ("eco", "财政与税收类", "财政税收", ["财政学", "税收学"]),
    ("mgt", "工商管理类", "工商管理", ["工商管理", "市场营销", "人力资源管理", "企业管理", "文化产业管理", "医药营销"]),
    ("mgt", "会计与财务类", "会计财务", ["会计学", "财务管理", "审计学", "会计"]),
    ("mgt", "物流与电商类", "物流电商", ["物流管理", "物流工程", "电子商务", "供应链管理", "采购管理"]),
    ("mgt", "公共管理类", "公共管理", ["行政管理", "公共事业管理", "土地资源管理", "城市管理", "劳动与社会保障", "健康服务与管理", "海关管理"]),
    ("mgt", "旅游与服务类", "旅游服务", ["旅游管理", "酒店管理", "会展经济", "航空服务"]),
    ("mgt", "管理与信息系统类", "信管", ["信息管理与信息系统", "大数据管理与应用", "工程管理", "管理科学"]),
    ("lit", "中国语言文学类", "中文", ["汉语言文学", "汉语国际教育", "汉语言", "秘书学", "中国语言"]),
    ("lit", "外国语言文学类", "外语", ["英语", "日语", "俄语", "德语", "法语", "西班牙语", "朝鲜语", "翻译", "商务英语", "阿拉伯语", "葡萄牙语", "外国语言"]),
    ("lit", "新闻传播类", "新闻传播", ["新闻", "广播电视", "广告学", "传播", "网络与新媒体", "编辑出版", "主持"]),
    ("law", "法学类", "法学", ["法学", "知识产权", "国际经贸规则"]),
    ("law", "政治学与思政类", "政治思政", ["思想政治教育", "政治学", "国际政治", "外交学"]),
    ("law", "社会学类", "社会学", ["社会学", "社会工作", "社会政策", "家政学", "人类学", "民族学"]),
    ("law", "公安类", "公安", ["治安学", "侦查", "公安", "警务", "法学（公安"]),
    ("edu", "教育学类", "教育学", ["教育学", "教育技术", "学前教育", "小学教育", "科学教育", "特殊教育", "教育康复", "艺术教育"]),
    ("edu", "体育类", "体育", ["体育教育", "运动训练", "社会体育", "运动康复", "体育"]),
    ("his", "历史学类", "历史学", ["历史学", "考古", "文物", "世界史"]),
    ("his", "哲学类", "哲学", ["哲学", "逻辑学", "宗教学"]),
    ("agr", "植物与动物类", "农林", ["农学", "园艺", "植物保护", "种子科学", "林学", "园林", "动物科学", "动物医学", "水产", "草业"]),
    ("agr", "农业工程与食品类", "农业工程", ["农业工程", "农业机械化", "农业水利", "食品科学", "粮食工程"]),
    ("art", "艺术设计类", "艺术设计", ["视觉传达", "环境设计", "产品设计", "服装与服饰", "数字媒体艺术", "公共艺术", "工艺美术", "艺术设计"]),
    ("art", "音乐与表演类", "音乐表演", ["音乐", "舞蹈", "表演", "戏剧", "播音"]),
    ("art", "美术类", "美术", ["美术学", "绘画", "雕塑", "摄影", "书法"]),
]

CATEGORY_NAMES = {
    "eng": "工学", "sci": "理学", "med": "医学", "eco": "经济学", "mgt": "管理学",
    "lit": "文学", "law": "法学", "edu": "教育学", "his": "历史学·哲学",
    "agr": "农学", "art": "艺术学", "other": "其他",
}

# 第二批补充：主表没覆盖到的长尾专业名（按频次人工看过一遍）
EXTRA: list[tuple[str, str, str, list[str]]] = [
    ("eng", "机械类", "机械", ["智能制造", "焊接技术", "智能装备", "增材制造"]),
    ("eng", "土木建筑类", "土木建筑", ["水利", "水文", "港口航道", "海岸工程", "地下空间", "市政工程", "建筑电气", "消防工程"]),
    ("eng", "计算机类", "计算机", ["虚拟现实", "智能交互", "数据计算"]),
    ("eng", "资源与矿业类", "资源矿业", ["资源勘查", "勘查技术", "采矿", "石油工程", "油气储运", "冶金", "矿物加工", "地质工程", "城市地下"]),
    ("eng", "航空航天与交通类", "航空航天交通", ["无人驾驶航空器", "低空技术", "飞行技术", "智慧交通", "轨道交通"]),
    ("eng", "生物医学工程类", "生医工程", ["智能医学工程", "医学信息工程", "生物医学"]),
    ("sci", "力学类", "力学", ["工程力学", "理论与应用力学", "力学"]),
    ("sci", "地理与大气类", "地理", ["遥感科学", "遥感科学与技术"]),
    ("sci", "生物科学类", "生物", ["合成生物", "生物育种"]),
    ("med", "基础与法医学类", "基础医学", ["基础医学", "法医学"]),
    ("med", "中医学类", "中医学", ["中医骨伤", "中医"]),
    ("mgt", "公共管理类", "公共管理", ["公共管理", "应急管理", "养老", "土地资源"]),
    ("mgt", "会计与财务类", "会计财务", ["资产评估", "审计"]),
    ("mgt", "管理与信息系统类", "信管", ["工业工程", "标准化工程", "质量管理"]),
    ("eco", "经济学类", "经济学", ["农林经济", "经济"]),
    ("agr", "植物与动物类", "农林", ["智慧农业", "设施农业", "农业资源", "种子科学", "园艺", "动植物检疫"]),
    ("law", "政治学与思政类", "政治思政", ["马克思主义", "政治学"]),
    ("art", "艺术管理类", "艺术管理", ["艺术管理", "文化产业管理"]),
    ("other", "试验班与预科", "trial", ["试验班", "预科", "专项计划"]),
]


def strip_brackets(text: str) -> str:
    """去掉括号及其中的说明，允许嵌套，也容忍多余的右括号。

    辽宁的投档表里有「专业类[具体专业(方向)]」这种嵌套写法。正则只能剥掉最内层，
    删完会留下孤零零的右括号（``法学类]``），所以这里用手写的计数法：进入括号后
    整段丢弃，多出来的右括号一并丢掉。
    """
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch in "（([【":
            depth += 1
        elif ch in "）)]】":
            if depth > 0:
                depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def normalise(raw: str) -> str:
    """去掉括号里的说明，再做一次全角/半角空白压缩。"""
    return CLEAN.sub("", strip_brackets(raw or "").strip())


def classify(name: str) -> tuple[str, str, str]:
    for cat, group, gid, keywords in (*RULES, *EXTRA):
        for word in keywords:
            if word in name:
                return cat, group, gid
    return "other", "其他", "other"


def main() -> None:
    stats: dict[str, dict] = {}
    for path in sorted(glob.glob(str(DATA / "*" / "toudang_*.csv"))):
        province_key = Path(path).parent.name
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = normalise(row.get("unit_name", ""))
                if not name:
                    continue
                try:
                    score = int(row.get("score") or 0)
                except ValueError:
                    continue
                item = stats.setdefault(
                    name,
                    {"name": name, "count": 0, "provinces": set(), "scores": [], "prov": {}},
                )
                item["count"] += 1
                item["provinces"].add(province_key)
                bucket = item["prov"].setdefault(province_key, {"count": 0, "scores": []})
                bucket["count"] += 1
                if score:
                    item["scores"].append(score)
                    bucket["scores"].append(score)

    majors = []
    for item in stats.values():
        if item["count"] < 5:
            continue
        cat, group, gid = classify(item["name"])
        scores = sorted(item["scores"])
        majors.append({
            "name": item["name"],
            "count": item["count"],
            "provinces": sorted(item["provinces"]),
            "score_min": scores[0] if scores else 0,
            "score_max": scores[-1] if scores else 0,
            "score_median": int(median(scores)) if scores else 0,
            "category": cat,
            "group": group,
            "group_id": gid,
            "is_group": bool(GROUPISH.search(item["name"])),
            "by_province": {
                key: {
                    "count": bucket["count"],
                    "median": int(median(bucket["scores"])) if bucket["scores"] else 0,
                }
                for key, bucket in item["prov"].items()
            },
        })

    majors.sort(key=lambda m: (-m["count"], m["name"]))

    groups: dict[str, dict] = {}
    for major in majors:
        key = major["group_id"]
        bucket = groups.setdefault(
            key,
            {
                "id": key,
                "name": major["group"],
                "category": major["category"],
                "category_name": CATEGORY_NAMES[major["category"]],
                "count": 0,
            },
        )
        bucket["count"] += 1

    catalog = {
        "version": 1,
        "source": "八省 2026 年投档表里的专业名去重归一（出现 ≥5 次）",
        "total_majors": len(majors),
        "total_rows": sum(m["count"] for m in majors),
        "categories": [
            {
                "id": cat,
                "name": name,
                "groups": sorted(
                    [g for g in groups.values() if g["category"] == cat],
                    key=lambda g: -g["count"],
                ),
            }
            for cat, name in CATEGORY_NAMES.items()
            if any(g["category"] == cat for g in groups.values())
        ],
        "majors": majors,
    }

    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {OUT}")
    print(f"专业 {len(majors)} 个，覆盖 {catalog['total_rows']} 个招生单元，{len(groups)} 个专业类")
    for cat in catalog["categories"]:
        names = " / ".join(f"{g['name']}{g['count']}" for g in cat["groups"])
        print(f"  {cat['name']:6s} {names}")


if __name__ == "__main__":
    main()
