"""专业画像的测试：结构对不对、名字能不能对上目录、坏数据能不能挡住。

画像文案靠人工抽检，但结构必须机器兜底——前端按字段名取数，
少一个字段就是一块空白，评委不会告诉你哪里错了。
"""

import unittest

from app import major_catalog, major_profile

SAMPLE_NAMES = ("计算机科学与技术", "临床医学", "社会工作")


class SampleCoverageTest(unittest.TestCase):
    """样例阶段：先保证三条标杆画像存在且完整。"""

    def test_samples_exist(self):
        names = set(major_profile.names())
        for name in SAMPLE_NAMES:
            self.assertIn(name, names, f"缺少样例画像：{name}")

    def test_every_profile_passes_check(self):
        for name in major_profile.names():
            item = major_profile.get(name)
            self.assertEqual(major_profile.check(item), [], f"{name} 结构不合格")

    def test_names_match_catalog(self):
        """画像里的专业名必须能在专业目录里找到，否则前端链接会 404。"""
        for name in major_profile.names():
            detail = major_catalog.detail(name)  # 不存在会抛 MajorError
            self.assertEqual(detail["name"], name)

    def test_group_and_category_match_catalog(self):
        """画像的分类字段与目录不一致时，页面会出现两个专业类名。"""
        for name in major_profile.names():
            item = major_profile.get(name)
            row = major_catalog.detail(name)
            self.assertEqual(item["category"], row["category"], f"{name} 门类不一致")
            self.assertEqual(item["group"], row["group"], f"{name} 专业类不一致")
            self.assertEqual(item["group_id"], row["group_id"], f"{name} 专业类 id 不一致")


class ShapeTest(unittest.TestCase):
    def test_lists_are_within_bounds(self):
        for name in major_profile.names():
            item = major_profile.get(name)
            for key, low in major_profile.MIN_LIST.items():
                self.assertGreaterEqual(len(item[key]), low, f"{name}.{key} 太少")
                self.assertLessEqual(
                    len(item[key]), major_profile.MAX_LIST[key], f"{name}.{key} 太多"
                )

    def test_salary_is_a_range_not_a_number(self):
        """起薪必须是区间：单点数字在口径不统一时没有说服力。"""
        for name in major_profile.names():
            salary = major_profile.get(name)["salary"]
            self.assertIsInstance(salary, dict)
            self.assertLess(salary["low"], salary["high"])
            self.assertTrue(salary["source"].strip())

    def test_scores_are_in_range(self):
        for name in major_profile.names():
            scores = major_profile.get(name)["scores"]
            for key in major_profile.SCORE_FIELDS:
                self.assertIn(scores[key], (1, 2, 3, 4, 5), f"{name}.{key} 越界")

    def test_sample_scores_reflect_reality(self):
        """几个好验证的判断，防止六维分是随手填的。"""
        cs = major_profile.get("计算机科学与技术")["scores"]
        med = major_profile.get("临床医学")["scores"]
        self.assertEqual(cs["job_width"], 5)
        self.assertLessEqual(med["job_width"], 3, "临床医学就业面不该比计算机宽")
        self.assertEqual(med["exam_need"], 5, "临床医学考研必要应为最高档")
        self.assertLessEqual(med["startup_fit"], 2, "开诊所门槛高，创业友好度不该高")


class AccessTest(unittest.TestCase):
    def test_get_unknown_raises(self):
        with self.assertRaises(major_profile.MajorError):
            major_profile.get("不存在的专业")

    def test_get_blank_raises(self):
        with self.assertRaises(major_profile.MajorError):
            major_profile.get("   ")

    def test_major_error_is_value_error(self):
        """server 靠 ValueError 把它转成 400，别的异常类型会直接 500。"""
        self.assertTrue(issubclass(major_profile.MajorError, ValueError))

    def test_stats_counts_every_major(self):
        stats = major_profile.stats()
        self.assertEqual(stats["total"], len(major_profile.names()))
        self.assertEqual(sum(stats["by_category"].values()), stats["total"])


class CompareTest(unittest.TestCase):
    def test_compare_returns_axes_and_items(self):
        data = major_profile.compare(["计算机科学与技术", "临床医学"])
        self.assertEqual(len(data["axes"]), 6)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["name"], "计算机科学与技术")

    def test_compare_rejects_too_few(self):
        with self.assertRaises(major_profile.MajorError):
            major_profile.compare(["计算机科学与技术"])

    def test_compare_rejects_too_many(self):
        with self.assertRaises(major_profile.MajorError):
            major_profile.compare(list(SAMPLE_NAMES) + ["法学", "汉语言文学"])

    def test_compare_rejects_duplicates(self):
        with self.assertRaises(major_profile.MajorError):
            major_profile.compare(["临床医学", "临床医学"])


class ValidatorTest(unittest.TestCase):
    """篡改一条合法画像，验证 check 能把每一类问题抓出来。"""

    def setUp(self):
        self.good = dict(major_profile.get("计算机科学与技术"))

    def test_missing_course_list_is_caught(self):
        bad = dict(self.good)
        bad["courses"] = []
        self.assertTrue(any("courses" in p for p in major_profile.check(bad)))

    def test_salary_without_source_is_caught(self):
        bad = dict(self.good)
        bad["salary"] = {"low": 7000, "high": 15000, "note": "区间"}
        self.assertTrue(any("source" in p for p in major_profile.check(bad)))

    def test_inverted_range_is_caught(self):
        bad = dict(self.good)
        bad["employment"] = {"low": 95, "high": 88, "note": "x", "source": "y"}
        self.assertTrue(any("low" in p for p in major_profile.check(bad)))

    def test_out_of_range_score_is_caught(self):
        bad = dict(self.good)
        bad["scores"] = dict(self.good["scores"], salary=9)
        self.assertTrue(any("salary" in p for p in major_profile.check(bad)))

    def test_good_profile_has_no_problem(self):
        self.assertEqual(major_profile.check(self.good), [])


if __name__ == "__main__":
    unittest.main()
