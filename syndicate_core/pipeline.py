"""
syndicate_core/pipeline.py — Data pipeline helpers

Contains: game directory resolution, D-file splitting, state combination,
and the active-game accessors that wrap st.session_state.

Decision log
------------
gkey / gs / gs_set kept in masterapp.py
    These three are pure session-state helpers used throughout every UI section.
    Moving them here would require importing streamlit AND would split the
    session-state API across two modules, making it harder to grep for all
    session-state access points. active_game / active_game_dirs / active_game_cfg
    are moved here because they're called by pipeline dispatch code, but
    gkey/gs/gs_set are called by virtually every UI widget and belong closer
    to the UI layer.

_picks_dedup / _picks_columns left in syndicate_core/scraping.py
    These helpers were moved to scraping.py during Step 3 (they are called
    exclusively by sweep_state_picks). Moving them here would require scraping.py
    to import from pipeline.py, creating a circular dependency.
"""

import re
import logging
import os as _os
from pathlib import Path

import pandas as pd
import streamlit as st

from syndicate_core.config import ROOT, GAME_KEYS, GAME_NAME_MAP, GAMES_CFG

__all__ = [
    # atomic I/O
    "_write_csv_atomic",
    # pipeline utilities
    "_warn_row_shrink", "_clean_for_pipeline",
    # game directory resolution
    "game_dirs",
    # D-file split + combine
    "split_d_by_game", "combine_states_for_game",
    # active-game accessors (wrap st.session_state)
    "active_game", "active_game_dirs", "active_game_cfg",
]


# ── Atomic CSV write ──────────────────────────────────────────────────────────

def _write_csv_atomic(path: Path, df: pd.DataFrame, **kwargs) -> None:
    """Write df to path atomically: write to .tmp then os.replace().

    Prevents half-written files on crash. pandas to_csv() opens in 'w' mode
    which immediately truncates the destination; a crash mid-write leaves an
    empty or partial file that pandas then silently reads back as fewer rows.
    """
    tmp = path.with_suffix(".tmp")
    try:
        df.to_csv(tmp, **kwargs)
        _os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


# ── Pipeline utilities ────────────────────────────────────────────────────────

def _warn_row_shrink(label: str, before: int, after: int,
                     threshold: float = 0.05) -> None:
    """Log a warning when a pipeline step drops more than `threshold` of rows."""
    if before > 0 and (before - after) / before > threshold:
        pct = (before - after) / before * 100
        logging.warning(
            "[row-count] %s: %d → %d rows (%.1f%% dropped — exceeds %.0f%% threshold)",
            label, before, after, pct, threshold * 100,
        )


def _clean_for_pipeline(gdf: pd.DataFrame) -> pd.DataFrame:
    """Retain only identity columns + w-columns from a split D DataFrame.

    Strips any extra columns produced by the API fetch so downstream
    pipeline steps receive a lean, consistent schema.
    (Was a nested function inside split_d_by_game; extracted to module level.)
    """
    w_cols = sorted([c for c in gdf.columns if re.match(r'^w\d+$', str(c), re.I)],
                    key=lambda x: int(str(x)[1:]))
    keep = [c for c in ("Syndicate_ID", "Syndicate_Name", "Game", "Games",
                         "Draw_Number", "Draw_Date", "Postcode", "State")
            if c in gdf.columns]
    if "PB" in gdf.columns:
        keep.append("PB")
    keep += w_cols
    return gdf[keep]


# ── Game directory resolution ─────────────────────────────────────────────────

def game_dirs(game_key: str) -> dict:
    """Return DIRS-like dict scoped to a specific game folder.

    All top-level subfolders are suffixed with _{game_key} so each game's
    folders are visually distinct and never confused with another game's data.
    e.g. Games/SAT/main_data_sat/, Games/OZ/formulas_oz/, etc.
    """
    g  = ROOT / "Games" / game_key.upper()
    gk = game_key.lower()

    var_inputs = g / f"variable_inputs_{gk}"   # was Variables/Variable_Elements
    gb         = g / f"games_breakdown_{gk}"   # per-game split D lives here
    formulas   = g / f"formulas_{gk}"

    d = {
        "Game":            g,
        "Main_Data":       g / f"main_data_{gk}",
        "Outputs":         g / f"outputs_{gk}",
        "Formulas":        formulas,
        "Containers":      g / f"containers_{gk}",
        "Scraper":         var_inputs / "Scraper",
        "Games_Breakdown": gb,
        "Direct":          gb,      # alias (legacy key) → same Games_Breakdown folder
        "Base":            var_inputs / "Base",
        "Splits":          var_inputs / "Splits",
        "Splits_Combi":    var_inputs / "Splits_Combi",
        "Rainbow":         var_inputs / "Rainbow",
        "ExcelPro":        var_inputs / "ExcelPro",
        "CVI":             g / f"container_variable_inputs_{gk}",
        "Selected_Counts": formulas / "Selected_Counts",
        "SinceLast":       g / f"sincelast_{gk}",
    }
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    return d


# ── D-file split + state combine ─────────────────────────────────────────────

def split_d_by_game(src_csv: Path, root: Path) -> dict:
    """
    Split a raw D_*.csv file by the Games column into per-game Direct/ folders.

    Handles:
    - Single game rows       → copied to that game's Direct/ folder
    - Pipe-separated rows    → a copy goes to EACH matching game folder
    - None-mapped games      → skipped intentionally (Super 66, Lucky Lotteries)
    - Unknown game names     → logged in _unknown_games for inspection

    Returns dict: {game_key: row_count_written, '_unknown_games': [...]}
    """
    try:
        df = pd.read_csv(src_csv)
    except Exception as ex:
        return {"error": str(ex)}

    if "Games" not in df.columns:
        return {"error": "No 'Games' column found in file"}

    game_rows: dict[str, list] = {k: [] for k in GAME_KEYS}
    unknown_games: set = set()
    skipped_games: set = set()

    for _, row in df.iterrows():
        raw_games = str(row.get("Games", "")).strip()
        if not raw_games or raw_games == "nan":
            continue

        parts = [g.strip() for g in raw_games.split("|")]

        matched: dict[str, str] = {}
        for part in parts:
            if part not in GAME_NAME_MAP:
                unknown_games.add(part)
            else:
                gk = GAME_NAME_MAP[part]
                if gk is None:
                    skipped_games.add(part)
                else:
                    matched[gk] = part

        for gk, canonical_name in matched.items():
            out_row = row.copy()
            out_row["Games"] = canonical_name
            game_rows[gk].append(out_row)

    state_tag = src_csv.stem
    results = {}

    for gk, rows in game_rows.items():
        if not rows:
            results[gk] = 0
            continue
        raw_count = len(rows)
        gdf = pd.DataFrame(rows).reset_index(drop=True)
        gdf = _clean_for_pipeline(gdf)
        _warn_row_shrink(f"split_d_by_game/{state_tag}/{gk}", raw_count, len(gdf))
        dest_dir = game_dirs(gk)["Direct"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{state_tag}_{gk}.csv"
        gdf.to_csv(dest_file, index=False)
        results[gk] = len(gdf)

    if unknown_games:
        results["_unknown_games"] = sorted(unknown_games)
    if skipped_games:
        results["_skipped_games"] = sorted(skipped_games)

    return results


def combine_states_for_game(game_key: str) -> dict:
    """Merge every per-state split file for a game into ONE national file.

    Reads all D_<STATE>_<game>.csv in the game's Games_Breakdown folder (e.g.
    D_NSW_pb.csv, D_VIC_pb.csv, …), concatenates them — each state's syndicates
    are distinct, so we keep them all (a "national view") — drops only rows with
    duplicate Syndicate_IDs (guards against an accidental re-run without losing
    valid unique rows from different states), and writes D_ALL_<game>.csv.
    Returns {"states": [...], "files": n, "rows": total}.
    """
    gb = game_dirs(game_key)["Games_Breakdown"]
    parts, states = [], []
    for fp in sorted(gb.glob(f"D_*_{game_key}.csv")):
        if fp.name.startswith("D_ALL_"):
            continue
        try:
            df = pd.read_csv(fp)
        except Exception as _read_err:
            logging.warning("combine_states_for_game: skipping unreadable file %s — %s",
                            fp.name, _read_err)
            continue
        if df.empty:
            continue
        tag = fp.stem[2:]
        if tag.endswith(f"_{game_key}"):
            tag = tag[: -(len(game_key) + 1)]
        states.append(tag)
        parts.append(df)
    if not parts:
        return {"states": [], "files": 0, "rows": 0}
    combined = pd.concat(parts, ignore_index=True)
    before = len(combined)
    dedup_cols = [c for c in ["Syndicate_ID"] if c in combined.columns]
    combined = (combined.drop_duplicates(subset=dedup_cols, keep="first")
                if dedup_cols else combined.drop_duplicates())
    combined = combined.reset_index(drop=True)
    _warn_row_shrink(f"combine_states_for_game({game_key})", before, len(combined))
    out = gb / f"D_ALL_{game_key}.csv"
    _write_csv_atomic(out, combined, index=False)
    return {"states": states, "files": len(parts),
            "rows": len(combined), "dropped_dups": before - len(combined),
            "path": str(out)}


# ── Active-game accessors (wrap st.session_state) ────────────────────────────

def active_game() -> str:
    return st.session_state.get("active_game", "sat")


def active_game_dirs() -> dict:
    return game_dirs(active_game())


def active_game_cfg() -> dict:
    return GAMES_CFG[active_game()]
