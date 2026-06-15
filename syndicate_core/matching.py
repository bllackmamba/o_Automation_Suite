"""
syndicate_core/matching.py — Matching and counting engine

Contains: vectorised numpy/DuckDB matching, CVI parsing, breakdown formatting,
the sequential run_matching engine, and the multiprocessing _parallel_worker.
"""

import re
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from syndicate_core.config import CHUNK_SIZE, DISPLAY_THRESHOLD

__all__ = [
    # constants
    "DUCKDB_THRESHOLD",
    # utilities
    "_count_csv_rows", "_duckdb_available",
    # core matching primitives
    "_match_chunk", "_match_duckdb", "_smart_match",
    "_parse_cvi_col", "_count_matches",
    # formatting
    "_count_str", "_breakdown_str",
    # stage helpers
    "_compute_stage_present", "_apply_stage_sc",
    # pre-loop + fill helpers
    "_prepare_matching_state", "_fill_exhausted_stages",
    # engines
    "run_matching", "run_matching_step", "_parallel_worker",
]

DUCKDB_THRESHOLD = 50 * 1024 * 1024   # 50 MB CSV → use DuckDB


# ── Utilities ─────────────────────────────────────────────────────────────────

def _count_csv_rows(path: Path) -> int:
    """Fast row count without loading into memory."""
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f) - 1
    except Exception:
        return 0


def _duckdb_available() -> bool:
    try:
        import duckdb
        return True
    except ImportError:
        return False


# ── Core matching primitives ──────────────────────────────────────────────────

def _match_chunk(chunk_arr: np.ndarray, cvi_arr: np.ndarray) -> np.ndarray:
    """
    Vectorised intersection count.
    chunk_arr: (N, K) float32 — main data chunk
    cvi_arr:   (M,)   float32 — CVI numbers
    returns:   (N,)   int32   — match count per row
    Handles 500K rows in ~0.05s on M3 Pro Max.

    NOTE (restored): the `def` line for this function had been lost in a
    previous edit. That left this body as unreachable code *inside*
    `_smart_match`, so `_match_chunk` was never actually defined — and every
    call to `_count_matches` / `run_matching` raised `NameError`. It is now a
    proper module-level function again. Logic is unchanged.
    """
    counts = np.zeros(chunk_arr.shape[0], dtype=np.int32)
    for j in range(chunk_arr.shape[1]):
        counts += np.isin(chunk_arr[:, j], cvi_arr).astype(np.int32)
    return counts


def _match_duckdb(csv_path: Path, cvi_nums: list[int],
                  n_col_count: int) -> np.ndarray:
    """
    DuckDB-based matching for very large CSV files.
    Reads CSV directly from disk — never loads full file into RAM.
    Works on 63M rows in ~30 seconds vs pandas which would freeze.

    csv_path:     path to the main data CSV file
    cvi_nums:     list of CVI numbers to match against
    n_col_count:  number of n-columns (n1..nN)

    Returns np.ndarray of match counts per row (length = row count in file).
    """
    import duckdb

    n_cols_sql = " + ".join(
        f"(CASE WHEN n{i} IN ({','.join(str(x) for x in cvi_nums)}) "
        f"THEN 1 ELSE 0 END)"
        for i in range(1, n_col_count + 1)
    )

    query = f"""
        SELECT {n_cols_sql} AS match_count
        FROM read_csv_auto('{csv_path}',
            ignore_errors=true,
            sample_size=10000)
        ORDER BY rowid
    """

    try:
        con = duckdb.connect(database=":memory:")
        result = con.execute(query).fetchnumpy()
        con.close()
        counts = result["match_count"].astype(np.int32)
        return counts
    except Exception:
        return np.array([], dtype=np.int32)


def _smart_match(main_df_or_path, n_cols: list,
                 cvi_nums: np.ndarray) -> np.ndarray:
    """
    Route to DuckDB (large files) or numpy (in-memory).
    main_df_or_path: pd.DataFrame already loaded, OR Path to CSV file.
    """
    if isinstance(main_df_or_path, Path):
        size = main_df_or_path.stat().st_size
        if size > DUCKDB_THRESHOLD and _duckdb_available():
            return _match_duckdb(
                main_df_or_path, cvi_nums.tolist(), len(n_cols))
        else:
            chunks = pd.read_csv(main_df_or_path, chunksize=500_000)
            df = pd.concat(chunks, ignore_index=True)
            return _count_matches(df, n_cols, cvi_nums)
    else:
        return _count_matches(main_df_or_path, n_cols, cvi_nums)


def _parse_cvi_col(series: pd.Series) -> list[int]:
    """
    Extract valid integers from a CVI column.
    Handles floats (1.0→1), strings ("1"), NaN safely.
    No upper range cap — CVI values are not raw lottery balls
    and can legitimately exceed 45 depending on the collation formula.
    """
    result = []
    for v in series.dropna():
        try:
            n = float(str(v).strip())
            if not pd.isna(n) and n >= 1:
                result.append(int(round(n)))
        except (ValueError, TypeError):
            pass
    return result


def _count_matches(df: pd.DataFrame, n_cols: list,
                   cvi_nums: np.ndarray) -> np.ndarray:
    """Vectorised match count — chunks handled internally.

    Accumulates each chunk's counts in a list and concatenates once at the end.
    (Previously this re-allocated and copied a growing array on every chunk —
    O(n²) total copying for many chunks. Output is identical.)
    """
    parts = []
    for start in range(0, len(df), CHUNK_SIZE):
        chunk = df.iloc[start:start + CHUNK_SIZE]
        arr   = chunk[n_cols].to_numpy(dtype=np.float32)
        arr   = np.nan_to_num(arr, nan=-1.0)
        parts.append(_match_chunk(arr, cvi_nums))
    return np.concatenate(parts) if parts else np.empty(0, dtype=np.int32)


# ── Formatting ────────────────────────────────────────────────────────────────

def _count_str(counts: np.ndarray) -> str:
    return ",".join(str(int(k)) for k in sorted(np.unique(counts)))


def _breakdown_str(counts: np.ndarray, sc_set: set,
                   prefix_sel="S", prefix_unsel="U") -> tuple[str, str, str, str]:
    """
    Returns (sel_bd_str, unsel_bd_str, unsel_count_str, count_dist_dict_str).
    """
    unique = sorted(int(k) for k in np.unique(counts))
    sel_parts, unsel_parts = [], []
    for k in unique:
        n_k = int((counts == k).sum())
        if k in sc_set:
            sel_parts.append(f"{prefix_sel}{k}:{n_k}")
        else:
            unsel_parts.append(f"{prefix_unsel}{k}:{n_k}")
    unsel_counts = [k for k in unique if k not in sc_set]
    return (
        "  ".join(sel_parts)   or "No breakdown",
        "  ".join(unsel_parts) or "No breakdown",
        ",".join(str(k) for k in unsel_counts) or "No count",
        {f"S{k}": int((counts == k).sum()) for k in unique},
    )


# ── Stage helpers (extracted from run_matching's loop body) ───────────────────

def _compute_stage_present(
    idx: int,
    w_cols: list,
    carry_fwd: dict,
    prev_sel: pd.DataFrame,
    prev_unsel: pd.DataFrame,
    main_df: pd.DataFrame,
    cvi_df: pd.DataFrame,
    n_cols: list,
    M: int,
) -> dict:
    """
    Determine the present pool and CVI match counts for one stage.

    Returns a dict with: w, w_num, direction, present_df, present_label,
    present_count, raw_cvi, cvi_nums, empty_cvi.
    When empty_cvi is False, also: pres_counts, pres_count_str.
    """
    w     = w_cols[idx]
    w_num = int(w[1:])
    direction = carry_fwd.get(w, carry_fwd.get(f"w{w_num}", "U")).upper()

    if idx == 0:
        present_df    = main_df.copy().reset_index(drop=True)
        present_label = f"M:{M}"
    elif direction == "S":
        present_df    = prev_sel.reset_index(drop=True)
        present_label = f"S:{len(prev_sel)}"
    else:
        present_df    = prev_unsel.reset_index(drop=True)
        present_label = f"U:{len(prev_unsel)}"

    present_count = len(present_df)
    if present_label.startswith("U:"):
        present_label = f"U:{present_count}"
    elif present_label.startswith("S:") and not present_label.startswith("S:0"):
        present_label = f"S:{present_count}"

    raw_cvi  = _parse_cvi_col(cvi_df[w])
    cvi_nums = np.array(raw_cvi, dtype=np.float32)

    if not len(cvi_nums):
        return {
            "w": w, "w_num": w_num, "direction": direction,
            "present_df": present_df, "present_label": present_label,
            "present_count": present_count,
            "raw_cvi": raw_cvi, "cvi_nums": cvi_nums,
            "empty_cvi": True,
        }

    pres_counts    = _smart_match(present_df, n_cols, cvi_nums)
    pres_count_str = _count_str(pres_counts)

    return {
        "w": w, "w_num": w_num, "direction": direction,
        "present_df": present_df, "present_label": present_label,
        "present_count": present_count,
        "raw_cvi": raw_cvi, "cvi_nums": cvi_nums,
        "empty_cvi": False,
        "pres_counts": pres_counts, "pres_count_str": pres_count_str,
    }


def _apply_stage_sc(
    stage_info: dict,
    sc_set: set,
    sc_str: str,
    w: str,
    w_num: int,
    M: int,
    main_df: pd.DataFrame,
    main_count_map: dict,
    main_bd_map: dict,
    main_counts_map: dict,
    n_cols: list,
    small_enough: bool,
) -> dict:
    """
    Apply SC selection to the matched stage and build all output rows.

    Returns a dict with: fig9_row, breakdown_row, debug_row,
    sel_df, unsel_df, new_prev_sel, new_prev_unsel, exhausted.
    """
    present_df     = stage_info["present_df"]
    present_label  = stage_info["present_label"]
    present_count  = stage_info["present_count"]
    direction      = stage_info["direction"]
    raw_cvi        = stage_info["raw_cvi"]
    pres_counts    = stage_info["pres_counts"]
    pres_count_str = stage_info["pres_count_str"]

    sel_bd_str, unsel_bd_str, unsel_count_str, count_dist = \
        _breakdown_str(pres_counts, sc_set)

    sel_mask = np.isin(pres_counts, list(sc_set))
    sel_df   = present_df[sel_mask].reset_index(drop=True)
    unsel_df = present_df[~sel_mask].reset_index(drop=True)

    if len(sel_df) + len(unsel_df) != present_count:
        logging.warning(
            "[run_matching] %s: sel(%d) + unsel(%d) != present(%d) — row loss in mask",
            w, len(sel_df), len(unsel_df), present_count,
        )

    if small_enough and not sel_df.empty:
        sel_df = sel_df.copy()
        sel_df["Count"] = pres_counts[sel_mask]
    if small_enough and not unsel_df.empty:
        unsel_df = unsel_df.copy()
        unsel_df["Count"] = pres_counts[~sel_mask]

    fig9_row = {
        "Row":             f"Row {w_num}",
        "Main\nData":      f"M:{M}",
        "CVI":             w,
        "Dir":             direction,
        "Main\nCount":     main_count_map[w],
        "Main\nBreakdown": main_bd_map[w],
        "Present\nData":   present_label,
        "Present\nCount":  pres_count_str,
        "SC":              sc_str,
        "Selected":        f"S:{len(sel_df)}" if not sel_df.empty else "S:0",
        "Sel\nBreakdown":  sel_bd_str,
        "Unsel\nCount":    unsel_count_str,
        "Unselected":      f"U:{len(unsel_df)}" if not unsel_df.empty else "U:0",
        "Unsel\nBreakdown":unsel_bd_str,
    }

    breakdown_row = {**count_dist, "w_col": w}

    main_df_with_count = None
    if small_enough:
        mc_arr = main_counts_map.get(w, np.array([], dtype=np.int32))
        if len(mc_arr) == M:
            main_df_with_count = main_df.copy()
            main_df_with_count["Count"] = mc_arr

    debug_row = {
        "w":              w,
        "direction":      direction,
        "cvi_numbers":    raw_cvi,
        "cvi_set":        set(raw_cvi),
        "present_in":     present_count,
        "present_label":  present_label,
        "sc":             sorted(sc_set),
        "selected_n":     len(sel_df),
        "unselected_n":   len(unsel_df),
        "main_count_str": main_count_map[w],
        "main_bd_str":    main_bd_map[w],
        "main_counts":    main_counts_map[w],
        "pres_count_str": pres_count_str,
        "count_dist":     count_dist,
        "note":           "",
        "sel_df":         sel_df   if small_enough else None,
        "unsel_df":       unsel_df if small_enough else None,
        "main_df_wc":     main_df_with_count,
        "n_cols":         n_cols,
    }

    new_prev_sel   = sel_df.drop(columns=["Count"], errors="ignore")
    new_prev_unsel = unsel_df.drop(columns=["Count"], errors="ignore")
    exhausted      = present_df.empty or (sel_df.empty and unsel_df.empty)

    return {
        "fig9_row":       fig9_row,
        "breakdown_row":  breakdown_row,
        "debug_row":      debug_row,
        "sel_df":         sel_df,
        "unsel_df":       unsel_df,
        "new_prev_sel":   new_prev_sel,
        "new_prev_unsel": new_prev_unsel,
        "exhausted":      exhausted,
    }


# ── Pre-loop state preparation ────────────────────────────────────────────────

def _prepare_matching_state(
    main_df: pd.DataFrame,
    cvi_df: pd.DataFrame,
    main_path=None,
) -> "dict | None":
    """
    Extract pre-loop setup shared by run_matching and run_matching_step.

    Returns None when either input is empty (caller handles early return).
    Otherwise returns:
        {"n_cols", "w_cols", "M", "small_enough",
         "main_count_map", "main_bd_map", "main_counts_map"}
    """
    if main_df.empty or cvi_df.empty:
        return None

    # ── Detect number columns ──────────────────────────────────────────────
    _explicit_n = [c for c in main_df.columns if re.match(r'^n\d+$', c, re.I)]
    if _explicit_n:
        n_cols = sorted(
            _explicit_n,
            key=lambda x: int(re.sub(r'\D', '', x) or 0)
        )[:20]
    else:
        _META_BLOCKED = frozenset({
            "postcode", "draw_number", "draw_no", "draw", "length",
            "share_cost", "available_shares", "total_shares", "outlet_id",
            "syndicate_id", "row_number", "rownum",
        })
        _ncands = []
        for _c in main_df.columns:
            if _c.lower() in _META_BLOCKED:
                continue
            _s = pd.to_numeric(main_df[_c], errors="coerce")
            if _s.notna().mean() > 0.9 and _s.max() <= 99:
                _ncands.append(_c)
        n_cols = sorted(
            _ncands,
            key=lambda x: int(re.sub(r'\D', '', x) or 0)
        )[:20]

    w_cols = sorted(
        [c for c in cvi_df.columns if re.match(r'^w\d+$', c)],
        key=lambda x: int(x[1:])
    )

    M            = len(main_df)
    small_enough = (M <= DISPLAY_THRESHOLD)

    main_count_map:  dict[str, str]        = {}
    main_bd_map:     dict[str, str]        = {}
    main_counts_map: dict[str, np.ndarray] = {}

    # ── Decide whether the pre-pass may use DuckDB ────────────────────────
    _duck_path = None
    try:
        if main_path is not None:
            _p = Path(main_path)
            _contiguous_n = (
                bool(n_cols)
                and all(c.lower() == f"n{i}" for i, c in enumerate(n_cols, 1))
            )
            if (_p.exists() and _p.suffix.lower() == ".csv"
                    and _duckdb_available()
                    and _p.stat().st_size > DUCKDB_THRESHOLD
                    and _contiguous_n
                    and _count_csv_rows(_p) == M):
                _duck_path = _p
    except Exception:
        _duck_path = None

    for w in w_cols:
        raw = _parse_cvi_col(cvi_df[w])
        if raw:
            mc = None
            if _duck_path is not None:
                duck_mc = _match_duckdb(_duck_path, raw, len(n_cols))
                if duck_mc.shape[0] == M:
                    mc = duck_mc
            if mc is None:
                mc = _count_matches(
                    main_df, n_cols, np.array(raw, dtype=np.float32))
            main_counts_map[w] = mc
            main_count_map[w]  = _count_str(mc)
            unique_k = sorted(int(k) for k in np.unique(mc))
            main_bd_map[w] = "  ".join(
                f"S{k}:{int((mc==k).sum())}" for k in unique_k
            )
        else:
            main_count_map[w]  = "—"
            main_bd_map[w]     = "—"
            main_counts_map[w] = np.array([], dtype=np.int32)

    return {
        "n_cols":          n_cols,
        "w_cols":          w_cols,
        "M":               M,
        "small_enough":    small_enough,
        "main_count_map":  main_count_map,
        "main_bd_map":     main_bd_map,
        "main_counts_map": main_counts_map,
    }


def _fill_exhausted_stages(
    w_cols: list,
    start_idx: int,
    M: int,
    carry_fwd: dict,
    main_count_map: dict,
    main_bd_map: dict,
    sc_dict: "dict | None" = None,
    *,
    n_cols: "list | None" = None,
) -> "tuple[list, list]":
    """
    Build fig9_rows and debug_rows for stages from start_idx onward when the
    present pool is exhausted.  sc_dict defaults to {} so "SC" is always "—"
    when omitted (run_matching_step has no future SCs).  run_matching passes
    its real sc_dict to preserve current behaviour exactly.
    """
    if sc_dict is None:
        sc_dict = {}
    if n_cols is None:
        n_cols = []

    fig9_rows_extra:  list = []
    debug_rows_extra: list = []

    for rw in w_cols[start_idx:]:
        rw_num = int(rw[1:])
        fig9_rows_extra.append({
            "Row": f"Row {rw_num}", "Main\nData": f"M:{M}",
            "CVI": rw, "Dir": carry_fwd.get(rw, "U"),
            "Main\nCount": main_count_map.get(rw, "—"),
            "Main\nBreakdown": main_bd_map.get(rw, "—"),
            "Present\nData": "U:0", "Present\nCount": "—",
            "SC": sc_dict.get(rw, "—"), "Selected": "S:0",
            "Sel\nBreakdown": "—", "Unsel\nCount": "—",
            "Unselected": "U:0", "Unsel\nBreakdown": "—",
        })
        debug_rows_extra.append({
            "w": rw, "direction": carry_fwd.get(rw, "U"),
            "cvi_numbers": [], "cvi_set": set(),
            "present_in": 0, "present_label": "U:0",
            "sc": [], "selected_n": 0, "unselected_n": 0,
            "main_count_str": main_count_map.get(rw, "—"),
            "main_bd_str":    main_bd_map.get(rw, "—"),
            "main_counts":    np.array([], dtype=np.int32),
            "pres_count_str": "—", "count_dist": {},
            "note": "No present data — exhausted",
            "sel_df": None, "unsel_df": None,
            "main_df_wc": None, "n_cols": n_cols,
        })

    return fig9_rows_extra, debug_rows_extra


# ── Sequential matching engine ────────────────────────────────────────────────

def run_matching(main_df: pd.DataFrame,
                 cvi_df:  pd.DataFrame,
                 sc_dict: dict,
                 carry_fwd: dict,
                 main_path=None) -> dict:
    """
    Sequential matching engine — corrected carry-forward logic.

    carry_fwd[w] = "U" or "S"  (default "U" for any missing key)
    Meaning of toggle at Row N:
        "U" → Row N's present = Row N-1's UNSELECTED
        "S" → Row N's present = Row N-1's SELECTED

    Main Count: pre-computed once against ORIGINAL main_df for every w-column.
                Never recalculated regardless of carry-forward state.

    Memory: if M > DISPLAY_THRESHOLD, per-row DataFrames are NOT stored —
            only count distributions are kept. Final stage data always stored.

    main_path (optional): path to the CSV that `main_df` was loaded from. When
        supplied AND it is a large CSV AND DuckDB is installed AND it is safe
        (file row-count == M and the n-columns are a contiguous n1…nN block),
        the heavy *main-count pre-pass* (one full-M scan per w-column) is run in
        DuckDB instead of pandas. If DuckDB returns an unexpected length for any
        column, that column silently falls back to the pandas path, so results
        are always identical to the pure-pandas engine. Passing None (the
        default) keeps the original all-pandas behavior.

        NOTE on scope: only the pre-pass uses DuckDB. The staged carry-forward
        matching still runs in memory on `main_df`, because each stage filters a
        shrinking pool of rows (selected vs unselected) — that is row-level and
        stateful, not a single SQL aggregate. So this lowers the cost of the
        most expensive *uniform* passes but does NOT remove the need to hold
        `main_df` in RAM. Fully streaming the staged engine is a larger,
        separate change.
    """
    state = _prepare_matching_state(main_df, cvi_df, main_path)
    if state is None:
        return {"selected": pd.DataFrame(), "unselected": pd.DataFrame(),
                "fig9_table": pd.DataFrame(), "breakdown": pd.DataFrame(),
                "debug_rows": []}

    n_cols          = state["n_cols"]
    w_cols          = state["w_cols"]
    M               = state["M"]
    small_enough    = state["small_enough"]
    main_count_map  = state["main_count_map"]
    main_bd_map     = state["main_bd_map"]
    main_counts_map = state["main_counts_map"]

    # ── Stage state ────────────────────────────────────────────────────────
    prev_sel   = pd.DataFrame()
    prev_unsel = main_df.copy().reset_index(drop=True)

    fig9_rows      = []
    breakdown_rows = []
    debug_rows     = []

    final_sel   = pd.DataFrame()
    final_unsel = prev_unsel.copy()

    for idx, w in enumerate(w_cols):
        w_num   = int(w[1:])
        sc_this = sc_dict.get(w, sc_dict.get(str(w_num), []))
        if isinstance(sc_this, (int, float)):
            sc_this = [int(sc_this)]
        elif isinstance(sc_this, str):
            sc_this = [int(x.strip()) for x in sc_this.split(",")
                       if x.strip().lstrip('-').isdigit()]
        sc_set = set(sc_this)
        sc_str = ",".join(str(s) for s in sorted(sc_set)) if sc_set else "—"

        stage_info = _compute_stage_present(
            idx, w_cols, carry_fwd, prev_sel, prev_unsel,
            main_df, cvi_df, n_cols, M)
        direction = stage_info["direction"]

        # ── Empty CVI column ──────────────────────────────────────────
        if stage_info["empty_cvi"]:
            present_df    = stage_info["present_df"]
            present_label = stage_info["present_label"]
            present_count = stage_info["present_count"]
            fig9_rows.append({
                "Row":             f"Row {w_num}",
                "Main\nData":      f"M:{M}",
                "CVI":             w,
                "Dir":             direction,
                "Main\nCount":     main_count_map[w],
                "Main\nBreakdown": main_bd_map[w],
                "Present\nData":   present_label,
                "Present\nCount":  "— No CVI",
                "SC":              sc_str,
                "Selected":        "S:0",
                "Sel\nBreakdown":  "—",
                "Unsel\nCount":    "—",
                "Unselected":      f"U:{present_count} (fwd)",
                "Unsel\nBreakdown":"—",
            })
            debug_rows.append({
                "w": w, "direction": direction,
                "cvi_numbers": [], "cvi_set": set(),
                "present_in": present_count, "present_label": present_label,
                "sc": list(sc_set), "selected_n": 0,
                "unselected_n": present_count,
                "main_count_str": main_count_map[w],
                "main_bd_str":    main_bd_map[w],
                "main_counts":    main_counts_map[w],
                "pres_count_str": "—", "count_dist": {},
                "note": "No CVI data — all carry forward",
                "sel_df": None,
                "unsel_df": present_df.copy() if small_enough else None,
                "n_cols": n_cols,
            })
            prev_sel   = pd.DataFrame()
            prev_unsel = present_df.copy()
            final_sel   = pd.DataFrame()
            final_unsel = present_df.copy()
            continue

        # ── Apply SC and build output ─────────────────────────────────
        result = _apply_stage_sc(
            stage_info, sc_set, sc_str, w, w_num, M,
            main_df, main_count_map, main_bd_map, main_counts_map,
            n_cols, small_enough)

        fig9_rows.append(result["fig9_row"])
        breakdown_rows.append(result["breakdown_row"])
        debug_rows.append(result["debug_row"])

        prev_sel    = result["new_prev_sel"]
        prev_unsel  = result["new_prev_unsel"]
        final_sel   = result["sel_df"]
        final_unsel = result["unsel_df"]

        # ── If present exhausted, fill remaining rows ─────────────────
        if result["exhausted"]:
            fig9_extra, debug_extra = _fill_exhausted_stages(
                w_cols, idx + 1, M, carry_fwd,
                main_count_map, main_bd_map, sc_dict,
                n_cols=n_cols)
            fig9_rows  += fig9_extra
            debug_rows += debug_extra
            break

    _final_total = len(final_sel) + len(final_unsel)
    if _final_total != M:
        logging.warning(
            "[run_matching] final: selected(%d) + unselected(%d) = %d, original M=%d%s",
            len(final_sel), len(final_unsel), _final_total, M,
            " (expected for multi-stage carry-forward)" if len(w_cols) > 1 else "",
        )

    return {
        "selected":    final_sel,
        "unselected":  final_unsel,
        "fig9_table":  pd.DataFrame(fig9_rows),
        "breakdown":   pd.DataFrame(breakdown_rows).fillna(0),
        "debug_rows":  debug_rows,
        "n_cols":      n_cols,
        "small_enough": small_enough,
    }


# ── Step-wise matching engine (SC Available: NO) ─────────────────────────────

def run_matching_step(
    resume_state,
    sc_for_stage=None,
    *,
    main_df: pd.DataFrame = None,
    cvi_df:  pd.DataFrame = None,
    carry_fwd: dict = None,
    main_path=None,
) -> dict:
    """
    Step-wise version of run_matching for interactive "SC Available: NO" mode.

    Call 1 — Setup (resume_state=None):
        Pass main_df, cvi_df, carry_fwd (and optionally main_path).
        Returns {"paused": True, "awaiting_sc_for_stage": idx, "w": w,
                 "count_dist": {...}, "resume_state": {...}}
        or {"paused": False, ...} when every stage has empty CVI.

    Call 2+ — Resume (resume_state + sc_for_stage given):
        main_df/cvi_df/carry_fwd kwargs are ignored; state comes from
        resume_state.  Applies the SC to the cached stage, then auto-advances
        through any empty-CVI stages and pauses again (or returns final result
        if the run completes or exhausts).

    Final result shape (paused=False) is a superset of run_matching's return:
        {"paused": False, "selected", "unselected", "fig9_table",
         "breakdown", "debug_rows", "n_cols", "small_enough"}
    """
    _EMPTY = {
        "paused":       False,
        "selected":     pd.DataFrame(),
        "unselected":   pd.DataFrame(),
        "fig9_table":   pd.DataFrame(),
        "breakdown":    pd.DataFrame(),
        "debug_rows":   [],
    }

    # ── Setup ─────────────────────────────────────────────────────────────
    if resume_state is None:
        if carry_fwd is None:
            carry_fwd = {}
        state = _prepare_matching_state(main_df, cvi_df, main_path)
        if state is None:
            return _EMPTY

        n_cols          = state["n_cols"]
        w_cols          = state["w_cols"]
        M               = state["M"]
        small_enough    = state["small_enough"]
        main_count_map  = state["main_count_map"]
        main_bd_map     = state["main_bd_map"]
        main_counts_map = state["main_counts_map"]

        prev_sel       = pd.DataFrame()
        prev_unsel     = main_df.copy().reset_index(drop=True)
        stage_idx      = 0
        fig9_rows:     list = []
        debug_rows:    list = []
        breakdown_rows: list = []
        final_sel      = pd.DataFrame()
        final_unsel    = prev_unsel.copy()

    # ── Resume ────────────────────────────────────────────────────────────
    else:
        rs = resume_state
        stage_idx       = rs["stage_idx"]
        prev_sel        = rs["prev_sel"]
        prev_unsel      = rs["prev_unsel"]
        n_cols          = rs["n_cols"]
        w_cols          = rs["w_cols"]
        M               = rs["M"]
        small_enough    = rs["small_enough"]
        main_count_map  = rs["main_count_map"]
        main_bd_map     = rs["main_bd_map"]
        main_counts_map = rs["main_counts_map"]
        main_df         = rs["main_df"]
        cvi_df          = rs["cvi_df"]
        carry_fwd       = rs["carry_fwd"]
        fig9_rows       = rs["fig9_rows"]
        debug_rows      = rs["debug_rows"]
        breakdown_rows  = rs["breakdown_rows"]
        final_sel       = rs["final_sel"]
        final_unsel     = rs["final_unsel"]
        cached_stage_info = rs["cached_stage_info"]

        w     = cached_stage_info["w"]
        w_num = cached_stage_info["w_num"]

        # Normalise sc_for_stage (same coercion as run_matching's sc_this block)
        sc_this = sc_for_stage if sc_for_stage is not None else []
        if isinstance(sc_this, (int, float)):
            sc_this = [int(sc_this)]
        elif isinstance(sc_this, str):
            sc_this = [int(x.strip()) for x in sc_this.split(",")
                       if x.strip().lstrip('-').isdigit()]
        sc_set = set(sc_this)
        sc_str = ",".join(str(s) for s in sorted(sc_set)) if sc_set else "—"

        result = _apply_stage_sc(
            cached_stage_info, sc_set, sc_str, w, w_num, M,
            main_df, main_count_map, main_bd_map, main_counts_map,
            n_cols, small_enough)

        fig9_rows.append(result["fig9_row"])
        breakdown_rows.append(result["breakdown_row"])
        debug_rows.append(result["debug_row"])

        prev_sel    = result["new_prev_sel"]
        prev_unsel  = result["new_prev_unsel"]
        final_sel   = result["sel_df"]
        final_unsel = result["unsel_df"]

        if result["exhausted"]:
            fig9_extra, debug_extra = _fill_exhausted_stages(
                w_cols, stage_idx + 1, M, carry_fwd,
                main_count_map, main_bd_map, n_cols=n_cols)
            fig9_rows  += fig9_extra
            debug_rows += debug_extra
            return {
                "paused":       False,
                "selected":     final_sel,
                "unselected":   final_unsel,
                "fig9_table":   pd.DataFrame(fig9_rows),
                "breakdown":    pd.DataFrame(breakdown_rows).fillna(0),
                "debug_rows":   debug_rows,
                "n_cols":       n_cols,
                "small_enough": small_enough,
            }

        stage_idx += 1

    # ── PHASE A: advance through empty-CVI stages, pause at first real stage ─
    while stage_idx < len(w_cols):
        stage_info = _compute_stage_present(
            stage_idx, w_cols, carry_fwd,
            prev_sel, prev_unsel,
            main_df, cvi_df, n_cols, M)

        w         = stage_info["w"]
        w_num     = stage_info["w_num"]
        direction = stage_info["direction"]

        if stage_info["empty_cvi"]:
            present_df    = stage_info["present_df"]
            present_label = stage_info["present_label"]
            present_count = stage_info["present_count"]
            fig9_rows.append({
                "Row":             f"Row {w_num}",
                "Main\nData":      f"M:{M}",
                "CVI":             w,
                "Dir":             direction,
                "Main\nCount":     main_count_map[w],
                "Main\nBreakdown": main_bd_map[w],
                "Present\nData":   present_label,
                "Present\nCount":  "— No CVI",
                "SC":              "—",
                "Selected":        "S:0",
                "Sel\nBreakdown":  "—",
                "Unsel\nCount":    "—",
                "Unselected":      f"U:{present_count} (fwd)",
                "Unsel\nBreakdown":"—",
            })
            debug_rows.append({
                "w": w, "direction": direction,
                "cvi_numbers": [], "cvi_set": set(),
                "present_in": present_count, "present_label": present_label,
                "sc": [], "selected_n": 0,
                "unselected_n": present_count,
                "main_count_str": main_count_map[w],
                "main_bd_str":    main_bd_map[w],
                "main_counts":    main_counts_map[w],
                "pres_count_str": "—", "count_dist": {},
                "note": "No CVI data — all carry forward",
                "sel_df": None,
                "unsel_df": present_df.copy() if small_enough else None,
                "n_cols": n_cols,
            })
            prev_sel    = pd.DataFrame()
            prev_unsel  = present_df.copy()
            final_sel   = pd.DataFrame()
            final_unsel = present_df.copy()
            stage_idx  += 1
            continue

        # Non-empty CVI — compute count_dist and pause for SC input
        _, _, _, count_dist = _breakdown_str(stage_info["pres_counts"], set())
        return {
            "paused":                True,
            "awaiting_sc_for_stage": stage_idx,
            "w":                     w,
            "count_dist":            count_dist,
            "resume_state": {
                "stage_idx":        stage_idx,
                "prev_sel":         prev_sel,
                "prev_unsel":       prev_unsel,
                "main_count_map":   main_count_map,
                "main_bd_map":      main_bd_map,
                "main_counts_map":  main_counts_map,
                "n_cols":           n_cols,
                "w_cols":           w_cols,
                "M":                M,
                "small_enough":     small_enough,
                "main_df":          main_df,
                "cvi_df":           cvi_df,
                "carry_fwd":        carry_fwd,
                "fig9_rows":        fig9_rows,
                "debug_rows":       debug_rows,
                "breakdown_rows":   breakdown_rows,
                "final_sel":        final_sel,
                "final_unsel":      final_unsel,
                "cached_stage_info": stage_info,
            },
        }

    # Every remaining stage was empty-CVI (or w_cols was empty) — no fill needed
    return {
        "paused":       False,
        "selected":     final_sel,
        "unselected":   final_unsel,
        "fig9_table":   pd.DataFrame(fig9_rows),
        "breakdown":    pd.DataFrame(breakdown_rows).fillna(0),
        "debug_rows":   debug_rows,
        "n_cols":       n_cols,
        "small_enough": small_enough,
    }


# ── Multiprocessing worker ────────────────────────────────────────────────────

def _parallel_worker(args: tuple) -> dict:
    """
    Standalone worker — no Streamlit state.
    Loads CVI, SC, CF from disk; runs matching; saves results.
    Returns summary dict.
    """
    import pandas as pd, numpy as np, re, json
    from pathlib import Path

    (formula_name, cvi_path, main_data_path,
     sc_path, cluster_id, cluster_label,
     lotto_type, draw_no, draw_date,
     output_dir) = args

    result = {
        "formula":    formula_name,
        "status":     "error",
        "selected_n": 0,
        "unselected_n": 0,
        "error":      "",
    }

    try:
        cvi_df  = pd.read_csv(cvi_path)
        main_df = pd.read_csv(main_data_path)

        for col in main_df.columns:
            main_df[col] = pd.to_numeric(main_df[col], errors="coerce")

        sc_dict = {}
        if sc_path and Path(sc_path).exists():
            sc_df = pd.read_csv(sc_path)
            if "w" in sc_df.columns and "Selected Count" in sc_df.columns:
                for _, row in sc_df.iterrows():
                    k = str(row["w"]).strip()
                    key = k if k.startswith("w") else f"w{k}"
                    sc_dict[key] = [int(x.strip()) for x in
                                    str(row["Selected Count"]).split(",")
                                    if x.strip().isdigit()]

        w_cols = sorted([c for c in cvi_df.columns
                         if re.match(r'^w\d+$', c)], key=lambda x: int(x[1:]))
        carry_fwd = {w: "U" for w in w_cols}

        # ── Detect n_cols (mirrors run_matching heuristic) ────────────────
        _explicit_n = [c for c in main_df.columns
                       if re.match(r'^n\d+$', c, re.I)]
        if _explicit_n:
            n_cols = sorted(
                _explicit_n,
                key=lambda x: int(re.sub(r'\D', '', x) or 0)
            )[:20]
        else:
            _META_BLOCKED = frozenset({
                "postcode", "draw_number", "draw_no", "draw", "length",
                "share_cost", "available_shares", "total_shares", "outlet_id",
                "syndicate_id", "row_number", "rownum",
            })
            _ncands = []
            for _c in main_df.columns:
                if _c.lower() in _META_BLOCKED:
                    continue
                _s = pd.to_numeric(main_df[_c], errors="coerce")
                if _s.notna().mean() > 0.9 and _s.max() <= 99:
                    _ncands.append(_c)
            n_cols = sorted(
                _ncands,
                key=lambda x: int(re.sub(r'\D', '', x) or 0)
            )[:20]

        M = len(main_df)
        prev_sel = pd.DataFrame()
        prev_unsel = main_df.copy().reset_index(drop=True)
        final_sel = pd.DataFrame()
        final_unsel = prev_unsel.copy()

        CSIZE = 500_000

        def parse_col(series):
            r = []
            for v in series.dropna():
                try:
                    n = float(str(v).strip())
                    if not pd.isna(n) and n >= 1:
                        r.append(int(round(n)))
                except Exception as _e:
                    logging.warning(
                        "parse_series: could not convert value %r to float: %s", v, _e)
            return r

        def match_chunk(arr, cvi_arr):
            counts = np.zeros(arr.shape[0], dtype=np.int32)
            for j in range(arr.shape[1]):
                counts += np.isin(arr[:, j], cvi_arr).astype(np.int32)
            return counts

        for idx, w in enumerate(w_cols):
            direction = carry_fwd.get(w, "U").upper()
            if idx == 0:
                present = main_df.copy().reset_index(drop=True)
            elif direction == "S":
                present = prev_sel.reset_index(drop=True)
            else:
                present = prev_unsel.reset_index(drop=True)

            raw_cvi = parse_col(cvi_df[w])
            if not raw_cvi:
                prev_sel    = pd.DataFrame()
                prev_unsel  = present.copy()
                final_sel   = pd.DataFrame()
                final_unsel = present.copy()
                continue

            cvi_arr = np.array(raw_cvi, dtype=np.float32)
            sc_this = sc_dict.get(w, [])
            sc_set  = set(sc_this)

            if present.empty:
                break

            all_counts = np.empty(0, dtype=np.int32)
            for start in range(0, len(present), CSIZE):
                chunk = present.iloc[start:start + CSIZE]
                arr   = chunk[n_cols].to_numpy(dtype=np.float32)
                arr   = np.nan_to_num(arr, nan=-1.0)
                all_counts = np.concatenate(
                    [all_counts, match_chunk(arr, cvi_arr)])

            sel_mask = np.isin(all_counts, list(sc_set))
            sel_df   = present[sel_mask].reset_index(drop=True)
            unsel_df = present[~sel_mask].reset_index(drop=True)

            if len(sel_df) + len(unsel_df) != len(present):
                logging.warning(
                    "[parallel_worker] %s: sel(%d) + unsel(%d) != present(%d)",
                    w, len(sel_df), len(unsel_df), len(present),
                )

            prev_sel   = sel_df
            prev_unsel = unsel_df
            final_sel   = sel_df
            final_unsel = unsel_df

        out    = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        prefix = f"{cluster_label}_{lotto_type}_{draw_no}_{draw_date}"

        sel_path   = out / f"{prefix}_{formula_name}_selected.csv"
        unsel_path = out / f"{prefix}_{formula_name}_unselected.csv"
        final_sel.to_csv(sel_path,   index=False)
        final_unsel.to_csv(unsel_path, index=False)

        result["status"]       = "complete"
        result["selected_n"]   = len(final_sel)
        result["unselected_n"] = len(final_unsel)
        result["sel_path"]     = str(sel_path)
        result["unsel_path"]   = str(unsel_path)

    except Exception as ex:
        result["error"] = str(ex)

    return result
