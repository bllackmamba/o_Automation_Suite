"""
syndicate_core/collation.py — Collation display helpers

Extracted from masterapp.py (6. COLLATION ENGINE).
Contains _to_w_rows, the universal variable→row-oriented transformer used by
the collation engine to normalise B, D, R, Ep, So, and Sp before display/export.

No streamlit dependency — safe to import in tests and CLI scripts.
"""

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "_to_w_rows",
    "_compute_sc_block",
    "_sc_distribution_table",
    "_save_sc_block",
    "_load_sc_blocks",
    "_run_sc_auto",
]

# Carry-forward flags used by _run_sc_auto callers
_IS_DIRECT = {"D": True}
_FORCE_COL = {"Sp": True}

# Metadata column names found in D / direct DataFrames.  Any DataFrame that
# contains at least one of these is treated as a D-style (row-oriented) source.
_D_META = frozenset({
    "syndicate_id", "syndicate_name", "game", "games", "pb",
    "draw_number", "draw_numbers", "outlet_id", "outlet_name",
    "postcode", "state", "share_cost", "available_shares",
    "total_shares", "address", "suburb",
})


def _to_w_rows(df: pd.DataFrame, is_direct: bool = False,
               force_column_oriented: bool = False) -> pd.DataFrame:
    """Return a variable as ROW-oriented w-sets with a leading Set_Label column.

    Returns a DataFrame: first column = "Set_Label" (original column name,
    Syndicate_ID for D, or "w" value for B); remaining columns = integer-indexed
    value columns 0, 1, 2, … that the caller renames to w1, w2, ….

    Three routing paths:
      • B (row-oriented, "w" label + pos_N columns):
          Set_Label = "w" column; data = non-empty pos_N columns. No transpose.
      • D (row-oriented, metadata + wN columns, or is_direct=True):
          Set_Label = Syndicate_ID; data = w-pattern columns. No transpose.
      • R/Ep/So/Sp (column-oriented, force_column_oriented=True for Sp):
          Set_Label = original column name preserved via reset_index() (not drop=True).
          Full transpose — never pre-filter to wcols, because Sp's split-key
          names (w10, w11, w20 …) match ^w\\d+$ and would silently drop 100/112 sets.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    wcols    = [c for c in df.columns if re.match(r'^w\d+$', str(c), re.I)]
    pos_cols = [c for c in df.columns if re.match(r'^pos_\d+$', str(c), re.I)]
    has_d_meta  = any(str(c).strip().lower() in _D_META for c in df.columns)
    w_label_col = next((c for c in df.columns
                        if str(c).strip().lower() == "w"), None)
    is_b_style  = w_label_col is not None and len(pos_cols) > 0
    has_ep_style = "sub_label" in df.columns and "pair" in df.columns
    has_r_style  = "combo" in df.columns

    if not force_column_oriented and has_r_style:
        # R row-oriented: combo = Set_Label; integer-named cols = data positions.
        int_cols = [c for c in df.columns
                    if isinstance(c, int)
                    or (isinstance(c, str) and re.match(r'^\d+$', c))]
        label = df["combo"].reset_index(drop=True)
        sub   = df[int_cols].reset_index(drop=True)
        out   = sub.copy()
        out.insert(0, "Set_Label", label)

    elif not force_column_oriented and has_ep_style:
        # Ep row-oriented: sub_label = Set_Label; integer-named cols = data positions.
        int_cols = [c for c in df.columns
                    if isinstance(c, int)
                    or (isinstance(c, str) and re.match(r'^\d+$', c))]
        label = df["sub_label"].reset_index(drop=True)
        sub   = df[int_cols].reset_index(drop=True)
        out   = sub.copy()
        out.insert(0, "Set_Label", label)

    elif not force_column_oriented and is_b_style:
        # B path: row-oriented — "w" column = Set_Label, pos_N columns = data.
        # Drop pos columns that are entirely NaN (trailing empty positions).
        live_pos = [c for c in pos_cols if df[c].notna().any()]
        label = df[w_label_col].reset_index(drop=True)
        sub   = df[live_pos].reset_index(drop=True)
        out   = sub.copy()
        out.insert(0, "Set_Label", label)

    elif not force_column_oriented and (is_direct or has_d_meta):
        # D path: row-oriented — Syndicate_ID = Set_Label, w-columns = data.
        sid_col = next((c for c in df.columns
                        if str(c).strip().lower() == "syndicate_id"), None)
        sub   = df[wcols].reset_index(drop=True) if wcols else df.reset_index(drop=True)
        label = (df[sid_col].reset_index(drop=True) if sid_col
                 else pd.Series([pd.NA] * len(sub), dtype=object))
        out   = sub.copy()
        out.insert(0, "Set_Label", label)

    else:
        # Column-oriented path (R/Ep/So, and Sp via force_column_oriented).
        # reset_index() not drop=True — preserves original column names as Set_Label.
        t   = df.T.reset_index()
        out = t.rename(columns={t.columns[0]: "Set_Label"})

    val_cols = [c for c in out.columns if c != "Set_Label"]
    out[val_cols] = out[val_cols].apply(pd.to_numeric, errors="coerce")
    out = out.dropna(subset=val_cols, how="all").reset_index(drop=True)
    return out


# ── Decentralized Selected Counts ─────────────────────────────────────────────

def _compute_sc_block(
    var_name: str,
    var_df: pd.DataFrame,
    main_df: pd.DataFrame,
    n_cols: list,
    is_direct: bool = False,
    force_column_oriented: bool = False,
) -> dict:
    """Compute per-position count distributions for one variable block.

    Returns {w1: np.ndarray, w2: np.ndarray, ..., "_meta": {...}} or {}
    on any error. Each ndarray has length len(main_df) — how many n-column
    values in each main_df row matched the CVI values at that position.
    """
    if var_df is None or (hasattr(var_df, "empty") and var_df.empty):
        logging.warning("_compute_sc_block [%s]: var_df is empty — skipping", var_name)
        return {}
    if main_df is None or (hasattr(main_df, "empty") and main_df.empty):
        logging.warning("_compute_sc_block [%s]: main_df is empty — skipping", var_name)
        return {}
    if not n_cols:
        logging.warning("_compute_sc_block [%s]: n_cols is empty — skipping", var_name)
        return {}

    try:
        rows = _to_w_rows(var_df, is_direct=is_direct,
                          force_column_oriented=force_column_oriented)
    except Exception as ex:
        logging.warning("_compute_sc_block [%s]: _to_w_rows failed: %s", var_name, ex)
        return {}

    if rows is None or rows.empty:
        logging.warning("_compute_sc_block [%s]: _to_w_rows returned empty", var_name)
        return {}

    val_cols = [c for c in rows.columns if c != "Set_Label"]
    rename_map = {c: f"w{i + 1}" for i, c in enumerate(val_cols)}
    rows = rows.rename(columns=rename_map)
    w_positions = [f"w{i + 1}" for i in range(len(val_cols))]

    # Local import to avoid circular dependency (matching imports nothing from collation).
    from syndicate_core.matching import _count_matches

    result: dict = {}
    for pos in w_positions:
        raw = rows[pos].dropna()
        cvi_series = pd.to_numeric(raw, errors="coerce").dropna()
        if cvi_series.empty:
            continue
        cvi_arr = cvi_series.to_numpy(dtype=np.float32)
        result[pos] = _count_matches(main_df, n_cols, cvi_arr)

    if not result:
        logging.warning("_compute_sc_block [%s]: all positions empty", var_name)
        return {}

    result["_meta"] = {
        "var_name":    var_name,
        "n_cvi_rows":  len(rows),
        "n_positions": len(val_cols),
        "n_main_rows": len(main_df),
    }
    return result


def _sc_distribution_table(counts_dict: dict) -> pd.DataFrame:
    """Convert _compute_sc_block output to a human-readable distribution table.

    Columns: position | count_value | n_main_rows | pct_main
    One row per (position, count_value) pair.
    """
    meta = counts_dict.get("_meta", {})
    n_main = meta.get("n_main_rows", 0)
    rows = []
    for pos, counts in counts_dict.items():
        if pos == "_meta":
            continue
        if not isinstance(counts, np.ndarray):
            continue
        unique, freq = np.unique(counts, return_counts=True)
        for val, cnt in zip(unique, freq):
            rows.append({
                "position":    pos,
                "count_value": int(val),
                "n_main_rows": int(cnt),
                "pct_main":    round(100.0 * cnt / n_main, 2) if n_main else 0.0,
            })
    if not rows:
        return pd.DataFrame(
            columns=["position", "count_value", "n_main_rows", "pct_main"])
    return pd.DataFrame(rows)


def _save_sc_block(
    var_name: str,
    game_key: str,
    sc_thresholds: dict,
    gdirs: dict,
) -> Path:
    """Write SC_{VAR}_{gk}.csv to gdirs["Selected_Counts"].

    sc_thresholds: {w1: [5,6], w2: [5], ...} — variable-relative positions.
    Returns the path written. Raises on write failure.
    """
    folder: Path = Path(gdirs["Selected_Counts"])
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for k, v in sc_thresholds.items():
        wkey = k if str(k).startswith("w") else f"w{k}"
        sc_str = (",".join(str(x) for x in v)
                  if isinstance(v, (list, tuple)) else str(v))
        rows.append({"w": wkey, "Selected Count": sc_str})
    df = pd.DataFrame(rows)
    path = folder / f"SC_{var_name}_{game_key}.csv"
    df.to_csv(path, index=False)
    return path


def _load_sc_blocks(
    variables: list,
    game_key: str,
    gdirs: dict,
) -> dict:
    """Load per-variable SC files and merge into a single sc_dict.

    Reads SC_{VAR}_{gk}.csv for each variable in `variables`. Missing or
    malformed files are skipped with a debug/warning log. Last-write-wins
    per relative position when multiple variables share the same key.
    Returns {} if no SC files found.
    """
    sc_folder = gdirs.get("Selected_Counts")
    if sc_folder is None:
        return {}
    sc_folder = Path(sc_folder)
    sc_merged: dict = {}
    for var in variables:
        path = sc_folder / f"SC_{var}_{game_key}.csv"
        if not path.exists():
            logging.debug("_load_sc_blocks: %s not found, skipping", path)
            continue
        try:
            df = pd.read_csv(path)
        except Exception as ex:
            logging.warning("_load_sc_blocks: could not read %s: %s", path, ex)
            continue
        if "w" not in df.columns or "Selected Count" not in df.columns:
            logging.warning("_load_sc_blocks: %s missing required columns, skipping", path)
            continue
        if df.empty:
            logging.warning("_load_sc_blocks: %s is empty, skipping", path)
            continue
        for _, row in df.iterrows():
            k = str(row["w"]).strip()
            wkey = k if k.startswith("w") else f"w{k}"
            vals = [int(x.strip()) for x in str(row["Selected Count"]).split(",")
                    if x.strip().isdigit()]
            if vals:
                sc_merged[wkey] = vals   # last-write-wins
    return sc_merged


def _run_sc_auto(
    var_order: list,
    var_map: dict,
    main_df: pd.DataFrame,
    n_cols: list,
    game_key: str,
    gdirs: dict,
    is_direct_map: dict = None,
    force_col_map: dict = None,
) -> dict:
    """Run SC computation for all variables sequentially.

    Returns per-variable status dict:
        {"B": {"status": "ok", "distributions": {...}, "path": None}, ...}
    "path" is None — thresholds are picked interactively; call _save_sc_block
    to write a file once the user has chosen them.
    """
    if is_direct_map is None:
        is_direct_map = {}
    if force_col_map is None:
        force_col_map = {}
    results: dict = {}
    for var in var_order:
        var_df = var_map.get(var)
        if var_df is None or (hasattr(var_df, "empty") and var_df.empty):
            results[var] = {"status": "skipped", "reason": "var_df empty"}
            continue
        if main_df is None or (hasattr(main_df, "empty") and main_df.empty):
            results[var] = {"status": "skipped", "reason": "main_df empty"}
            continue
        try:
            counts_dict = _compute_sc_block(
                var, var_df, main_df, n_cols,
                is_direct=is_direct_map.get(var, False),
                force_column_oriented=force_col_map.get(var, False),
            )
        except Exception as ex:
            logging.warning("_run_sc_auto [%s]: error: %s", var, ex)
            results[var] = {"status": "error", "reason": str(ex)}
            continue
        if not counts_dict:
            results[var] = {"status": "skipped",
                            "reason": "_compute_sc_block returned empty"}
            continue
        results[var] = {"status": "ok", "distributions": counts_dict, "path": None}
    return results
