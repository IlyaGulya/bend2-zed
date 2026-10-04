#!/usr/bin/env python3
"""Regression-check the release decisions exposed in upstream reports."""
import unittest
from check_upstream import review_results


class ReviewGate(unittest.TestCase):
    def gate(self, classification, status):
        return review_results(
            [{"file": "fixture.bend", "status": status}],
            {"review_complete": True, "reviews": [{"file": "fixture.bend", "classification": classification}]},
        )

    def test_compiler_owned_constraint_keeps_editor_tree(self):
        self.assertTrue(self.gate("compiler-only-constraint", "accepted")["passed"])
        rejected = self.gate("compiler-only-constraint", "rejected")
        self.assertFalse(rejected["passed"])
        self.assertEqual(rejected["accepted_regressions"], ["fixture.bend"])

    def test_repaired_valid_syntax_cannot_become_exempt_rejection(self):
        self.assertTrue(self.gate("valid-syntax", "accepted")["passed"])
        rejected = self.gate("valid-syntax", "rejected")
        self.assertFalse(rejected["passed"])
        self.assertEqual(rejected["accepted_regressions"], ["fixture.bend"])

    def test_malformed_syntax_becoming_accepted_requires_review(self):
        self.assertTrue(self.gate("malformed-syntax", "rejected")["passed"])
        accepted = self.gate("malformed-syntax", "accepted")
        self.assertFalse(accepted["passed"])
        self.assertEqual(accepted["formerly_rejected_accepted"], ["fixture.bend"])

    def test_known_valid_gap_never_passes_as_expected_rejection(self):
        rejected = self.gate("valid-source-grammar-gap", "rejected")
        self.assertFalse(rejected["passed"])
        self.assertEqual(rejected["valid_source_gaps"], ["fixture.bend"])

    def test_timeout_is_not_a_syntax_rejection(self):
        failed = self.gate("malformed-syntax", "timeout")
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["infrastructure_failures"], ["fixture.bend"])
        self.assertEqual(failed["new_rejections"], [])

    def test_new_rejection_requires_explicit_review(self):
        failed = review_results([{"file": "new.bend", "status": "rejected"}],
                                {"review_complete": True, "reviews": []})
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["new_rejections"], ["new.bend"])


if __name__ == "__main__":
    unittest.main()
