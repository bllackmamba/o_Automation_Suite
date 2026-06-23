"""
tests/test_collation.py — Unit tests for syndicate_core/collation.py

Covers: _compute_sc_block, _sc_distribution_table, _save_sc_block,
        _load_sc_blocks, _run_sc_auto.
"""

import numpy as np
import pandas as pd
import pytest

from syndicate_core.collation import (
    _compute_sc_block,
    _load_sc_blocks,
    _run_sc_auto,
    _save_sc_block,
    _sc_distribution_table,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def main_df():
    return pd.DataFrame({
        "n1": [1, 4, 7],
        "n2": [2, 5, 8],
        "n3": [3, 6, 9],
    })


@pytest.fixture()
def n_cols():
    return ["n1", "n2", "n3"]


@pytest.fixture()
def b_var_df():
    """B-style (row-oriented, w label + pos_N columns)."""
    return pd.DataFrame({
        "w":     ["w1", "w2"],
        "pos_1": [1,    4],
        "pos_2": [2,    5],
        "pos_3": [3,    6],
    })


# ── _compute_sc_block ─────────────────────────────────────────────────────────

class TestComputeScBlock:

    def test_basic_returns_per_position_arrays(self, b_var_df, main_df, n_cols):
        """_compute_sc_block returns np.ndarrays for each position and a _meta dict."""
        result = _compute_sc_block("B", b_var_df, main_df, n_cols)

        assert isinstance(result, dict)
        assert "_meta" in result
        # Three value columns → w1, w2, w3
        assert "w1" in result
        assert "w2" in result
        assert "w3" in result
        # Each value is a count array with one entry per main_df row
        assert isinstance(result["w1"], np.ndarray)
        assert len(result["w1"]) == len(main_df)

    def test_correct_counts(self, b_var_df, main_df, n_cols):
        """Position w1 values [1,4] — rows 0 and 1 each get count=1, row 2 gets 0."""
        result = _compute_sc_block("B", b_var_df, main_df, n_cols)
        # w1 CVI values: [1, 4] (first pos column across both sets)
        # row0: n1=1 ∈ {1,4} → 1; row1: n1=4 ∈ {1,4} → 1; row2: nothing → 0
        assert list(result["w1"]) == [1, 1, 0]

    def test_meta_fields(self, b_var_df, main_df, n_cols):
        result = _compute_sc_block("B", b_var_df, main_df, n_cols)
        meta = result["_meta"]
        assert meta["var_name"] == "B"
        assert meta["n_cvi_rows"] == 2     # 2 sets in b_var_df
        assert meta["n_positions"] == 3    # pos_1, pos_2, pos_3
        assert meta["n_main_rows"] == 3

    def test_empty_var_df_returns_empty(self, main_df, n_cols):
        result = _compute_sc_block("B", pd.DataFrame(), main_df, n_cols)
        assert result == {}

    def test_empty_main_df_returns_empty(self, b_var_df, n_cols):
        result = _compute_sc_block("B", b_var_df, pd.DataFrame(), n_cols)
        assert result == {}

    def test_none_var_df_returns_empty(self, main_df, n_cols):
        result = _compute_sc_block("B", None, main_df, n_cols)
        assert result == {}

    def test_d_style_is_direct(self, main_df, n_cols):
        """D-style var_df (has wN columns) processed via is_direct=True."""
        d_var_df = pd.DataFrame({
            "Syndicate_ID": ["SYN1", "SYN2"],
            "w1": [1, 4],
            "w2": [2, 5],
            "w3": [3, 6],
        })
        result = _compute_sc_block("D", d_var_df, main_df, n_cols, is_direct=True)
        assert "w1" in result
        assert len(result["w1"]) == len(main_df)


# ── _sc_distribution_table ────────────────────────────────────────────────────

class TestScDistributionTable:

    def test_shape_and_columns(self, b_var_df, main_df, n_cols):
        counts_dict = _compute_sc_block("B", b_var_df, main_df, n_cols)
        tbl = _sc_distribution_table(counts_dict)

        assert set(tbl.columns) == {"position", "count_value", "n_main_rows", "pct_main"}
        assert not tbl["count_value"].isna().any()
        assert not tbl["n_main_rows"].isna().any()

    def test_counts_sum_to_n_main(self, b_var_df, main_df, n_cols):
        """Within each position, n_main_rows sums to len(main_df)."""
        counts_dict = _compute_sc_block("B", b_var_df, main_df, n_cols)
        tbl = _sc_distribution_table(counts_dict)
        for pos, grp in tbl.groupby("position"):
            assert grp["n_main_rows"].sum() == len(main_df), \
                f"Position {pos}: row counts don't sum to {len(main_df)}"

    def test_empty_counts_dict_returns_empty_df(self):
        tbl = _sc_distribution_table({})
        assert tbl.empty
        assert list(tbl.columns) == ["position", "count_value", "n_main_rows", "pct_main"]


# ── _save_sc_block + _load_sc_blocks round-trip ───────────────────────────────

class TestSaveLoadRoundtrip:

    def test_roundtrip(self, tmp_path):
        """Save thresholds then load them back — values survive."""
        gdirs = {"Selected_Counts": tmp_path}
        thresholds = {"w1": [5, 6], "w2": [5], "w3": [4, 5, 6]}

        path = _save_sc_block("B", "sat", thresholds, gdirs)

        assert path.exists()
        assert path.name == "SC_B_sat.csv"

        loaded = _load_sc_blocks(["B"], "sat", gdirs)
        assert loaded == thresholds

    def test_roundtrip_single_value(self, tmp_path):
        gdirs = {"Selected_Counts": tmp_path}
        thresholds = {"w1": [7]}
        _save_sc_block("D", "oz", thresholds, gdirs)
        loaded = _load_sc_blocks(["D"], "oz", gdirs)
        assert loaded == thresholds


# ── _load_sc_blocks: merge + missing-file graceful skip ──────────────────────

class TestLoadScBlocks:

    def test_last_write_wins_on_shared_key(self, tmp_path):
        """Two variables with overlapping w-key: latter variable's value wins."""
        gdirs = {"Selected_Counts": tmp_path}
        _save_sc_block("B", "sat", {"w1": [5, 6]}, gdirs)
        _save_sc_block("D", "sat", {"w1": [4, 5, 6]}, gdirs)

        loaded = _load_sc_blocks(["B", "D"], "sat", gdirs)
        # D is last → D's w1 wins
        assert loaded["w1"] == [4, 5, 6]

    def test_missing_file_skipped_gracefully(self, tmp_path):
        """Missing SC file is skipped; other variables still load."""
        gdirs = {"Selected_Counts": tmp_path}
        _save_sc_block("B", "sat", {"w1": [5]}, gdirs)

        # "R" file does not exist — should not raise
        loaded = _load_sc_blocks(["B", "R"], "sat", gdirs)
        assert "w1" in loaded
        assert loaded["w1"] == [5]

    def test_no_files_returns_empty(self, tmp_path):
        gdirs = {"Selected_Counts": tmp_path}
        loaded = _load_sc_blocks(["B", "R", "D"], "sat", gdirs)
        assert loaded == {}

    def test_bad_columns_file_skipped(self, tmp_path):
        """File with wrong columns is skipped, not raised."""
        bad = tmp_path / "SC_B_sat.csv"
        pd.DataFrame({"x": [1], "y": [2]}).to_csv(bad, index=False)
        gdirs = {"Selected_Counts": tmp_path}
        loaded = _load_sc_blocks(["B"], "sat", gdirs)
        assert loaded == {}


# ── _run_sc_auto ──────────────────────────────────────────────────────────────

class TestRunScAuto:

    def test_basic_ok_status(self, b_var_df, main_df, n_cols):
        var_map = {"B": b_var_df}
        result = _run_sc_auto(["B"], var_map, main_df, n_cols,
                              "sat", {"Selected_Counts": "/tmp"})
        assert result["B"]["status"] == "ok"
        assert "distributions" in result["B"]

    def test_empty_var_skipped(self, main_df, n_cols):
        var_map = {"B": pd.DataFrame()}
        result = _run_sc_auto(["B"], var_map, main_df, n_cols,
                              "sat", {"Selected_Counts": "/tmp"})
        assert result["B"]["status"] == "skipped"

    def test_empty_main_all_skipped(self, b_var_df, n_cols):
        var_map = {"B": b_var_df}
        result = _run_sc_auto(["B"], var_map, pd.DataFrame(), n_cols,
                              "sat", {"Selected_Counts": "/tmp"})
        assert result["B"]["status"] == "skipped"

    def test_missing_var_in_var_map_skipped(self, main_df, n_cols):
        result = _run_sc_auto(["R"], {}, main_df, n_cols,
                              "sat", {"Selected_Counts": "/tmp"})
        assert result["R"]["status"] == "skipped"
