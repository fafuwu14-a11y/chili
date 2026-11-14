"""Unit tests for the MOOC recommender (feature 04)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import mooc_data  # noqa: E402


class MoocTest(unittest.TestCase):
    def test_catalog_integrity(self) -> None:
        self.assertGreaterEqual(len(mooc_data.COURSES), 30)
        ids = [c["id"] for c in mooc_data.COURSES]
        self.assertEqual(len(ids), len(set(ids)))
        for course in mooc_data.COURSES:
            self.assertTrue(course["url"].startswith("https://"))
            self.assertGreaterEqual(course["weeks"], 1)
            self.assertTrue(0 <= course["rating"] <= 5)

    def test_majors_cover_programs(self) -> None:
        names = set(mooc_data.majors())
        for expected in ("计算机科学与技术", "临床医学", "法学", "汉语言文学", "金融学类"):
            self.assertIn(expected, names)

    def test_exact_major_ranks_first(self) -> None:
        result = mooc_data.recommend("计算机科学与技术", limit=6)
        self.assertEqual(result["major"], "计算机科学与技术")
        self.assertEqual(len(result["items"]), 6)
        self.assertIn("计算机科学与技术", result["items"][0]["majors"])
        self.assertGreater(result["items"][0]["match"], 50)

    def test_matches_are_sorted(self) -> None:
        items = mooc_data.recommend("临床医学", limit=8)["items"]
        matches = [item["match"] for item in items]
        self.assertEqual(matches, sorted(matches, reverse=True))

    def test_every_item_has_reason(self) -> None:
        for item in mooc_data.recommend("会计学", limit=6)["items"]:
            self.assertTrue(item["reason"])

    def test_partial_major_still_matches(self) -> None:
        items = mooc_data.recommend("口腔医学", limit=5)["items"]
        titles = " ".join(item["title"] for item in items)
        self.assertIn("口腔", titles)

    def test_unknown_major_falls_back_to_general(self) -> None:
        items = mooc_data.recommend("神秘学", limit=4)["items"]
        self.assertEqual(len(items), 4)
        self.assertTrue(all(item["match"] == 0 for item in items))

    def test_unrelated_courses_never_leak(self) -> None:
        items = mooc_data.recommend("法学", limit=6)["items"]
        titles = " ".join(item["title"] for item in items)
        for bad in ("解剖", "高等数学", "数据库"):
            self.assertNotIn(bad, titles)
        self.assertEqual(items[0]["title"], "法理学导论")

    def test_limit_bounds(self) -> None:
        self.assertLessEqual(len(mooc_data.recommend("计算机科学与技术", limit=99)["items"]), 12)
        self.assertEqual(len(mooc_data.recommend("法学", limit=0)["items"]), 1)

    def test_empty_major_rejected(self) -> None:
        with self.assertRaises(ValueError):
            mooc_data.recommend("  ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
