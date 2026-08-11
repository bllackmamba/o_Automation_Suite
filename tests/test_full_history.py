"""Tests for syndicate_core.full_history — B1 + draw_history splice.

Uses synthetic frames so the invariants are checked deterministically, plus one
real-data lock (skipped when the sat files are absent) that asserts the actual
sat splice reaches the 2761→4701 range with a clean overlap.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from syndicate_core import full_history as fh


# ── synthetic builders ────────────────────────────────────────────────────────

def _b1_df(rows: list[list[int]], updates: list | None = None) -> pd.DataFrame:
    """rows newest-first, each a 6-number list → B1 shape (w/update/pos_1..6)."""
    data = {"w": [f"w{i+1}" for i in range(len(rows))]}
    data["update"] = updates if updates is not None else [""] * len(rows)
    for j in range(6):
        data[f"pos_{j+1}"] = [r[j] for r in rows]
    return pd.DataFrame(data)


def _dh_df(draws: list[int], sets: list[list[int]], dates: list[str] | None = None) -> pd.DataFrame:
    dates = dates or [f"2026-01-{i+1:02d}" for i in range(len(draws))]
    return pd.DataFrame({
        "draw": [str(d) for d in draws],
        "date": dates,
        "numbers": ["[" + ", ".join(map(str, s)) + "]" for s in sets],
    })


# ── record extraction ─────────────────────────────────────────────────────────

def test_b1_records_reads_ball_columns_newest_first():
    df = _b1_df([[3, 11, 15, 30, 32, 42], [2, 6, 8, 12, 22, 43]])
    recs = fh.b1_records(df, pick=6)
    assert len(recs) == 2
    assert recs[0]["nums"] == {3, 11, 15, 30, 32, 42}
    assert recs[1]["nums"] == {2, 6, 8, 12, 22, 43}


def test_draw_history_records_parse_and_drop_blank():
    df = _dh_df([4701, 4699], [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]])
    df.loc[len(df)] = {"draw": "4697", "date": "x", "numbers": "[]"}  # blank → dropped
    recs = fh.draw_history_records(df)
    assert len(recs) == 2
    assert recs[0]["draw"] == "4701" and recs[0]["nums"] == {1, 2, 3, 4, 5, 6}


def test_infer_step_uses_modal_positive_diff():
    df = _dh_df([4701, 4699, 4697, 4695], [[1]*6, [2]*6, [3]*6, [4]*6])
    assert fh.infer_step(fh.draw_history_records(df)) == 2


# ── alignment / overlap ───────────────────────────────────────────────────────

def test_best_offset_finds_one_draw_top_gap():
    # dh has one extra newest draw (4701) that B1 lacks → offset 1, zero mismatch
    b1 = fh.b1_records(_b1_df([[10, 11, 12, 13, 14, 15], [20, 21, 22, 23, 24, 25]]), 6)
    dh = fh.draw_history_records(_dh_df(
        [4701, 4699, 4697],
        [[1, 2, 3, 4, 5, 6], [10, 11, 12, 13, 14, 15], [20, 21, 22, 23, 24, 25]]))
    offset, mm, n = fh.best_offset(b1, dh)
    assert offset == 1 and mm == 0 and n == 2


def test_overlap_mismatches_flags_disagreement():
    b1 = fh.b1_records(_b1_df([[10, 11, 12, 13, 14, 15], [20, 21, 22, 23, 24, 25]]), 6)
    # same alignment (offset 1) but the older overlap draw disagrees
    dh = fh.draw_history_records(_dh_df(
        [4701, 4699, 4697],
        [[1, 2, 3, 4, 5, 6], [10, 11, 12, 13, 14, 15], [99, 98, 97, 96, 95, 94]]))
    offset, _, _ = fh.best_offset(b1, dh)
    mm = fh.overlap_mismatches(b1, dh, offset)
    assert len(mm) == 1 and mm[0]["dh_draw"] == "4697"


# ── full splice ───────────────────────────────────────────────────────────────

def test_build_full_history_numbers_b1_and_takes_top_from_dh():
    # B1: 3 draws newest-first; dh: adds 4701 on top and covers the 2 newest of B1
    b1 = _b1_df([[10, 11, 12, 13, 14, 15],
                 [20, 21, 22, 23, 24, 25],
                 [30, 31, 32, 33, 34, 35]])
    dh = _dh_df([4701, 4699, 4697],
                [[1, 2, 3, 4, 5, 6], [10, 11, 12, 13, 14, 15], [20, 21, 22, 23, 24, 25]])
    full, rep = fh.build_full_history(b1, dh, pick=6)

    assert rep["overlap_agree"] is True
    assert rep["offset"] == 1 and rep["step"] == 2 and rep["anchor_draw"] == 4699
    assert rep["top_from_dh"] == ["4701"]
    # newest-first: 4701 (from dh) then B1 numbered 4699,4697,4695
    assert [r["draw"] for r in full] == ["4701", "4699", "4697", "4695"]
    assert rep["newest_draw"] == 4701 and rep["oldest_draw"] == 4695
    assert rep["n_full"] == 4
    # dates borrowed from dh where they overlap; unknown older draw blank
    assert full[1]["date"] == "2026-01-02"   # draw 4699 date came from dh
    assert full[3]["date"] == ""             # draw 4695 predates dh


def test_build_full_history_crosschecks_b1_update_column():
    # B1 carries its own (correct) update numbers for the first rows
    b1 = _b1_df([[10, 11, 12, 13, 14, 15], [20, 21, 22, 23, 24, 25]],
                updates=[4699, 4697])
    dh = _dh_df([4701, 4699], [[1, 2, 3, 4, 5, 6], [10, 11, 12, 13, 14, 15]])
    full, rep = fh.build_full_history(b1, dh, pick=6)
    assert rep["b1_update_crosscheck_mismatches"] == []   # derived == B1's own


def test_records_to_df_roundtrips_into_reader_schema():
    b1 = _b1_df([[10, 11, 12, 13, 14, 15], [20, 21, 22, 23, 24, 25]])
    dh = _dh_df([4701, 4699], [[1, 2, 3, 4, 5, 6], [10, 11, 12, 13, 14, 15]])
    df, _ = fh.build_full_range_df(b1, dh, pick=6)
    assert list(df.columns) == ["draw", "date", "numbers"]
    # re-parse via the same records path → identical number sets
    reparsed = fh.draw_history_records(df)
    assert reparsed[0]["nums"] == {1, 2, 3, 4, 5, 6}


# ── real-data lock (sat) ──────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[1]
_B1 = _ROOT / "Games/SAT/Variable_inputs_sat/Base_sat/B1_sat_updated.csv"
_DH = _ROOT / "Games/SAT/SinceLast_sat/draw_history.csv"


@pytest.mark.skipif(not (_B1.exists() and _DH.exists()), reason="sat B1/draw_history absent")
def test_real_sat_splice_reaches_full_range_with_clean_overlap():
    b1 = pd.read_csv(_B1, dtype=str)
    dh = pd.read_csv(_DH, dtype=str)
    full, rep = fh.build_full_history(b1, dh, pick=6)
    assert rep["overlap_agree"] is True, rep["overlap_mismatches"][:3]
    assert rep["b1_update_crosscheck_mismatches"] == []
    assert rep["newest_draw"] == 4701
    assert rep["oldest_draw"] <= 2761
    assert rep["n_full"] >= 970
