import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matrix_reach import expand_matrix, audit_workflow_text  # noqa: E402
from matrix_reach.cli import self_test, scan  # noqa: E402


class ExpansionTests(unittest.TestCase):
    def test_cartesian_product(self):
        r = expand_matrix("b", {"os": ["l", "w"], "py": ["3.11", "3.12"]})
        self.assertEqual(len(r.base), 4)
        self.assertEqual(len(r.final), 4)

    def test_exclude_subset_match(self):
        r = expand_matrix("b", {"os": ["l", "w"], "py": ["3.11", "3.12"],
                                "exclude": [{"os": "w"}]})
        self.assertEqual([c["os"] for c in r.final], ["l", "l"])

    def test_include_augments_matching_combos(self):
        r = expand_matrix("b", {"os": ["l", "w"], "include": [{"os": "l", "cc": "gcc"}]})
        self.assertEqual(len(r.final), 2)
        self.assertEqual([c.get("cc") for c in r.final], ["gcc", None])

    def test_include_without_axis_keys_applies_to_all(self):
        r = expand_matrix("b", {"os": ["l", "w"], "include": [{"color": "green"}]})
        self.assertTrue(all(c["color"] == "green" for c in r.final))

    def test_include_new_combo(self):
        r = expand_matrix("b", {"os": ["l"], "arch": ["x86"],
                                "include": [{"os": "l", "arch": "arm"}]})
        self.assertEqual(len(r.final), 2)
        self.assertEqual(r.added, 1)

    def test_duplicate_combo_detected(self):
        r = expand_matrix("b", {"os": ["l", "l"]})
        self.assertIn("MR001", [p["rule"] for p in r.problems])

    def test_expression_is_skipped_not_guessed(self):
        r = expand_matrix("b", {"os": "${{ fromJSON(needs.x.outputs.m) }}"})
        self.assertIsNotNone(r.skipped)

    def test_max_parallel_and_fail_fast_from_strategy(self):
        r = expand_matrix("b", {"os": ["l"]}, {"max-parallel": 9, "fail-fast": "yes"})
        rules = [p["rule"] for p in r.problems]
        self.assertIn("MR007", rules)
        self.assertIn("MR008", rules)


class SelfTestTests(unittest.TestCase):
    def test_every_rule_is_proven(self):
        ok, rows = self_test()
        self.assertTrue(ok, rows)
        self.assertEqual(len(rows), 10)

    def test_cli_self_test_exit_zero(self):
        root = Path(__file__).resolve().parents[1]
        p = subprocess.run([sys.executable, "-m", "matrix_reach.cli", "--self-test"],
                           cwd=root, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)["ok"])

    def test_scan_corpus(self):
        root = Path(__file__).resolve().parents[1]
        report = scan([str(root / "examples")])
        self.assertGreaterEqual(report["matrices"], 3)
        self.assertGreater(report["combinations"], 10)


if __name__ == "__main__":
    unittest.main()
