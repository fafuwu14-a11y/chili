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


def public_questions() -> list[dict]:
    """给前端渲染用的题目：**不含 scores**。

    权重留在服务端，前端拿到的只是题干和选项文案；改前端也刷不出分。
    """
    items: list[dict] = []
    for q in QUESTIONS:
        item = {
            key: q[key]
            for key in ("id", "kind", "group", "topic", "dim", "title", "hint")
            if key in q
        }
        if q["kind"] == "single":
            item["options"] = [{"id": o["id"], "text": o["text"]} for o in q["options"]]
        items.append(item)
    return items


def meta() -> dict:
    """给前端做开场页的元信息。"""
    single = sum(1 for q in QUESTIONS if q["kind"] == "single")
    scale = sum(1 for q in QUESTIONS if q["kind"] == "scale")
    groups: dict[str, int] = {}
    for q in QUESTIONS:
        groups[q["group"]] = groups.get(q["group"], 0) + 1
    return {
        "count": len(QUESTIONS),
        "single": single,
        "scales": scale,
        "minutes": 6,
        "groups": groups,
        "subjects": [{"key": k, "name": SUBJECT_NAMES[k]} for k in SUBJECT_KEYS],
        "abilities": [{"key": k, "name": ABILITY_NAMES[k]} for k in ABILITY_KEYS],
        "clusters": [{"key": k, "name": CLUSTER_NAMES[k]} for k in CLUSTER_KEYS],
        "values": [{"key": k, "name": VALUE_NAMES[k]} for k in VALUE_KEYS],
        "scale": SCALE,
    }


def validate(answers: dict) -> list[str]:
    """检查答案是否完整合法，返回错误信息列表（空列表 = 通过）。"""
    errors: list[str] = []
    if not isinstance(answers, dict):
        return ["answers 必须是 {题号: 选项} 的对象"]
    for q in QUESTIONS:
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
