#!/usr/bin/env python3
"""Per-row CVI match CLI — every CVI row vs the full main-data set.

Usage:
    python3 scripts/per_row_cvi_match.py <game> <formula>
    e.g. python3 scripts/per_row_cvi_match.py sat BRDEpSoSp

Loads CVI_*<formula>*.csv and the game's main-data CSV, runs the tested
``syndicate_core.matching._match_cvi_rows`` engine (single source of truth),
and writes ``CVI_per_row_match_<game>_<formula>_FULL.csv`` at the repo root.
A ``.status`` sibling file records progress.

Because the full BRDEpSoSp run is ~30 min, launch it DETACHED so it survives
the shell/terminal closing (the failure mode that lost a prior baseline):

    nohup python3 scripts/per_row_cvi_match.py sat BRDEpSoSp \\
        > per_row_match_sat_BRDEpSoSp.log 2>&1 & disown
"""
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from syndicate_core.config import GAMES_CFG            # noqa: E402
from syndicate_core.pipeline import game_dirs          # noqa: E402
from syndicate_core.matching import _match_cvi_rows    # noqa: E402


def _detect_number_cols(main_df: pd.DataFrame) -> list:
    """Main-data number columns — handles both ``n1..`` and bare ``1..`` names."""
    cols = [c for c in main_df.columns if re.match(r"^n?\d+$", str(c), re.I)]
    if not cols:
        num = main_df.apply(pd.to_numeric, errors="coerce")
        cols = [c for c in main_df.columns
                if num[c].notna().mean() > 0.9 and num[c].max() <= 99]
    return cols


def _build_main_arr(main_df: pd.DataFrame, n_cols: list, pool_max: int) -> np.ndarray:
    """Numeric main-data array. Out-of-range values become 0 (excluded from
    matching) rather than clipped — clipping would fabricate matches."""
    raw = (main_df[n_cols].apply(pd.to_numeric, errors="coerce")
           .to_numpy(dtype=np.float64))
    raw = np.nan_to_num(raw, nan=0.0)
    return np.where((raw >= 1) & (raw <= pool_max), raw, 0).astype(np.int32)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: per_row_cvi_match.py <game> <formula>")
    game, formula = sys.argv[1].lower(), sys.argv[2]
    if game not in GAMES_CFG:
        sys.exit(f"unknown game '{game}' (known: {', '.join(GAMES_CFG)})")

    pool_max = int(GAMES_CFG[game]["pool"])
    gdirs = game_dirs(game)

    cvi_hits = sorted(gdirs["CVI"].glob(f"CVI_*{formula}*.csv"))
    if not cvi_hits:
        sys.exit(f"no CVI file matching CVI_*{formula}*.csv in {gdirs['CVI']}")
    cvi_df = pd.read_csv(cvi_hits[0])

    main_hits = sorted(gdirs["Main_Data"].glob("*.csv"))
    if not main_hits:
        sys.exit(f"no main-data CSV in {gdirs['Main_Data']}")
    main_df = pd.read_csv(main_hits[0])

    n_cols = _detect_number_cols(main_df)
    if not n_cols:
        sys.exit(f"could not detect number columns in {main_hits[0].name}")
    main_arr = _build_main_arr(main_df, n_cols, pool_max)
    del main_df

    out = ROOT / f"CVI_per_row_match_{game}_{formula}_FULL.csv"
    status = out.with_suffix(".status")
    total = len(cvi_df)
    t0 = time.time()
    print(f"[start] {cvi_hits[0].name} rows={total} main={main_arr.shape} "
          f"pool=1..{pool_max}", flush=True)

    def _progress(done: int, tot: int) -> None:
        el = time.time() - t0
        msg = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} {done}/{tot} "
               f"{el:.0f}s eta {el / done * (tot - done):.0f}s")
        status.write_text(msg + "\n")
        print("[progress] " + msg, flush=True)

    result = _match_cvi_rows(cvi_df, main_arr, pool_max=pool_max,
                             progress_cb=_progress)
    result.to_csv(out, index=False)
    status.write_text(f"DONE {time.time() - t0:.0f}s rows={len(result)} "
                      f"-> {out.name}\n")
    print(f"[done] {time.time() - t0:.0f}s saved {out} "
          f"({out.stat().st_size / 1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
