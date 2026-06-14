"""
syndicate_core/collation.py — Collation display helpers

Extracted from masterapp.py (6. COLLATION ENGINE).
Contains _to_w_rows, the universal variable→row-oriented transformer used by
the collation engine to normalise B, D, R, Ep, So, and Sp before display/export.

No streamlit dependency — safe to import in tests and CLI scripts.
"""

import re

import pandas as pd

__all__ = ["_to_w_rows"]

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

    if not force_column_oriented and is_b_style:
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
