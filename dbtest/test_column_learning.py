"""
causelist_core._learn_column_thresholds(): the four column starts of a cause
list, learned from where its lines begin.

The 26.11.2026 Srinagar list had its advocate column's lines split between
x=411 and x=414 (two 3pt buckets). Both made the top four, the real Sr No
column (x=36) dropped out, and the whole 54-page list parsed as a single
entry with a 19,154-character Sr No. Line-start counts below are that list's.
Run: python -m unittest dbtest/test_column_learning.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import causelist_core as cc  # noqa: E402


def lines_starting_at(counts):
    return [[{"x0": x, "x1": x + 10, "top": 0, "text": "w"}] for x, n in counts.items() for _ in range(n)]


class ColumnLearning(unittest.TestCase):
    def test_column_split_across_two_buckets_is_merged(self):
        # 26.11.2026: 57:931, 411:903, 207:465, 414:408, 36:356, 210:154, 480:54
        counts = {57: 931, 411: 903, 207: 465, 414: 408, 36: 356, 210: 154, 480: 54, 99: 47}
        self.assertEqual(cc._learn_column_thresholds(lines_starting_at(counts)), [36, 57, 207, 411])

    def test_cleanly_split_list_is_unchanged(self):
        counts = {36: 400, 57: 900, 207: 600, 411: 800, 414: 40, 480: 30}
        self.assertEqual(cc._learn_column_thresholds(lines_starting_at(counts)), [36, 57, 207, 411])

    def test_too_few_columns(self):
        self.assertIsNone(cc._learn_column_thresholds(lines_starting_at({36: 5, 57: 5, 207: 5})))


if __name__ == "__main__":
    unittest.main()
