"""Tests for the B1 Parallel Main-Count feature's testable pieces.

The UI wiring lives in masterapp.py (not import-safe), but its two supporting
pure helpers live in syndicate_core.pipeline:

  * b1_path()         — game-agnostic B1 source resolver via game_dirs()["Base"]
  * b1_ball_columns() — rename-proof ball-column detection (pos_N or wN/w_N)

plus reuse of the already-tested per-row engine _match_cvi_rows against a B1
array. These tests cover resolution, absence, the rename-proofing, and that the
'update' draw-number column is never mistaken for a ball.
"""
import math

import numpy as np
import pandas as pd
import pytest

import syndicate_core.pipeline as _pipeline_mod
from syndicate_core.pipeline import b1_path, b1_ball_columns, game_dirs
from syndicate_core.matching import _match_cvi_rows


@pytest.fixture
def patched_root(tmp_path, monkeypatch):
    """Redirect game_dirs() to write inside tmp_path instead of the real tree."""
    monkeypatch.setattr(_pipeline_mod, "ROOT", tmp_path)
    return tmp_path


def _write_b1(gk: str, filename: str, df: pd.DataFrame) -> "None":
    """Write a B1 CSV into the game's Base_{gk} folder (created by game_dirs)."""
    base = game_dirs(gk)["Base"]
    df.to_csv(base / filename, index=False)


# ── b1_path resolution ────────────────────────────────────────────────────────

def test_b1_path_resolves_primary_name(patched_root):
    df = pd.DataFrame({"w": ["w1"], "update": [4695],
                       "pos_1": [5], "pos_2": [7], "pos_3": [13]})
    _write_b1("sat", "B1_sat_updated.csv", df)

    p = b1_path("sat")
    assert p is not None
    assert p.name == "B1_sat_updated.csv"


def test_b1_path_glob_fallback(patched_root):
    # No _updated file; a differently-suffixed B1 file still resolves.
    df = pd.DataFrame({"w": ["w1"], "pos_1": [5], "pos_2": [7]})
    _write_b1("oz", "B1_oz_2026.csv", df)

    p = b1_path("oz")
    assert p is not None
    assert p.name == "B1_oz_2026.csv"


def test_b1_path_none_when_absent(patched_root):
    # game_dirs creates the empty Base folder; no B1 file inside.
    assert b1_path("mwf") is None


def test_b1_path_is_game_agnostic(patched_root):
    # A sat B1 must not leak into another game's lookup.
    _write_b1("sat", "B1_sat_updated.csv",
              pd.DataFrame({"pos_1": [1], "pos_2": [2]}))
    assert b1_path("sat") is not None
    assert b1_path("pb") is None


# ── b1_ball_columns detection ──────────────────────────────────────────────────

def test_ball_columns_pos_convention():
    df = pd.DataFrame({
        "w": ["w1", "w2"], "update": [4695, np.nan],
        "pos_1": [5, 13], "pos_2": [7, 14], "pos_3": [13, 16],
        "pos_4": [24, 21], "pos_5": [30, 29], "pos_6": [41, 41],
    })
    cols = b1_ball_columns(df, pick=6)
    assert cols == ["pos_1", "pos_2", "pos_3", "pos_4", "pos_5", "pos_6"]
    # metadata columns are never treated as balls
    assert "w" not in cols
    assert "update" not in cols


def test_ball_columns_survive_w_rename():
    # Post-rename headers (pos_N -> wN). Detector must still find the balls,
    # and the singular 'w' label column must stay excluded.
    df = pd.DataFrame({
        "w": ["w1", "w2"], "update": [4695, np.nan],
        "w1": [5, 13], "w2": [7, 14], "w3": [13, 16],
        "w4": [24, 21], "w5": [30, 29], "w6": [41, 41],
    })
    cols = b1_ball_columns(df, pick=6)
    assert cols == ["w1", "w2", "w3", "w4", "w5", "w6"]
    assert "w" not in cols
    assert "update" not in cols


def test_ball_columns_capped_at_pick_and_ordered():
    df = pd.DataFrame({
        "pos_10": [10], "pos_2": [2], "pos_1": [1], "pos_3": [3],
    })
    cols = b1_ball_columns(df, pick=3)
    # ordered by trailing integer, capped at pick
    assert cols == ["pos_1", "pos_2", "pos_3"]


def test_ball_columns_ignores_nonnumeric_matches():
    # A pos_-named column that holds no numbers is not a ball.
    df = pd.DataFrame({
        "pos_1": [1, 2], "pos_2": [3, 4],
        "pos_note": ["a", "b"],   # would not match the regex anyway
    })
    cols = b1_ball_columns(df, pick=6)
    assert cols == ["pos_1", "pos_2"]


# ── engine reuse against a B1 array ────────────────────────────────────────────

def test_engine_against_b1_array_counts():
    # B1 pool = 3 rows; CVI row {1,2,4} matched independently against each.
    b1 = pd.DataFrame({
        "w": ["w1", "w2", "w3"], "update": [1, np.nan, np.nan],
        "pos_1": [1, 4, 1], "pos_2": [2, 5, 4], "pos_3": [3, 6, 6],
    })
    cols = b1_ball_columns(b1, pick=3)
    arr = b1[cols].to_numpy(dtype=np.int32)

    cvi = pd.DataFrame([
        {"Row_ID": 1, "Source": "B", "Set_Label": "x",
         "w1": 1, "w2": 2, "w3": 4},
    ])
    out = _match_cvi_rows(cvi, arr, pool_max=6)

    # B1 rows: [1,2,3]→has 1,2 =2 ; [4,5,6]→has 4 =1 ; [1,4,6]→has 1,4 =2
    # distribution over the 3 B1 rows: count 2 twice, count 1 once
    assert out.iloc[0]["Main_Count"] == "1,2"
    bd = out.iloc[0]["Main_Breakdown"]
    assert "S1:1" in bd
    assert "S2:2" in bd


def test_engine_against_b1_matches_closed_form():
    # Full C(6,3) space as the B1 pool → per-row distribution must equal the
    # hypergeometric closed form, same guarantee as the Main-Data engine tests.
    import itertools
    pool_max, pick = 6, 3
    arr = np.array(list(itertools.combinations(range(1, pool_max + 1), pick)),
                   dtype=np.int32)
    cvi = pd.DataFrame([
        {"Row_ID": 1, "Source": "B", "Set_Label": "x", "w1": 1, "w2": 2, "w3": 3},
    ])
    out = _match_cvi_rows(cvi, arr, pool_max=pool_max)

    s = 3
    expected = {
        k: math.comb(s, k) * math.comb(pool_max - s, pick - k)
        for k in range(pick + 1)
    }
    expected = {k: v for k, v in expected.items() if v > 0}
    bd = {int(p.split(":")[0][1:]): int(p.split(":")[1])
          for p in out.iloc[0]["Main_Breakdown"].split("  ")}
    assert bd == expected
