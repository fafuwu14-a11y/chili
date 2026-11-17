"""方向细分（P1-A）的单元测试。

覆盖四块：
1. 六条方向轴的题库、权重、打分是否自洽；
2. 21 个「大类画像」→ 56 个专业类的映射是否完整，基准向量是否齐全；
3. 投档表里的职业本科变体名能不能被折掉；
4. matcher 输出给结果页的 majors / directions 形状对不对。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import major_catalog, major_direction, matcher, quiz_data  # noqa: E402
from app.mock_data import build_dataset  # noqa: E402
from app.predictor import Dataset  # noqa: E402


AXIS_KEYS = {"build", "code", "theory", "people", "rule", "create"}

# 一套「强技术」答案：兴趣偏理工（拆东西、算东西）+ 方向偏动手和代码，
# 和 test_quiz.py 里的 TECH 同源，另外补上能力题、偏好题与方向题。
TECH_ANSWERS = {
    "i01": 5, "i02": 5, "i03": 1, "i04": 5, "i05": 5, "i06": 1,
    "i07": 3, "i08": 3, "i09": 3, "i10": 3, "i11": 3, "i12": 4,
    "i13": 2, "i14": 2, "i15": 4, "i16": 3, "i17": 2, "i18": 4,
    "a01": 5, "a02": 4, "a03": 3, "a04": 2, "a05": 2, "a06": 2,
    "p01": 5, "p02": 4, "p03": 4, "p04": 2, "p05": 3, "p06": 3,
    "p07": 2, "p08": 4, "p09": 3, "p10": 2,
    "d01": 5, "d02": 5, "d03": 3, "d04": 2, "d05": 2, "d06": 2,
}


class DirectionQuestionTest(unittest.TestCase):
    """题库本身。"""

    def test_six_axes(self):
        self.assertEqual(set(major_direction.DIRECTION_AXES), AXIS_KEYS)
        table = major_direction.axes_table()
        self.assertEqual(len(table), 6)
        for row in table:
            self.assertIn(row["key"], AXIS_KEYS)
            self.assertTrue(row["label"])

    def test_six_questions(self):
        questions = major_direction.questions()
        self.assertEqual(len(questions), 6)
        ids = [question["id"] for question in questions]
        self.assertEqual(len(ids), len(set(ids)))
        for question_id in ids:
            self.assertTrue(question_id.startswith(major_direction.QUESTION_PREFIX))

    def test_weights_hit_known_axes(self):
        for question in major_direction.questions():
            self.assertTrue(question["text"])
            weights = question.get("w") or {}
            self.assertTrue(weights, f'{question["id"]} 没有配权重')
            for axis, weight in weights.items():
                self.assertIn(axis, AXIS_KEYS)
                self.assertGreater(weight, 0)

    def test_every_axis_is_asked(self):
        """六个轴都得有题在问，否则总有一个方向永远算不出来。"""
        covered = set()
        for question in major_direction.questions():
            covered.update(question["w"])
        self.assertEqual(covered, AXIS_KEYS)


class DirectionMappingTest(unittest.TestCase):
    """大类画像 → 专业类 → 基准向量。"""

    @classmethod
    def setUpClass(cls):
        meta = major_catalog.meta()
        cls.group_ids = {group["id"] for category in meta["categories"] for group in category["groups"]}

    def test_profiles_all_mapped(self):
        self.assertEqual(set(major_direction.PROFILE_TO_GROUP), set(quiz_data.MAJOR_PROFILES))

    def test_mapped_groups_exist(self):
        for profile, group_id in major_direction.PROFILE_TO_GROUP.items():
            self.assertIn(group_id, self.group_ids, f"{profile} 映射到了不存在的专业类 {group_id}")

    def test_group_directions_cover_catalog(self):
        missing = self.group_ids - set(major_direction.GROUP_DIRECTIONS)
        self.assertEqual(missing, set())

    def test_group_directions_only_known_axes(self):
        for group_id, vector in major_direction.GROUP_DIRECTIONS.items():
            self.assertTrue(vector, f"{group_id} 的基准向量是空的")
            self.assertLessEqual(set(vector), AXIS_KEYS, f"{group_id} 里有未知的轴")
            for value in vector.values():
                self.assertGreaterEqual(value, 0)

    def test_unknown_group_falls_back(self):
        self.assertEqual(major_direction.group_direction("不存在的类"), major_direction._NEUTRAL)

    def test_known_professions_have_character(self):
        """抽查几个专业，方向向量应该符合常识。"""
        cases = {
            ("软件工程", "计算机"): "code",
            ("会计学", "会计财务"): "rule",
            ("护理学", "护理康复"): "people",
            ("汉语言文学", "中文"): "create",
        }
        for (major, group_id), axis in cases.items():
            vector = major_direction.vector_of(major, group_id)
            top = max(vector, key=lambda key: vector[key])
            self.assertEqual(top, axis, f"{major} 最突出的轴是 {top}，预期 {axis}")


class DirectionScoreTest(unittest.TestCase):
    """把答案折成方向向量。"""

    def test_cosine_identity(self):
        vector = {"code": 1.0, "theory": 0.5}
        self.assertAlmostEqual(major_direction.cosine(vector, vector), 1.0, places=6)

    def test_cosine_orthogonal_and_empty(self):
        self.assertAlmostEqual(major_direction.cosine({"code": 1.0}, {"people": 1.0}), 0.0)
        self.assertEqual(major_direction.cosine({}, {"code": 1.0}), 0.0)
        self.assertEqual(major_direction.cosine({"code": 1.0}, {}), 0.0)

    def test_all_high_sets_peak_to_one(self):
        answers = {question["id"]: 5 for question in major_direction.questions()}
        result = major_direction.score_answers(answers)
        self.assertIsNotNone(result)
        self.assertEqual(result["answered"], 6)
        self.assertAlmostEqual(max(result["vector"].values()), 1.0, places=4)
        self.assertIn(result["peak"], AXIS_KEYS)

    def test_missing_answers_counts(self):
        answers = {"d01": 5, "d02": 5, "d03": 1}
        result = major_direction.score_answers(answers)
        self.assertEqual(result["answered"], 3)

    def test_empty_or_neutral_returns_none(self):
        self.assertIsNone(major_direction.score_answers({}))
        neutral = {question["id"]: 3 for question in major_direction.questions()}
        self.assertIsNone(major_direction.score_answers(neutral))

    def test_invalid_values_are_ignored(self):
        result = major_direction.score_answers({"d01": 9, "d02": "x", "d03": None, "d04": 5, "d05": 4})
        self.assertEqual(result["answered"], 2)

    def test_tech_answers_favour_code(self):
        result = major_direction.score_answers(TECH_ANSWERS)
        vector = result["vector"]
        self.assertGreater(vector["code"], vector["people"])
        self.assertGreater(vector["build"], vector["create"])


class DirectionVariantTest(unittest.TestCase):
    """投档表里的重复名与职业本科变体。"""

    def test_is_variant_short_name_is_variant(self):
        self.assertTrue(major_direction.is_variant("软件工程技术", {"软件工程", "计算机科学与技术"}))
        self.assertTrue(major_direction.is_variant("智能建造工程", {"智能建造", "土木工程"}))

    def test_is_variant_keeps_real_majors(self):
        siblings = {"软件工程", "计算机科学与技术", "密码科学与技术"}
        self.assertFalse(major_direction.is_variant("计算机科学与技术", siblings))
        self.assertFalse(major_direction.is_variant("软件工程", siblings))

    def test_group_listing_is_clean(self):
        majors = major_direction.majors_in_group("计算机")
        self.assertGreater(len(majors), 10)
        names = {major["name"] for major in majors}
        for banned in ("软件工程技术", "物联网工程技术", "物联网应用技术"):
            self.assertNotIn(banned, names, f"{banned} 是职业本科变体，不该出现在本科专业里")
        for major in majors:
            self.assertFalse(major["is_group"], f'{major["name"]} 是专业类，不是专业')
            self.assertGreater(major["count"], 0)

    def test_unknown_group_returns_empty(self):
        self.assertEqual(major_direction.majors_in_group("不存在的类"), [])


class DirectionOutputTest(unittest.TestCase):
    """matcher 交给结果页的东西。"""

    @classmethod
    def setUpClass(cls):
        cls.dataset = Dataset(build_dataset())

    def test_match_returns_specific_majors(self):
        result = matcher.match(self.dataset, "standard", TECH_ANSWERS, limit=4)
        majors = result["majors"]
        self.assertTrue(majors)
        self.assertLessEqual(len(majors), 6)
        names = [row["major"] for row in majors]
        self.assertEqual(len(names), len(set(names)), "同一个专业不该重复出现")
        scores = [row["match"] for row in majors]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for row in majors:
            self.assertTrue(row["group"])
            self.assertTrue(row["category"])
            self.assertGreaterEqual(row["match"], 0)
            self.assertLessEqual(row["match"], 100)

    def test_items_carry_directions(self):
        result = matcher.match(self.dataset, "standard", TECH_ANSWERS, limit=4)
        for item in result["items"]:
            self.assertIn("directions", item)
            self.assertLessEqual(len(item["directions"]), 3)
            for row in item["directions"]:
                self.assertTrue(row["major"])
                self.assertLessEqual(row["match"], item["match"])

    def test_self_named_item_ranks_itself_first(self):
        """「软件工程」这种本身就是专业的条目，第一条应该是它自己。"""
        result = matcher.match(self.dataset, "standard", TECH_ANSWERS, limit=6)
        for item in result["items"]:
            if item["major"].endswith("类"):
                continue
            self.assertEqual(item["directions"][0]["major"], item["major"])

    def test_direction_block_for_standard(self):
        result = matcher.match(self.dataset, "standard", TECH_ANSWERS, limit=4)
        block = result["direction"]
        self.assertTrue(block["available"])
        self.assertEqual(block["answered"], 6)
        self.assertEqual(block["total"], 6)
        self.assertEqual(len(block["axes"]), 6)
        self.assertIn("更偏", block["note"])
        self.assertEqual(block["axes"][0]["value"], 1.0)

    def test_direction_block_for_quick(self):
        result = matcher.match(self.dataset, "quick", TECH_ANSWERS, limit=4)
        block = result["direction"]
        self.assertFalse(block["available"])
        self.assertIn("快测", block["note"])

    def test_direction_block_without_answers(self):
        answers = {key: value for key, value in TECH_ANSWERS.items() if not key.startswith("d")}
        result = matcher.match(self.dataset, "standard", answers, limit=4)
        block = result["direction"]
        self.assertTrue(block["available"])
        self.assertEqual(block["answered"], 0)
        self.assertIn("方向题没答", block["note"])

    def test_quick_still_returns_majors(self):
        result = matcher.match(self.dataset, "quick", TECH_ANSWERS, limit=4)
        self.assertTrue(result["majors"])


if __name__ == "__main__":
    unittest.main()
