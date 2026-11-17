"""冲稳保志愿方案生成（功能 03）。

在 ``Dataset.predict`` 的结果上做二次挑选：从每个档位里按不同策略选出
最值得填的院校专业组，排成一张从「冲」到「保」递减的志愿表。

选法（不是简单取前 N 个）：

* 冲：在概率 < 45% 的池子里挑概率最高的（离够得着最近的那几所）
* 稳：在 45%–85% 的池子里挑概率最接近 66% 的
* 保：在 ≥85% 的池子里挑概率最低的（刚好能兜住、院校层次最好的）

同一所院校出现的次数由 ``mode`` 决定（见 ``CAP_BY_MODE``）：

* ``auto``   —— 默认，一所院校最多 2 个专业组（专业模式下 3 个专业）
* ``school`` —— 按学校排：一所院校只出 1 个，把整张表铺到尽可能多的学校上
* ``major``  —— 按专业排：允许同一所院校的多个专业同时进表（组模式 3、专业模式 6），
                适合「就想盯着某几个方向填」的考生
"""

from __future__ import annotations

import time

from .predictor import TIER_BAO, TIER_CHONG, TIER_WEN, Dataset

DEFAULT_SLOTS = {"chong": 4, "wen": 8, "bao": 6}
MAX_SLOTS = 45  # 省份没配 slots_max 时的兜底上限
PER_COLLEGE_CAP = 2
# auto 下：专业组模式 2 个就够；「专业+学校」模式下一个校名可能有几十个专业，
# 放宽到 3 个，否则一张 18 个志愿的表里会出现同一个学校的 3 个专业挤占名额。
CAP_BY_KIND = {"group": 2, "major": 3}
# 三种生成口径下「同一所院校最多出现几次」
CAP_BY_MODE = {
    "auto": {"group": 2, "major": 3},
    "school": {"group": 1, "major": 1},
    "major": {"group": 3, "major": 6},
}
PLAN_MODES = tuple(CAP_BY_MODE)
TARGET_STABLE_P = 0.66


def _unit_word(unit: str) -> str:
    return "专业" if unit == "major" else "专业组"


def _mode_label(mode: str, word: str) -> str:
    if mode == "school":
        return "按学校排：一所学校只占一个志愿，把表铺到更多学校上"
    if mode == "major":
        return f"按专业排：同一所学校的多个{word}都可以进表，适合盯着方向填"
    return "智能排：同校适量重复，兼顾覆盖面与被录取可能"


def build_plan(
    dataset: Dataset,
    province: str,
    track: str,
    score: int | None = None,
    rank: int | None = None,
    chong: int = DEFAULT_SLOTS["chong"],
    wen: int = DEFAULT_SLOTS["wen"],
    bao: int = DEFAULT_SLOTS["bao"],
    mode: str = "auto",
) -> dict:
    # 每个省本科批能填的志愿数不一样（江苏 40 个专业组、辽宁 112 个专业…），
    # 上限跟着省走，让三档加起来正好能填满一张表。
    province_conf = dataset.raw.get("provinces", {}).get(province, {})
    slots_max = int(province_conf.get("slots_max") or MAX_SLOTS)

    mode = (mode or "auto").strip().lower()
    if mode not in CAP_BY_MODE:
        raise ValueError(f"不支持的方案排法：{mode}（可选 {', '.join(PLAN_MODES)}）")

    chong, wen, bao = (_clamp(x, 0, slots_max) for x in (chong, wen, bao))
    if chong + wen + bao == 0:
        raise ValueError("冲、稳、保三个档位不能都是 0，请至少给一个档位留出名额")

    squeezed = False
    if chong + wen + bao > slots_max:
        scale = slots_max / (chong + wen + bao)
        chong = int(chong * scale)
        wen = int(wen * scale)
        bao = slots_max - chong - wen
        squeezed = True

    # limit=0：拿全量候选。只取前 200 条「匹配度最高」的话，保底档会空掉。
    result = dataset.predict(province=province, track=track, score=score, rank=rank, limit=0)
    items = result["items"]

    unit = dataset.raw.get("provinces", {}).get(province, {}).get("unit", "group")
    cap = CAP_BY_MODE[mode].get(unit, PER_COLLEGE_CAP)
    word = _unit_word(unit)

    pools: dict[str, list[dict]] = {TIER_CHONG: [], TIER_WEN: [], TIER_BAO: []}
    for item in items:
        pools[item["tier"]].append(item)

    used: dict[str, int] = {}
    chase = _pick(pools[TIER_CHONG], chong, key=lambda x: -x["probability"], used=used, cap=cap)
    stable = _pick(
        pools[TIER_WEN], wen, key=lambda x: abs(x["probability"] - TARGET_STABLE_P), used=used, cap=cap
    )
    safe = _pick(pools[TIER_BAO], bao, key=lambda x: x["probability"], used=used, cap=cap)

    slots: list[dict] = []
    for tier, chosen in ((TIER_CHONG, chase), (TIER_WEN, stable), (TIER_BAO, safe)):
        # 按专业排：同一所学校的多个专业聚在一起，且在档内按分数从高到低；
        # 其余两种排法维持「档内按预测分降序」。
        if mode == "major":
            chosen.sort(key=lambda x: (x["college"]["name"], -x["predicted_score"]))
        else:
            chosen.sort(key=lambda x: x["predicted_score"], reverse=True)
        for item in chosen:
            slots.append(
                {
                    "index": len(slots) + 1,
                    "tier": tier,
                    "college": item["college"],
                    "program_id": item["program_id"],
                    "program": item["name"],
                    "kind": item.get("kind", "group"),
                    "requirement": item["requirement"],
                    "probability": item["probability"],
                    "predicted_score": item["predicted_score"],
                    "predicted_rank": item["predicted_rank"],
                    "plan": item["plan"],
                    "advice": item["advice"],
                }
            )

    got = {"chong": len(chase), "wen": len(stable), "bao": len(safe)}
    wanted = {"chong": chong, "wen": wen, "bao": bao}
    note = _note(got, wanted, word)
    if squeezed:
        note = f"这个省本科批最多填 {slots_max} 个，已按比例压到 {chong} / {wen} / {bao}。" + note
    distinct_colleges = len({slot["college"]["id"] for slot in slots})
    return {
        "input": result["input"],
        "slots": slots,
        "summary": {
            "chong": got["chong"],
            "wen": got["wen"],
            "bao": got["bao"],
            "total": len(slots),
            "slots_max": slots_max,
            "mode": mode,
            "mode_label": _mode_label(mode, word),
            "college_count": distinct_colleges,
            "requested": wanted,
            "note": note,
        },
        "advice": _plan_advice(got, wanted, word),
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "source": "mock",
    }


def _pick(
    pool: list[dict], count: int, key, used: dict[str, int], cap: int = PER_COLLEGE_CAP
) -> list[dict]:
    if count <= 0:
        return []
    chosen: list[dict] = []
    for item in sorted(pool, key=key):
        college_id = item["college"]["id"]
        if used.get(college_id, 0) >= cap:
            continue
        chosen.append(item)
        used[college_id] = used.get(college_id, 0) + 1
        if len(chosen) >= count:
            break
    return chosen


def _note(got: dict, wanted: dict, word: str = "专业组") -> str:
    missing = [f"{name}{wanted[key]}-{got[key]}" for key, name in (("chong", "冲"), ("wen", "稳"), ("bao", "保")) if got[key] < wanted[key]]
    if not missing:
        return "三档数量都满足，可以直接照表填报。"
    return f"受可选{word}数量限制，" + "、".join(missing) + " 没有凑满，建议适当增减其他档位。"


def _plan_advice(got: dict, wanted: dict, word: str = "专业组") -> str:
    if wanted["chong"] == 0:
        return "你没有要冲的志愿，这张表只有稳和保，等于放弃了「捡漏」的机会；如果只是想先稳住，可以照表填报，并确认保底足够。"
    if got["chong"] == 0:
        return "没有可冲的院校，说明你的位次已经高于库里所有院校，建议把重心放在稳和保，并关注更高层次院校的提前批。"
    if got["bao"] < 2:
        return f"保底志愿偏少，建议至少保留 2–3 个保底{word}，并勾选「服从专业调剂」，避免滑档。"
    if got["wen"] < 2:
        if word == "专业":
            return "稳妥志愿偏少，冲的部分风险较高，建议增加 2–3 个稳的专业。"
        return "稳妥志愿偏少，冲的部分风险较高，建议增加 2–3 个稳的院校专业组。"
    return "冲稳保结构完整。填报时按表内顺序从上到下填写，冲的放在前面、保的放在最后，并全部勾选服从专业调剂。"


def _clamp(value: int, low: int, high: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError("档位数量必须是整数") from None
    return max(low, min(high, value))
