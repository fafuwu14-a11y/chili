"""功能 02：选科问卷（高一版）—— 用情景问答代替量表。

设计原则（对着高一学生）：

1. **不问「你喜不喜欢物理」**，问「如果学校开放一间实验室给你随便用，你想做」。
   高一学生对自己的学科偏好往往说不清，但对具体场景有直觉。
2. **四选一为主**，每题 4 个选项分别指向不同学科 / 专业簇，一次点击给多维度加分。
3. **少量五级量表**只用于能力自评和价值观，这两类东西问不出情景。
4. 全程 23 题、约 6 分钟，答完立刻有结果，不依赖 AI。

题目结构：

    kind = "single"  四选一，每个选项 scores 打到 subject / cluster / ability
    kind = "scale"   五级量表，dim 指定打到哪个 ability / value 维度

维度：
    subject  7 门选考学科  physics chemistry biology politics history geography technology
    ability  6 维能力      logic memory handson expression data spatial
    cluster  12 个专业簇   tech eng med agri sci biz law edu humanities art social police
    value    4 个取向      stability salary research interest
"""

from __future__ import annotations

SUBJECT_KEYS = ("physics", "chemistry", "biology", "politics", "history", "geography", "technology")
SUBJECT_NAMES = {
    "physics": "物理", "chemistry": "化学", "biology": "生物", "politics": "政治",
    "history": "历史", "geography": "地理", "technology": "技术",
}

ABILITY_KEYS = ("logic", "memory", "handson", "expression", "data", "spatial")
ABILITY_NAMES = {
    "logic": "逻辑推理", "memory": "记忆归纳", "handson": "动手实验",
    "expression": "表达沟通", "data": "数据分析", "spatial": "空间想象",
}

CLUSTER_KEYS = (
    "tech", "eng", "med", "agri", "sci", "biz",
    "law", "edu", "humanities", "art", "social", "police",
)
CLUSTER_NAMES = {
    "tech": "信息与智能", "eng": "工程与制造", "med": "医学与健康",
    "agri": "农林与食品", "sci": "基础科学", "biz": "经济与管理",
    "law": "法学与公共事务", "edu": "教育与体育", "humanities": "人文与语言",
    "art": "艺术与设计", "social": "社会与人际", "police": "公安与安全",
}

VALUE_KEYS = ("stability", "salary", "research", "interest")
VALUE_NAMES = {
    "stability": "稳定优先", "salary": "收入优先",
    "research": "科研深造", "interest": "兴趣优先",
}

SCALE = {
    "min": 1, "max": 5,
    "labels": ["完全不符合", "不太符合", "说不好", "比较符合", "非常符合"],
}

QUESTIONS = (
    # ---------------- A 组：学科趣味（8 题） ----------------
    {
        "id": "q1", "kind": "single", "group": "interest", "topic": "学科趣味",
        "title": "学校开放一间实验室给你随便用，你最想做什么？",
        "hint": "别想成绩，想「哪件事我愿意干一下午」。",
        "options": [
            {"id": "a", "text": "组装一台机器人，写程序让它自己走",
             "scores": {"subject": {"technology": 3, "physics": 2}, "cluster": {"tech": 3, "eng": 2}}, "tags": ["tech"]},
            {"id": "b", "text": "配试剂、看颜色变化，把一种物质提纯出来",
             "scores": {"subject": {"chemistry": 3}, "cluster": {"sci": 3, "med": 1}}, "tags": ["chem"]},
            {"id": "c", "text": "培养微生物、观察细胞，搞清楚它怎么活",
             "scores": {"subject": {"biology": 3, "chemistry": 1}, "cluster": {"med": 3, "agri": 2}}, "tags": ["bio"]},
            {"id": "d", "text": "测地形、分析气象数据，画一张别人没画过的图",
             "scores": {"subject": {"geography": 3, "physics": 1}, "cluster": {"sci": 2, "eng": 2}}, "tags": ["geo"]},
        ],
    },
    {
        "id": "q2", "kind": "single", "group": "interest", "topic": "学科趣味",
        "title": "刷到一篇长文章，哪种标题最让你点进去？",
        "hint": "第一反应，不要选「应该看」的那个。",
        "options": [
            {"id": "a", "text": "《一项新技术，正在悄悄改写这个行业》",
             "scores": {"subject": {"technology": 2}, "cluster": {"tech": 3}}, "tags": ["tech"]},
            {"id": "b", "text": "《这场战役为什么输？三个被忽略的细节》",
             "scores": {"subject": {"history": 3, "politics": 2}, "cluster": {"humanities": 3, "social": 1}}, "tags": ["history"]},
            {"id": "c", "text": "《一个物种是怎么演化出这种能力的》",
             "scores": {"subject": {"biology": 3}, "cluster": {"sci": 2, "agri": 2}}, "tags": ["bio"]},
            {"id": "d", "text": "《一项政策落地后，普通人的账本变了多少》",
             "scores": {"subject": {"politics": 3}, "cluster": {"biz": 2, "social": 2, "law": 1}}, "tags": ["politics"]},
        ],
    },
    {
        "id": "q3", "kind": "single", "group": "interest", "topic": "学科趣味",
        "title": "小组作业里，你自然而然会接手哪部分？",
        "hint": "看你「做得快还不烦」的那件事。",
        "options": [
            {"id": "a", "text": "算数据、建模型、把结论算出来",
             "scores": {"subject": {"physics": 2, "technology": 1}, "ability": {"logic": 2, "data": 3}, "cluster": {"sci": 2, "tech": 2}}, "tags": ["logic"]},
            {"id": "b", "text": "写报告、做 PPT、上台讲",
             "scores": {"ability": {"expression": 3}, "cluster": {"humanities": 2, "art": 1, "biz": 1}}, "tags": ["expr"]},
            {"id": "c", "text": "查资料、理时间线、把来龙去脉搞清楚",
             "scores": {"subject": {"history": 2, "politics": 1}, "ability": {"memory": 2, "logic": 1}, "cluster": {"humanities": 2, "law": 1}}, "tags": ["history"]},
            {"id": "d", "text": "协调分工、催进度、处理组内矛盾",
             "scores": {"ability": {"expression": 2}, "cluster": {"biz": 2, "social": 2, "law": 1, "edu": 1}}, "tags": ["social"]},
        ],
    },
    {
        "id": "q4", "kind": "single", "group": "ability", "topic": "能力自评",
        "title": "下面哪句话最像你同学对你的评价？",
        "hint": "同学的原话通常比自我评价准。",
        "options": [
            {"id": "a", "text": "「他一听就能把复杂的东西拆成几步」",
             "scores": {"ability": {"logic": 3, "data": 1}, "subject": {"physics": 1}, "cluster": {"tech": 1, "sci": 1}}, "tags": ["logic"]},
            {"id": "b", "text": "「他记性好，年代、公式、条文张口就来」",
             "scores": {"ability": {"memory": 3}, "subject": {"history": 1, "politics": 1}, "cluster": {"law": 1, "med": 1}}, "tags": ["memory"]},
            {"id": "c", "text": "「他动手快，东西坏了找他」",
             "scores": {"ability": {"handson": 3, "spatial": 1}, "subject": {"technology": 1, "physics": 1}, "cluster": {"eng": 2}}, "tags": ["handson"]},
            {"id": "d", "text": "「他嘴皮子利索，能把人说服」",
             "scores": {"ability": {"expression": 3}, "cluster": {"law": 2, "biz": 2, "social": 1}}, "tags": ["expr"]},
        ],
    },
    {
        "id": "q5", "kind": "single", "group": "interest", "topic": "学科趣味",
        "title": "新闻说「某地发现一座大型矿」，你第一反应是？",
        "hint": "第一反应暴露真实兴趣。",
        "options": [
            {"id": "a", "text": "这矿是怎么形成的？多少年？",
             "scores": {"subject": {"geography": 3}, "cluster": {"sci": 2, "eng": 1}}, "tags": ["geo"]},
            {"id": "b", "text": "开采会不会污染地下水？",
             "scores": {"subject": {"chemistry": 2, "geography": 1}, "cluster": {"eng": 2, "agri": 1, "sci": 1}}, "tags": ["chem"]},
            {"id": "c", "text": "这对当地经济和就业意味着什么？",
             "scores": {"subject": {"politics": 2}, "cluster": {"biz": 3}}, "tags": ["biz"]},
            {"id": "d", "text": "其他国家会不会来抢？",
             "scores": {"subject": {"politics": 3, "history": 1}, "cluster": {"social": 2, "law": 2}}, "tags": ["politics"]},
        ],
    },
    {
        "id": "q6", "kind": "single", "group": "interest", "topic": "学科趣味",
        "title": "如果每周多两节选修课，你会选哪门？",
        "hint": "选你真会去上的，不是家长让你上的。",
        "options": [
            {"id": "a", "text": "编程与算法：让电脑替你干活",
             "scores": {"subject": {"technology": 3}, "cluster": {"tech": 3}}, "tags": ["tech"]},
            {"id": "b", "text": "人体与健康：身体是怎么运转的",
             "scores": {"subject": {"biology": 3}, "cluster": {"med": 3}}, "tags": ["bio"]},
            {"id": "c", "text": "国际关系：世界为什么这样运转",
             "scores": {"subject": {"politics": 3, "history": 1}, "cluster": {"social": 3, "law": 2}}, "tags": ["politics"]},
            {"id": "d", "text": "天文与宇宙：我们从哪来",
             "scores": {"subject": {"physics": 3, "geography": 1}, "cluster": {"sci": 3}}, "tags": ["physics"]},
        ],
    },
    {
        "id": "q7", "kind": "single", "group": "interest", "topic": "学科趣味",
        "title": "实验做失败了，数据全废，你会？",
        "hint": "你处理挫折的方式，就是你在这一科能走多远。",
        "options": [
            {"id": "a", "text": "改一个参数重做，每次记录变化",
             "scores": {"subject": {"chemistry": 2, "physics": 1}, "ability": {"logic": 2, "handson": 2}, "cluster": {"sci": 2}}, "tags": ["chem"]},
            {"id": "b", "text": "先查别人怎么做的，找现成方案",
             "scores": {"ability": {"memory": 2, "logic": 1}, "cluster": {"sci": 1, "eng": 2}}, "tags": ["memory"]},
            {"id": "c", "text": "找人聊聊，听不同思路",
             "scores": {"ability": {"expression": 2}, "cluster": {"social": 2, "biz": 1, "edu": 1}}, "tags": ["social"]},
            {"id": "d", "text": "推倒重来，换一条完全不同的路",
             "scores": {"subject": {"technology": 1}, "ability": {"spatial": 1, "logic": 1}, "cluster": {"tech": 2, "art": 1}}, "tags": ["tech"]},
        ],
    },
    {
        "id": "q8", "kind": "single", "group": "value", "topic": "价值取向",
        "title": "想象十年后一个普通工作日，你更想在哪儿？",
        "hint": "不要想「体面」，想「待得住」。",
        "options": [
            {"id": "a", "text": "实验室或机房，安静、专注、少应酬",
             "scores": {"value": {"research": 2}, "cluster": {"sci": 2, "tech": 2}}, "tags": ["lab"]},
            {"id": "b", "text": "户外或现场，跑动多、每天不一样",
             "scores": {"value": {"interest": 1}, "cluster": {"eng": 2, "agri": 2}}, "tags": ["field"]},
            {"id": "c", "text": "会议室或谈判桌，和人打交道",
             "scores": {"value": {"salary": 2}, "cluster": {"biz": 3, "law": 1}}, "tags": ["biz"]},
            {"id": "d", "text": "自己的工作室，自由安排节奏",
             "scores": {"value": {"interest": 2}, "cluster": {"art": 3, "humanities": 1}}, "tags": ["art"]},
        ],
    },

    # ---------------- B 组：能力自评（5 题，五级量表） ----------------
    {
        "id": "q9", "kind": "scale", "group": "ability", "topic": "能力自评", "dim": "logic",
        "title": "我能跟上数学课上的推导，看到图形能想象出立体关系。",
        "hint": "按最近一次考试和作业的真实感受打分。",
    },
    {
        "id": "q10", "kind": "scale", "group": "ability", "topic": "能力自评", "dim": "memory",
        "title": "背东西对我来说不算痛苦，年代、条文、单词记得住。",
        "hint": "政治、历史、生物都有大量记忆成分。",
    },
    {
        "id": "q11", "kind": "scale", "group": "ability", "topic": "能力自评", "dim": "handson",
        "title": "实验课上我更愿意自己动手，而不是看别人做。",
        "hint": "物理、化学、生物的实验占分不低。",
    },
    {
        "id": "q12", "kind": "scale", "group": "ability", "topic": "能力自评", "dim": "expression",
        "title": "写文章、做汇报、当众讲话，我不发怵。",
        "hint": "文科和大部分专业的答辩都靠这个。",
    },
    {
        "id": "q13", "kind": "scale", "group": "ability", "topic": "能力自评", "dim": "data",
        "title": "看表格、读图表、从数据里找规律，我上手很快。",
        "hint": "新高考地理、生物、经济类都吃这个能力。",
    },

    # ---------------- C 组：专业情境（6 题） ----------------
    {
        "id": "q14", "kind": "single", "group": "cluster", "topic": "专业情境",
        "title": "如果让你在医院待一天，你最想去哪个科室？",
        "hint": "选你真好奇的，不是听起来最赚钱的。",
        "options": [
            {"id": "a", "text": "急诊或手术室，抢救、见生死",
             "scores": {"cluster": {"med": 3}, "subject": {"biology": 2, "chemistry": 1}}, "tags": ["clinical"]},
            {"id": "b", "text": "口腔科，精细、手要稳",
             "scores": {"cluster": {"med": 2}, "ability": {"handson": 2}, "subject": {"biology": 1}}, "tags": ["stomatology"]},
            {"id": "c", "text": "影像科，看片子、找病灶",
             "scores": {"cluster": {"med": 2}, "ability": {"spatial": 1, "data": 1}, "subject": {"physics": 1, "biology": 1}}, "tags": ["imaging"]},
            {"id": "d", "text": "疾控或公共卫生，管一群人而不是一个人",
             "scores": {"cluster": {"med": 1, "social": 2, "law": 1}, "subject": {"biology": 1, "politics": 1}}, "tags": ["public_health"]},
        ],
    },
    {
        "id": "q15", "kind": "single", "group": "cluster", "topic": "专业情境",
        "title": "一座老城区要改造，你想参与哪个环节？",
        "hint": "同一个项目，四种完全不同的专业。",
        "options": [
            {"id": "a", "text": "设计新建筑和街区形态",
             "scores": {"cluster": {"eng": 2, "art": 2}, "ability": {"spatial": 2}, "subject": {"physics": 1}}, "tags": ["architecture"]},
            {"id": "b", "text": "算结构、管施工、保证不倒",
             "scores": {"cluster": {"eng": 3}, "subject": {"physics": 2}, "ability": {"logic": 1}}, "tags": ["civil"]},
            {"id": "c", "text": "做规划，决定哪里拆哪里留",
             "scores": {"cluster": {"eng": 1, "social": 1, "law": 1}, "subject": {"geography": 2, "politics": 1}}, "tags": ["planning"]},
            {"id": "d", "text": "把老街区做成文旅项目",
             "scores": {"cluster": {"biz": 2, "humanities": 1, "art": 1}, "subject": {"geography": 1, "history": 1}}, "tags": ["tourism"]},
        ],
    },
    {
        "id": "q16", "kind": "single", "group": "cluster", "topic": "专业情境",
        "title": "一家公司要进入一个新市场，你想负责哪块？",
        "hint": "商业链条上，你站哪一环。",
        "options": [
            {"id": "a", "text": "研究用户、定价、怎么卖",
             "scores": {"cluster": {"biz": 3}, "subject": {"politics": 1}, "ability": {"expression": 1, "data": 1}}, "tags": ["marketing"]},
            {"id": "b", "text": "算钱、控风险、看报表",
             "scores": {"cluster": {"biz": 2}, "ability": {"data": 2, "logic": 1}}, "tags": ["finance"]},
            {"id": "c", "text": "审合同、防合规风险",
             "scores": {"cluster": {"law": 3}, "subject": {"politics": 2}, "ability": {"memory": 1}}, "tags": ["law"]},
            {"id": "d", "text": "管供应链、仓储、物流",
             "scores": {"cluster": {"biz": 1, "eng": 2}, "ability": {"logic": 1, "data": 1}}, "tags": ["logistics"]},
        ],
    },
    {
        "id": "q17", "kind": "single", "group": "cluster", "topic": "专业情境",
        "title": "一个 App 从 0 做到 1，你想负责哪部分？",
        "hint": "互联网公司里的四种典型岗位。",
        "options": [
            {"id": "a", "text": "写代码，把功能实现出来",
             "scores": {"cluster": {"tech": 3}, "subject": {"technology": 2}, "ability": {"logic": 2}}, "tags": ["dev"]},
            {"id": "b", "text": "做界面和交互，让它好用",
             "scores": {"cluster": {"art": 2, "tech": 1}, "ability": {"spatial": 1, "expression": 1}}, "tags": ["design"]},
            {"id": "c", "text": "做算法，让它更聪明",
             "scores": {"cluster": {"tech": 2, "sci": 2}, "subject": {"physics": 1, "technology": 1}, "ability": {"logic": 2, "data": 2}}, "tags": ["algorithm"]},
            {"id": "d", "text": "做运营，拉用户、看数据、改策略",
             "scores": {"cluster": {"biz": 2, "tech": 1}, "ability": {"expression": 1, "data": 2}}, "tags": ["ops"]},
        ],
    },
    {
        "id": "q18", "kind": "single", "group": "cluster", "topic": "专业情境",
        "title": "老家想发展特色农业，你最想帮上哪一环？",
        "hint": "农业早就不是「种地」两个字了。",
        "options": [
            {"id": "a", "text": "改良品种、提高产量和抗病性",
             "scores": {"cluster": {"agri": 3, "sci": 1}, "subject": {"biology": 2, "chemistry": 1}}, "tags": ["plant"]},
            {"id": "b", "text": "搞养殖、防病害",
             "scores": {"cluster": {"agri": 2}, "subject": {"biology": 2}, "ability": {"handson": 1}}, "tags": ["animal"]},
            {"id": "c", "text": "做深加工，把果子变成能卖的食品",
             "scores": {"cluster": {"agri": 1, "eng": 2}, "subject": {"chemistry": 2}}, "tags": ["food"]},
            {"id": "d", "text": "做品牌和电商，卖到全国",
             "scores": {"cluster": {"biz": 3, "agri": 1}, "ability": {"expression": 2}}, "tags": ["ecommerce"]},
        ],
    },
    {
        "id": "q19", "kind": "single", "group": "cluster", "topic": "专业情境",
        "title": "一件公共事件引发全网争论，你更想以什么身份介入？",
        "hint": "同样关心社会，四条完全不同的路。",
        "options": [
            {"id": "a", "text": "记者，去现场把事实挖出来",
             "scores": {"cluster": {"humanities": 2, "social": 2}, "ability": {"expression": 2}}, "tags": ["journalism"]},
            {"id": "b", "text": "律师，看程序和法律上站不站得住",
             "scores": {"cluster": {"law": 3}, "ability": {"logic": 1, "memory": 1}}, "tags": ["law"]},
            {"id": "c", "text": "公务员，把政策改得更合理",
             "scores": {"cluster": {"law": 1, "social": 2, "biz": 1, "police": 1}, "subject": {"politics": 2}}, "tags": ["public_admin"]},
            {"id": "d", "text": "研究者，用数据把机制说清楚",
             "scores": {"cluster": {"sci": 1, "social": 2}, "ability": {"data": 2, "logic": 1}}, "tags": ["research"]},
        ],
    },

    # ---------------- D 组：价值观（4 题，五级量表） ----------------
    {
        "id": "q20", "kind": "scale", "group": "value", "topic": "价值取向", "dim": "stability",
        "title": "「工作稳定、不容易失业」对我很重要。",
        "hint": "会影响师范、医学、公安、体制内方向的推荐权重。",
    },
    {
        "id": "q21", "kind": "scale", "group": "value", "topic": "价值取向", "dim": "salary",
        "title": "「收入高」比「工作轻松」更吸引我。",
        "hint": "不影响选科合法性，只影响专业排序。",
    },
    {
        "id": "q22", "kind": "scale", "group": "value", "topic": "价值取向", "dim": "research",
        "title": "我愿意读到硕士甚至博士，不急着工作。",
        "hint": "医学、基础科学、法学对长学制依赖度高。",
    },
    {
        "id": "q23", "kind": "scale", "group": "value", "topic": "价值取向", "dim": "interest",
        "title": "就算某个专业不好找工作，只要我真喜欢，我也认。",
        "hint": "诚实地答，这题决定我们怎么帮你权衡。",
    },
)

_BY_ID = {q["id"]: q for q in QUESTIONS}


def questions() -> tuple:
    """整套题（前端按顺序渲染）。"""
    return QUESTIONS


def get(question_id: str):
    return _BY_ID.get(question_id)


def public_questions(edition: str = "simple") -> list[dict]:
    """给前端渲染用的题目：**不含 scores**。

    权重留在服务端，前端拿到的只是题干和选项文案；改前端也刷不出分。
    """
    items: list[dict] = []
    for q in questions_for(edition):
        item = {
            key: q[key]
            for key in ("id", "kind", "group", "topic", "dim", "title", "hint")
            if key in q
        }
        if q["kind"] == "single":
            item["options"] = [{"id": o["id"], "text": o["text"]} for o in q["options"]]
        items.append(item)
    return items


def meta(edition: str = "simple") -> dict:
    """给前端做开场页的元信息。"""
    bank = questions_for(edition)
    spec = SPEC_INDEX.get(edition, SPEC_SIMPLE)
    single = sum(1 for q in bank if q["kind"] == "single")
    scale = sum(1 for q in bank if q["kind"] == "scale")
    groups: dict[str, int] = {}
    for q in bank:
        groups[q["group"]] = groups.get(q["group"], 0) + 1
    return {
        "count": len(bank),
        "single": single,
        "scales": scale,
        "minutes": spec["minutes"],
        "edition": spec["key"],
        "editions": [
            {k: v for k, v in s.items() if k != "groups"} for s in SPECS
        ],
        "groups": groups,
        "subjects": [{"key": k, "name": SUBJECT_NAMES[k]} for k in SUBJECT_KEYS],
        "abilities": [{"key": k, "name": ABILITY_NAMES[k]} for k in ABILITY_KEYS],
        "clusters": [{"key": k, "name": CLUSTER_NAMES[k]} for k in CLUSTER_KEYS],
        "values": [{"key": k, "name": VALUE_NAMES[k]} for k in VALUE_KEYS],
        "scale": SCALE,
    }


def validate(answers: dict, edition: str = "simple") -> list[str]:
    """检查答案是否完整合法，返回错误信息列表（空列表 = 通过）。"""
    errors: list[str] = []
    if not isinstance(answers, dict):
        return ["answers 必须是 {题号: 选项} 的对象"]
    for q in questions_for(edition):
        qid = q["id"]
        if qid not in answers:
            errors.append(f"缺少第 {qid} 题")
            continue
        value = answers[qid]
        if q["kind"] == "single":
            ids = {opt["id"] for opt in q["options"]}
            if value not in ids:
                errors.append(f"第 {qid} 题选项 {value!r} 不存在，应为 {sorted(ids)}")
        else:
            try:
                num = int(value)
            except (TypeError, ValueError):
                errors.append(f"第 {qid} 题必须是 1-5 的整数")
                continue
            if not 1 <= num <= 5:
                errors.append(f"第 {qid} 题打分 {num} 超出 1-5")
    return errors

# --------------------------------------------------------------------------
# 深度版追加题（q24 起）：简易版不含这些题
# --------------------------------------------------------------------------
# 设计原则和前面一致：问具体场景，不问「你喜不喜欢这门课」。
# 简易版 23 题能分出大方向；深度版补的是「同一方向里到底偏向哪一支」——
# 比如同样偏理科，是更喜欢动手做装置，还是更喜欢坐下来推公式。
EXTRA_QUESTIONS = (
    # ---------------- C 组：学科细分（10 题） ----------------
    {
        "id": "q24", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "物理里这几块内容，哪一块你愿意多花一小时？",
        "hint": "不用管哪块好考，想哪块你想得下去。",
        "options": [
            {"id": "a", "text": "力学与运动：为什么球这样飞、车这样刹",
             "scores": {"subject": {"physics": 3}, "ability": {"logic": 2, "spatial": 1}, "cluster": {"eng": 2, "sci": 1}}, "tags": ["physics"]},
            {"id": "b", "text": "电与磁：电路怎么搭、信号怎么走",
             "scores": {"subject": {"physics": 2, "technology": 2}, "ability": {"handson": 2}, "cluster": {"tech": 2, "eng": 2}}, "tags": ["electric"]},
            {"id": "c", "text": "光学与波动：彩虹、透镜、声音的传播",
             "scores": {"subject": {"physics": 3}, "ability": {"spatial": 2}, "cluster": {"sci": 3}}, "tags": ["optics"]},
            {"id": "d", "text": "原子与量子：看不见的世界怎么运作",
             "scores": {"subject": {"physics": 3, "chemistry": 1}, "ability": {"logic": 2}, "cluster": {"sci": 3}}, "tags": ["quantum"]},
        ],
    },
    {
        "id": "q25", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "化学实验课给你三样东西，你最想拿哪个开始？",
        "hint": "想「手伸向哪个」，不是「哪个分高」。",
        "options": [
            {"id": "a", "text": "几种溶液和试纸：我想看它们混起来会怎样",
             "scores": {"subject": {"chemistry": 3}, "ability": {"handson": 2}, "cluster": {"sci": 3}}, "tags": ["chem"]},
            {"id": "b", "text": "一台分析仪器：我想知道它怎么测出成分",
             "scores": {"subject": {"chemistry": 2, "physics": 1}, "ability": {"data": 2}, "cluster": {"sci": 2, "tech": 1}}, "tags": ["instrument"]},
            {"id": "c", "text": "一堆药品说明书：我想搞清楚这些成分干什么用",
             "scores": {"subject": {"chemistry": 2, "biology": 2}, "cluster": {"med": 3}}, "tags": ["pharma"]},
            {"id": "d", "text": "土壤和水样：我想测测这片地到底怎么样",
             "scores": {"subject": {"chemistry": 1, "geography": 2, "biology": 1}, "cluster": {"agri": 3, "sci": 1}}, "tags": ["env"]},
        ],
    },
    {
        "id": "q26", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "生物里你最想搞清楚的是哪一面？",
        "hint": "生物在不同人眼里是完全不同的学科。",
        "options": [
            {"id": "a", "text": "身体怎么运作、病是怎么来的",
             "scores": {"subject": {"biology": 3, "chemistry": 1}, "cluster": {"med": 3}}, "tags": ["bio"]},
            {"id": "b", "text": "基因、细胞、遗传规律",
             "scores": {"subject": {"biology": 3}, "ability": {"logic": 2}, "cluster": {"sci": 2, "med": 1}}, "tags": ["gene"]},
            {"id": "c", "text": "生态、物种、环境之间怎么互相影响",
             "scores": {"subject": {"biology": 2, "geography": 2}, "cluster": {"agri": 2, "sci": 2}}, "tags": ["eco"]},
            {"id": "d", "text": "动植物怎么养、怎么种、怎么改良",
             "scores": {"subject": {"biology": 2}, "ability": {"handson": 2}, "cluster": {"agri": 3, "edu": 1}}, "tags": ["farm"]},
        ],
    },
    {
        "id": "q27", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "班级要定一条新规则，讨论时你最想争的是？",
        "hint": "这条其实在测你对「制度怎么运转」的兴趣。",
        "options": [
            {"id": "a", "text": "这条规则对每个人是不是公平",
             "scores": {"subject": {"politics": 3}, "cluster": {"law": 3, "social": 1}}, "tags": ["politics"]},
            {"id": "b", "text": "执行起来成本高不高、能不能落地",
             "scores": {"subject": {"politics": 1}, "ability": {"logic": 2}, "cluster": {"biz": 2, "law": 1}}, "tags": ["biz"]},
            {"id": "c", "text": "大家愿不愿意接受、怎么说服人",
             "scores": {"subject": {"politics": 2}, "ability": {"expression": 2}, "cluster": {"social": 3, "edu": 1}}, "tags": ["social"]},
            {"id": "d", "text": "有没有先例、别的班怎么做的",
             "scores": {"subject": {"history": 2, "politics": 1}, "ability": {"memory": 2}, "cluster": {"law": 2, "humanities": 1}}, "tags": ["history"]},
        ],
    },
    {
        "id": "q28", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "给你一摞没人整理过的旧档案，你会先干什么？",
        "hint": "历史不是背年份，是处理材料。",
        "options": [
            {"id": "a", "text": "按时间排好，理出事情发生的顺序",
             "scores": {"subject": {"history": 3}, "ability": {"memory": 2, "logic": 1}, "cluster": {"humanities": 3}}, "tags": ["history"]},
            {"id": "b", "text": "找里面的矛盾和漏洞，看谁在说谎",
             "scores": {"subject": {"history": 2, "politics": 1}, "ability": {"logic": 2}, "cluster": {"law": 2, "social": 1}}, "tags": ["logic"]},
            {"id": "c", "text": "看里面的人怎么生活、怎么想事情",
             "scores": {"subject": {"history": 2}, "ability": {"expression": 1}, "cluster": {"humanities": 3, "art": 1}}, "tags": ["humanities"]},
            {"id": "d", "text": "把里面的数字和表格整理出来做统计",
             "scores": {"subject": {"history": 1}, "ability": {"data": 3}, "cluster": {"biz": 2, "sci": 1}}, "tags": ["data"]},
        ],
    },
    {
        "id": "q29", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "拿到一张陌生地区的地图，你最想从上面读出什么？",
        "hint": "地理既是文科也是理科，看你往哪边靠。",
        "options": [
            {"id": "a", "text": "这里为什么长成这样：山脉、河流、气候",
             "scores": {"subject": {"geography": 3}, "cluster": {"sci": 2}}, "tags": ["geo"]},
            {"id": "b", "text": "这里的人靠什么活：产业、交通、城市",
             "scores": {"subject": {"geography": 2, "politics": 1}, "cluster": {"biz": 2, "social": 1}}, "tags": ["econ"]},
            {"id": "c", "text": "这块地的边界和归属有什么讲究",
             "scores": {"subject": {"geography": 2, "politics": 2}, "cluster": {"law": 2, "social": 2}}, "tags": ["border"]},
            {"id": "d", "text": "我想自己画一张更清楚的图",
             "scores": {"subject": {"geography": 2, "technology": 1}, "ability": {"spatial": 3}, "cluster": {"art": 1, "tech": 2}}, "tags": ["spatial"]},
        ],
    },
    {
        "id": "q30", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "有件事你每周要重复做三小时，你最想怎么处理它？",
        "hint": "这题测的是「技术」这门课在你身上有没有根。",
        "options": [
            {"id": "a", "text": "写个小工具让它自动跑，我一次搞定",
             "scores": {"subject": {"technology": 3}, "ability": {"logic": 2, "data": 1}, "cluster": {"tech": 3}}, "tags": ["tech"]},
            {"id": "b", "text": "做个物理装置替代手工，省力就行",
             "scores": {"subject": {"technology": 2, "physics": 1}, "ability": {"handson": 3, "spatial": 1}, "cluster": {"eng": 3}}, "tags": ["eng"]},
            {"id": "c", "text": "重新设计流程，让它根本不需要做",
             "scores": {"ability": {"logic": 2}, "cluster": {"biz": 2, "tech": 1}}, "tags": ["biz"]},
            {"id": "d", "text": "找人分工，我只做最擅长那段",
             "scores": {"ability": {"expression": 2}, "cluster": {"social": 2, "biz": 1}}, "tags": ["social"]},
        ],
    },
    {
        "id": "q31", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "下面哪个「交叉问题」最让你想深挖？",
        "hint": "交叉学科是选科时最容易被忽略的机会。",
        "options": [
            {"id": "a", "text": "用算法预测一种材料的性能",
             "scores": {"subject": {"technology": 2, "chemistry": 1, "physics": 1}, "cluster": {"tech": 2, "sci": 2}}, "tags": ["tech"]},
            {"id": "b", "text": "某种疾病在人群里为什么这样分布",
             "scores": {"subject": {"biology": 2, "geography": 1}, "ability": {"data": 2}, "cluster": {"med": 2, "sci": 1}}, "tags": ["med"]},
            {"id": "c", "text": "一项政策出台后，普通家庭会怎么变",
             "scores": {"subject": {"politics": 2, "history": 1}, "cluster": {"social": 3, "law": 1}}, "tags": ["social"]},
            {"id": "d", "text": "机器能不能理解人的语言和情绪",
             "scores": {"subject": {"technology": 2}, "ability": {"logic": 2}, "cluster": {"tech": 3, "humanities": 1}}, "tags": ["ai"]},
        ],
    },
    {
        "id": "q32", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "一门课你学得吃力但确实有意思，你会？",
        "hint": "吃力时的选择，比顺风时更能说明你会走多远。",
        "options": [
            {"id": "a", "text": "多花时间啃，难才有意思",
             "scores": {"ability": {"logic": 2, "memory": 1}, "cluster": {"sci": 2}}, "tags": ["persist"]},
            {"id": "b", "text": "找同学一起讨论，边讲边理",
             "scores": {"ability": {"expression": 2}, "cluster": {"edu": 2, "social": 1}}, "tags": ["social"]},
            {"id": "c", "text": "先把能拿的分拿到，剩下的不较劲",
             "scores": {"value": {"stability": 1}, "cluster": {"biz": 1}}, "tags": ["pragmatic"]},
            {"id": "d", "text": "换个角度理解它，找和生活的联系",
             "scores": {"ability": {"spatial": 1}, "cluster": {"humanities": 1, "art": 1}}, "tags": ["creative"]},
        ],
    },
    {
        "id": "q33", "kind": "single", "group": "interest", "topic": "学科细分",
        "title": "同一门课，哪种学法你最舒服？",
        "hint": "方法适配比内容偏好更能预测成绩。",
        "options": [
            {"id": "a", "text": "刷题、总结规律，越练越熟",
             "scores": {"ability": {"logic": 2, "memory": 1}, "cluster": {"sci": 1, "eng": 1}}, "tags": ["drill"]},
            {"id": "b", "text": "看书、写笔记，自己慢慢想通",
             "scores": {"ability": {"memory": 2}, "cluster": {"humanities": 2, "med": 1}}, "tags": ["read"]},
            {"id": "c", "text": "动手做、实际试一遍",
             "scores": {"ability": {"handson": 3}, "cluster": {"eng": 2, "agri": 1}}, "tags": ["handson"]},
            {"id": "d", "text": "给别人讲一遍，讲明白才算学会",
             "scores": {"ability": {"expression": 3}, "cluster": {"edu": 3, "social": 1}}, "tags": ["teach"]},
        ],
    },

    # ---------------- D 组：专业情境·深度（12 题，十二个簇各一题） ----------------
    {
        "id": "q34", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "让你负责一个「让校园更智能」的小项目，你挑哪块？",
        "hint": "信息与智能这一类里，其实分很多活。",
        "options": [
            {"id": "a", "text": "写一个能自动回答问题的机器人",
             "scores": {"cluster": {"tech": 3}, "ability": {"logic": 2}, "subject": {"technology": 2}}, "tags": ["tech"]},
            {"id": "b", "text": "设计一套传感器，采集教室的温湿度",
             "scores": {"cluster": {"tech": 2, "eng": 2}, "ability": {"handson": 2}, "subject": {"physics": 1}}, "tags": ["iot"]},
            {"id": "c", "text": "分析校园卡数据，看学生什么时候最忙",
             "scores": {"cluster": {"tech": 1, "biz": 2, "sci": 1}, "ability": {"data": 3}}, "tags": ["data"]},
            {"id": "d", "text": "做界面和交互，让它看起来好用",
             "scores": {"cluster": {"art": 2, "tech": 2}, "ability": {"spatial": 1}}, "tags": ["design"]},
        ],
    },
    {
        "id": "q35", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "一座小桥要重修，你觉得最关键的环节是？",
        "hint": "工程与制造看的是你对「造东西」的哪一环有感觉。",
        "options": [
            {"id": "a", "text": "算清楚受力，保证不会塌",
             "scores": {"cluster": {"eng": 3}, "ability": {"logic": 2, "spatial": 1}, "subject": {"physics": 2}}, "tags": ["struct"]},
            {"id": "b", "text": "选材料、定工艺，控制成本",
             "scores": {"cluster": {"eng": 2, "biz": 2}, "subject": {"chemistry": 1}}, "tags": ["material"]},
            {"id": "c", "text": "现场组织施工、盯进度",
             "scores": {"cluster": {"eng": 2, "social": 1}, "ability": {"expression": 1}}, "tags": ["site"]},
            {"id": "d", "text": "设计成好看的地标",
             "scores": {"cluster": {"art": 2, "eng": 2}, "ability": {"spatial": 3}}, "tags": ["design"]},
        ],
    },
    {
        "id": "q36", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "医院里这些岗位，哪个你更愿意站一天？",
        "hint": "学医不只是当临床医生。",
        "options": [
            {"id": "a", "text": "门诊：一个个病人看过去，快速判断",
             "scores": {"cluster": {"med": 3}, "ability": {"logic": 1, "memory": 1}, "subject": {"biology": 2}}, "tags": ["clinic"]},
            {"id": "b", "text": "手术室：精细操作，一站几个小时",
             "scores": {"cluster": {"med": 3}, "ability": {"handson": 3}, "subject": {"biology": 2}}, "tags": ["surgery"]},
            {"id": "c", "text": "检验科：对着仪器和样本出结果",
             "scores": {"cluster": {"med": 2, "sci": 2}, "ability": {"data": 2}, "subject": {"chemistry": 2}}, "tags": ["lab"]},
            {"id": "d", "text": "公共卫生：管一片人群的健康",
             "scores": {"cluster": {"med": 1, "social": 2, "law": 1}, "ability": {"data": 1}}, "tags": ["public"]},
        ],
    },
    {
        "id": "q37", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "给你一块地，你最想用它做什么？",
        "hint": "农林与食品不只是种地。",
        "options": [
            {"id": "a", "text": "试种新品种，看哪种产量高品质好",
             "scores": {"cluster": {"agri": 3}, "subject": {"biology": 2}, "ability": {"handson": 2}}, "tags": ["crop"]},
            {"id": "b", "text": "办个加工厂，把农产品做成能卖的东西",
             "scores": {"cluster": {"agri": 2, "biz": 2}, "subject": {"chemistry": 1}}, "tags": ["food"]},
            {"id": "c", "text": "做成生态农场，搞观光和研学",
             "scores": {"cluster": {"agri": 2, "social": 1, "biz": 1}, "ability": {"expression": 1}}, "tags": ["eco"]},
            {"id": "d", "text": "研究这块地的土壤和微生物",
             "scores": {"cluster": {"agri": 1, "sci": 3}, "subject": {"biology": 2, "chemistry": 1}}, "tags": ["soil"]},
        ],
    },
    {
        "id": "q38", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "「基础科学」这一类，你最想追的是哪个问题？",
        "hint": "基础科学要能长期忍受「暂时没用」。",
        "options": [
            {"id": "a", "text": "宇宙怎么来的、物质最基本是什么",
             "scores": {"cluster": {"sci": 3}, "subject": {"physics": 3}, "ability": {"logic": 2}}, "tags": ["physics"]},
            {"id": "b", "text": "生命最初是怎么出现的",
             "scores": {"cluster": {"sci": 2, "med": 1}, "subject": {"biology": 3}}, "tags": ["bio"]},
            {"id": "c", "text": "数学里那些「没用但很美」的结构",
             "scores": {"cluster": {"sci": 3}, "subject": {"physics": 1}, "ability": {"logic": 3}}, "tags": ["math"]},
            {"id": "d", "text": "气候和地球系统怎么演化",
             "scores": {"cluster": {"sci": 2, "agri": 1}, "subject": {"geography": 3}}, "tags": ["geo"]},
        ],
    },
    {
        "id": "q39", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "学校旁边有家店一直亏钱，你觉得该先看什么？",
        "hint": "经济与管理看的是你对「钱怎么流动」的直觉。",
        "options": [
            {"id": "a", "text": "账本：收入和支出各是什么结构",
             "scores": {"cluster": {"biz": 3}, "ability": {"data": 2}}, "tags": ["account"]},
            {"id": "b", "text": "客人：为什么来过一次就不来了",
             "scores": {"cluster": {"biz": 2, "social": 1}, "ability": {"expression": 1}}, "tags": ["market"]},
            {"id": "c", "text": "对手：旁边那家为什么活得好",
             "scores": {"cluster": {"biz": 3}, "ability": {"logic": 2}}, "tags": ["strategy"]},
            {"id": "d", "text": "行业：这条路以后会不会没人走",
             "scores": {"cluster": {"biz": 2, "sci": 1}, "subject": {"politics": 1}}, "tags": ["trend"]},
        ],
    },
    {
        "id": "q40", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "小区要为加装电梯投票，你最想扮演什么角色？",
        "hint": "法学与公共事务关心的是「规则怎么定、怎么执行」。",
        "options": [
            {"id": "a", "text": "查清相关规定，看程序合不合法",
             "scores": {"cluster": {"law": 3}, "ability": {"memory": 2}, "subject": {"politics": 2}}, "tags": ["law"]},
            {"id": "b", "text": "组织投票、把各方意见汇总",
             "scores": {"cluster": {"social": 2, "law": 1}, "ability": {"expression": 2}}, "tags": ["organize"]},
            {"id": "c", "text": "算清费用分摊，找最优方案",
             "scores": {"cluster": {"biz": 2}, "ability": {"data": 2}}, "tags": ["cost"]},
            {"id": "d", "text": "站在老人和低层住户角度想问题",
             "scores": {"cluster": {"social": 2, "edu": 1}, "ability": {"expression": 1}}, "tags": ["empathy"]},
        ],
    },
    {
        "id": "q41", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "让你带一个十二人的小组，你最想改进哪件事？",
        "hint": "教育与体育的核心是「让人变好」。",
        "options": [
            {"id": "a", "text": "把复杂知识讲得谁都听得懂",
             "scores": {"cluster": {"edu": 3}, "ability": {"expression": 3}}, "tags": ["teach"]},
            {"id": "b", "text": "设计一套训练计划，让他们体能上去",
             "scores": {"cluster": {"edu": 2, "med": 1}, "ability": {"handson": 2}}, "tags": ["sport"]},
            {"id": "c", "text": "摸清每个人卡在哪，单独给方案",
             "scores": {"cluster": {"edu": 2, "social": 1}, "ability": {"logic": 1}}, "tags": ["coach"]},
            {"id": "d", "text": "做一套评估，量化他们进步了多少",
             "scores": {"cluster": {"edu": 1, "sci": 1}, "ability": {"data": 2}}, "tags": ["assess"]},
        ],
    },
    {
        "id": "q42", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "「把一件复杂的事讲给别人听」，你会选哪种形式？",
        "hint": "人文与语言不只是写作文。",
        "options": [
            {"id": "a", "text": "写一篇结构清楚的深度文章",
             "scores": {"cluster": {"humanities": 3}, "ability": {"expression": 3}, "subject": {"history": 1}}, "tags": ["write"]},
            {"id": "b", "text": "做一支短片，用画面说话",
             "scores": {"cluster": {"art": 2, "humanities": 1}, "ability": {"spatial": 1}}, "tags": ["video"]},
            {"id": "c", "text": "翻成另一种语言，让外面的人也能懂",
             "scores": {"cluster": {"humanities": 3}, "ability": {"memory": 2}}, "tags": ["translate"]},
            {"id": "d", "text": "做成播客，用对话讲明白",
             "scores": {"cluster": {"humanities": 1, "social": 2}, "ability": {"expression": 2}}, "tags": ["podcast"]},
        ],
    },
    {
        "id": "q43", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "学校要重做校服，你愿意负责哪一块？",
        "hint": "艺术与设计里，审美和落地是两种能力。",
        "options": [
            {"id": "a", "text": "定整体风格和配色",
             "scores": {"cluster": {"art": 3}, "ability": {"spatial": 2}}, "tags": ["art"]},
            {"id": "b", "text": "画款式图，让人一眼看懂",
             "scores": {"cluster": {"art": 3}, "ability": {"spatial": 2, "handson": 1}}, "tags": ["draw"]},
            {"id": "c", "text": "找厂家、谈价格、控质量",
             "scores": {"cluster": {"biz": 2, "art": 1}, "ability": {"expression": 1}}, "tags": ["biz"]},
            {"id": "d", "text": "发问卷收集同学意见",
             "scores": {"cluster": {"social": 2, "art": 1}, "ability": {"data": 1}}, "tags": ["survey"]},
        ],
    },
    {
        "id": "q44", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "社区里老人多、年轻人少，你觉得最该先做什么？",
        "hint": "社会与人际关心的是一群人的处境。",
        "options": [
            {"id": "a", "text": "建日间照料中心，解决吃饭和看护",
             "scores": {"cluster": {"social": 3, "med": 1}, "ability": {"expression": 1}}, "tags": ["care"]},
            {"id": "b", "text": "组织活动，让老人有事可做",
             "scores": {"cluster": {"social": 3, "edu": 1}, "ability": {"expression": 2}}, "tags": ["activity"]},
            {"id": "c", "text": "调研需求，写报告争取政策支持",
             "scores": {"cluster": {"social": 2, "law": 1}, "ability": {"data": 2}}, "tags": ["research"]},
            {"id": "d", "text": "引入智能设备，减少人力依赖",
             "scores": {"cluster": {"tech": 2, "social": 1}, "ability": {"logic": 1}}, "tags": ["tech"]},
        ],
    },
    {
        "id": "q45", "kind": "single", "group": "cluster", "topic": "专业情境·深入",
        "title": "「公安与安全」这一类，你觉得哪部分最像你？",
        "hint": "这个簇对体能、心理、纪律要求都很实。",
        "options": [
            {"id": "a", "text": "现场处置：突发情况下快速判断",
             "scores": {"cluster": {"police": 3}, "ability": {"logic": 1, "handson": 2}}, "tags": ["field"]},
            {"id": "b", "text": "案件侦破：从细节里还原真相",
             "scores": {"cluster": {"police": 2, "law": 2}, "ability": {"logic": 2, "memory": 1}}, "tags": ["detect"]},
            {"id": "c", "text": "技术取证：数据和设备里找证据",
             "scores": {"cluster": {"police": 2, "tech": 2}, "ability": {"data": 2}}, "tags": ["forensic"]},
            {"id": "d", "text": "社区警务：长期和一片人打交道",
             "scores": {"cluster": {"police": 2, "social": 2}, "ability": {"expression": 2}}, "tags": ["community"]},
        ],
    },

    # ---------------- E 组：能力追问（4 题，量表，同一维度换角度再测一次） ----------------
    {
        "id": "q46", "kind": "scale", "group": "ability", "topic": "能力追问", "dim": "spatial",
        "title": "看到一个立体图形，我能在脑子里把它转过来、拆开看。",
        "hint": "空间想象对工程、建筑、医学影像、设计都很关键。",
    },
    {
        "id": "q47", "kind": "scale", "group": "ability", "topic": "能力追问", "dim": "logic",
        "title": "一串条件摆在一起，我能很快看出它们能不能同时成立。",
        "hint": "这是判断推理的核心能力。",
    },
    {
        "id": "q48", "kind": "scale", "group": "ability", "topic": "能力追问", "dim": "expression",
        "title": "我能把一件事按对方能听懂的顺序讲出来，而不是想到哪说到哪。",
        "hint": "表达不是话多，是结构清楚。",
    },
    {
        "id": "q49", "kind": "scale", "group": "ability", "topic": "能力追问", "dim": "data",
        "title": "看到一张表格，我能很快找出里面的异常和规律。",
        "hint": "数据感是可以练的，先按现在打分。",
    },

    # ---------------- F 组：现实约束与价值观追问（7 题） ----------------
    {
        "id": "q50", "kind": "scale", "group": "value", "topic": "价值追问", "dim": "stability",
        "title": "比起「有意思」，我更希望将来的工作「靠得住、不会被淘汰」。",
        "hint": "按你真实的第一反应打分。",
    },
    {
        "id": "q51", "kind": "scale", "group": "value", "topic": "价值追问", "dim": "salary",
        "title": "我愿意为了更高的收入，接受更长的工作时间和更大的压力。",
        "hint": "想想你能不能长期这样过。",
    },
    {
        "id": "q52", "kind": "scale", "group": "value", "topic": "价值追问", "dim": "research",
        "title": "读研、读博这条更长的路，我愿意认真考虑。",
        "hint": "医学、法学、基础科学都绕不开。",
    },
    {
        "id": "q53", "kind": "scale", "group": "value", "topic": "价值追问", "dim": "interest",
        "title": "就算收入一般，我也想做自己真正感兴趣的事。",
        "hint": "这题和上一题是刻意冲突的，选更像你的那个。",
    },
    {
        "id": "q54", "kind": "single", "group": "value", "topic": "现实约束",
        "title": "家里对你选专业的态度，最接近哪一种？",
        "hint": "这题影响的是「可行性」，不是「对错」。",
        "options": [
            {"id": "a", "text": "完全由我定，他们支持",
             "scores": {"value": {"interest": 2}, "cluster": {"art": 1, "humanities": 1}}, "tags": ["free"]},
            {"id": "b", "text": "会强烈建议，倾向稳定或体面的方向",
             "scores": {"value": {"stability": 2}, "cluster": {"edu": 1, "law": 1, "med": 1}}, "tags": ["stable"]},
            {"id": "c", "text": "很看重收入和发展，希望别选冷门",
             "scores": {"value": {"salary": 2}, "cluster": {"biz": 1, "tech": 1}}, "tags": ["salary"]},
            {"id": "d", "text": "他们不太了解，基本要靠我自己判断",
             "scores": {"value": {"research": 1}, "cluster": {"sci": 1}}, "tags": ["alone"]},
        ],
    },
    {
        "id": "q55", "kind": "single", "group": "value", "topic": "现实约束",
        "title": "上大学你更愿意去哪种地方？",
        "hint": "地域会影响分数线、实习机会和生活成本。",
        "options": [
            {"id": "a", "text": "一线或新一线，机会多、节奏快",
             "scores": {"value": {"salary": 1}, "cluster": {"biz": 2, "tech": 1}}, "tags": ["city"]},
            {"id": "b", "text": "离家近，方便照顾家里",
             "scores": {"value": {"stability": 1}, "cluster": {"edu": 1}}, "tags": ["home"]},
            {"id": "c", "text": "哪所学校这个专业强就去哪",
             "scores": {"value": {"research": 1}, "cluster": {"sci": 1}}, "tags": ["major"]},
            {"id": "d", "text": "生活成本低的地方，压力小一点",
             "scores": {"value": {"stability": 1}}, "tags": ["cost"]},
        ],
    },
    {
        "id": "q56", "kind": "single", "group": "value", "topic": "现实约束",
        "title": "有些专业要读五年以上、学费也高，你会怎么想？",
        "hint": "这是很多家庭真正卡住的地方。",
        "options": [
            {"id": "a", "text": "只要能学到东西，时间和钱都值得",
             "scores": {"value": {"research": 3}, "cluster": {"med": 1, "sci": 1}}, "tags": ["long"]},
            {"id": "b", "text": "要看回报，毕业能不能挣回来",
             "scores": {"value": {"salary": 2}, "cluster": {"biz": 1}}, "tags": ["roi"]},
            {"id": "c", "text": "尽量选四年制，早点工作",
             "scores": {"value": {"stability": 1}, "cluster": {"tech": 1, "eng": 1}}, "tags": ["short"]},
            {"id": "d", "text": "先看能不能申请助学或奖学金",
             "scores": {"value": {"research": 1}, "cluster": {"edu": 1}}, "tags": ["aid"]},
        ],
    },
)


# --------------------------------------------------------------------------
# 两版规格
# --------------------------------------------------------------------------
SPEC_SIMPLE = {
    "key": "simple",
    "name": "简易测试",
    "count": len(QUESTIONS),
    "minutes": 6,
    "level": "6 分钟",
    "desc": "23 道情景题，四选一为主。测学科趣味、能力自评、专业簇、价值取向，答完直接出选科组合建议。",
    "covers": ["学科趣味", "能力自评", "专业情境", "价值取向"],
    "groups": ["interest", "ability", "cluster", "value"],
}

SPEC_DEEP = {
    "key": "deep",
    "name": "深度测试",
    "count": len(QUESTIONS) + len(EXTRA_QUESTIONS),
    "minutes": 14,
    "level": "14 分钟",
    "desc": "56 题八段式：在简易版基础上加学科细分 10 题、专业情境深入到十二个簇各一题、能力追问 4 题、现实约束与价值观 7 题。能区分同一方向里的具体分支。",
    "covers": ["学科趣味", "学科细分", "能力自评", "专业情境", "专业情境·深入", "价值取向", "现实约束"],
    "groups": ["interest", "ability", "cluster", "value"],
}

SPECS = (SPEC_SIMPLE, SPEC_DEEP)
SPEC_INDEX = {spec["key"]: spec for spec in SPECS}

QUESTIONS_BY_EDITION = {
    "simple": QUESTIONS,
    "deep": QUESTIONS + EXTRA_QUESTIONS,
}


def questions_for(edition: str = "simple"):
    """按版本取题库，未知版本回落到简易版。"""
    return QUESTIONS_BY_EDITION.get(edition) or QUESTIONS_BY_EDITION["simple"]
