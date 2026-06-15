"""
syndicate_core/b_sync.py — B-variable draw-history synchronisation

Compares B's current-newest draw (at row b_hist_start) against cached draw
history to detect missing draws, then inserts them newest-first at the right
position.

Public API
----------
sync_b_with_latest_draws(game, b_df, hist_df) -> dict
append_draws_to_b(game, b_df, draws)          -> pd.DataFrame

Pure internals (exposed for testing)
-------------------------------------
_parse_hist_nums(val)                          -> frozenset[int]
_b_row_nums(b_df, row_idx)                    -> frozenset[int]
_sync_b(b_df, hist_df, b_hist_start)          -> dict
_append_draws(b_df, draws, b_hist_start)      -> pd.DataFrame
"""

import re

import pandas as pd

from syndicate_core.config import GAMES_CFG

__all__ = [
    "sync_b_with_latest_draws",
    "append_draws_to_b",
    "_sync_b",
    "_append_draws",
    "_parse_hist_nums",
    "_b_row_nums",
]


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_hist_nums(val) -> frozenset:
    """Return a frozenset of ints from a history 'numbers' cell.

    Handles:
    - Python list/tuple  (fresh fetch)
    - String repr        "[4, 7, 13, 21, 29, 38]"  (after CSV round-trip)
    """
    if isinstance(val, (list, tuple)):
        return frozenset(int(x) for x in val if str(x).strip().isdigit()
                         or (isinstance(x, (int, float)) and x == int(x)))
    return frozenset(int(x) for x in re.findall(r'\d+', str(val)))


def _b_row_nums(b_df: pd.DataFrame, row_idx: int) -> frozenset:
    """Extract the number-set from row_idx of a row-oriented B DataFrame."""
    row = b_df.iloc[row_idx]
    nums = set()
    for col in b_df.columns:
        if not str(col).startswith("pos_"):
            continue
        v = row[col]
        if pd.isna(v):
            continue
        try:
            nums.add(int(v))
        except (ValueError, TypeError):
            pass
    return frozenset(nums)


# ── Pure sync logic ───────────────────────────────────────────────────────────

def _sync_b(b_df: pd.DataFrame, hist_df: pd.DataFrame,
             b_hist_start) -> dict:
    """Compare B's row at b_hist_start against draw history.

    hist_df must be newest-first (as returned by fetch_draw_history).

    Returns one of:
        {"status": "not_configured"}
        {"status": "current", "draw": str, "numbers": list[int]}
        {"status": "behind",  "missing_draws": list[dict], "count": int}
        {"status": "gap_too_large", "detail": str}
    """
    if b_hist_start is None:
        return {"status": "not_configured"}

    if b_df is None or b_df.empty:
        return {"status": "gap_too_large",
                "detail": "B is empty — load B first"}

    if b_hist_start >= len(b_df):
        return {"status": "gap_too_large",
                "detail": f"b_hist_start={b_hist_start} but B has only {len(b_df)} rows"}

    if hist_df is None or hist_df.empty:
        return {"status": "gap_too_large",
                "detail": "No draw history available — fetch draw history first (section 2)"}

    if "numbers" not in hist_df.columns:
        return {"status": "gap_too_large",
                "detail": "Draw history missing 'numbers' column"}

    b_nums = _b_row_nums(b_df, b_hist_start)

    match_pos = None
    for pos in range(len(hist_df)):
        if _parse_hist_nums(hist_df.iloc[pos]["numbers"]) == b_nums:
            match_pos = pos
            break

    if match_pos is None:
        return {
            "status": "gap_too_large",
            "detail": (
                f"B row {b_hist_start} numbers {sorted(b_nums)} not found in "
                f"{len(hist_df)} history entries — try fetching more history pages"
            ),
        }

    draw_label = str(hist_df.iloc[match_pos].get("draw", match_pos))

    if match_pos == 0:
        return {"status": "current", "draw": draw_label, "numbers": sorted(b_nums)}

    missing = [
        {
            "draw":    str(hist_df.iloc[p].get("draw", "")),
            "date":    str(hist_df.iloc[p].get("date", "")),
            "numbers": sorted(_parse_hist_nums(hist_df.iloc[p]["numbers"])),
        }
        for p in range(match_pos)
    ]
    return {"status": "behind", "missing_draws": missing, "count": len(missing)}


# ── Pure insert logic ─────────────────────────────────────────────────────────

def _draw_to_b_row(draw_dict: dict, b_columns) -> dict:
    """Build a row-oriented B row from a draw dict, aligned to b_columns."""
    nums = sorted(_parse_hist_nums(draw_dict["numbers"]))
    row = {col: pd.NA for col in b_columns}
    row["w"] = str(draw_dict.get("draw", ""))
    for i, n in enumerate(nums):
        col = f"pos_{i + 1}"
        if col in row:
            row[col] = n
        else:
            row[col] = n  # extend if new draw has more numbers than B's schema
    return row


def _append_draws(b_df: pd.DataFrame, draws: list,
                   b_hist_start: int) -> pd.DataFrame:
    """Insert draws (newest-first) at row b_hist_start, shifting rest down.

    draws: list of {"draw": ..., "date": ..., "numbers": [...]} newest-first.
    """
    if not draws:
        return b_df

    new_rows = pd.DataFrame([_draw_to_b_row(d, list(b_df.columns)) for d in draws])

    # Align columns: add any pos_ columns B doesn't have yet (edge case)
    for col in new_rows.columns:
        if col not in b_df.columns:
            b_df = b_df.copy()
            b_df[col] = pd.NA

    # Reorder new_rows to match b_df column order, adding NA for extras
    for col in b_df.columns:
        if col not in new_rows.columns:
            new_rows[col] = pd.NA
    new_rows = new_rows[b_df.columns]

    before = b_df.iloc[:b_hist_start]
    after  = b_df.iloc[b_hist_start:]

    return pd.concat([before, new_rows, after], ignore_index=True)


# ── Public API ────────────────────────────────────────────────────────────────

def sync_b_with_latest_draws(game: str, b_df: pd.DataFrame,
                              hist_df: pd.DataFrame) -> dict:
    """Public entry point — reads b_hist_start from GAMES_CFG."""
    b_hist_start = GAMES_CFG.get(game, {}).get("b_hist_start")
    return _sync_b(b_df, hist_df, b_hist_start)


def append_draws_to_b(game: str, b_df: pd.DataFrame,
                       draws: list) -> pd.DataFrame:
    """Public entry point — reads b_hist_start from GAMES_CFG."""
    b_hist_start = GAMES_CFG.get(game, {}).get("b_hist_start")
    if b_hist_start is None:
        raise ValueError(f"b_hist_start not configured for game '{game}'")
    return _append_draws(b_df, draws, b_hist_start)
