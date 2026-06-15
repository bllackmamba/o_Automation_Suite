"""
tests/test_matching_step.py — Tests for run_matching_step (Phase 2b).

Coverage:
  1. Full multi-stage drive via step interface — compare with run_matching
  2. Empty-CVI stage auto-skipped; subsequent stage sees correct present pool
  3. Exhaustion mid-run returns paused=False with "SC": "—" fill rows
  4. All stages empty-CVI — completes without pausing, no fill needed
"""

import numpy as np
import pandas as pd
import pytest

from syndicate_core.matching import run_matching, run_matching_step


# ── helpers ───────────────────────────────────────────────────────────────────

def _drive_step(main_df, cvi_df, carry_fwd, sc_values):
    """
    Drive run_matching_step through a full multi-stage run.

    sc_values: list of (stage_idx, sc_for_stage) in expected pause order.
    Returns the final (paused=False) result dict.
    """
    state = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                               carry_fwd=carry_fwd)
    for expected_idx, sc_val in sc_values:
        assert state["paused"], f"Expected pause at stage {expected_idx}"
        assert state["awaiting_sc_for_stage"] == expected_idx, (
            f"Expected pause at {expected_idx}, got {state['awaiting_sc_for_stage']}")
        state = run_matching_step(state["resume_state"], sc_for_stage=sc_val)
    assert not state["paused"], "Expected final (paused=False) result"
    return state


# ── Test 1: byte-identical comparison with run_matching ───────────────────────

class TestStepVsRunMatching:
    """
    Drive the same 4-stage dataset used in test_carry_forward_s_direction
    through run_matching_step and verify the final result matches run_matching.
    """

    def _dataset(self):
        main_df = pd.DataFrame({
            "n1": [1, 2, 3, 4, 5, 6],
            "n2": [10, 11, 12, 13, 14, 15],
            "n3": [20, 21, 22, 23, 24, 25],
        })
        cvi_df = pd.DataFrame({
            "w1": [1.0, 2.0, 3.0],
            "w2": [10.0, 11.0, 12.0],
            "w3": [5.0, np.nan, np.nan],
            "w4": [7.0, np.nan, np.nan],
        })
        sc_dict   = {"w1": 1, "w2": "1", "w3": [0]}
        carry_fwd = {"w1": "U", "w2": "S", "w3": "U", "w4": "U"}
        return main_df, cvi_df, sc_dict, carry_fwd

    def test_pauses_at_expected_stages(self):
        main_df, cvi_df, sc_dict, carry_fwd = self._dataset()
        # Stage 0 (w1): non-empty CVI → pause
        s1 = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                                carry_fwd=carry_fwd)
        assert s1["paused"]
        assert s1["awaiting_sc_for_stage"] == 0
        assert s1["w"] == "w1"
        assert "count_dist" in s1
        assert "resume_state" in s1

    def test_count_dist_shape_at_w1(self):
        main_df, cvi_df, sc_dict, carry_fwd = self._dataset()
        s1 = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                                carry_fwd=carry_fwd)
        # w1 CVI=[1,2,3]: rows 0-2 match once (count=1), rows 3-5 no match (count=0)
        cd = s1["count_dist"]
        assert cd.get("S0") == 3
        assert cd.get("S1") == 3

    def test_full_run_matches_run_matching(self):
        main_df, cvi_df, sc_dict, carry_fwd = self._dataset()

        # run_matching reference result
        ref = run_matching(main_df, cvi_df, sc_dict, carry_fwd)

        # step run — provide sc_values in pause order:
        # w1 (idx=0) → SC=1; w2 (idx=1) → SC="1"; w3 (idx=2) → SC=[0]
        final = _drive_step(main_df, cvi_df, carry_fwd, [
            (0, 1),
            (1, "1"),
            (2, [0]),
        ])

        assert final["selected"].equals(ref["selected"]), "selected mismatch"
        assert final["unselected"].equals(ref["unselected"]), "unselected mismatch"
        assert final["fig9_table"].equals(ref["fig9_table"]), "fig9_table mismatch"
        assert final["breakdown"].equals(ref["breakdown"]), "breakdown mismatch"
        assert len(final["debug_rows"]) == len(ref["debug_rows"])

    def test_final_result_has_required_keys(self):
        main_df, cvi_df, sc_dict, carry_fwd = self._dataset()
        final = _drive_step(main_df, cvi_df, carry_fwd, [
            (0, 1), (1, "1"), (2, [0]),
        ])
        for key in ("paused", "selected", "unselected", "fig9_table",
                    "breakdown", "debug_rows", "n_cols", "small_enough"):
            assert key in final, f"Missing key: {key}"


# ── Test 2: empty-CVI auto-advance ────────────────────────────────────────────

class TestEmptyCVIAutoAdvance:
    """
    Stage 0 has empty CVI → auto-advanced without pausing.
    Stage 1 has data → pause; present pool should be the carry-forward from stage 0.
    """

    def test_empty_cvi_stage_not_paused(self):
        main_df = pd.DataFrame({"n1": [1, 2, 3], "n2": [10, 11, 12]})
        cvi_df  = pd.DataFrame({
            "w1": [np.nan, np.nan, np.nan],   # empty
            "w2": [1.0, 2.0, np.nan],          # has data
        })
        carry_fwd = {"w1": "U", "w2": "U"}

        s = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                               carry_fwd=carry_fwd)
        # Should pause at w2 (idx=1), NOT w1 (idx=0)
        assert s["paused"]
        assert s["awaiting_sc_for_stage"] == 1
        assert s["w"] == "w2"

    def test_empty_cvi_row_in_fig9_before_pause(self):
        main_df = pd.DataFrame({"n1": [1, 2, 3], "n2": [10, 11, 12]})
        cvi_df  = pd.DataFrame({
            "w1": [np.nan, np.nan, np.nan],
            "w2": [1.0, 2.0, np.nan],
        })
        carry_fwd = {"w1": "U", "w2": "U"}

        s = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                               carry_fwd=carry_fwd)
        # resume_state should already have the w1 fig9 row buffered
        assert len(s["resume_state"]["fig9_rows"]) == 1
        assert s["resume_state"]["fig9_rows"][0]["CVI"] == "w1"
        assert s["resume_state"]["fig9_rows"][0]["Present\nCount"] == "— No CVI"

    def test_subsequent_stage_sees_carry_forward_pool(self):
        """
        After an empty-CVI stage, prev_unsel carries the full present pool
        forward.  The next stage (direction=U) should see all 3 main rows.
        """
        main_df = pd.DataFrame({"n1": [1, 2, 3], "n2": [10, 11, 12]})
        cvi_df  = pd.DataFrame({
            "w1": [np.nan, np.nan, np.nan],
            "w2": [1.0, 2.0, np.nan],
        })
        carry_fwd = {"w1": "U", "w2": "U"}

        s = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                               carry_fwd=carry_fwd)
        # count_dist at w2 should reflect 3 rows (carry-forward from w1)
        # CVI=[1,2]: row 0 matches n1=1 (count=1), row 1 matches n1=2 (count=1),
        # row 2 has n1=3 which is NOT in CVI=[1,2] (count=0)
        cd = s["count_dist"]
        total = sum(cd.values())
        assert total == 3, f"Expected 3 rows in count_dist, got {total}: {cd}"


# ── Test 3: exhaustion mid-run fills remaining stages with "SC": "—" ──────────

class TestExhaustionFill:
    """
    Stage 0 selects all rows → prev_unsel=empty.
    Stage 1 direction=U → present=empty → _apply_stage_sc → exhausted=True.
    Stage 2 must be filled with SC="—", never processed.
    """

    def _dataset(self):
        main_df = pd.DataFrame({"n1": [1, 2], "n2": [10, 11]})
        cvi_df  = pd.DataFrame({
            "w1": [1.0, 2.0],      # all rows selected (count=1 each, sc={1})
            "w2": [3.0, np.nan],   # present=empty (unsel after w1)
            "w3": [5.0, np.nan],   # never processed
        })
        carry_fwd = {"w1": "U", "w2": "U", "w3": "U"}
        return main_df, cvi_df, carry_fwd

    def test_exhaustion_returns_not_paused(self):
        main_df, cvi_df, carry_fwd = self._dataset()
        # w1 → SC=1 (select both rows, unsel=empty); w2 → SC=[] (empty present)
        final = _drive_step(main_df, cvi_df, carry_fwd, [(0, 1), (1, [])])
        assert not final["paused"]

    def test_fill_row_has_empty_sc(self):
        main_df, cvi_df, carry_fwd = self._dataset()
        final = _drive_step(main_df, cvi_df, carry_fwd, [(0, 1), (1, [])])
        fig9  = final["fig9_table"]
        assert len(fig9) == 3
        # w3 must have been filled (not processed), SC="—"
        w3_row = fig9[fig9["CVI"] == "w3"].iloc[0]
        assert w3_row["SC"] == "—"
        assert w3_row["Present\nCount"] == "—"
        assert w3_row["Selected"] == "S:0"

    def test_fill_debug_row_note(self):
        main_df, cvi_df, carry_fwd = self._dataset()
        final = _drive_step(main_df, cvi_df, carry_fwd, [(0, 1), (1, [])])
        w3_debug = next(r for r in final["debug_rows"] if r["w"] == "w3")
        assert w3_debug["note"] == "No present data — exhausted"


# ── Test 4: all stages empty-CVI, no pause, no fill ──────────────────────────

class TestAllEmptyCVI:
    """
    Every w-column has empty CVI → completes without ever pausing.
    Final result: selected=empty, unselected=main_df (carried through all stages).
    """

    def test_no_pause_when_all_cvi_empty(self):
        main_df = pd.DataFrame({"n1": [1, 2, 3]})
        cvi_df  = pd.DataFrame({
            "w1": [np.nan, np.nan, np.nan],
            "w2": [np.nan, np.nan, np.nan],
        })
        carry_fwd = {"w1": "U", "w2": "U"}

        result = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                                    carry_fwd=carry_fwd)
        assert not result["paused"]

    def test_final_unselected_is_full_main(self):
        main_df = pd.DataFrame({"n1": [1, 2, 3]})
        cvi_df  = pd.DataFrame({
            "w1": [np.nan, np.nan, np.nan],
            "w2": [np.nan, np.nan, np.nan],
        })
        carry_fwd = {"w1": "U", "w2": "U"}

        result = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                                    carry_fwd=carry_fwd)
        # All 3 rows should be in unselected (carried forward)
        assert len(result["unselected"]) == 3
        assert result["selected"].empty

    def test_fig9_has_two_empty_cvi_rows(self):
        main_df = pd.DataFrame({"n1": [1, 2, 3]})
        cvi_df  = pd.DataFrame({
            "w1": [np.nan, np.nan, np.nan],
            "w2": [np.nan, np.nan, np.nan],
        })
        carry_fwd = {"w1": "U", "w2": "U"}

        result = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                                    carry_fwd=carry_fwd)
        fig9 = result["fig9_table"]
        assert len(fig9) == 2
        assert all(fig9["Present\nCount"] == "— No CVI")

    def test_empty_inputs_return_not_paused(self):
        """Empty main_df → immediate paused=False with empty DataFrames."""
        result = run_matching_step(
            None,
            main_df=pd.DataFrame(),
            cvi_df=pd.DataFrame({"w1": [1.0]}),
            carry_fwd={},
        )
        assert not result["paused"]
        assert result["selected"].empty
        assert result["fig9_table"].empty


# ── Test 5: step result is a superset of run_matching result keys ─────────────

class TestStepSupersetKeys:
    """
    The step-driven final result must contain AT LEAST every key that
    run_matching returns (it may also carry extra step-mode keys).
    """

    def test_step_result_keys_are_superset_of_run_matching_keys(self):
        main_df = pd.DataFrame({
            "n1": [1, 2, 3],
            "n2": [10, 11, 12],
        })
        cvi_df = pd.DataFrame({
            "w1": [1.0, 2.0, np.nan],
            "w2": [10.0, np.nan, np.nan],
        })
        sc_dict   = {"w1": 1, "w2": 1}
        carry_fwd = {"w1": "U", "w2": "U"}

        ref_result   = run_matching(main_df, cvi_df, sc_dict, carry_fwd)
        step_result  = _drive_step(main_df, cvi_df, carry_fwd, [(0, 1), (1, 1)])

        missing = set(ref_result.keys()) - set(step_result.keys())
        assert not missing, (
            f"step result is missing keys present in run_matching: {missing}"
        )
