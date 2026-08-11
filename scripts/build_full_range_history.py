"""Build & validate the B1-fed full-range draw history for the Stacked Draws view.

Splices B1 (deep win history) with draw_history.csv (top + explicit numbering),
runs the overlap sanity-check the join depends on, writes a drop-in
``draw_history_full_{gk}.csv`` in the reader's schema, and smoke-tests the
``stacked_blocks`` engine over the full range so we know the Blocked-flat view
renders for any window across 2761→4701 — not just the newest 10.

Usage:
    python3 -m scripts.build_full_range_history [game_key]   # default: sat
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from syndicate_core import full_history as fh
from syndicate_core import stacked_blocks as sb
from syndicate_core.config import GAMES_CFG
from syndicate_core.pipeline import b1_path, game_dirs


def _load(game_key: str) -> tuple[pd.DataFrame, pd.DataFrame, Path, int]:
    gk = game_key.lower()
    b1p = b1_path(gk)
    if b1p is None or not b1p.exists():
        sys.exit(f"[abort] no B1 source for '{gk}' — this splice needs B1 (deep history).")
    dirs = game_dirs(gk)
    dhp = dirs["SinceLast"] / "draw_history.csv"
    if not dhp.exists():
        sys.exit(f"[abort] no draw_history.csv for '{gk}' at {dhp} — fetch it (Stats tab) first.")
    pick = int(GAMES_CFG[gk]["pick"])
    return pd.read_csv(b1p, dtype=str), pd.read_csv(dhp, dtype=str), dirs["SinceLast"], pick


def _print_report(rep: dict) -> None:
    print("── splice report ─────────────────────────────────────────────")
    print(f"  B1 rows           : {rep['n_b1']}")
    print(f"  draw_history rows : {rep['n_dh']}")
    print(f"  pick / step       : {rep['pick']} / {rep['step']}")
    print(f"  align offset      : {rep['offset']}  (draws only in draw_history: {rep['top_from_dh']})")
    print(f"  anchor draw       : {rep['anchor_draw']}  (= B1's newest row)")
    print(f"  full range        : {rep['oldest_draw']} → {rep['newest_draw']}  ({rep['n_full']} draws)")
    print("── overlap sanity-check (draws in BOTH sources) ──────────────")
    print(f"  overlapping draws : {rep['overlap_n']}")
    if rep["overlap_agree"]:
        print("  number sets       : ✅ ALL AGREE — join is safe to trust")
    else:
        mm = rep["overlap_mismatches"]
        print(f"  number sets       : ❌ {len(mm)} DISAGREE — join NOT trustworthy")
        for m in mm[:5]:
            print(f"      draw {m['dh_draw']}: B1 {m['b1_nums']} vs DH {m['dh_nums']}")
    xc = rep["b1_update_crosscheck_mismatches"]
    if xc:
        print(f"  B1 update crosscheck: ⚠️ {len(xc)} of B1's own draw numbers ≠ derived")
        for m in xc[:5]:
            print(f"      row {m['b1_index']}: B1 update {m['b1_update']} vs derived {m['derived']}")
    else:
        print("  B1 update crosscheck: ✅ B1's own (sparse) draw numbers match derived")


def _engine_smoke(records: list[dict], pool: int) -> bool:
    """Exercise the real Blocked-flat engine across the full range."""
    n = len(records)
    ok = True
    # block_layout partitions 1..pool exactly once, at newest / middle / oldest.
    for idx in (0, n // 2, n - 1):
        blocks = sb.block_layout(idx, records, pool)
        flat = [x for blk in blocks for x in blk]
        if sorted(flat) != list(range(1, pool + 1)):
            print(f"  ✗ block_layout[{idx}] does not partition 1..{pool}")
            ok = False
    # A 10-wide window rendered at the deep (oldest) end — the case the old
    # 150-row file could never reach.
    start = max(0, n - 10)
    dis = list(range(start, min(start + 10, n)))
    cols = sb.render_columns(dis, records, pool)
    pads = sb.column_pads(dis, records)
    if len(cols) != len(dis) or len(pads) != len(dis):
        print("  ✗ render_columns/column_pads shape mismatch on deep window")
        ok = False
    # SL sane at the oldest draw (all numbers get a value, none negative).
    sl = sb.since_last_map(n - 1, records, pool)
    if len(sl) != pool or any(v < 0 for v in sl.values()):
        print("  ✗ since_last_map invalid at oldest draw")
        ok = False
    print(f"  engine smoke      : {'✅ ok' if ok else '❌ failed'} "
          f"(block_layout ×3, render deep window D{records[dis[0]]['draw']}→"
          f"D{records[dis[-1]]['draw']}, SL@oldest)")
    return ok


def main() -> None:
    game_key = (sys.argv[1] if len(sys.argv) > 1 else "sat").lower()
    b1_df, dh_df, out_dir, pick = _load(game_key)
    pool = int(GAMES_CFG[game_key]["pool"])

    records, rep = fh.build_full_history(b1_df, dh_df, pick)
    _print_report(rep)

    engine_ok = _engine_smoke(records, pool)

    out_path = out_dir / f"draw_history_full_{game_key}.csv"
    fh.records_to_df(records).to_csv(out_path, index=False)
    print("── output ────────────────────────────────────────────────────")
    print(f"  wrote {rep['n_full']} draws → {out_path}")

    if not rep["overlap_agree"] or not engine_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
