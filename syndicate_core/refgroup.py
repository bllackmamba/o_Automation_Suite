"""
syndicate_core/refgroup.py — Reference Group (RefGroup_w1) breakdown.

Pure, import-safe, Streamlit-free logic for the live RefGroup panel and the
combined-CVI 7th block. Confirmed design 2026-07-13 (Tai + Claude).

RefGroup_w1 = the newest completed draw's ``pick`` winning numbers, matched
against the FULL C(pool, pick) combination space, split into S0..S_pick by how
many of the reference numbers a combination shares, then bucketed into Tai's
Selected{1,2,3} / Unselected{0,4,5,6} split.

CRITICAL invariance property (this is why the panel advertises the numbers as
never-changing, not a caching bug):

    The S0..S_pick distribution is a FIXED hypergeometric property of
    (pool, pick). It does NOT depend on WHICH numbers are the reference set —
    the count of C(pool,pick) combinations sharing exactly k of any fixed
    pick-sized set is C(pick,k)·C(pool-pick, pick-k), independent of the set's
    identity. Only the *labels* (which 6 numbers are RefGroup_w1) change week
    to week; the breakdown counts never do.

Computation is the closed-form (Option A, chosen 2026-07-13): free, needs no
data load, exact against The Lott's published Division-1 odds (S6 == 1 out of
C(45,6) = 8,145,060 for Saturday Lotto). The combined-CVI export path matches
RefGroup_w1 through the ordinary ``_match_cvi_rows`` engine (Option B) — the
two now agree to the exact integer including S0. (Before 2026-07-15 the sat
main-data file had no header row, so pandas consumed combo 1,2,3,4,5,6 as its
column names and excluded it from matching, making the engine report S0 one
lower at M = C(45,6) − 1; that file now carries a proper n1..n6 header, so the
full 8,145,060-row space is matched and the single-combo offset is gone.)
"""
from __future__ import annotations

from math import comb
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

# RefGroup_w1 carries a DISTINCT Source/Set_Label so it can never collide with
# R's own "w1" or B's own "w1" (different rows, different meaning) in the
# collation stack. It is matched only as itself, never against R/B row sets.
SOURCE = "RefGroup"
SET_LABEL = "RefGroup_w1"

# LOCKED Repeat/No_repeat split (confirmed 2026-07-15, empirical + closed-form +
# real-draw-history verified). Stated generally so it extends correctly to any
# new game:
#     Selected (Repeat)    = {1 .. pick-3}
#     Unselected (No_repeat) = {0} ∪ {pick-2, pick-1, pick}
# 0 NEVER belongs in Selected —0 shared numbers is the definitional opposite of
# a repeat, not a repeat (an earlier draft that put 0 in Selected was rejected).
#   pick=6 (sat, mwf) → Selected {1,2,3}   Unselected {0,4,5,6}
#   pick=7 (pb,oz,sfl) → Selected {1,2,3,4} Unselected {0,5,6,7}
# SELECTED_BANDS is the pick-6 instance kept for backward-compatible defaults;
# prefer selected_bands_for_pick(pick) for anything game-general.
SELECTED_BANDS: tuple[int, ...] = (1, 2, 3)


def selected_bands_for_pick(pick: int) -> tuple[int, ...]:
    """The locked Selected (Repeat) bands {1 .. pick-3} for a given pick size.

    pick=6 → (1, 2, 3); pick=7 → (1, 2, 3, 4). Empty for pick < 4 (no mid-range
    band exists). 0 is never included — see the module-level split note.
    """
    return tuple(range(1, pick - 2)) if pick >= 4 else ()


def classify_shared(shared: int, pick: int) -> str:
    """Classify a shared-number count under the locked split.

    Returns ``"Repeat"`` iff ``shared`` is in the locked Selected bands
    {1 .. pick-3}, else ``"No_repeat"`` (covers 0 and the extreme tail
    {pick-2, pick-1, pick}).
    """
    return "Repeat" if shared in selected_bands_for_pick(pick) else "No_repeat"


def main_data_stream(shared: int) -> str:
    """Rule 1 (Main Data split): the nonzero/zero boundary.

    Returns ``"Repeat"`` iff ``shared`` >= 1 (the row shares at least one number
    with the reference draw), else ``"No_Repeat"``. This is the LOCKED-doc Rule
    Set 1 split applied to the Main Data pool — reference-invariant (it depends
    only on set sizes, not which numbers). For sat this partitions C(45,6) into
    Repeat = 4,882,437 and No_Repeat = 3,262,623.

    Distinct from :func:`classify_shared` (Rule 2), which keeps only the
    ``{1 .. pick-3}`` candidate bands: a share of pick-2/pick-1/pick is Repeat
    here but No_repeat under Rule 2. Do not conflate the two.
    """
    return "Repeat" if shared > 0 else "No_Repeat"


def total_space(pool: int, pick: int) -> int:
    """Size of the full combination space C(pool, pick)."""
    return comb(pool, pick)


def hypergeometric_breakdown(pool: int, pick: int) -> dict[int, int]:
    """S0..S_pick counts for ANY pick-sized reference set vs the C(pool, pick) space.

    S_k = C(pick, k) · C(pool - pick, pick - k) — the number of combinations
    sharing exactly ``k`` numbers with the reference set. Independent of which
    numbers the reference set holds. ``sum(S_k) == C(pool, pick)`` exactly.
    """
    return {k: comb(pick, k) * comb(pool - pick, pick - k) for k in range(pick + 1)}


def selected_unselected(
    breakdown: Mapping[int, int],
    selected_bands: Sequence[int] = SELECTED_BANDS,
) -> tuple[int, int]:
    """Split an S0..S_pick breakdown into (selected_total, unselected_total).

    Selected = sum of the ``selected_bands`` buckets (default S1+S2+S3).
    Unselected = every other bucket (default S0 + S4 + S5 + S6 …).
    """
    sel_set = set(selected_bands)
    selected = sum(cnt for k, cnt in breakdown.items() if k in sel_set)
    unselected = sum(cnt for k, cnt in breakdown.items() if k not in sel_set)
    return selected, unselected


def empirical_stream_counts(
    main_df: pd.DataFrame,
    n_cols: Sequence[str],
    ref_numbers: Sequence[int],
    pick: int,
) -> dict:
    """Bucket every REAL main-data row by shared count vs ``ref_numbers``.

    Touches the actual uploaded main data (vectorized ``isin`` over ``n_cols``),
    NOT the closed form — the closed form is reserved for the RefGroup live
    panel. For a full C(pool, pick) main-data file this returns the exact same
    integers as ``hypergeometric_breakdown`` (verified this session), but it is
    computed empirically so the SC preset never substitutes theory for data.

    Returns ``{"bands": {k: count}, "selected", "unselected", "M"}`` where the
    Selected/Unselected split follows the locked per-pick rule.
    """
    ref = np.array(sorted({int(n) for n in ref_numbers}), dtype=np.int64)
    arr = main_df[list(n_cols)].to_numpy()
    shared = np.isin(arr, ref).sum(axis=1)
    bands = {k: int((shared == k).sum()) for k in range(pick + 1)}
    sel_set = set(selected_bands_for_pick(pick))
    selected = sum(c for k, c in bands.items() if k in sel_set)
    unselected = sum(c for k, c in bands.items() if k not in sel_set)
    return {"bands": bands, "selected": selected,
            "unselected": unselected, "M": int(shared.shape[0])}


def locked_sc_dict(w_cols: Sequence[str], pick: int) -> dict[str, list[int]]:
    """Preset Selected-Counts dict for the locked Repeat/No_repeat split.

    Every w-position's Selected set is the locked Selected bands {1 .. pick-3},
    so feeding this straight into ``run_matching``'s ``sc_dict`` buckets each
    candidate row into Repeat (Selected) vs No_repeat (Unselected) with no manual
    threshold entry. Keyed by the w-column names (``"w1"``, ``"w2"``, …).
    """
    sel = list(selected_bands_for_pick(pick))
    return {str(w): list(sel) for w in w_cols}


def parse_draw_numbers(val) -> list[int]:
    """Parse a draw_history ``numbers`` cell into a list of ints.

    Faithful copy of masterapp's ``_sd_parse_nums`` (the Stacked Draws parser)
    so RefGroup reads the newest draw exactly as the Blocked-flat / Cascading
    views do. Accepts a list or a "[1, 5, 12, …]" string.
    """
    if isinstance(val, list):
        return [int(x) for x in val]
    s = str(val).strip("[]")
    result: list[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok.isdigit():
            result.append(int(tok))
    return result


def newest_reference_numbers(history_df: pd.DataFrame, pick: int) -> list[int] | None:
    """The newest completed draw's ``pick`` winning numbers, sorted ascending.

    ``history_df`` is the newest-first ``draw_history.csv`` the Stacked Draws
    views already load — read-only, never written. Returns the sorted numbers,
    or ``None`` when history is empty or the newest row does not have exactly
    ``pick`` valid numbers (so the caller can surface a clear warning instead of
    computing against a malformed reference set). This is what makes the feature
    auto-update: it always reads row 0, so a new draw is picked up on next load.
    """
    if history_df is None or history_df.empty or "numbers" not in history_df.columns:
        return None
    nums = sorted(set(parse_draw_numbers(history_df.iloc[0]["numbers"])))
    if len(nums) != pick:
        return None
    return nums


def load_newest_reference(history_path, pick: int) -> list[int] | None:
    """Read ``draw_history.csv`` at ``history_path`` and return RefGroup_w1's numbers.

    Read-only convenience wrapper around :func:`newest_reference_numbers`: loads
    the CSV with the same ``dtype=str`` the Stacked Draws views use, then returns
    the newest draw's sorted ``pick`` numbers — or ``None`` when the file is
    missing, empty, or its newest row is malformed. Never writes to the history
    file. Shared by the live panel and the combined-CVI export so both read the
    newest draw identically.
    """
    path = Path(history_path)
    if not path.exists():
        return None
    hist = pd.read_csv(path, dtype=str)
    return newest_reference_numbers(hist, pick)


def build_ref_group_piece(numbers: Sequence[int]) -> pd.DataFrame:
    """One-row collation block for RefGroup_w1: [Source, Set_Label, w1..wN].

    Shaped exactly like the per-variable blocks ``execute_collation`` stacks, so
    appending it to the ``pieces`` list and running the pipeline's usual
    ``pd.concat`` + ``Row_ID = range(1, len+1)`` assigns RefGroup_w1 the next
    sequential Row_ID by construction — never a hand-picked or hardcoded ID.
    """
    row = {f"w{i + 1}": int(n) for i, n in enumerate(numbers)}
    piece = pd.DataFrame([row])
    piece.insert(0, "Set_Label", SET_LABEL)
    piece.insert(0, "Source", SOURCE)
    return piece
