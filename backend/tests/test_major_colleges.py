"""院校优势聚合的单元测试。

用一只手捏出来的 ``FakeDataset`` 覆盖聚合规则（跨省同名合并、专业组排除、
位次排序、百分位换算），再用真实数据做一次冒烟，防止真实字段改名后静默失灵。
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import major_colleges  # noqa: E402


class FakeDataset:
    """只保留 major_colleges 用到的四个字段。"""

    def __init__(self) -> None:
        self.colleges = {
            "he-1": {"id": "he-1", "name": "复旦大学[公办]", "city": "上海", "tags": ["985"]},
            "ln-1": {"id": "ln-1", "name": "复旦大学[公办]", "city": "上海", "tags": ["985"]},
            "he-2": {"id": "he-2", "name": "南京大学", "city": "南京", "tags": ["985"]},
            "js-9": {"id": "js-9", "name": "东南大学", "city": "南京", "tags": []},
        }
        self.programs = [
            {"id": "p1", "college_id": "he-1", "name": "计算机科学与技术", "kind": "major",
             "province": "河北", "track": "物理类", "requirement": ""},
            {"id": "p2", "college_id": "ln-1", "name": "计算机科学与技术(拔尖班)", "kind": "major",
             "province": "辽宁", "track": "物理类", "requirement": ""},
            {"id": "p3", "college_id": "he-2", "name": "计算机科学与技术", "kind": "major",
             "province": "河北", "track": "物理类", "requirement": ""},
            # 专业组必须被忽略：它不对应任何具体专业
            {"id": "p4", "college_id": "js-9", "name": "09专业组", "kind": "group",
             "province": "江苏", "track": "物理类", "requirement": "(化学)"},
        ]
        self.stats = {
            "p1": [{"year": 2024, "min_score": 680, "min_rank": 500, "plan": 0},
                   {"year": 2025, "min_score": 682, "min_rank": 400, "plan": 12}],
            "p2": [{"year": 2025, "min_score": 690, "min_rank": 300, "plan": 0}],
            "p3": [{"year": 2025, "min_score": 670, "min_rank": 900, "plan": 0}],
            "p4": [{"year": 2025, "min_score": 600, "min_rank": 50, "plan": 0}],
        }
        self.province_info = {
            "河北": {"tracks": {"物理类": {"candidates": 300_000}}},
            "辽宁": {"tracks": {"物理类": {"candidates": 100_000}}},
            "江苏": {"tracks": {"物理类": {"candidates": 200_000}}},
        }


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.ds = FakeDataset()

    def test_专业组不进索引(self):
        index = major_colleges._index(self.ds)
        self.assertNotIn("09专业组", index)
        self.assertIn("计算机科学与技术", index)

    def test_带后缀的专业归到同一个名字(self):
        index = major_colleges._index(self.ds)
        self.assertEqual(len(index["计算机科学与技术"]), 3)

    def test_数据粒度只认专业级省份(self):
        self.assertEqual(major_colleges.data_provinces(self.ds), ["河北", "辽宁"])


class AdvantageTest(unittest.TestCase):
    def setUp(self):
        self.ds = FakeDataset()

    def test_按最好位次升序(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术", province="河北")
        ranks = [item["best_rank"] for item in result["items"]]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(result["items"][0]["college"], "复旦大学")

    def test_同一所学校跨省只出现一次(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术")
        names = [item["college"] for item in result["items"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names.count("复旦大学"), 1)

    def test_院校名去掉方括号后缀(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术")
        for item in result["items"]:
            self.assertNotIn("[", item["college"])

    def test_跨年份取最好位次且depth按年份数(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术", province="河北")
        fudan = next(i for i in result["items"] if i["college"] == "复旦大学")
        self.assertEqual(fudan["best_rank"], 400)
        self.assertEqual(fudan["best_year"], 2025)
        self.assertEqual(fudan["depth"], 2)
        self.assertEqual(fudan["years"], [2024, 2025])

    def test_省份没有专业级数据时降级并说明原因(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术", province="江苏")
        self.assertEqual(result["granularity"], "cross_province")
        self.assertIn("江苏", result["note"])
        self.assertIn("专业组", result["note"])
        self.assertTrue(result["items"])

    def test_有专业级数据的省份标记为major(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术", province="河北")
        self.assertEqual(result["granularity"], "major")

    def test_百分位用数据来源省的考生数(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术", province="河北")
        fudan = next(i for i in result["items"] if i["college"] == "复旦大学")
        # 400 / 300000 → 99.87
        self.assertAlmostEqual(fudan["percentile"], 99.87, places=2)

    def test_模糊匹配避开专业类(self):
        ds = FakeDataset()
        ds.programs.append({
            "id": "p5", "college_id": "he-2", "name": "计算机类", "kind": "major",
            "province": "河北", "track": "物理类", "requirement": "",
        })
        ds.stats["p5"] = [{"year": 2025, "min_score": 660, "min_rank": 1200, "plan": 0}]
        major_colleges._INDEX_CACHE.clear()
        result = major_colleges.advantage(ds, "计算机")
        self.assertEqual(result["major"], "计算机科学与技术")

    def test_未知专业抛错(self):
        with self.assertRaises(ValueError):
            major_colleges.advantage(self.ds, "根本不存在的专业名")

    def test_limit被夹在合法区间(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术", limit=999)
        self.assertLessEqual(len(result["items"]), major_colleges.MAX_LIMIT)


class RealDataSmokeTest(unittest.TestCase):
    """真实数据只用来确认字段还在，不做精确断言。"""

    @classmethod
    def setUpClass(cls):
        from backend.app.server import build_dataset_for

        cls.ds = build_dataset_for("real")

    def test_真实数据能查到一个专业(self):
        result = major_colleges.advantage(self.ds, "计算机科学与技术", limit=5)
        self.assertTrue(result["items"])
        first = result["items"][0]
        for key in ("college", "best_rank", "best_score", "depth", "percentile"):
            self.assertIn(key, first)

    def test_真实数据里专业级省份不少于四个(self):
        self.assertGreaterEqual(len(major_colleges.data_provinces(self.ds)), 4)


if __name__ == "__main__":
    unittest.main()
