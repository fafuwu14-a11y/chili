"""功能 01 的单元测试：五级量表问卷、三套规格、打分与惩罚。"""

from __future__ import annotations

import unittest

from app import matcher
from app.mock_data import build_dataset
from app.predictor import Dataset
from app.quiz_data import QUESTIONS


def _levels(value: int, question_ids) -> dict:
    return {qid: value for qid in question_ids}


QS = QUESTIONS["quick"]
IDS = [q["id"] for q in QS]


# 技术型：喜欢拆东西、算东西，不喜欢读文写字、不爱应酬
TECH = {
    "i01": 5, "i02": 5, "i03": 1, "i04": 5, "i05": 5, "i06": 1,
    "i07": 3, "i08": 3, "i09": 3, "i10": 3, "i11": 3, "i12": 4,
    "i13": 2, "i14": 2, "i15": 4, "i16": 3, "i17": 2, "i18": 4,
}

# 文科型：喜欢阅读写作和讨论，躲开计算与设备
ARTS = {
    "i01": 2, "i02": 2, "i03": 5, "i04": 2, "i05": 2, "i06": 5,
    "i07": 3, "i08": 3, "i09": 3, "i10": 2, "i11": 2, "i12": 5,
    "i13": 5, "i14": 5, "i15": 1, "i16": 4, "i17": 4, "i18": 2,
}

# 医科型：关心身体与照顾人，回避解剖
MED = {
    "i01": 3, "i02": 3, "i03": 3, "i04": 3, "i05": 3, "i06": 3,
    "i07": 5, "i08": 5, "i09": 1, "i10": 2, "i11": 2, "i12": 4,
    "i13": 3, "i14": 3, "i15": 3, "i16": 5, "i17": 3, "i18": 2,
}

# 商科型：对钱和市场敏感，喜欢协调推进
BIZ = {
    "i01": 3, "i02": 4, "i03": 3, "i04": 3, "i05": 3, "i06": 3,
    "i07": 2, "i08": 2, "i09": 4, "i10": 5, "i11": 5, "i12": 1,
    "i13": 2, "i14": 2, "i15": 4, "i16": 3, "i17": 5, "i18": 3,
}

TECH_MAJORS = {"电子信息类", "自动化类", "计算机科学与技术", "软件工程", "机械类", "能源动力类"}
ARTS_MAJORS = {"汉语言文学", "新闻传播学类", "历史学类", "英语", "法学"}
BIZ_MAJORS = {"金融学类", "会计学", "经济学类"}


class QuizSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = Dataset(build_dataset())

    def test_spec_counts(self):
        counts = {spec["key"]: spec["count"] for spec in matcher.spec_list()}
        self.assertEqual(counts, {"quick": 18, "deep": 78})
        self.assertEqual(len(QUESTIONS["quick"]), 18)
        self.assertEqual(len(QUESTIONS["standard"]), 40)
        self.assertEqual(len(QUESTIONS["deep"]), 78)

    def test_spec_list_shape(self):
        for spec in matcher.spec_list():
            self.assertIn("key", spec)
            self.assertTrue(spec["name"])
            self.assertGreater(spec["minutes"], 0)
            self.assertTrue(spec["covers"])
            self.assertNotIn("questions", spec)

    def test_detail_has_five_level_scale(self):
        detail = matcher.spec_detail("quick")
        self.assertEqual(detail["scale"]["min"], 1)
        self.assertEqual(detail["scale"]["max"], 5)
        self.assertEqual(len(detail["scale"]["labels"]), 5)
        self.assertEqual(detail["questions"][0]["scale"], list(detail["scale"]["labels"]))
        self.assertNotIn("options", detail["questions"][0])

    def test_specs_are_nested_prefixes(self):
        quick = [q["id"] for q in QUESTIONS["quick"]]
        standard = [q["id"] for q in QUESTIONS["standard"]]
        deep = [q["id"] for q in QUESTIONS["deep"]]
        self.assertEqual(standard[: len(quick)], quick)
        self.assertEqual(deep[: len(standard)], standard)
        self.assertEqual(len(deep), 78)

    def test_question_ids_are_unique(self):
        deep = [q["id"] for q in QUESTIONS["deep"]]
        self.assertEqual(len(deep), len(set(deep)))

    def test_unknown_spec(self):
        with self.assertRaises(matcher.QuizError):
            matcher.spec_detail("nope")
        with self.assertRaises(matcher.QuizError):
            matcher.match(self.dataset, "nope", TECH)


class QuizScoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = Dataset(build_dataset())

    def _top(self, answers, spec="quick", limit=6):
        result = matcher.match(self.dataset, spec, answers, limit=limit)
        return [item["major"] for item in result["items"]], result

    def test_tech_profile_ranks_engineering(self):
        majors, result = self._top(TECH)
        self.assertTrue(set(majors[:4]).issubset(TECH_MAJORS), majors)
        self.assertGreaterEqual(result["items"][0]["match"], 75)

    def test_arts_profile_ranks_humanities(self):
        majors, _ = self._top(ARTS)
        self.assertTrue(set(majors[:4]).issubset(ARTS_MAJORS), majors)

    def test_med_profile_ranks_medicine(self):
        majors, _ = self._top(MED)
        self.assertIn(majors[0], {"临床医学", "口腔医学"}, majors)

    def test_biz_profile_ranks_business(self):
        majors, _ = self._top(BIZ)
        self.assertIn(majors[0], BIZ_MAJORS, majors)

    def test_sorted_by_score(self):
        _, result = self._top(TECH, limit=21)
        scores = [item["match"] for item in result["items"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_scores_are_spread_out(self):
        _, result = self._top(TECH)
        scores = [item["match"] for item in result["items"]]
        self.assertGreaterEqual(scores[0] - scores[-1], 3, scores)

    def test_limit_is_clamped(self):
        self.assertEqual(len(self._top(TECH, limit=0)[0]), 1)
        self.assertEqual(len(self._top(TECH, limit=99)[0]), 21)

    def test_each_item_has_reason_and_colleges(self):
        _, result = self._top(TECH, limit=21)
        for item in result["items"]:
            self.assertTrue(item["reason"].strip())
            self.assertTrue(item["colleges"])
            self.assertLessEqual(len(item["colleges"]), 3)
            self.assertTrue(item["blurb"])
            self.assertEqual(len(item["dims"]), 6)

    def test_interest_rows_normalized(self):
        _, result = self._top(TECH)
        rows = result["interest"]
        self.assertEqual(len(rows), 6)
        self.assertAlmostEqual(max(row["value"] for row in rows), 1.0)
        for row in rows:
            self.assertGreaterEqual(row["value"], 0.0)
            self.assertLessEqual(row["value"], 1.0)

    def test_missing_interest_raises(self):
        with self.assertRaises(matcher.QuizError):
            matcher.match(self.dataset, "quick", {})

    def test_all_neutral_raises(self):
        with self.assertRaises(matcher.QuizError):
            matcher.match(self.dataset, "quick", _levels(3, IDS))

    def test_invalid_values_are_ignored(self):
        dirty = dict(TECH)
        dirty["i01"] = 0
        dirty["i02"] = 6
        dirty["i03"] = "x"
        result = matcher.match(self.dataset, "quick", dirty)
        self.assertEqual(result["answered"], 15)

    def test_numeric_strings_are_accepted(self):
        stringy = {key: str(value) for key, value in TECH.items()}
        result = matcher.match(self.dataset, "quick", stringy)
        self.assertEqual(result["answered"], 18)

    def test_uniform_high_answers_are_flagged(self):
        answers = _levels(5, IDS)
        result = matcher.match(self.dataset, "quick", answers)
        self.assertIn("都可以试试", result["advice"])
        self.assertLess(result["items"][0]["match"], 70)

    def test_confidence_high_and_low(self):
        high = matcher.match(self.dataset, "quick", TECH)["confidence"]
        self.assertEqual(high["level"], "高")
        self.assertEqual(high["percent"], 100)
        low = matcher.match(self.dataset, "quick", {k: TECH[k] for k in list(TECH)[:4]})["confidence"]
        self.assertEqual(low["level"], "低")

    def test_quick_has_no_ability_rows(self):
        result = matcher.match(self.dataset, "quick", TECH)
        self.assertEqual(result["ability"], [])

    def test_standard_reports_abilities(self):
        answers = dict(TECH, a01=5, a02=4, a03=3, a04=2, a05=2, a06=2)
        result = matcher.match(self.dataset, "standard", answers)
        self.assertTrue(result["ability"])
        keys = [row["key"] for row in result["ability"]]
        self.assertIn("math", keys)

    def test_next_links(self):
        result = matcher.match(self.dataset, "quick", TECH)
        self.assertIn("plan.html", result["next"]["plan"])
        # P0 把预测页从 index.html 拆成独立的 predict.html，这里跟着改
        self.assertEqual(result["next"]["predict"], "predict.html")
        self.assertIn("mooc.html", result["next"]["mooc"])


class QuizConstraintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = Dataset(build_dataset())

    def _score_of(self, answers, major, spec="deep"):
        result = matcher.match(self.dataset, spec, answers, limit=21)
        for item in result["items"]:
            if item["major"] == major:
                return item["match"]
        self.fail(f"没找到专业：{major}")

    def test_long_program_penalty(self):
        accept = dict(MED, f01=5)
        refuse = dict(MED, f01=1)
        self.assertGreater(
            self._score_of(accept, "临床医学"),
            self._score_of(refuse, "临床医学"),
        )

    def test_lab_penalty(self):
        accept = dict(TECH, f02=5)
        refuse = dict(TECH, f02=1)
        self.assertGreater(
            self._score_of(accept, "机械类"),
            self._score_of(refuse, "机械类"),
        )

    def test_region_bonus(self):
        home = dict(TECH, f03=5)
        far = dict(TECH, f03=1)
        self.assertGreater(
            self._score_of(home, "计算机科学与技术"),
            self._score_of(far, "计算机科学与技术"),
        )

    def test_weak_math_lowers_cs(self):
        strong = dict(TECH, a01=5, a02=5)
        weak = dict(TECH, a01=1, a02=1)
        self.assertGreater(
            self._score_of(strong, "计算机科学与技术"),
            self._score_of(weak, "计算机科学与技术"),
        )

    def test_budget_penalty_hits_long_programs(self) -> None:
        """预算紧（f06 认同）时，长学制专业要降分。"""
        tight = dict(MED, f06=5)
        loose = dict(MED, f06=1)
        self.assertGreater(
            self._score_of(loose, "临床医学"),
            self._score_of(tight, "临床医学"),
        )

    def test_pref_tags_are_matched(self):
        answers = dict(TECH, p01=5, p09=5)
        result = matcher.match(self.dataset, "standard", answers, limit=21)
        fin = next(item for item in result["items"] if item["major"] == "金融学类")
        self.assertIn("高薪", fin["matched_tags"])
        self.assertIn("高薪", result["prefs"])

    def test_reverse_items_pull_down(self):
        # 认可「长时间对着代码调试很枯燥」应该让工程类往下掉
        like = dict(TECH, i06=1)
        dislike = dict(TECH, i06=5)
        self.assertGreater(
            self._score_of(like, "软件工程"),
            self._score_of(dislike, "软件工程"),
        )


if __name__ == "__main__":
    unittest.main()
