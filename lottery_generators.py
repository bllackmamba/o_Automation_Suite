"""
lottery_generators.py — variable generators for the Syndicate System pipeline.

Each generator is a PURE function: DataFrame(s) in → DataFrame(s) out. No Streamlit,
no input() prompts, no disk side-effects. masterapp imports these and feeds the
results into the variable pipeline (S["R"], S["Sp"], S["So"], S["Ep"]); the existing
row-collation transposes their column-oriented output into stacked w-rows.

Generators (built incrementally):
  • generate_rainbow   ← task2.py        (input: Since-Last table)            [R]
  • generate_splits    ← task1b.py       (input: D's 4 longest rows)          [Sp]  (next)
  • generate_splits_combi ← automation_vba.py (input: D's 4 longest rows)     [So]  (next)
  • generate_excelpro  ← ExcelPro (Java→Python) (input: D's 8 longest + R wt) [Ep]  (next)
"""
from __future__ import annotations
from itertools import chain, combinations
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def _bounded_combos(keys, max_comb):
    """All combinations of `keys` of size 1..max_comb, generated DIRECTLY.

    This replaces the original `powerset(...)` + size-filter, which materialised
    all 2**K subsets before discarding the big ones — the cause of the "don't set
    max too high or it malfunctions" warning. Generating sizes 1..max_comb directly
    never builds the explosive tail, so max_comb can safely go as high as the
    combo-count guard allows.
    """
    keys = list(keys)
    hi = min(max_comb, len(keys))
    return chain.from_iterable(combinations(keys, r) for r in range(1, hi + 1))


def _combo_count(n_keys, max_comb):
    """How many combinations sizes 1..max_comb over n_keys keys would be produced."""
    from math import comb
    hi = min(max_comb, n_keys)
    return sum(comb(n_keys, r) for r in range(1, hi + 1))


# ─────────────────────────────────────────────────────────────────────────────
# R — Rainbow  (ported from task2.py)
# ─────────────────────────────────────────────────────────────────────────────
def generate_rainbow(sl_df: pd.DataFrame,
                     max_comb: int | None = None,
                     combo_guard: int = 200_000):
    """Build the Rainbow (R) sets from the Since-Last table.

    Input `sl_df` columns (case-insensitive, flexible): a number column, a
    'Since Last' column, and a 'to_keep' column — the lottolyzer-style table.

      • Group the numbers by their Since-Last value.
      • For every combination of 1..max_comb of those groups, union the numbers,
        then keep only the ones present in to_keep.
      • Each combination becomes one output COLUMN (named by the group tuple);
        the collation later transposes these columns into R's w-rows.

    Returns (result_df, wt_df, info):
      result_df : the Rainbow output (columns = combinations of kept numbers)
      wt_df     : the 'wt' frame (incl. a wt_abcd column) — this is what Ep reads
                  as its input2 "All wt"
      info      : dict with n_groups, max_comb used, n_combos, capped (bool)
    """
    df = _normalise_sl(sl_df)
    # group numbers by Since-Last
    grouped = df.groupby("since_last")["numbers"].apply(list).to_dict()
    to_keep = set(df["to_keep"].dropna().tolist())
    keys = sorted(grouped.keys())

    # choose / clamp max_comb. Default = "as many groups as safe".
    n = len(keys)
    requested = n if max_comb is None else int(max_comb)
    requested = max(1, min(requested, n))
    capped = False
    while requested > 1 and _combo_count(n, requested) > combo_guard:
        requested -= 1
        capped = True
    use_max = requested

    result = {}
    for comb in _bounded_combos(keys, use_max):
        ref = []
        for g in comb:
            ref += grouped[g]
        kept = [e for e in ref if e in to_keep]
        result[str(comb)] = kept

    result_df = pd.DataFrame(
        {k: pd.Series(v, dtype="Int64") for k, v in result.items()})
    # order columns by fewest blanks first (densest combos first), like the original
    if not result_df.empty:
        order = result_df.isna().sum().sort_values(kind="stable").index
        result_df = result_df[order]

    wt_df = _wt_writer(df)
    info = {"n_groups": n, "max_comb": use_max,
            "n_combos": result_df.shape[1], "capped": capped,
            "combo_guard": combo_guard}
    return result_df, wt_df, info


def _normalise_sl(sl_df: pd.DataFrame) -> pd.DataFrame:
    """Map a Since-Last table to canonical columns: numbers, since_last, to_keep."""
    df = sl_df.copy()
    lower = {str(c).strip().lower(): c for c in df.columns}

    def pick(*cands):
        for cand in cands:
            if cand in lower:
                return lower[cand]
        return None

    c_num = pick("numbers", "number", "n", "ball")
    c_sl = pick("since last", "since_last", "sincelast", "since", "sl")
    c_keep = pick("to_keep", "to keep", "tokeep", "keep")
    if c_num is None or c_sl is None:
        raise ValueError("Since-Last table needs a number column and a "
                         "'Since Last' column (got: %s)" % list(df.columns))
    out = pd.DataFrame({
        "numbers": pd.to_numeric(df[c_num], errors="coerce"),
        "since_last": pd.to_numeric(df[c_sl], errors="coerce"),
    })
    out["to_keep"] = (pd.to_numeric(df[c_keep], errors="coerce")
                      if c_keep is not None else out["numbers"])
    out = out.dropna(subset=["since_last", "numbers"], how="any")
    out["since_last"] = out["since_last"].astype(int) + 1   # original did +1
    out["numbers"] = out["numbers"].astype(int)
    return out


def _wt_writer(df: pd.DataFrame) -> pd.DataFrame:
    """Reproduce task2.py's 'wt' sheet (SL / wt / … / wt_abcd) from the Since-Last
    table. This frame is what Ep consumes as input2 'All wt'."""
    listed = df.groupby("since_last")["numbers"].apply(list).to_dict()
    keep = set(df["to_keep"].dropna().tolist())
    i0, w0, i1, w1, iF, wF = [], [], [], [], [], []
    for i in sorted(listed.keys()):
        i0 += [i] + [None] * (len(listed[i]) - 1)
        i1 += [i] + [None] * len(listed[i])
        w0 += listed[i]
        w1 += listed[i] + [None]
        kref = [e for e in listed[i] if e in keep]
        iF += [i] + [None] * (len(kref) - 1)
        wF += kref
    gen = [i0, w0, i1, w1, iF, wF]
    out = pd.DataFrame({n: pd.Series(gen[n]) for n in range(len(gen))})
    out.columns = ["SL", "wt", "SL_", "wt_", "_SL_", "wt_abcd"]
    return out
