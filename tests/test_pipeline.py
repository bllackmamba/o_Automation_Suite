"""
tests/test_pipeline.py — Unit tests for pipeline helpers and the collation engine.

Tests:
  split_d_by_game  — no row loss / no spurious duplication across game folders
  _to_w_rows       — B path, D path, R path, Sp regression (12/112 bug)
"""

import pytest
import pandas as pd

import syndicate_core.pipeline as _pipeline_mod
from syndicate_core.pipeline import split_d_by_game
from syndicate_core.collation import _to_w_rows


# ═══════════════════════════════════════════════════════════════════════════════
# split_d_by_game
# ═══════════════════════════════════════════════════════════════════════════════

def _make_d_csv(tmp_path, rows: list[dict]) -> "Path":
    """Write a synthetic D CSV to tmp_path and return the path."""
    df = pd.DataFrame(rows)
    src = tmp_path / "D_NSW.csv"
    df.to_csv(src, index=False)
    return src


@pytest.fixture()
def patched_root(tmp_path, monkeypatch):
    """Redirect game_dirs() to write inside tmp_path instead of the real Games/ tree."""
    monkeypatch.setattr(_pipeline_mod, "ROOT", tmp_path)
    return tmp_path


def test_split_d_by_game_no_loss_single_game_rows(patched_root, tmp_path):
    """Each single-game input row reaches exactly one output folder → no loss."""
    rows = [
        {"Syndicate_ID": "S1", "Games": "Powerball",      "w1": 1,  "w2": 10},
        {"Syndicate_ID": "S2", "Games": "Powerball",      "w1": 2,  "w2": 11},
        {"Syndicate_ID": "S3", "Games": "TattsLotto",     "w1": 3,  "w2": 12},
        {"Syndicate_ID": "S4", "Games": "TattsLotto",     "w1": 4,  "w2": 13},
        {"Syndicate_ID": "S5", "Games": "Oz Lotto",       "w1": 5,  "w2": 14},
        {"Syndicate_ID": "S6", "Games": "Oz Lotto",       "w1": 6,  "w2": 15},
        {"Syndicate_ID": "S7", "Games": "Monday Lotto",   "w1": 7,  "w2": 16},
    ]
    src = _make_d_csv(tmp_path, rows)
    results = split_d_by_game(src, patched_root)

    game_counts = {k: v for k, v in results.items() if not k.startswith("_")}
    total_out = sum(game_counts.values())

    assert total_out == len(rows), (
        f"Row count mismatch: {len(rows)} in → {total_out} out "
        f"(per-game breakdown: {game_counts})"
    )
    assert game_counts.get("pb", 0) == 2
    assert game_counts.get("sat", 0) == 2
    assert game_counts.get("oz", 0) == 2
    assert game_counts.get("mwf", 0) == 1


def test_split_d_by_game_pipe_separated_duplicates_correctly(patched_root, tmp_path):
    """A pipe-separated row appears in EACH matching game folder (intentional copy)."""
    rows = [
        # 1 row that belongs to both pb and oz
        {"Syndicate_ID": "MULTI1", "Games": "Powerball|Oz Lotto", "w1": 7, "w2": 33},
        # 2 plain pb rows
        {"Syndicate_ID": "PB1", "Games": "Powerball", "w1": 1, "w2": 10},
        {"Syndicate_ID": "PB2", "Games": "Powerball", "w1": 2, "w2": 11},
    ]
    src = _make_d_csv(tmp_path, rows)
    results = split_d_by_game(src, patched_root)

    # MULTI1 goes to pb AND oz → total output > input
    pb_count  = results.get("pb", 0)
    oz_count  = results.get("oz", 0)
    assert pb_count == 3, f"pb should have 3 rows (2 plain + 1 pipe copy), got {pb_count}"
    assert oz_count == 1, f"oz should have 1 row (the pipe copy), got {oz_count}"


def test_split_d_by_game_unknown_games_logged(patched_root, tmp_path):
    """Unknown game names are captured in '_unknown_games', not silently dropped."""
    rows = [
        {"Syndicate_ID": "K1", "Games": "Powerball",         "w1": 1},
        {"Syndicate_ID": "K2", "Games": "FakeGame9000",      "w1": 2},
    ]
    src = _make_d_csv(tmp_path, rows)
    results = split_d_by_game(src, patched_root)

    assert results.get("pb", 0) == 1
    assert "FakeGame9000" in results.get("_unknown_games", [])


def test_split_d_by_game_skipped_games_excluded(patched_root, tmp_path):
    """None-mapped games (Super 66, Lucky Lotteries) are skipped with no error."""
    rows = [
        {"Syndicate_ID": "L1", "Games": "Lucky Lotteries", "w1": 1},
        {"Syndicate_ID": "L2", "Games": "Super 66",        "w1": 2},
        {"Syndicate_ID": "P1", "Games": "Powerball",       "w1": 3},
    ]
    src = _make_d_csv(tmp_path, rows)
    results = split_d_by_game(src, patched_root)

    game_counts = {k: v for k, v in results.items() if not k.startswith("_")}
    assert sum(game_counts.values()) == 1     # only the Powerball row
    assert results.get("pb", 0) == 1
    assert "_skipped_games" in results


# ═══════════════════════════════════════════════════════════════════════════════
# _to_w_rows — B path
# ═══════════════════════════════════════════════════════════════════════════════

def test_to_w_rows_b_set_label_from_w_column():
    """B DataFrame: Set_Label comes from the 'w' column, row count is preserved."""
    df_b = pd.DataFrame({
        "w":     ["SetA", "SetB", "SetC"],
        "pos_1": [1,       7,      13],
        "pos_2": [2,       8,      14],
        "pos_3": [3,       9,      15],
        "pos_4": [pd.NA,  pd.NA,   16],   # trailing NaN in first two rows
    })
    result = _to_w_rows(df_b)

    assert "Set_Label" in result.columns, "Set_Label column missing"
    assert list(result["Set_Label"]) == ["SetA", "SetB", "SetC"]
    assert len(result) == 3, f"Expected 3 rows, got {len(result)}"


def test_to_w_rows_b_drops_all_nan_pos_columns():
    """Trailing pos columns that are entirely NaN must not appear in output."""
    df_b = pd.DataFrame({
        "w":     ["X", "Y"],
        "pos_1": [5,    10],
        "pos_2": [6,    11],
        "pos_3": [pd.NA, pd.NA],   # entirely NaN → should be dropped
    })
    result = _to_w_rows(df_b)

    col_names = list(result.columns)
    assert "Set_Label" in col_names
    # pos_3 (all NaN) must not produce a surviving non-NaN column
    val_cols = [c for c in col_names if c != "Set_Label"]
    for vc in val_cols:
        assert result[vc].notna().any(), \
            f"Column {vc!r} is all-NaN — should have been dropped"


# ═══════════════════════════════════════════════════════════════════════════════
# _to_w_rows — D path
# ═══════════════════════════════════════════════════════════════════════════════

def test_to_w_rows_d_set_label_from_syndicate_id():
    """D DataFrame: Set_Label comes from Syndicate_ID."""
    df_d = pd.DataFrame({
        "Syndicate_ID": ["SYN001", "SYN002", "SYN003"],
        "w1": [1,  7,  13],
        "w2": [2,  8,  14],
        "w3": [3,  9,  15],
    })
    result = _to_w_rows(df_d, is_direct=True)

    assert "Set_Label" in result.columns
    assert list(result["Set_Label"]) == ["SYN001", "SYN002", "SYN003"]
    assert len(result) == 3


def test_to_w_rows_d_via_meta_detection():
    """D path is also triggered by D metadata columns (no is_direct flag needed)."""
    df_d = pd.DataFrame({
        "Syndicate_ID": ["A", "B"],
        "Games":        ["Powerball", "Oz Lotto"],
        "w1": [1, 2],
        "w2": [3, 4],
    })
    # is_direct=False but has_d_meta=True (Syndicate_ID + Games)
    result = _to_w_rows(df_d)

    assert list(result["Set_Label"]) == ["A", "B"]
    assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# _to_w_rows — R path (column-oriented, tuple-named columns)
# ═══════════════════════════════════════════════════════════════════════════════

def test_to_w_rows_r_column_names_become_set_labels():
    """R DataFrame: each column name becomes a Set_Label row."""
    df_r = pd.DataFrame({
        "(1,)":   [1, 2, 3, pd.NA],
        "(2,)":   [7, 8, pd.NA, pd.NA],
        "(1, 2)": [1, 2, 7, 8],
    })
    result = _to_w_rows(df_r, force_column_oriented=True)

    assert "Set_Label" in result.columns
    assert len(result) == 3, f"Expected 3 rows (one per column), got {len(result)}"
    assert set(result["Set_Label"]) == {"(1,)", "(2,)", "(1, 2)"}


# ═══════════════════════════════════════════════════════════════════════════════
# _to_w_rows — Sp path  (regression: 12 / 112 pre-filter bug)
# ═══════════════════════════════════════════════════════════════════════════════

def test_to_w_rows_sp_all_columns_become_rows():
    """
    Regression: Sp column names like w10, w11, w20 match ^w\\d+$ but must NOT be
    pre-filtered — ALL columns must produce rows, not just the w-pattern subset.

    Historical bug: code that filtered to wcols (^w\\d+$) before transposing
    would emit only 12 rows for a 112-column Sp DataFrame (the 12/112 bug).
    """
    # Mirrors Sp's column mix: 4 cols matching ^w\d+$, 8 others
    w_cols    = ["w10", "w11", "w20", "w0"]
    other_cols = ["o0", "o1", "p0", "y0", "e0", "f0", "s0", "x0"]
    all_cols  = w_cols + other_cols   # 12 total; only 4 match ^w\d+$

    sp_df = pd.DataFrame({c: pd.Series([1, 2, 3]) for c in all_cols})
    result = _to_w_rows(sp_df, force_column_oriented=True)

    assert "Set_Label" in result.columns
    assert len(result) == len(all_cols), (
        f"Expected {len(all_cols)} rows (one per column), got {len(result)}. "
        f"Only {len(w_cols)} cols match ^w\\d+$ — if result == {len(w_cols)}, "
        f"the pre-filter bug has re-appeared."
    )
    assert set(result["Set_Label"]) == set(all_cols)
