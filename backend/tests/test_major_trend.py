"""趋势预警（major_trend）的用例。

这个模块的特点：**数据本来就不齐**。所以测试的重点不是「算得准不准」，
而是三件事——

1. 有多少年说多少年，缺的年份必须出现在 ``missing_years`` 里；
2. 单年省份、专业组制省份不能被硬凑成趋势，要么标 ``single`` 要么标 ``unsupported``；
3. 统计口径本身别写错（院校数按院校去重，不是拿科类去重）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import major_catalog, major_trend  # noqa: E402

# 挑几个数据比较全的专业，避免每个用例都扫一遍全表。
SAMPLE_MAJORS = ("计算机科学与技术", "临床医学", "会计学")


class DataCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cover = major_trend.cover()

    def test_cover_has_three_buckets(self):
        self.assertIn("trendable", self.cover)
        self.assertIn("single_year", self.cover)
        self.assertIn("group_mode", self.cover)

    def test_liaoning_is_the_only_trendable_province(self):
        """当前只有辽宁有两个年份的投档表；这条用例挂了说明数据补齐了，可以放宽结论。"""
        names = [item["province"] for item in self.cover["trendable"]]
        self.assertEqual(names, ["辽宁"])
        self.assertEqual(self.cover["trendable"][0]["years"], [2024, 2026])

    def test_group_mode_provinces_are_listed(self):
        names = {item["province"] for item in self.cover["group_mode"]}
        self.assertEqual(names, {"江苏", "广东", "湖北", "山西"})

    def test_single_year_provinces(self):
        names = {item["province"] for item in self.cover["single_year"]}
        self.assertEqual(names, {"浙江", "山东", "河北"})

    def test_cover_note_mentions_province(self):
        self.assertIn("辽宁", self.cover["note"])


class TrendShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = major_trend.trend("计算机科学与技术")

    def test_top_level_fields(self):
        for key in ("major", "category", "group", "cover", "provinces", "unsupported", "has_trend", "summary"):
            self.assertIn(key, self.data)
        self.assertEqual(self.data["major"], "计算机科学与技术")
        self.assertEqual(self.data["category"], "工学")

    def test_liaoning_block_is_comparable(self):
        block = self._block("辽宁")
        self.assertEqual(block["status"], "ok")
        self.assertEqual(block["first"], 2024)
        self.assertEqual(block["last"], 2026)
        self.assertEqual(block["span"], 2)
        self.assertEqual(len(block["years"]), 2)

    def test_missing_year_is_declared(self):
        block = self._block("辽宁")
        self.assertEqual(block["missing_years"], [2025])
        self.assertIn("2025", block["note"])
        # 缺的那年不能出现在实际序列里
        self.assertNotIn(2025, [year["year"] for year in block["years"]])

    def test_year_rows_carry_all_metrics(self):
        for row in self._block("辽宁")["years"]:
            for key in ("year", "units", "colleges", "median", "rank_share"):
                self.assertIn(key, row)
            self.assertGreater(row["units"], 0)
            self.assertGreater(row["colleges"], 0)
            self.assertGreater(row["median"], 0)
            self.assertTrue(0 < row["rank_share"] <= 100)

    def test_signals_cover_three_axes(self):
        block = self._block("辽宁")
        keys = [signal["key"] for signal in block["signals"]]
        self.assertEqual(keys, ["scale", "colleges", "heat"])
        for signal in block["signals"]:
            self.assertTrue(signal["text"])
            self.assertTrue(signal["level"])

    def test_scale_level_matches_pct(self):
        block = self._block("辽宁")
        self.assertEqual(block["scale_level"], major_trend._scale_level(block["units_pct"]))

    def _block(self, province: str) -> dict:
        for item in self.data["provinces"]:
            if item["province"] == province:
                return item["tracks"][0]
        self.fail(f"返回里没有 {province}")


class TrendGapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = major_trend.trend("计算机科学与技术")

    def test_single_year_province_says_so(self):
        singles = [
            block
            for item in self.data["provinces"]
            for block in item["tracks"]
            if block["status"] == "single"
        ]
        self.assertTrue(singles)
        for block in singles:
            self.assertEqual(block["scale_level"], "数据不足")
            self.assertIn("看不了同比", block["note"])
            self.assertEqual(len(block["years"]), 1)

    def test_group_mode_provinces_are_unsupported(self):
        self.assertEqual(self.data["unsupported"], ["江苏", "广东", "湖北", "山西"])
        # 专业组制的省不应该出现在 provinces 里（它们根本采不到专业行）
        names = {item["province"] for item in self.data["provinces"]}
        self.assertFalse(names & set(self.data["unsupported"]))

    def test_summary_mentions_province(self):
        self.assertIn("辽宁", self.data["summary"])


class TrendEdgeTest(unittest.TestCase):
    def test_unknown_major_raises(self):
        with self.assertRaises(major_catalog.MajorError):
            major_trend.trend("不存在的专业")

    def test_blank_name_raises(self):
        with self.assertRaises(major_catalog.MajorError):
            major_trend.trend("   ")

    def test_scale_level_thresholds(self):
        self.assertEqual(major_trend._scale_level(None), "数据不足")
        self.assertEqual(major_trend._scale_level(20), "明显扩张")
        self.assertEqual(major_trend._scale_level(6), "小幅扩张")
        self.assertEqual(major_trend._scale_level(0), "基本持平")
        self.assertEqual(major_trend._scale_level(-6), "小幅收缩")
        self.assertEqual(major_trend._scale_level(-20), "明显收缩")

    def test_heat_level_thresholds(self):
        """位次占比变小 = 位次前移 = 变热，所以负值是升温。"""
        self.assertEqual(major_trend._heat_level(None), "数据不足")
        self.assertEqual(major_trend._heat_level(-2), "升温")
        self.assertEqual(major_trend._heat_level(-0.5), "略升")
        self.assertEqual(major_trend._heat_level(0), "稳定")
        self.assertEqual(major_trend._heat_level(0.5), "略降")
        self.assertEqual(major_trend._heat_level(2), "降温")

    def test_pct_handles_zero_base(self):
        self.assertIsNone(major_trend._pct(0, 10))
        self.assertEqual(major_trend._pct(100, 110), 10.0)

    def test_normalise_strips_brackets(self):
        self.assertEqual(major_trend.normalise("计算机科学与技术(卓越班)"), "计算机科学与技术")
        self.assertEqual(major_trend.normalise("  会计 学 "), "会计学")
        # 辽宁的「专业类[具体专业(方向)]」是嵌套括号，要整段剥干净，
        # 不能残留右括号——否则目录里会出现「法学类]」这种脏名字。
        self.assertEqual(major_trend.normalise("临床医学类[临床医学(协和)]"), "临床医学类")
        self.assertEqual(major_trend.normalise("法学类]"), "法学类")
        self.assertEqual(major_trend.normalise("工科试验班（含计算机、电子信息）"), "工科试验班")


class YearStatsTest(unittest.TestCase):
    """回归：院校数曾经错拿成科类（`for _, x, *_` 解包错位），这里钉住口径。"""

    def test_colleges_are_deduplicated_by_college(self):
        rows = [
            ("辽宁", "物理类", 2024, "A大学", 600, None),
            ("辽宁", "物理类", 2024, "A大学", 610, None),
            ("辽宁", "物理类", 2024, "B大学", 620, None),
        ]
        stats = major_trend._year_stats(rows)
        self.assertEqual(stats["units"], 3)
        self.assertEqual(stats["colleges"], 2)

    def test_median_and_plan(self):
        rows = [
            ("浙江", "综合改革", 2026, "A大学", 650, 20),
            ("浙江", "综合改革", 2026, "B大学", 640, 30),
            ("浙江", "综合改革", 2026, "C大学", 0, 10),
        ]
        stats = major_trend._year_stats(rows)
        self.assertEqual(stats["median"], 645.0)  # 0 分不参与中位数
        self.assertEqual(stats["plan"], 60)

    def test_no_scores_means_no_median(self):
        stats = major_trend._year_stats([("河北", "物理类", 2026, "A大学", 0, None)])
        self.assertIsNone(stats["median"])
        self.assertIsNone(stats["plan"])


class TrendSampleMajorsTest(unittest.TestCase):
    """几个常见专业都要能跑通，且各自的结论自洽。"""

    def test_sample_majors_are_comparable(self):
        for name in SAMPLE_MAJORS:
            with self.subTest(major=name):
                data = major_trend.trend(name)
                self.assertEqual(data["major"], name)
                ok_blocks = [
                    block
                    for item in data["provinces"]
                    for block in item["tracks"]
                    if block["status"] == "ok"
                ]
                self.assertTrue(ok_blocks, f"{name} 应该有可比对的省份")
                for block in ok_blocks:
                    # 两年的数据都要在，且年份严格递增
                    years = [row["year"] for row in block["years"]]
                    self.assertEqual(years, sorted(years))
                    self.assertGreaterEqual(len(years), 2)
                    self.assertEqual(block["missing_years"], [2025])


if __name__ == "__main__":
    unittest.main()
