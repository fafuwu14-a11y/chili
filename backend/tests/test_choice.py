"""选科问卷与推荐引擎的单元测试（纯规则，不联网）。"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import choice_engine, choice_quiz, subject_map, subjects  # noqa: E402

DATA = json.loads((pathlib.Path(__file__).resolve().parents[1] / "data" / "major_catalog.json").read_text("utf-8"))
MAJORS = DATA["majors"]


def answers_all(first: str = "a", scale: int = 3) -> dict:
    """每个单选题都选同一个选项，量表统一给分。"""
    return {q["id"]: (scale if q["kind"] == "scale" else first) for q in choice_quiz.QUESTIONS}


def answers_by(picks: dict, scale: int = 3) -> dict:
    return {q["id"]: (scale if q["kind"] == "scale" else picks.get(q["id"], "a")) for q in choice_quiz.QUESTIONS}


class QuizDataTest(unittest.TestCase):
    def test_question_count_and_unique_ids(self):
        qs = choice_quiz.questions()
        self.assertEqual(len(qs), 23)
        self.assertEqual(len({q["id"] for q in qs}), 23)

    def test_every_question_has_content(self):
        for q in choice_quiz.questions():
            self.assertTrue(q["title"], q["id"])
            self.assertIn(q["kind"], {"single", "scale"})
            self.assertIn(q["group"], {"interest", "ability", "cluster", "value"})
            if q["kind"] == "single":
                self.assertEqual(len(q["options"]), 4, q["id"])
                self.assertEqual(len({o["id"] for o in q["options"]}), 4, q["id"])
                for opt in q["options"]:
                    self.assertTrue(opt["text"])
                    self.assertTrue(opt["scores"], f"{q['id']}-{opt['id']} 没有打分")
                    for bucket in opt["scores"]:
                        self.assertIn(bucket, {"subject", "ability", "cluster", "value"})
            else:
                self.assertIn(q["dim"], choice_quiz.ABILITY_KEYS + choice_quiz.VALUE_KEYS)

    def test_options_cover_dimensions(self):
        """四个选项不能全打到同一个维度，否则题目白问。"""
        for q in choice_quiz.questions():
            if q["kind"] != "single":
                continue
            keys = set()
            for opt in q["options"]:
                for bucket, scores in opt["scores"].items():
                    keys.update(f"{bucket}:{k}" for k in scores)
            self.assertGreater(len(keys), 4, q["id"])

    def test_meta(self):
        meta = choice_quiz.meta()
        self.assertEqual(meta["count"], 23)
        self.assertEqual(meta["single"] + meta["scales"], 23)
        self.assertEqual(len(meta["subjects"]), 7)


class ValidateTest(unittest.TestCase):
    def test_complete_answers_pass(self):
        self.assertEqual(choice_quiz.validate(answers_all()), [])

    def test_missing_question(self):
        ans = answers_all()
        del ans["q1"]
        errors = choice_quiz.validate(ans)
        self.assertTrue(any("q1" in e for e in errors))

    def test_bad_option(self):
        ans = answers_all()
        ans["q1"] = "z"
        self.assertTrue(any("q1" in e for e in choice_quiz.validate(ans)))

    def test_scale_out_of_range(self):
        ans = answers_all()
        ans["q9"] = 9
        self.assertTrue(any("q9" in e for e in choice_quiz.validate(ans)))
        ans["q9"] = "x"
        self.assertTrue(any("q9" in e for e in choice_quiz.validate(ans)))

    def test_not_a_dict(self):
        self.assertTrue(choice_quiz.validate([]))


class ScoreTest(unittest.TestCase):
    def test_all_dimensions_present_and_bounded(self):
        profile = choice_engine.score(answers_all())
        for bucket, keys in (
            ("subject", choice_quiz.SUBJECT_KEYS),
            ("ability", choice_quiz.ABILITY_KEYS),
            ("cluster", choice_quiz.CLUSTER_KEYS),
            ("value", choice_quiz.VALUE_KEYS),
        ):
            self.assertEqual(set(profile[bucket]), set(keys), bucket)
            for key, value in profile[bucket].items():
                self.assertGreaterEqual(value, 0, f"{bucket}.{key}")
                self.assertLessEqual(value, 100, f"{bucket}.{key}")

    def test_tech_answers_favour_physics(self):
        profile = choice_engine.score(answers_by({"q1": "a", "q2": "a", "q6": "a"}))
        self.assertGreater(profile["subject"]["physics"], profile["subject"]["history"])

    def test_humanities_answers_favour_history(self):
        profile = choice_engine.score(answers_by({"q1": "c", "q2": "b", "q6": "c"}))
        self.assertGreater(profile["subject"]["history"], profile["subject"]["physics"])

    def test_scale_monotonic(self):
        low = choice_engine.score(answers_all(scale=1))
        high = choice_engine.score(answers_all(scale=5))
        for key in choice_quiz.ABILITY_KEYS:
            self.assertLessEqual(low["ability"][key], high["ability"][key], key)

    def test_values_track_scale(self):
        low = choice_engine.score(answers_all(scale=1))["value"]
        high = choice_engine.score(answers_all(scale=5))["value"]
        for key in choice_quiz.VALUE_KEYS:
            self.assertLess(low[key], high[key], key)

    def test_top_subjects_sorted(self):
        profile = choice_engine.score(answers_all())
        values = [v for _, v in profile["top_subjects"]]
        self.assertEqual(values, sorted(values, reverse=True))


class ComboTest(unittest.TestCase):
    def test_combos_are_legal_for_province(self):
        for province in ("江苏", "浙江", "上海", "西藏"):
            legal = {"+".join(c["subjects"]) for c in subjects.combos(province)}
            profile = choice_engine.score(answers_all())
            for combo in choice_engine.recommend_combos(profile, province, MAJORS):
                self.assertIn("+".join(combo["subjects"]), legal, province)
                self.assertEqual(len(combo["subjects"]), 3)

    def test_scores_sorted_desc(self):
        profile = choice_engine.score(answers_all())
        combos = choice_engine.recommend_combos(profile, "江苏", MAJORS)
        self.assertEqual([c["score"] for c in combos], sorted([c["score"] for c in combos], reverse=True))

    def test_top_n(self):
        profile = choice_engine.score(answers_all())
        self.assertEqual(len(choice_engine.recommend_combos(profile, "江苏", MAJORS, top=2)), 2)

    def test_coverage_between_zero_and_one(self):
        profile = choice_engine.score(answers_all())
        for combo in choice_engine.recommend_combos(profile, "山东", MAJORS):
            self.assertGreater(combo["coverage_ratio"], 0)
            self.assertLessEqual(combo["coverage_ratio"], 1)

    def test_physics_combo_covers_more_than_humanities(self):
        profile = choice_engine.score(answers_all())
        combos = {tuple(c["subjects"]): c for c in choice_engine.recommend_combos(profile, "江苏", MAJORS, top=12)}
        science = next(c for c in combos.values() if "物理" in c["subjects"] and "化学" in c["subjects"])
        arts = next(c for c in combos.values() if "历史" in c["subjects"])
        self.assertGreater(science["coverage_ratio"], arts["coverage_ratio"])


class MajorTest(unittest.TestCase):
    def test_recommended_majors_are_eligible(self):
        profile = choice_engine.score(answers_all())
        combo = ["物理", "化学", "生物"]
        for row in choice_engine.recommend_majors(profile, combo, MAJORS, top=10):
            gid = subject_map.group_of_major(row["name"])
            self.assertTrue(subjects.group_eligible(gid, combo), row["name"])

    def test_no_exempt_names(self):
        profile = choice_engine.score(answers_all())
        for row in choice_engine.recommend_majors(profile, ["物理", "化学", "生物"], MAJORS, top=30):
            self.assertFalse(subject_map.is_exempt(row["name"]), row["name"])

    def test_per_group_cap(self):
        profile = choice_engine.score(answers_all())
        rows = choice_engine.recommend_majors(profile, ["物理", "化学", "生物"], MAJORS, top=30, per_group=1)
        ids = [r["group_id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_science_student_gets_science_majors(self):
        ans = answers_by({"q1": "a", "q2": "a", "q3": "a", "q4": "a", "q6": "a", "q17": "a"})
        report = choice_engine.build_report(ans, "江苏", MAJORS)
        clusters = {m["cluster"] for m in report["majors"][:5]}
        self.assertTrue(clusters & {"tech", "sci", "eng"}, clusters)

    def test_humanities_student_gets_humanities_majors(self):
        ans = answers_by({"q1": "c", "q2": "b", "q3": "b", "q4": "b", "q6": "c", "q19": "a"})
        report = choice_engine.build_report(ans, "江苏", MAJORS)
        clusters = {m["cluster"] for m in report["majors"][:5]}
        self.assertTrue(clusters & {"humanities", "social", "law", "art"}, clusters)

    def test_scores_sorted_desc(self):
        profile = choice_engine.score(answers_all())
        rows = choice_engine.recommend_majors(profile, ["物理", "化学", "生物"], MAJORS)
        self.assertEqual([r["score"] for r in rows], sorted([r["score"] for r in rows], reverse=True))


class ReportTest(unittest.TestCase):
    def test_report_shape(self):
        report = choice_engine.build_report(answers_all(), "江苏", MAJORS)
        self.assertTrue(report["ok"])
        for key in ("province", "mode", "profile", "combos", "majors", "meta"):
            self.assertIn(key, report)
        self.assertEqual(report["mode"], "3+1+2")
        self.assertEqual(len(report["combos"]), 3)
        self.assertTrue(report["combos"][0]["why"])
        self.assertTrue(report["combos"][0]["risk"])

    def test_invalid_answers_short_circuit(self):
        report = choice_engine.build_report({}, "江苏", MAJORS)
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])

    def test_unknown_province(self):
        report = choice_engine.build_report(answers_all(), "火星", MAJORS)
        self.assertFalse(report["ok"])

    def test_all_provinces_build(self):
        ans = answers_all()
        for province in subjects.PROVINCES:
            with self.subTest(province=province):
                report = choice_engine.build_report(ans, province, MAJORS, top_majors=5)
                self.assertTrue(report["ok"], province)
                self.assertEqual(len(report["majors"]), 5, province)


class SubjectMapTest(unittest.TestCase):
    def test_coverage_ratio(self):
        stats = subject_map.stats(MAJORS)
        self.assertGreaterEqual(stats["ratio"], 0.95)
        self.assertEqual(stats["missed_total"], 0)

    def test_group_mapping_stable(self):
        self.assertEqual(subject_map.group_of_major("计算机科学与技术"), "computer")
        self.assertEqual(subject_map.group_of_major("临床医学（5+3一体化）"), "clinical")
        self.assertEqual(subject_map.group_of_major("法学"), "law")
        self.assertEqual(subject_map.group_of_major("泰语"), "foreign")
        self.assertEqual(subject_map.group_of_major("少数民族预科班"), "other")

    def test_all_majors_map_to_known_group(self):
        mapping = subject_map.map_all(MAJORS)
        for name, gid in mapping.items():
            if subject_map.is_exempt(name):
                continue
            self.assertIn(gid, subjects.GROUP_INDEX, name)


if __name__ == "__main__":
    unittest.main()
