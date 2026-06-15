"""Tests for syndicate_core/matching.py"""

import numpy as np
import pandas as pd

from syndicate_core.matching import run_matching


class TestRunMatching:
    def test_multi_stage_exhaustion_and_nonlist_sc(self):
        """
        3 stages: stage 1 selects all 3 rows (count=1, sc={1} via string "1"),
        leaving prev_unsel empty.  Stage 2 direction=U → present is empty →
        _apply_stage_sc runs but exhausted=True → stage 3 is filled by the
        exhaustion-fill loop (never processed).

        Also exercises non-list sc_dict values: "1" (string) and 2 (int).
        """
        main_df = pd.DataFrame({
            "n1": [1, 2, 3],
            "n2": [10, 11, 12],
            "n3": [20, 21, 22],
        })
        # w1 CVI=[1,2,3]: each row hits n1 exactly once → pres_counts=[1,1,1]
        # w2 CVI=[4]: present pool is empty (prev_unsel after stage 1)
        # w3 CVI=[5]: never processed — filled by exhaustion loop
        cvi_df = pd.DataFrame({
            "w1": [1.0, 2.0, 3.0],
            "w2": [4.0, np.nan, np.nan],
            "w3": [5.0, np.nan, np.nan],
        })
        sc_dict   = {"w1": "1", "w2": 2}          # string and int — non-list
        carry_fwd = {"w1": "U", "w2": "U", "w3": "U"}

        result = run_matching(main_df, cvi_df, sc_dict, carry_fwd)
        fig9  = result["fig9_table"]
        debug = result["debug_rows"]

        assert len(fig9)  == 3
        assert len(debug) == 3

        # Stage 1 (w1): sc="1" → {1}; all 3 rows get count=1 → selected
        assert fig9.iloc[0]["Selected"]   == "S:3"
        assert fig9.iloc[0]["Unselected"] == "U:0"

        # Stage 2 (w2): present pool is empty → processed normally but exhausted
        assert fig9.iloc[1]["Present\nData"] == "U:0"
        assert fig9.iloc[1]["Selected"]       == "S:0"
        assert fig9.iloc[1]["Unselected"]     == "U:0"
        assert debug[1]["note"] == ""          # processed (not the exhausted-fill label)

        # Stage 3 (w3): filled by exhaustion loop, never ran _apply_stage_sc
        assert fig9.iloc[2]["Present\nData"]  == "U:0"
        assert fig9.iloc[2]["Present\nCount"] == "—"
        assert debug[2]["note"] == "No present data — exhausted"

    def test_carry_forward_s_direction(self):
        """
        4 stages covering all three dispatcher paths in one pass:

        w1 (U, idx=0): present=full M=6; CVI=[1,2,3]; sc=1 (int) →
            rows 0-2 selected (n1 in CVI, count=1), rows 3-5 unselected.
        w2 (S):        present=prev_sel=rows 0-2; CVI=[10,11,12]; sc="1" (str) →
            all 3 rows match n2, all selected → prev_unsel=empty.
        w3 (U):        present=prev_unsel=empty → _apply_stage_sc runs on
            empty pool, exhausted=True → fill loop fires for w4.
        w4:            filled inline by exhaustion loop (never processed).

        Expected values were derived by running BOTH the pre-refactor
        (commit dfe5b67) and post-refactor (783deef) run_matching on this
        identical dataset and asserting old.equals(new) for "selected",
        "unselected", "fig9_table", and "breakdown" — all four matched.
        The assertions below are hardcoded from that verified run.
        """
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
        sc_dict   = {"w1": 1, "w2": "1", "w3": [0]}   # int, string, list
        carry_fwd = {"w1": "U", "w2": "S", "w3": "U", "w4": "U"}

        result = run_matching(main_df, cvi_df, sc_dict, carry_fwd)
        fig9  = result["fig9_table"]
        debug = result["debug_rows"]

        assert len(fig9)  == 4
        assert len(debug) == 4

        # w1 — U-direction (idx=0 always uses full main_df)
        assert fig9.iloc[0]["Dir"]           == "U"
        assert fig9.iloc[0]["Present\nData"] == "M:6"
        assert fig9.iloc[0]["Selected"]      == "S:3"
        assert fig9.iloc[0]["Unselected"]    == "U:3"
        assert debug[0]["direction"]         == "U"

        # w2 — S-direction: present = prev_sel (rows 0-2)
        assert fig9.iloc[1]["Dir"]             == "S"
        assert fig9.iloc[1]["Present\nData"]   == "S:3"
        assert fig9.iloc[1]["Present\nCount"]  == "1"
        assert fig9.iloc[1]["Selected"]        == "S:3"
        assert fig9.iloc[1]["Unselected"]      == "U:0"
        assert debug[1]["direction"]           == "S"   # confirms S-branch was taken

        # w3 — U-direction, empty present pool → processed, exhausted=True
        assert fig9.iloc[2]["Dir"]             == "U"
        assert fig9.iloc[2]["Present\nData"]   == "U:0"
        assert fig9.iloc[2]["Present\nCount"]  == ""    # _count_str(empty) → ""
        assert fig9.iloc[2]["Selected"]        == "S:0"
        assert fig9.iloc[2]["Unselected"]      == "U:0"
        assert debug[2]["note"]                == ""    # processed, not the fill-loop label

        # w4 — filled by exhaustion loop (Present\nCount hardcoded "—")
        assert fig9.iloc[3]["Present\nData"]   == "U:0"
        assert fig9.iloc[3]["Present\nCount"]  == "—"
        assert fig9.iloc[3]["Selected"]        == "S:0"
        assert debug[3]["note"]                == "No present data — exhausted"
