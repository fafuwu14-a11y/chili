"""Unit tests for the prediction model (stdlib unittest, no pytest needed).

    cd backend && python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.mock_data import PROVINCES, build_dataset, curve_for  # noqa: E402
from app.predictor import Dataset  # noqa: E402

DATASET = Dataset(build_dataset())


class DatasetTest(unittest.TestCase):
    def test_shape(self) -> None:
        meta = DATASET.meta()
        self.assertEqual(meta["college_count"], 45)
        self.assertGreater(meta["program_count"], 300)
        self.assertEqual(meta["stat_count"], meta["program_count"] * 3)
        self.assertEqual(meta["years"], [2023, 2024, 2025])

    def test_every_route_has_programs(self) -> None:
        for province, info in PROVINCES.items():
            for track in info["tracks"]:
                rows = DATASET.by_route[(province, track)]
                self.assertGreaterEqual(len(rows), 100, f"{province}/{track}")
                for program in rows:
                    history = DATASET.program_history(program["id"])
                    self.assertEqual(len(history), 3)
                    self.assertEqual([row["year"] for row in history], [2023, 2024, 2025])
                    for row in history:
                        self.assertGreater(row["min_rank"], 0)
                        self.assertGreater(row["min_score"], 0)
                        self.assertLessEqual(row["min_score"], 750)


class CurveTest(unittest.TestCase):
    def test_monotone(self) -> None:
        curve = curve_for("江苏", "物理类")
        previous = 10**9
        for score in range(curve.line - 80, 751, 5):
            rank = curve.rank(score)
            self.assertLess(rank, previous)
            previous = rank

    def test_round_trip(self) -> None:
        curve = curve_for("广东", "历史类")
        for rank in (3_000, 8_000, 40_000, 120_000):
            score = curve.score(rank)
            back = curve.rank(score)
            self.assertLessEqual(abs(back - rank) / rank, 0.06, (rank, score, back))


class PredictTest(unittest.TestCase):
    def test_basic_prediction(self) -> None:
        result = DATASET.predict("江苏", "物理类", score=620)
        self.assertTrue(result["items"])
        self.assertEqual(result["input"]["score"], 620)
        self.assertEqual(result["input"]["year"], 2026)
        self.assertEqual(
            result["summary"]["total"],
            len(result["items"]),
        )
        probabilities = [item["probability"] for item in result["items"]]
        self.assertEqual(probabilities, sorted(probabilities, reverse=True))
        for item in result["items"]:
            self.assertGreaterEqual(item["probability"], 0.01)
            self.assertLessEqual(item["probability"], 0.99)
            self.assertIn(item["tier"], ("冲", "稳", "保"))
            self.assertGreater(len(item["history"]), 1)
            self.assertIn("advice", item)

    def test_higher_score_means_higher_chance(self) -> None:
        low = DATASET.predict("江苏", "物理类", score=560)
        high = DATASET.predict("江苏", "物理类", score=680)
        avg_low = sum(i["probability"] for i in low["items"]) / len(low["items"])
        avg_high = sum(i["probability"] for i in high["items"]) / len(high["items"])
        self.assertGreater(avg_high, avg_low + 0.15)

    def test_rank_input_is_used(self) -> None:
        result = DATASET.predict("广东", "历史类", rank=8000)
        self.assertEqual(result["input"]["rank"], 8000)
        self.assertGreater(result["input"]["score"], 0)
        self.assertLess(result["input"]["percentile"], 10)

    def test_tier_filter(self) -> None:
        result = DATASET.predict("江苏", "物理类", score=620, tier="冲")
        self.assertTrue(all(item["tier"] == "冲" for item in result["items"]))

    def test_bad_input(self) -> None:
        with self.assertRaises(ValueError):
            DATASET.predict("江苏", "物理类")
        with self.assertRaises(ValueError):
            DATASET.predict("江苏", "物理类", score=900)
        with self.assertRaises(ValueError):
            DATASET.predict("火星", "物理类", score=600)
        with self.assertRaises(ValueError):
            DATASET.predict("江苏", "艺术类", score=600)

    def test_college_detail(self) -> None:
        detail = DATASET.college_detail("c05", "江苏", "物理类")
        self.assertEqual(detail["college"]["name"], "浙江大学")
        self.assertEqual(len(detail["programs"]), 3)
        for program in detail["programs"]:
            self.assertEqual(len(program["history"]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class CollegeSearchTest(unittest.TestCase):
    """按校搜索与「只看一所学校」的预测。"""

    def test_search_matches_name(self) -> None:
        rows = DATASET.search_colleges("大学", "江苏", "物理类", limit=5)
        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 5)
        for row in rows:
            self.assertIn("大学", row["name"])
            self.assertGreater(row["program_count"], 0)
            self.assertTrue(row["id"])

    def test_search_shorter_name_first(self) -> None:
        # 搜「南京」时，名字更短的更可能是本意，不能被「南京信息工程大学」挤到后面
        rows = DATASET.search_colleges("南京", "江苏", "物理类", limit=6)
        names = [r["name"] for r in rows]
        self.assertIn("南京大学", names)
        if "南京信息工程大学" in names:
            self.assertLess(names.index("南京大学"), names.index("南京信息工程大学"))

    def test_search_empty_and_unknown(self) -> None:
        self.assertEqual(DATASET.search_colleges("", "江苏", "物理类"), [])
        self.assertEqual(DATASET.search_colleges("不存在的学校", "江苏", "物理类"), [])

    def test_predict_restricted_to_one_college(self) -> None:
        row = DATASET.search_colleges("南京大学", "江苏", "物理类", limit=1)[0]
        data = DATASET.predict("江苏", "物理类", score=620, college=row["id"])
        self.assertTrue(data["items"])
        self.assertEqual(data["summary"]["college"], row["id"])
        total = len(DATASET.by_route[("江苏", "物理类")])
        self.assertLess(len(data["items"]), total)
        for item in data["items"]:
            self.assertEqual(item["college"]["id"], row["id"])
        # 只看一所学校时按往年录取分从高到低排，读起来是「这校从难到易」
        scores = [item["predicted_score"] for item in data["items"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_predict_college_does_not_change_probability(self) -> None:
        row = DATASET.search_colleges("南京大学", "江苏", "物理类", limit=1)[0]
        one = DATASET.predict("江苏", "物理类", score=620, college=row["id"])
        full = DATASET.predict("江苏", "物理类", score=620, limit=0)
        by_id = {item["program_id"]: item for item in full["items"]}
        for item in one["items"]:
            other = by_id[item["program_id"]]
            self.assertAlmostEqual(item["probability"], other["probability"], places=9)
            self.assertEqual(item["tier"], other["tier"])
