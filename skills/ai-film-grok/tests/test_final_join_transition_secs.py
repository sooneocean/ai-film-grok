"""Failure-mode tests for the join_transition_secs → join_use_ts resolver leaf.

Peeled from render_final() video-concat stage (W4 internal-leaf extraction).
Pure: deterministic, no I/O. Each test pins a failure mode that used to live
inline in the orchestrator.
"""

from __future__ import annotations

import unittest

from final.media_ops import resolve_join_transition_secs


class ResolveJoinTransitionSecsTests(unittest.TestCase):
    # --- raw input guards -------------------------------------------------
    def test_non_list_raw_returns_none(self) -> None:
        for bad in (None, 0.3, "0.3", {"a": 1}):
            with self.subTest(bad=bad):
                out = resolve_join_transition_secs(
                    bad, n_parts=3, n_shots=2, transition_sec=0.3
                )
                self.assertIsNone(out)

    def test_wrong_length_raw_returns_none(self) -> None:
        # needs len == n_shots - 1; n_shots=4 requires len 3, we give 2
        out = resolve_join_transition_secs(
            [0.2, 0.3], n_parts=4, n_shots=4, transition_sec=0.3
        )
        self.assertIsNone(out)

    def test_unconvertible_element_returns_none(self) -> None:
        for bad in ("abc", None, object()):
            with self.subTest(bad=bad):
                out = resolve_join_transition_secs(
                    [0.2, bad], n_parts=3, n_shots=3, transition_sec=0.3
                )
                self.assertIsNone(out)

    # --- pad presence branches -------------------------------------------
    def test_unmatched_large_join_count_returns_none(self) -> None:
        # n_parts=5 → n_joins=4; n_shots=2 → 4 matches none of shots+1/shots/shots-1
        out = resolve_join_transition_secs(
            [0.2, 0.3], n_parts=5, n_shots=2, transition_sec=0.4
        )
        self.assertIsNone(out)

    def test_no_pads_when_n_joins_equals_shots_minus_one(self) -> None:
        # n_parts=2 → n_joins=1; n_shots=2 → 1 == n_shots - 1 → bare story_secs
        out = resolve_join_transition_secs(
            [0.2], n_parts=2, n_shots=2, transition_sec=0.4
        )
        self.assertEqual(out, [0.2])

    def test_title_pad_when_n_joins_equals_shots(self) -> None:
        out = resolve_join_transition_secs(
            [0.2, 0.3], n_parts=4, n_shots=3, transition_sec=0.4
        )
        self.assertEqual(out, [0.4, 0.2, 0.3])

    def test_both_pads_when_n_joins_equals_shots_plus_one_full(self) -> None:
        out = resolve_join_transition_secs(
            [0.2, 0.3], n_parts=5, n_shots=3, transition_sec=0.4
        )
        # n_joins = 4, n_shots = 3 → n_joins == n_shots + 1
        self.assertEqual(out, [0.4, 0.2, 0.3, 0.4])

    def test_unmatched_join_count_returns_none(self) -> None:
        out = resolve_join_transition_secs(
            [0.2], n_parts=6, n_shots=2, transition_sec=0.4
        )
        self.assertIsNone(out)

    # --- value clamping ---------------------------------------------------
    def test_values_clamped_to_zero_and_eight_tenths(self) -> None:
        # n_parts=3 → n_joins=2; n_shots=3 → 2 == n_shots - 1 → bare story_secs
        out = resolve_join_transition_secs(
            [-0.5, 0.9], n_parts=3, n_shots=3, transition_sec=0.4
        )
        self.assertEqual(out, [0.0, 0.8])

    def test_edge_uses_epsilon_when_transition_sec_non_positive(self) -> None:
        for t in (0.0, -0.1):
            with self.subTest(t=t):
                out = resolve_join_transition_secs(
                    [0.2, 0.3], n_parts=5, n_shots=3, transition_sec=t
                )
                self.assertEqual(out[0], 0.05)
                self.assertEqual(out[-1], 0.05)

    def test_edge_uses_transition_sec_when_positive(self) -> None:
        out = resolve_join_transition_secs(
            [0.2, 0.3], n_parts=5, n_shots=3, transition_sec=0.7
        )
        self.assertEqual(out[0], 0.7)
        self.assertEqual(out[-1], 0.7)


if __name__ == "__main__":
    unittest.main()
