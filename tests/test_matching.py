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
