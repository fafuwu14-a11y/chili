"""专业目录（专业集合功能）的单元测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import major_catalog  # noqa: E402

KNOWN_MAJORS = ("计算机科学与技术", "临床医学", "法学", "汉语言文学", "会计学")
REQUIRED_BRIEF_FIELDS = (
    "name",
    "category",
    "category_name",
    "group",
    "group_id",
    "count",
    "provinces",
    "score_median",
    "is_group",
)


class MajorCatalogTest(unittest.TestCase):
    def test_catalog_integrity(self) -> None:
        data = major_catalog._catalog()
        names = [item["name"] for item in data["majors"]]
        self.assertEqual(len(names), len(set(names)), "专业名必须唯一，否则详情无法按名字定位")
        self.assertEqual(data["total_majors"], len(names))
        self.assertGreaterEqual(len(data["categories"]), 10)
        self.assertEqual(
            [item["id"] for item in data["categories"]],
            major_catalog.CATEGORY_ORDER,
            "门类顺序要和 CATEGORY_ORDER 一致，前端树直接用这个顺序",
        )

    def test_every_category_name_resolves(self) -> None:
        """majors 里只存门类 id，展示名要从 categories 表里查出来（曾因直接下标 KeyError）。"""
        data = major_catalog._catalog()
        for item in data["majors"]:
            brief = major_catalog._brief(item)
            self.assertTrue(brief["category_name"], f"{item['name']} 缺门类中文名")
        for category in data["categories"]:
            for group in category["groups"]:
                self.assertEqual(group["category"], category["id"])
                self.assertEqual(group["category_name"], category["name"])

    def test_names_have_no_stray_brackets(self) -> None:
        """辽宁投档表里的「专业类[专业(方向)]」要整段剥掉。

        早期正则只剥最内层，目录里留下过「法学类]」「工科试验班]」这种脏名字。
        """
        data = major_catalog._catalog()
        dirty = [item["name"] for item in data["majors"] if any(ch in item["name"] for ch in "()（）[]【】")]
        self.assertEqual(dirty, [], f"目录里还有带括号残留的专业名：{dirty[:5]}")
        for category in data["categories"]:
            for group in category["groups"]:
                self.assertFalse(any(ch in group["name"] for ch in "()（）[]【】"), group["name"])

    def test_meta_shape(self) -> None:
        meta = major_catalog.meta()
        self.assertGreaterEqual(meta["total_majors"], 800)
        self.assertGreater(meta["total_rows"], 0)
        self.assertTrue(meta["source"])
        groups = [group for category in meta["categories"] for group in category["groups"]]
        self.assertGreaterEqual(len(groups), 40)

    def test_known_majors_present(self) -> None:
        names = {item["name"] for item in major_catalog._catalog()["majors"]}
        for major in KNOWN_MAJORS:
            self.assertIn(major, names)

    def test_search_returns_brief_fields(self) -> None:
        result = major_catalog.search(limit=10)
        self.assertEqual(result["listed"], 10)
        self.assertGreaterEqual(result["total"], 800)
        for item in result["items"]:
            self.assertEqual(set(item), set(REQUIRED_BRIEF_FIELDS))

    def test_search_sorted_by_count(self) -> None:
        items = major_catalog.search(limit=20)["items"]
        counts = [item["count"] for item in items]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_search_by_category(self) -> None:
        result = major_catalog.search(category="eng", limit=400)
        self.assertGreater(result["total"], 0)
        self.assertTrue(all(item["category"] == "eng" for item in result["items"]))
        listed = major_catalog.search(category="eng", limit=400)["total"]
        self.assertGreaterEqual(listed, len(result["items"]))

    def test_search_by_group(self) -> None:
        result = major_catalog.search(group="计算机", limit=400)
        self.assertGreater(result["total"], 0)
        self.assertTrue(all(item["group_id"] == "计算机" for item in result["items"]))
        self.assertIn("计算机科学与技术", [item["name"] for item in result["items"]])

    def test_search_keyword_exact_first(self) -> None:
        for major in KNOWN_MAJORS:
            items = major_catalog.search(query=major, limit=5)["items"]
            self.assertTrue(items, f"{major} 搜不到")
            self.assertEqual(items[0]["name"], major, "完全匹配的专业要排第一")

    def test_search_matches_group_name(self) -> None:
        items = major_catalog.search(query="计算机", limit=10)["items"]
        self.assertTrue(items)
        self.assertTrue(any("计算机" in item["group"] or "计算机" in item["name"] for item in items))

    def test_search_blank_and_unknown(self) -> None:
        self.assertGreater(major_catalog.search(query="   ", limit=5)["listed"], 0)
        self.assertEqual(major_catalog.search(query="不存在的专业XYZ")["total"], 0)

    def test_search_limit_bounds(self) -> None:
        self.assertEqual(major_catalog.search(limit=3)["listed"], 3)
        self.assertLessEqual(major_catalog.search(limit=9999)["listed"], 400)
        # limit=0 表示不截断，返回全部
        full = major_catalog.search(limit=0)
        self.assertEqual(full["listed"], full["total"])

    def test_detail_shape(self) -> None:
        detail = major_catalog.detail("计算机科学与技术")
        self.assertEqual(detail["name"], "计算机科学与技术")
        self.assertEqual(detail["category"], "eng")
        self.assertEqual(detail["category_name"], "工学")
        self.assertGreater(detail["count"], 0)
        self.assertLessEqual(detail["score_min"], detail["score_median"])
        self.assertLessEqual(detail["score_median"], detail["score_max"])
        self.assertTrue(detail["by_province"])
        self.assertEqual(len(detail["provinces"]), len(detail["by_province"]))
        self.assertLessEqual(len(detail["courses"]), 4)

    def test_detail_provinces_sorted(self) -> None:
        provinces = major_catalog.detail("临床医学")["by_province"]
        counts = [row["count"] for row in provinces]
        self.assertEqual(counts, sorted(counts, reverse=True))
        for row in provinces:
            self.assertTrue(row["key"])
            self.assertGreater(row["count"], 0)
            self.assertGreater(row["median"], 0)

    def test_detail_every_major_works(self) -> None:
        """逐个跑一遍详情，防止个别专业缺字段把接口打 500。"""
        for item in major_catalog._catalog()["majors"]:
            detail = major_catalog.detail(item["name"])
            self.assertEqual(detail["name"], item["name"])
            self.assertTrue(detail["category_name"])

    def test_detail_rejects_bad_input(self) -> None:
        with self.assertRaises(major_catalog.MajorError):
            major_catalog.detail("")
        with self.assertRaises(major_catalog.MajorError):
            major_catalog.detail("   ")
        with self.assertRaises(major_catalog.MajorError):
            major_catalog.detail("不存在的专业XYZ")

    def test_major_error_is_value_error(self) -> None:
        """server.py 用 `except ValueError` 统一转 400，所以这里必须是 ValueError 子类。"""
        self.assertTrue(issubclass(major_catalog.MajorError, ValueError))


if __name__ == "__main__":
    unittest.main(verbosity=2)
