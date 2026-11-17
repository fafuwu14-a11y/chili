"""二次检验（学完先导课还感不感兴趣）的单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import mooc_retest  # noqa: E402


class QuestionTest(unittest.TestCase):
    def test_三道题且id稳定(self):
        items = mooc_retest.questions("计算机科学与技术")
        self.assertEqual([item["id"] for item in items], ["invest", "curiosity", "resist"])

    def test_题干带专业名(self):
        items = mooc_retest.questions("法学")
        for item in items:
            self.assertIn("法学", item["title"])

    def test_主干课写进第二题(self):
        titles = [item["title"] for item in mooc_retest.questions("计算机科学与技术")]
        self.assertIn("《", titles[1])

    def test_空专业报错(self):
        with self.assertRaises(ValueError):
            mooc_retest.questions("  ")


class EvaluateTest(unittest.TestCase):
    def test_高分建议深入(self):
        result = mooc_retest.evaluate("计算机科学与技术", {"invest": 5, "curiosity": 4, "resist": 4})
        self.assertEqual(result["verdict"], "deep")
        self.assertEqual(result["title"], "建议深入")
        self.assertGreaterEqual(result["score"], 4)

    def test_中分建议先试课(self):
        result = mooc_retest.evaluate("法学", {"invest": 3, "curiosity": 3, "resist": 2})
        self.assertEqual(result["verdict"], "trial")

    def test_低分建议换专业(self):
        result = mooc_retest.evaluate("会计学", {"invest": 1, "curiosity": 2, "resist": 1})
        self.assertEqual(result["verdict"], "switch")

    def test_指出最弱的一环(self):
        result = mooc_retest.evaluate("土木工程", {"invest": 5, "curiosity": 1, "resist": 5})
        self.assertEqual(result["weakest"]["id"], "curiosity")
        self.assertEqual(result["weakest"]["score"], 1)

    def test_分数照原样回传(self):
        result = mooc_retest.evaluate("数学类", {"invest": 2, "curiosity": 5, "resist": 3})
        scores = {item["id"]: item["score"] for item in result["items"]}
        self.assertEqual(scores, {"invest": 2, "curiosity": 5, "resist": 3})
        self.assertEqual(result["score"], round((2 + 5 + 3) / 3, 2))

    def test_缺题报错(self):
        with self.assertRaises(ValueError):
            mooc_retest.evaluate("数学类", {"invest": 3})

    def test_越界分数报错(self):
        for bad in (0, 6, -1, 99):
            with self.assertRaises(ValueError):
                mooc_retest.evaluate("数学类", {"invest": bad, "curiosity": 3, "resist": 3})

    def test_非数字报错(self):
        with self.assertRaises(ValueError):
            mooc_retest.evaluate("数学类", {"invest": "5", "curiosity": 3, "resist": 3})
        with self.assertRaises(ValueError):
            mooc_retest.evaluate("数学类", {"invest": True, "curiosity": 3, "resist": 3})

    def test_答案不是对象报错(self):
        with self.assertRaises(ValueError):
            mooc_retest.evaluate("数学类", [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
