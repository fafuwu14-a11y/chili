"""六维量化的测试：56 个专业类全覆盖、分数在 1–5、和已发布的样例画像一致。

最后一条最重要：样例画像是人工判断的，量化规则是代码生成的，
两边对不上就说明规则写错了——要么改规则，要么改样例，不能两边都留着。
"""

import unittest

from app import major_catalog, major_quant, major_profile

SAMPLE_NAMES = ("计算机科学与技术", "临床医学", "社会工作")


def all_group_ids() -> set[str]:
    return {
        group["id"]
        for category in major_catalog.meta()["categories"]
        for group in category["groups"]
    }


class CoverageTest(unittest.TestCase):
    def test_every_group_has_scores(self):
        ids = all_group_ids()
        missing = ids - set(major_quant.GROUP_SCORES)
        self.assertEqual(missing, set(), f"这些专业类没有基准分：{sorted(missing)}")

    def test_no_extra_group(self):
        """多出来的键多半是拼写错误，会让某个专业类悄悄回落到中性分。"""
        extra = set(major_quant.GROUP_SCORES) - all_group_ids()
        self.assertEqual(extra, set(), f"这些键在目录里不存在：{sorted(extra)}")

    def test_every_score_is_in_range(self):
        for group_id, scores in major_quant.GROUP_SCORES.items():
            self.assertEqual(set(scores), set(major_profile.SCORE_FIELDS), f"{group_id} 维度不齐")
            for key, value in scores.items():
                self.assertIn(value, (1, 2, 3, 4, 5), f"{group_id}.{key} = {value}")


class SampleConsistencyTest(unittest.TestCase):
    """样例画像与量化规则必须给出同一组分数。"""

    def test_samples_match_generated_scores(self):
        for name in SAMPLE_NAMES:
            item = major_profile.get(name)
            generated = major_quant.scores_for(name, item["group_id"])
            self.assertEqual(
                generated, item["scores"], f"{name} 的样例画像与量化规则不一致"
            )


class KeywordTest(unittest.TestCase):
    def test_software_engineering_needs_less_exam(self):
        base = major_quant.scores_for("计算机科学与技术", "计算机")
        software = major_quant.scores_for("软件工程", "计算机")
        self.assertLess(software["exam_need"], base["exam_need"])

    def test_ai_needs_more_exam(self):
        ai = major_quant.scores_for("人工智能", "计算机")
        self.assertEqual(ai["exam_need"], 5)

    def test_longest_keyword_wins(self):
        """「计算机科学与技术」不该被「计算机」这类短词误伤；这里用分数验证结果稳定。"""
        a = major_quant.scores_for("计算机科学与技术", "计算机")
        self.assertEqual(a["job_width"], 5)

    def test_unknown_group_falls_back(self):
        scores = major_quant.scores_for("某个专业", "不存在的类")
        self.assertEqual(scores, major_quant.GROUP_SCORES["other"])


class ExplainTest(unittest.TestCase):
    def test_explain_returns_six_rules(self):
        data = major_quant.explain("临床医学", "临床医学")
        self.assertEqual(len(data["rules"]), 6)
        self.assertEqual(data["scores"]["exam_need"], 5)

    def test_explain_rule_scores_match(self):
        data = major_quant.explain("口腔医学", "口腔医学")
        by_key = {rule["key"]: rule["score"] for rule in data["rules"]}
        self.assertEqual(by_key, data["scores"])

    def test_explain_text_is_human_readable(self):
        data = major_quant.explain("临床医学", "临床医学")
        self.assertTrue(all(rule["text"] for rule in data["rules"]))


if __name__ == "__main__":
    unittest.main()
