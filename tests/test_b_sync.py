"""Tests for syndicate_core/b_sync.py"""

import pandas as pd
import pytest

from syndicate_core.b_sync import (
    _append_draws,
    _b_row_nums,
    _parse_hist_nums,
    _sync_b,
    append_draws_to_b,
    sync_b_with_latest_draws,
)
from syndicate_core.config import GAMES_CFG


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _b(rows):
    """Build a row-oriented B DataFrame. rows = [(label, [nums...]), ...]."""
    result = []
    for label, nums in rows:
        row = {"w": label}
        row.update({f"pos_{i + 1}": n for i, n in enumerate(sorted(nums))})
        result.append(row)
    return pd.DataFrame(result)


def _hist(draws):
    """Build a draw history DataFrame (newest-first).

    draws = [(draw_no, date_str, [nums...]), ...]
    Numbers stored as string repr to simulate CSV round-trip.
    """
    return pd.DataFrame([
        {"draw": d[0], "date": d[1], "numbers": str(sorted(d[2]))}
        for d in draws
    ])


# ── _parse_hist_nums ──────────────────────────────────────────────────────────

class TestParseHistNums:
    def test_from_python_list(self):
        assert _parse_hist_nums([4, 7, 13]) == frozenset({4, 7, 13})

    def test_from_csv_string(self):
        assert _parse_hist_nums("[4, 7, 13, 21, 29, 38]") == frozenset({4, 7, 13, 21, 29, 38})

    def test_from_tuple(self):
        assert _parse_hist_nums((1, 2, 3)) == frozenset({1, 2, 3})

    def test_ignores_order(self):
        assert _parse_hist_nums("[38, 4, 21]") == _parse_hist_nums("[4, 21, 38]")


# ── _b_row_nums ───────────────────────────────────────────────────────────────

class TestBRowNums:
    def test_extracts_pos_columns(self):
        b = _b([("w1", [3, 9, 15, 21, 27, 33])])
        assert _b_row_nums(b, 0) == frozenset({3, 9, 15, 21, 27, 33})

    def test_skips_na(self):
        b = pd.DataFrame([{"w": "w1", "pos_1": 5, "pos_2": pd.NA, "pos_3": 10}])
        assert _b_row_nums(b, 0) == frozenset({5, 10})

    def test_correct_row_selected(self):
        b = _b([("w1", [1, 2, 3, 4, 5, 6]), ("w2", [7, 8, 9, 10, 11, 12])])
        assert _b_row_nums(b, 1) == frozenset({7, 8, 9, 10, 11, 12})


# ── _sync_b ───────────────────────────────────────────────────────────────────

class TestSyncB:
    def test_not_configured_when_none(self):
        result = _sync_b(_b([("w1", [1, 2, 3, 4, 5, 6])]),
                         _hist([(1001, "2026-01-01", [1, 2, 3, 4, 5, 6])]),
                         None)
        assert result["status"] == "not_configured"

    def test_gap_too_large_when_b_empty(self):
        result = _sync_b(pd.DataFrame(), _hist([(1, "2026-01-01", [1, 2, 3])]), 0)
        assert result["status"] == "gap_too_large"

    def test_gap_too_large_when_hist_empty(self):
        result = _sync_b(_b([("w1", [1, 2, 3, 4, 5, 6])]), pd.DataFrame(), 0)
        assert result["status"] == "gap_too_large"

    def test_gap_too_large_when_b_hist_start_out_of_range(self):
        b = _b([("w1", [1, 2, 3, 4, 5, 6])])  # only 1 row
        result = _sync_b(b, _hist([(1, "2026-01-01", [1, 2, 3, 4, 5, 6])]), 5)
        assert result["status"] == "gap_too_large"

    def test_gap_too_large_when_numbers_not_found(self):
        b = _b([("w1", [40, 41, 42, 43, 44, 45])])
        hist = _hist([(1001, "2026-01-01", [1, 2, 3, 4, 5, 6])])
        result = _sync_b(b, hist, 0)
        assert result["status"] == "gap_too_large"
        assert "not found" in result["detail"]

    def test_current_when_b_matches_newest(self):
        b = _b([("w1", [4, 7, 13, 21, 29, 38])])
        hist = _hist([(4685, "2026-06-14", [4, 7, 13, 21, 29, 38])])
        result = _sync_b(b, hist, 0)
        assert result["status"] == "current"
        assert result["draw"] == "4685"
        assert result["numbers"] == [4, 7, 13, 21, 29, 38]

    def test_behind_single_missing_draw(self):
        b = _b([("w1", [1, 2, 3, 4, 5, 6])])
        hist = _hist([
            (1002, "2026-01-15", [7, 8, 9, 10, 11, 12]),   # newer — missing
            (1001, "2026-01-08", [1, 2, 3, 4, 5, 6]),       # matches B row 0
        ])
        result = _sync_b(b, hist, 0)
        assert result["status"] == "behind"
        assert result["count"] == 1
        assert result["missing_draws"][0]["draw"] == "1002"
        assert result["missing_draws"][0]["numbers"] == [7, 8, 9, 10, 11, 12]

    def test_behind_multiple_newest_first_ordering(self):
        b = _b([("w1", [1, 2, 3, 4, 5, 6])])
        hist = _hist([
            (1003, "2026-01-22", [13, 14, 15, 16, 17, 18]),
            (1002, "2026-01-15", [7, 8, 9, 10, 11, 12]),
            (1001, "2026-01-08", [1, 2, 3, 4, 5, 6]),
        ])
        result = _sync_b(b, hist, 0)
        assert result["status"] == "behind"
        assert result["count"] == 2
        assert result["missing_draws"][0]["draw"] == "1003"  # newest first
        assert result["missing_draws"][1]["draw"] == "1002"

    def test_numbers_survive_csv_roundtrip(self):
        """Numbers column stored as string after CSV save/load."""
        b = _b([("w1", [4, 7, 13, 21, 29, 38])])
        hist = pd.DataFrame([
            {"draw": 4685, "date": "2026-06-14", "numbers": "[4, 7, 13, 21, 29, 38]"}
        ])
        result = _sync_b(b, hist, 0)
        assert result["status"] == "current"

    def test_b_hist_start_offset_respected(self):
        """Rows before b_hist_start are ignored; only row N is the anchor."""
        b = _b([
            ("pre1", [99, 98, 97, 96, 95, 94]),   # row 0 — not the anchor
            ("w1",   [1, 2, 3, 4, 5, 6]),          # row 1 = b_hist_start
        ])
        hist = _hist([(1001, "2026-01-08", [1, 2, 3, 4, 5, 6])])
        result = _sync_b(b, hist, b_hist_start=1)
        assert result["status"] == "current"


# ── _append_draws ─────────────────────────────────────────────────────────────

class TestAppendDraws:
    def test_single_draw_inserted_at_hist_start(self):
        b = _b([
            ("pre1", [1, 2, 3, 4, 5, 6]),    # row 0 — prefix
            ("pre2", [2, 3, 4, 5, 6, 7]),    # row 1 — prefix
            ("w3",   [10, 11, 12, 13, 14, 15]),  # row 2 = b_hist_start
            ("w4",   [20, 21, 22, 23, 24, 25]),  # row 3
        ])
        draws = [{"draw": "9999", "date": "2026-06-21", "numbers": [33, 34, 35, 36, 37, 38]}]
        result = _append_draws(b, draws, b_hist_start=2)

        assert len(result) == 5
        assert result.iloc[0]["w"] == "pre1"
        assert result.iloc[1]["w"] == "pre2"
        assert result.iloc[2]["w"] == "9999"   # new draw at position 2
        assert result.iloc[2]["pos_1"] == 33
        assert result.iloc[3]["w"] == "w3"     # old row 2 shifted to 3
        assert result.iloc[4]["w"] == "w4"

    def test_multiple_draws_newest_first(self):
        b = _b([("w1", [1, 2, 3, 4, 5, 6])])   # row 0 = b_hist_start
        draws = [
            {"draw": "1002", "date": "2026-01-15", "numbers": [7, 8, 9, 10, 11, 12]},
            {"draw": "1001", "date": "2026-01-08", "numbers": [3, 4, 5, 6, 7, 8]},
        ]
        result = _append_draws(b, draws, b_hist_start=0)

        assert len(result) == 3
        assert result.iloc[0]["w"] == "1002"   # newest
        assert result.iloc[1]["w"] == "1001"
        assert result.iloc[2]["w"] == "w1"     # original shifted down

    def test_empty_draws_returns_unchanged(self):
        b = _b([("w1", [1, 2, 3, 4, 5, 6])])
        result = _append_draws(b, [], b_hist_start=0)
        assert len(result) == 1
        assert result.iloc[0]["w"] == "w1"

    def test_column_alignment_na_fill(self):
        """Wider B (7-number game) → new row's missing pos_ cols get NA."""
        b = _b([("w1", [1, 2, 3, 4, 5, 6, 7])])
        draws = [{"draw": "999", "date": "2026-01-01", "numbers": [3, 4, 5, 6, 7, 8, 9]}]
        result = _append_draws(b, draws, b_hist_start=0)
        assert result.iloc[0]["pos_7"] == 9

    def test_numbers_from_csv_string_in_draws(self):
        """Draw numbers stored as string (as they come from hist_df after sync)."""
        b = _b([("w1", [1, 2, 3, 4, 5, 6])])
        draws = [{"draw": "1001", "date": "2026-01-08",
                  "numbers": "[7, 8, 9, 10, 11, 12]"}]
        result = _append_draws(b, draws, b_hist_start=0)
        assert result.iloc[0]["pos_1"] == 7


# ── Public API wrappers ───────────────────────────────────────────────────────

class TestPublicAPI:
    def test_append_raises_for_unconfigured_game(self):
        """Unknown game key has no b_hist_start → raises ValueError."""
        b = _b([("w1", [1, 2, 3, 4, 5, 6, 7])])
        with pytest.raises(ValueError, match="b_hist_start not configured"):
            append_draws_to_b("xx", b, [{"draw": "1", "date": "", "numbers": [1, 2, 3]}])

    def test_b_hist_start_values(self):
        """All five games have correct 0-based iloc b_hist_start values."""
        assert GAMES_CFG["sat"]["b_hist_start"] == 42  # w43 = iloc[42]
        assert GAMES_CFG["pb"]["b_hist_start"]  == 38  # w39 = iloc[38]
        assert GAMES_CFG["oz"]["b_hist_start"]  == 42  # w43 = iloc[42]
        assert GAMES_CFG["sfl"]["b_hist_start"] == 42  # w43 = iloc[42]
        assert GAMES_CFG["mwf"]["b_hist_start"] == 42  # w43 = iloc[42]


# ── Integration: sat "current" check ─────────────────────────────────────────

def _load_sat_b():
    """Try to load sat's actual B from disk. Returns empty DataFrame if absent."""
    try:
        from syndicate_core.config import ROOT, GAMES_CFG
        gcfg = GAMES_CFG["sat"]
        candidates = list(ROOT.rglob(gcfg["b_file"]))
        if not candidates:
            return pd.DataFrame()
        xl = __import__("pandas").ExcelFile(candidates[0], engine="openpyxl")
        sheet = gcfg["b_sheet"] if gcfg["b_sheet"] in xl.sheet_names else None
        if sheet is None:
            return pd.DataFrame()
        raw = xl.parse(sheet, header=None)
        col0 = [str(raw.iloc[r, 0]).strip() for r in range(raw.shape[0])]
        rows = []
        for r, label in enumerate(col0):
            if label.lower().startswith("w"):
                nums = [int(float(v)) for v in raw.iloc[r, 1:].dropna()
                        if str(v).replace(".", "").replace("-", "").isdigit()
                        and float(v) >= 1]
                if nums:
                    row = {"w": label}
                    row.update({f"pos_{i + 1}": n for i, n in enumerate(nums)})
                    rows.append(row)
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@pytest.mark.integration
def test_sat_current_against_draw_4685():
    """sat B row 43 should match draw 4685 — verifies b_hist_start=43 is correct.

    Uses a synthetic hist_df containing draw 4685 at position 0 (newest).
    Skipped if sat B file is not available on disk.
    """
    b = _load_sat_b()
    if b.empty or len(b) <= 42:
        pytest.skip("sat B file not available or too short — skipping integration test")

    # Build a synthetic hist_df: draw 4685 is newest (pos 0), matching B row iloc[42] (Excel w43)
    b_row_43_nums = sorted(_b_row_nums(b, 42))
    hist = pd.DataFrame([
        {"draw": 4685, "date": "2026-06-14", "numbers": str(b_row_43_nums)},
        {"draw": 4684, "date": "2026-06-07", "numbers": "[1, 2, 3, 4, 5, 6]"},  # dummy older
    ])

    result = sync_b_with_latest_draws("sat", b, hist)
    assert result["status"] == "current", (
        f"Expected 'current' but got {result}. "
        f"B row 43 numbers: {b_row_43_nums}"
    )
    assert result["draw"] == "4685"
