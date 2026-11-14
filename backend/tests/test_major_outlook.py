"""专业前景画像的测试。

重点不是文案好不好看，而是：任何一个专业查过来都得有话说，且每句话都得挂在
具体字段上（不能是空字符串——前端会把空的整块渲染出来）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import major_catalog, major_outlook  # noqa: E402


class CoverageTest(unittest.TestCase):
    """目录里的每个专业类、每个门类都要有画像，否则前端会露出空白块。"""

    def test_every_group_has_outlook(self) -> None:
        meta = major_catalog.meta()
        ids = [group["id"] for cat in meta["categories"] for group in cat["groups"]]
        missing = [gid for gid in ids if gid not in major_outlook.GROUP_OUTLOOK]
        self.assertEqual(missing, [], f"这些专业类还没有画像：{missing}")

    def test_every_category_has_fallback(self) -> None:
        meta = major_catalog.meta()
        for category in meta["categories"]:
            self.assertIn(category["id"], major_outlook.CATEGORY_FALLBACK, category["name"])

    def test_group_outlook_fields_are_complete(self) -> None:
        for gid, profile in major_outlook.GROUP_OUTLOOK.items():
            for field in ("verdict", "what", "market", "risk"):
                self.assertTrue(profile.get(field), f"{gid} 缺 {field}")
            self.assertEqual(len(profile.get("path") or []), 4, f"{gid} 的四年路线要正好四步")

    def test_keyword_patch_fields_are_subset(self) -> None:
        """关键词修正只能覆盖已有字段，不能凭空塞一个前端不认识的键。"""
        allowed = {"verdict", "what", "market", "risk", "path"}
        for gid, profile in major_outlook.GROUP_OUTLOOK.items():
            for word, patch in (profile.get("keyword") or {}).items():
                self.assertTrue(word, gid)
                for key in patch:
                    self.assertIn(key, allowed, f"{gid} 的「{word}」修正里有未知字段 {key}")


class BuildTest(unittest.TestCase):
    """build() 的输入输出契约。"""

    def test_unknown_major_raises(self) -> None:
        with self.assertRaises(major_catalog.MajorError):
            major_outlook.build("不存在的专业名")
        with self.assertRaises(major_catalog.MajorError):
            major_outlook.build("")

    def test_returns_all_sections(self) -> None:
        data = major_outlook.build("会计学")
        for field in ("major", "group", "group_id", "category", "category_name", "source"):
            self.assertTrue(data.get(field), field)
        for field in ("verdict", "what", "market", "risk", "signal", "basis"):
            self.assertTrue(data.get(field), field)
        self.assertEqual(len(data["path"]), 4)

    def test_group_matches_catalog(self) -> None:
        item = major_catalog.detail("计算机科学与技术")
        data = major_outlook.build("计算机科学与技术")
        self.assertEqual(data["group_id"], item["group_id"])
        self.assertEqual(data["category"], item["category"])

    def test_every_major_can_be_built(self) -> None:
        """821 个专业逐个跑：任何一条查不到、或者某段是空字符串，都算失败。"""
        names = [item["name"] for item in major_catalog._catalog()["majors"]]
        self.assertGreater(len(names), 800)
        for name in names:
            data = major_outlook.build(name)
            self.assertTrue(data["verdict"], name)
            self.assertTrue(data["what"], name)
            self.assertTrue(data["market"], name)
            self.assertTrue(data["risk"], name)
            self.assertEqual(len(data["path"]), 4, name)
            self.assertIn(data["source"], {"专业类画像", "这个方向的具体判断", "门类通用判断"}, name)


class KeywordTest(unittest.TestCase):
    """同组内不同专业要能拉开差距，否则「具体分析」就成了空话。"""

    def test_keyword_beats_group_default(self) -> None:
        software = major_outlook.build("软件工程")
        generic = major_outlook.build("计算机科学与技术")
        self.assertEqual(software["source"], "这个方向的具体判断")
        self.assertIn("学了就能干活", software["verdict"])
        self.assertNotEqual(software["verdict"], generic["verdict"])

    def test_longest_keyword_wins(self) -> None:
        # 「信息安全」和「信息」都在表里时，必须命中更长的那个
        hit = major_outlook._pick_keyword("信息安全", {"信息": {"verdict": "短"}, "信息安全": {"verdict": "长"}})
        self.assertEqual(hit["verdict"], "长")

    def test_data_signal_mentions_scale(self) -> None:
        data = major_outlook.build("计算机科学与技术")
        self.assertIn("招生单元", data["signal"])
        self.assertIn("省", data["signal"])

    def test_verdict_is_not_a_slogan(self) -> None:
        """判断要说出代价，不能只有「前景广阔」这类空话。"""
        for name in ("计算机科学与技术", "临床医学", "法学", "土木工程", "汉语言文学"):
            verdict = major_outlook.build(name)["verdict"]
            self.assertGreaterEqual(len(verdict), 8, f"{name} 的判断太短：{verdict}")
            self.assertNotIn("前景广阔", verdict)


class PathTest(unittest.TestCase):
    """四年路线是给「已经决定走这条路」的人看的，必须写成动作。"""

    def test_steps_start_with_a_stage(self) -> None:
        data = major_outlook.build("临床医学")
        for index, step in enumerate(data["path"]):
            self.assertIn("：", step, f"第 {index + 1} 步缺少「阶段：动作」的结构")
            head = step.split("：")[0]
            self.assertTrue(head, step)

    def test_no_duplicate_steps(self) -> None:
        data = major_outlook.build("机械设计制造及其自动化")
        self.assertEqual(len(set(data["path"])), len(data["path"]))


if __name__ == "__main__":
    unittest.main()
