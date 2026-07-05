"""
Part B — Pace × SC-source 4-combination matrix.

The UI splits one conflated toggle into two independent axes:
  Pace     : Auto  -> run_matching (straight through)
             Manual-> run_matching_step (pause per w_row)
  SC source: FILE  -> sc_dict / sc_for_stage carries the SC criterion
             NONE  -> empty SC: counts only, NO fabricated fallback

These tests pin the engine behaviour each combo routes into. The key
guarantee (Auto + None) is that Main Count / Main Breakdown still populate
at every w_row while Selected/Unselected show no selection.
"""
import numpy as np
import pandas as pd

from syndicate_core.matching import run_matching, run_matching_step


def _dataset():
    # w1 CVI = {1, 2}: rows 0,1 match once (count=1); rows 2,3 no match (count=0)
    main_df = pd.DataFrame({
        "n1": [1, 2, 3, 4],
        "n2": [10, 11, 12, 13],
    })
    cvi_df = pd.DataFrame({"w1": [1.0, 2.0, np.nan, np.nan]})
    carry_fwd = {"w1": "U"}
    return main_df, cvi_df, carry_fwd


def _w1_row(fig9):
    return fig9[fig9["CVI"] == "w1"].iloc[0]


# ── Auto + SC loaded ─────────────────────────────────────────────────────────

def test_auto_file_selects_using_sc_threshold():
    main_df, cvi_df, carry_fwd = _dataset()
    res = run_matching(main_df, cvi_df, {"w1": [1]}, carry_fwd)
    # SC={1}: the two count==1 rows are selected, the two count==0 rows are not.
    assert len(res["selected"]) == 2
    assert len(res["unselected"]) == 2
    row = _w1_row(res["fig9_table"])
    assert row["SC"] == "1"
    assert row["Selected"] == "S:2"


# ── Auto + None (the case that prompted the fix) ─────────────────────────────

def test_auto_none_is_counts_only_no_selection_no_fabricated_sc():
    main_df, cvi_df, carry_fwd = _dataset()
    res = run_matching(main_df, cvi_df, {}, carry_fwd)   # empty SC == None

    # No selection happened, everything carried as unselected.
    assert res["selected"].empty
    assert len(res["unselected"]) == 4

    row = _w1_row(res["fig9_table"])
    # Main Count / Main Breakdown DO populate (counts only).
    assert row["Main\nCount"] not in ("", "—")
    assert row["Main\nBreakdown"] not in ("", "—")
    # No fabricated fallback SC, and no Selected population.
    assert row["SC"] == "—"
    assert row["Selected"] == "S:0"


# ── Manual + SC loaded (pre-filled suggestion accepted) ─────────────────────

def test_manual_file_applies_suggested_sc():
    main_df, cvi_df, carry_fwd = _dataset()
    s = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                          carry_fwd=carry_fwd)
    assert s["paused"] and s["awaiting_sc_for_stage"] == 0
    # UI pre-fills SC file value [1] as the suggestion; user accepts it.
    final = run_matching_step(s["resume_state"], sc_for_stage=[1])
    assert not final["paused"]
    assert len(final["selected"]) == 2
    assert len(final["unselected"]) == 2


# ── Manual + None (pick live; picks nothing) ────────────────────────────────

def test_manual_none_no_selection_when_empty_pick():
    main_df, cvi_df, carry_fwd = _dataset()
    s = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                          carry_fwd=carry_fwd)
    assert s["paused"] and s["awaiting_sc_for_stage"] == 0
    final = run_matching_step(s["resume_state"], sc_for_stage=[])
    assert not final["paused"]
    assert final["selected"].empty
    assert len(final["unselected"]) == 4


# ── Cross-check: Auto+None and Manual+None agree (no engine divergence) ──────

def test_auto_none_and_manual_none_agree():
    main_df, cvi_df, carry_fwd = _dataset()
    auto = run_matching(main_df, cvi_df, {}, carry_fwd)
    s = run_matching_step(None, main_df=main_df, cvi_df=cvi_df,
                          carry_fwd=carry_fwd)
    manual = run_matching_step(s["resume_state"], sc_for_stage=[])
    assert auto["selected"].empty and manual["selected"].empty
    assert len(auto["unselected"]) == len(manual["unselected"]) == 4
