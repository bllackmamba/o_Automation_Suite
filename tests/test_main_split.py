"""
tests/test_main_split.py — RefGroup-keyed Main Data split (Rule 1).

Covers syndicate_core/main_split.py:
  • split_streams — the pure nonzero/zero (Rule 1) partition of a Main Data
    pool against the newest-draw reference numbers.
  • ref_key_of / load_or_build_split — the RefGroup-keyed parquet cache that
    rebuilds only when the reference draw rolls over.

The Rule 1 boundary itself (Repeat = shared >= 1, No_Repeat = shared == 0) is
locked in test_refgroup.py::main_data_stream; here we prove the DataFrame-level
partition and the cache/invalidation behaviour.
"""
from itertools import combinations
from pathlib import Path

import pandas as pd
import pytest

from syndicate_core.main_split import (
    load_or_build_split,
    ref_key_of,
    split_streams,
)

N4 = ["n1", "n2", "n3", "n4"]

# The REAL full sat pool = C(45,6) = 8,145,060 rows, header n1..n6. This is the
# app's own main data CSV — NOT core/Main_Data_sat_plus.numbers, which is the
# 575,344-row diff=1 NList "plus" output (wrong dataset) stored as an Apple
# Numbers bundle (not pandas-loadable). Gitignored, so absent on other checkouts.
SAT_FULL_POOL = (Path(__file__).resolve().parents[1]
                 / "Games" / "SAT" / "Main_Data_sat" / "Main_Data_sat.csv")
N6 = ["n1", "n2", "n3", "n4", "n5", "n6"]


def _full_c8_4() -> pd.DataFrame:
    """The full C(8,4)=70 combination space as synthetic main data."""
    return pd.DataFrame(list(combinations(range(1, 9), 4)), columns=N4)


# ── split_streams (pure Rule 1 partition) ─────────────────────────────────────

def test_split_streams_basic_nonzero_vs_zero():
    # Arrange — 3 rows: two share >=1 with ref, one shares none.
    main = pd.DataFrame([[1, 2, 3, 4],      # shares 4 → Repeat
                         [4, 9, 10, 11],    # shares 1 (the 4) → Repeat
                         [9, 10, 11, 12]],  # shares 0 → No_Repeat
                        columns=N4)
    # Act
    streams = split_streams(main, N4, [1, 2, 3, 4])
    # Assert
    assert len(streams["Repeat"]) == 2
    assert len(streams["No_Repeat"]) == 1
    assert streams["No_Repeat"].iloc[0].tolist() == [9, 10, 11, 12]


def test_split_streams_full_space_matches_closed_form():
    # Against ref {1,2,3,4} over C(8,4): only {5,6,7,8} shares 0 → No_Repeat = 1.
    streams = split_streams(_full_c8_4(), N4, [1, 2, 3, 4])
    assert len(streams["No_Repeat"]) == 1
    assert len(streams["Repeat"]) == 69
    assert streams["No_Repeat"].iloc[0].tolist() == [5, 6, 7, 8]


def test_split_streams_is_a_partition():
    main = _full_c8_4()
    streams = split_streams(main, N4, [2, 4, 6, 8])
    rep, nor = streams["Repeat"], streams["No_Repeat"]
    # Complete + disjoint: counts sum to M, and the two row-sets don't overlap.
    assert len(rep) + len(nor) == len(main)
    rep_set = {tuple(r) for r in rep[N4].to_numpy().tolist()}
    nor_set = {tuple(r) for r in nor[N4].to_numpy().tolist()}
    assert rep_set.isdisjoint(nor_set)
    assert rep_set | nor_set == {tuple(r) for r in main[N4].to_numpy().tolist()}


def test_split_streams_empty_ref_is_all_no_repeat():
    main = _full_c8_4()
    streams = split_streams(main, N4, [])
    assert len(streams["No_Repeat"]) == len(main)
    assert len(streams["Repeat"]) == 0


def test_split_streams_empty_main_returns_two_empty_frames():
    empty = pd.DataFrame(columns=N4)
    streams = split_streams(empty, N4, [1, 2, 3, 4])
    assert streams["Repeat"].empty
    assert streams["No_Repeat"].empty


def test_split_streams_is_read_only_on_input():
    main = _full_c8_4()
    before = main.copy()
    split_streams(main, N4, [1, 2, 3, 4])
    pd.testing.assert_frame_equal(main, before)


# ── ref_key_of ────────────────────────────────────────────────────────────────

def test_ref_key_of_is_order_independent_and_deduped():
    assert ref_key_of([3, 1, 2]) == ref_key_of([2, 3, 1]) == "1-2-3"
    assert ref_key_of([5, 5, 1]) == "1-5"


# ── load_or_build_split (RefGroup-keyed cache + invalidation) ──────────────────

def test_first_call_builds_and_writes_cache(tmp_path):
    main = _full_c8_4()
    out = load_or_build_split(main, N4, [1, 2, 3, 4], tmp_path)
    # Built on first call, streams correct.
    assert out["_meta"]["rebuilt"] is True
    assert len(out["No_Repeat"]) == 1 and len(out["Repeat"]) == 69
    # Parquets + marker on disk under the ref_key.
    key = ref_key_of([1, 2, 3, 4])
    assert (tmp_path / f"Repeat__{key}.parquet").exists()
    assert (tmp_path / f"No_Repeat__{key}.parquet").exists()
    assert (tmp_path / "_split_marker.json").exists()


def test_second_call_same_ref_uses_cache(tmp_path):
    main = _full_c8_4()
    load_or_build_split(main, N4, [1, 2, 3, 4], tmp_path)
    out2 = load_or_build_split(main, N4, [1, 2, 3, 4], tmp_path)
    assert out2["_meta"]["rebuilt"] is False
    assert len(out2["No_Repeat"]) == 1 and len(out2["Repeat"]) == 69


def test_rollover_rebuilds_and_drops_stale(tmp_path):
    main = _full_c8_4()
    old_key = ref_key_of([1, 2, 3, 4])
    load_or_build_split(main, N4, [1, 2, 3, 4], tmp_path)
    assert (tmp_path / f"Repeat__{old_key}.parquet").exists()
    # New reference draw → rollover.
    out = load_or_build_split(main, N4, [5, 6, 7, 8], tmp_path)
    new_key = ref_key_of([5, 6, 7, 8])
    assert out["_meta"]["rebuilt"] is True
    # New ref's own numbers now share 0 with... itself? {5,6,7,8} shares 4 → the
    # only 0-share combo vs {5,6,7,8} is {1,2,3,4}. So No_Repeat == 1 again.
    assert len(out["No_Repeat"]) == 1
    assert out["No_Repeat"].iloc[0].tolist() == [1, 2, 3, 4]
    # Stale parquets from the old ref_key are gone; new ones present.
    assert not (tmp_path / f"Repeat__{old_key}.parquet").exists()
    assert (tmp_path / f"Repeat__{new_key}.parquet").exists()


def test_cached_content_matches_direct_split(tmp_path):
    main = _full_c8_4()
    direct = split_streams(main, N4, [2, 4, 6, 8])
    load_or_build_split(main, N4, [2, 4, 6, 8], tmp_path)          # build
    cached = load_or_build_split(main, N4, [2, 4, 6, 8], tmp_path)  # read back
    assert cached["_meta"]["rebuilt"] is False
    for stream in ("Repeat", "No_Repeat"):
        a = direct[stream][N4].reset_index(drop=True)
        b = cached[stream][N4].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)


# ── Real-data lock: the actual full sat pool must hit the invariant counts ─────
# Rule 1 is reference-invariant — ANY valid 6-number draw splits the full C(45,6)
# space into exactly Repeat=4,882,437 / No_Repeat=3,262,623. Running against the
# REAL on-disk pool (not a synthetic space) is the test that catches a parsing,
# dtype, header, or duplicate-row defect a toy combinatorial fixture can't.

@pytest.mark.skipif(not SAT_FULL_POOL.exists(),
                    reason="full sat C(45,6) pool absent (gitignored 8.1M-row data file)")
def test_split_streams_real_sat_pool_hits_locked_counts():
    main = pd.read_csv(SAT_FULL_POOL)
    assert len(main) == 8_145_060          # full space present, no missing/dup rows
    # D4687's numbers are as valid a reference as any other 6-set (invariant).
    streams = split_streams(main, N6, [3, 6, 9, 14, 21, 22])
    assert len(streams["Repeat"]) == 4_882_437
    assert len(streams["No_Repeat"]) == 3_262_623
    assert len(streams["Repeat"]) + len(streams["No_Repeat"]) == 8_145_060
