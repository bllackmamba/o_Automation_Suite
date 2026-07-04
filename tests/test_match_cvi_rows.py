"""Tests for the per-row CVI engine (_match_cvi_rows / _match_cvi_row_counts).

Uses small COMPLETE combination spaces so each empirical per-row distribution
must equal the exact hypergeometric closed form C(s, c) * C(pool-s, pick-c).
"""
import itertools
import math

import numpy as np
import pandas as pd

from syndicate_core.matching import _match_cvi_rows, _match_cvi_row_counts


def _full_space(pool_max: int, pick: int) -> np.ndarray:
    return np.array(list(itertools.combinations(range(1, pool_max + 1), pick)),
                    dtype=np.int32)


def _bd_to_dict(bd: str) -> dict:
    return {int(p.split(":")[0][1:]): int(p.split(":")[1]) for p in bd.split("  ")}


def test_lookup_counts_direct():
    main = np.array([[1, 2, 3], [4, 5, 6], [1, 4, 6]], dtype=np.int32)
    counts = _match_cvi_row_counts(np.array([1, 2, 4]), main, pool_max=6)
    # row0 has 1,2 → 2 ; row1 has 4 → 1 ; row2 has 1,4 → 2
    assert list(counts) == [2, 1, 2]


def test_row_distribution_matches_closed_form():
    pool_max, pick = 6, 3
    main = _full_space(pool_max, pick)          # C(6,3) = 20 combinations
    cvi = pd.DataFrame([
        {"Row_ID": 1, "Source": "B", "Set_Label": "x", "w1": 1, "w2": 2, "w3": 3},
    ])
    out = _match_cvi_rows(cvi, main, pool_max=pool_max)

    s = 3  # |{1,2,3}|
    expected = {c: math.comb(s, c) * math.comb(pool_max - s, pick - c)
                for c in range(0, pick + 1)
                if math.comb(s, c) * math.comb(pool_max - s, pick - c) > 0}
    assert _bd_to_dict(out.iloc[0]["Main_Breakdown"]) == expected
    assert out.iloc[0]["Row_Length"] == 3
    assert out.iloc[0]["Main_Count"] == ",".join(str(k) for k in sorted(expected))


def test_row_id_not_treated_as_a_number():
    # Row_ID = 999 must NOT count as a lottery number; only w-cols feed matching.
    main = _full_space(6, 3)
    cvi = pd.DataFrame([
        {"Row_ID": 999, "Source": "D", "Set_Label": "a", "w1": 1, "w2": 2, "w3": 3},
    ])
    out = _match_cvi_rows(cvi, main, pool_max=6)
    assert out.iloc[0]["Row_Length"] == 3            # not 4


def test_source_carried_and_empty_row_placeholders():
    main = _full_space(6, 3)
    cvi = pd.DataFrame([
        {"Row_ID": 1, "Source": "D", "Set_Label": "a", "w1": 1, "w2": 2, "w3": np.nan},
        {"Row_ID": 2, "Source": "Sp", "Set_Label": "b", "w1": np.nan, "w2": np.nan, "w3": np.nan},
    ])
    out = _match_cvi_rows(cvi, main, pool_max=6)
    assert list(out["Source"]) == ["D", "Sp"]
    assert out.iloc[0]["Row_Length"] == 2
    assert out.iloc[1]["Row_Length"] == 0
    assert out.iloc[1]["Main_Count"] == "—"
    assert out.iloc[1]["Main_Breakdown"] == "—"


def test_every_row_distribution_sums_to_M():
    main = _full_space(7, 3)                     # C(7,3) = 35
    cvi = pd.DataFrame([
        {"Row_ID": 1, "Source": "R", "Set_Label": "x", "w1": 2, "w2": 5, "w3": 7, "w4": 1},
    ])
    out = _match_cvi_rows(cvi, main, pool_max=7)
    total = sum(v for v in _bd_to_dict(out.iloc[0]["Main_Breakdown"]).values())
    assert total == len(main)


def test_out_of_pool_cvi_numbers_ignored():
    main = _full_space(6, 3)
    # 99 is outside pool 1..6 → cannot match, ignored for counting (but counts
    # toward Row_Length, which reflects the row's own declared numbers).
    cvi = pd.DataFrame([
        {"Row_ID": 1, "Source": "B", "Set_Label": "x", "w1": 1, "w2": 2, "w3": 99},
    ])
    out = _match_cvi_rows(cvi, main, pool_max=6)
    # distribution should equal that of just {1,2} (s=2)
    s = 2
    expected = {c: math.comb(s, c) * math.comb(6 - s, 3 - c)
                for c in range(0, 3 + 1)
                if math.comb(s, c) * math.comb(6 - s, 3 - c) > 0}
    assert _bd_to_dict(out.iloc[0]["Main_Breakdown"]) == expected
