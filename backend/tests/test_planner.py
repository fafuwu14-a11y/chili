"""Unit tests for the plan builder (feature 03)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.mock_data import build_dataset  # noqa: E402
from app.planner import DEFAULT_SLOTS, MAX_SLOTS, PER_COLLEGE_CAP, build_plan  # noqa: E402
from app.predictor import Dataset  # noqa: E402

DATASET = Dataset(build_dataset())


class PlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_plan(DATASET, province="江苏", track="物理类", score=620)

    def test_default_counts(self) -> None:
        summary = self.plan["summary"]
        self.assertEqual(summary["requested"], DEFAULT_SLOTS)
        self.assertEqual(summary["chong"], DEFAULT_SLOTS["chong"])
        self.assertEqual(summary["wen"], DEFAULT_SLOTS["wen"])
        self.assertEqual(summary["bao"], DEFAULT_SLOTS["bao"])
        self.assertEqual(summary["total"], sum(DEFAULT_SLOTS.values()))

    def test_slots_ordered_and_numbered(self) -> None:
        slots = self.plan["slots"]
        self.assertEqual([s["index"] for s in slots], list(range(1, len(slots) + 1)))
        tiers = [s["tier"] for s in slots]
        self.assertEqual(tiers, ["冲"] * DEFAULT_SLOTS["chong"] + ["稳"] * DEFAULT_SLOTS["wen"] + ["保"] * DEFAULT_SLOTS["bao"])

    def test_tier_probability_ranges(self) -> None:
        for slot in self.plan["slots"]:
            p = slot["probability"]
            if slot["tier"] == "冲":
                self.assertLess(p, 0.45)
            elif slot["tier"] == "稳":
                self.assertTrue(0.45 <= p < 0.85)
            else:
                self.assertGreaterEqual(p, 0.85)

    def test_college_cap(self) -> None:
        counts: dict[str, int] = {}
        for slot in self.plan["slots"]:
            key = slot["college"]["id"]
            counts[key] = counts.get(key, 0) + 1
        self.assertLessEqual(max(counts.values()), PER_COLLEGE_CAP)

    def test_stable_close_to_target(self) -> None:
        stable = [s for s in self.plan["slots"] if s["tier"] == "稳"]
        self.assertTrue(stable)
        for slot in stable:
            self.assertLess(abs(slot["probability"] - 0.66), 0.2)

    def test_mode_school_uses_one_college_once(self) -> None:
        plan = build_plan(DATASET, province="江苏", track="物理类", score=620, mode="school")
        colleges = [slot["college"]["id"] for slot in plan["slots"]]
        self.assertEqual(len(colleges), len(set(colleges)))
        self.assertEqual(plan["summary"]["college_count"], plan["summary"]["total"])
        self.assertEqual(plan["summary"]["mode"], "school")

    def test_mode_major_allows_repeats(self) -> None:
        plan = build_plan(DATASET, province="江苏", track="物理类", score=620, mode="major")
        colleges = [slot["college"]["id"] for slot in plan["slots"]]
        self.assertLess(len(set(colleges)), len(colleges))
        self.assertLessEqual(plan["summary"]["college_count"], plan["summary"]["total"])

    def test_mode_unknown_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_plan(DATASET, province="江苏", track="物理类", score=620, mode="whatever")

    def test_custom_counts_and_clamp(self) -> None:
        plan = build_plan(DATASET, province="江苏", track="物理类", score=620, chong=1, wen=2, bao=1)
        self.assertEqual(plan["summary"]["total"], 4)
        huge = build_plan(DATASET, province="江苏", track="物理类", score=620, chong=999, wen=0, bao=0)
        self.assertLessEqual(huge["summary"]["requested"]["chong"], MAX_SLOTS)

    def test_zero_total_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_plan(DATASET, province="江苏", track="物理类", score=620, chong=0, wen=0, bao=0)

    def test_rank_input_equivalent(self) -> None:
        by_rank = build_plan(DATASET, province="江苏", track="物理类", rank=4063)
        by_score = build_plan(DATASET, province="江苏", track="物理类", score=620)
        self.assertAlmostEqual(by_rank["input"]["rank"], 4063, delta=1)
        self.assertEqual(by_rank["summary"]["total"], by_score["summary"]["total"])

    def test_high_score_has_no_chong(self) -> None:
        plan = build_plan(DATASET, province="江苏", track="物理类", score=750, chong=4, wen=4, bao=2)
        self.assertEqual(plan["summary"]["chong"], 0)
        self.assertTrue(plan["advice"])

    def test_advice_mentions_structure(self) -> None:
        self.assertIn("冲稳保", self.plan["advice"])

    def test_zero_chong_request_is_not_reported_as_unreachable(self) -> None:
        """用户主动不要冲，不该被说成「位次高于库里所有院校」。"""
        plan = build_plan(DATASET, province="江苏", track="物理类", score=620, chong=0, wen=4, bao=2)
        self.assertEqual(plan["summary"]["requested"]["chong"], 0)
        self.assertNotIn("高于库里所有院校", plan["advice"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
