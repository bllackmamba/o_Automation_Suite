"""Export the full-range "Blocked flat (all_wt)" Stacked-Draws view to .xlsx.

Replicates the Streamlit render (masterapp.py Blocked-flat branch, ~L3412-3564)
CELL-FOR-CELL: the same recursive column alignment from
``syndicate_core.stacked_blocks.render_columns`` / ``column_pads`` /
``group_rail_flags`` / ``visible_group_count``, over the full-range history
spliced by ``syndicate_core.full_history.build_full_history`` (B1 + draw_history).

Colour logic is copied VERBATIM from the UI so the two never drift:

  * value bands ............. masterapp._num_colour  (bg hex per 1-9/10-19/… band)
  * deep (repeat) shade ..... masterapp._bf_deep     (band bg blended 40% → black)
  * wall / caught holes ..... masterapp _WALL / _CATCH
  * gray group rail ......... masterapp _bf_row ("#777")

Faithful-medium notes (Excel can't do a few CSS things 1:1 — flagged, not silent):
  * num-cell border is CSS ``rgba(0,0,0,.15)`` (15%-alpha black). Excel borders are
    opaque, so we approximate with a hairline light-grey (#D9D9D9).
  * a WALL hole is #FF0000 (pure red). The hairline outline (originally added so a
    white wall would read on Excel's white sheet) is now redundant but retained
    unchanged. Spacer/pad cells stay truly empty (transparent, as in the UI).
  * in Blocked-flat the UI deliberately has NO red R-combo outline (masterapp
    L3470-3471: "the full pool is always in R") — so none is drawn here either.

Layout: newest-left (col A = newest draw), matching the live orientation; the
oldest draw seeds the recursion at the far right. Three frozen header rows
(draw id / date / "N grp"). Every column bottom-aligns cell-for-cell.

Space reclamation is window-global (``reclaim_window_dead_runs``): an SL run is
reclaimed only if it is dead across the WHOLE displayed window, removed uniformly
from every column so no surviving number ever shifts row. The full-range export
displays every column, and its oldest column is the clean all_wt seed (no dead
run there), so nothing is reclaimed — the export is the fully-aligned view. Space
savings only appear in a sub-window (e.g. the live app's slider window), where a
run can be dead throughout the visible columns.

Usage:
    python3 scripts/export_blocked_flat_xlsx.py [game_key] [out_path]
    # defaults: sat, exports/blocked_flat_full_range_<game>.xlsx
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import xlsxwriter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from syndicate_core.full_history import build_full_history            # noqa: E402
from syndicate_core.pipeline import b1_path, game_dirs, GAMES_CFG     # noqa: E402
from syndicate_core.stacked_blocks import (                          # noqa: E402
    render_columns, column_pads, group_rail_flags, visible_group_count,
    reclaim_window_dead_runs)

# ── colour constants (copied verbatim from masterapp.py) ────────────────────
# _num_colour: (bg, fg) by value band. In Blocked-flat only the bg is used and
# the fg is overridden (black on light, white on deep), so we keep bg only here.
_LIGHT_BANDS = ((9, "#FFFF00"), (19, "#00B0F0"), (29, "#A0A0A0"), (39, "#92D050"))
_PINK = "#FF69B4"                       # 40+
_WALL = "#FF0000"                       # fresh no-contrast hole = solid red wall
_CATCH = "#8B6F47"                      # catch hole = one fixed muted brown (round 7)
_RAIL = "#777777"                       # group rail (masterapp _bf_row "#777")
_FAINT = "#D9D9D9"                      # ~= CSS rgba(0,0,0,.15) num-cell border
_HDR_BG = "#222222"                     # header box bg (masterapp header div)
_DEEP_F = 0.40                          # _bf_deep blend factor
_EXTRA = "#FFA500"                      # orange — validated/extrapolated marker only
                                        # (NOT in the value/deep/wall/caught/rail palette)


def _band_bg(n: int) -> str:
    for hi, hexc in _LIGHT_BANDS:
        if n <= hi:
            return hexc
    return _PINK


def _deep_bg(hexc: str) -> str:
    """masterapp._bf_deep — light band blended ~40% toward black (same hue)."""
    h = hexc.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    f = _DEEP_F
    return "#%02X%02X%02X" % (int(r * (1 - f)), int(g * (1 - f)), int(b * (1 - f)))


def cell_style(cell: tuple, railed: bool) -> dict | None:
    """Map one render cell + rail flag to its visual style, mirroring
    masterapp._bf_cell_html + _bf_row exactly. Returns None for a spacer/pad or an
    unrailed inherited hole (drawn as an empty transparent cell), else a dict:
        {"bg","font","text","faint","wall_edge","railed"}.
    A hole is painted (wall/caught) only in its origin column (cell[2] True); an
    inherited hole gets no fill — ``bg`` None — keeping only the rail if present.
    """
    kind = cell[0]
    if kind == "num":
        n, deep = cell[1], cell[2]
        bg = _band_bg(n)
        if deep:                        # deep → darker band, white digits
            return {"bg": _deep_bg(bg), "font": "#FFFFFF", "text": n,
                    "faint": True, "wall_edge": False, "railed": railed}
        return {"bg": bg, "font": "#000000", "text": n,      # light → black digits
                "faint": True, "wall_edge": False, "railed": railed}
    if kind == "hole":
        if cell[2]:                      # origin column → paint wall/caught
            is_wall = cell[1] == "wall"
            return {"bg": _WALL if is_wall else _CATCH, "font": None, "text": None,
                    "faint": False, "wall_edge": is_wall, "railed": railed}
        # inherited hole → no fill (transparent); keep the group rail if present
        if railed:
            return {"bg": None, "font": None, "text": None,
                    "faint": False, "wall_edge": False, "railed": True}
        return None
    return None                          # spacer / pad → transparent


def _fmt_key(s: dict) -> tuple:
    return (s["bg"], s["font"], s["text"] is not None,
            s["faint"], s["wall_edge"], s["railed"])


def _make_format(wb, s: dict):
    props = {"align": "center", "valign": "vcenter",
             "font_name": "Menlo", "font_size": 8}
    if s["bg"] is not None:              # None → no fill (transparent inherited hole)
        props["bg_color"] = s["bg"]
    if s["font"]:
        props["font_color"] = s["font"]
    if s["text"] is not None:
        props["bold"] = True
    # faint all-around border for num cells; hairline outline for white walls
    if s["faint"] or s["wall_edge"]:
        props.update(top=1, bottom=1, left=1, right=1,
                     top_color=_FAINT, bottom_color=_FAINT,
                     left_color=_FAINT, right_color=_FAINT)
    # rail = darker, heavier left edge marking the group's extent
    if s["railed"]:
        props.update(left=2, left_color=_RAIL)
    return wb.add_format(props)


def build_export(game_key: str, out_path: Path, labeled: bool = False) -> dict:
    pick = int(GAMES_CFG[game_key].get("pick", 6))
    pool = int(GAMES_CFG[game_key].get("pool", 45))

    b1p = b1_path(game_key)
    if b1p is None or not b1p.exists():
        raise SystemExit(f"No B1 source for {game_key}: {b1p}")
    dhp = game_dirs(game_key)["SinceLast"] / "draw_history.csv"
    if not dhp.exists():
        raise SystemExit(f"No draw_history.csv for {game_key}: {dhp}")

    recs, rep = build_full_history(pd.read_csv(b1p, dtype=str),
                                   pd.read_csv(dhp, dtype=str), pick)
    if not rep["overlap_agree"]:
        raise SystemExit("Splice overlap DISAGREES — refusing to export an "
                         f"untrusted join ({len(rep['overlap_mismatches'])} mismatches).")

    # ── validated/extrapolated boundary (additive marker) ───────────────────
    # A draw is VALIDATED iff it carries external draw_history corroboration:
    # either a top-from-dh draw (newer than B1) or one of the overlap_n draws
    # that agree. Everything older is B1-only, its draw-number extrapolated.
    # The cutoff is taken from the splice report, never assumed (~4403 for sat).
    step, anchor, overlap_n = rep["step"], rep["anchor_draw"], rep["overlap_n"]
    validated_ids = (set(int(x) for x in rep["top_from_dh"])
                     | {anchor - step * i for i in range(overlap_n)})
    cutoff = min(validated_ids)          # oldest validated draw id

    n = len(recs)                                   # 971 for sat
    idx = list(range(n))                            # newest-first → newest-left
    t0 = time.time()
    # Fully-aligned columns, then window-global reclamation over the displayed
    # window (here = every column). For the full range the oldest displayed
    # column is the clean seed, so nothing is reclaimed and this is a no-op that
    # returns the aligned view — every column bottom-aligns, no row-position drift.
    cols, pads = reclaim_window_dead_runs(
        render_columns(idx, recs, pool), column_pads(idx, recs), idx)
    rails = [group_rail_flags(c) for c in cols]
    grps = [visible_group_count(c) for c in cols]   # unaffected by reclamation
    height = max(pads[j] + len(cols[j]) for j in range(n))
    print(f"[compute] {n} cols · body height {height} · "
          f"splice {rep['oldest_draw']}→{rep['newest_draw']} · "
          f"overlap {rep['overlap_n']} agree · {time.time()-t0:.1f}s")

    HDR_ROWS = 4 if labeled else 3          # +1 row for validated/extrapolated label
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(out_path), {"constant_memory": True})
    ws = wb.add_worksheet(f"BlockedFlat_{game_key}")

    hdr_id = wb.add_format({"bg_color": _HDR_BG, "font_color": "#CCCCCC",
                            "align": "center", "valign": "vcenter", "bold": True,
                            "font_name": "Menlo", "font_size": 8})
    hdr_date = wb.add_format({"bg_color": _HDR_BG, "font_color": "#888888",
                              "align": "center", "valign": "vcenter",
                              "font_name": "Menlo", "font_size": 7})
    hdr_grp = wb.add_format({"bg_color": _HDR_BG, "font_color": "#66CCFF",
                             "align": "center", "valign": "vcenter",
                             "font_name": "Menlo", "font_size": 7})
    # 4th-row label formats (labeled mode only). Extrapolated columns also get a
    # thin orange top-border strip on this row so the boundary is scannable.
    hdr_val = wb.add_format({"bg_color": _HDR_BG, "font_color": "#9DD69B",
                             "align": "center", "valign": "vcenter",
                             "font_name": "Menlo", "font_size": 7})
    hdr_ext = wb.add_format({"bg_color": _HDR_BG, "font_color": _EXTRA,
                             "align": "center", "valign": "vcenter",
                             "font_name": "Menlo", "font_size": 7,
                             "top": 1, "top_color": _EXTRA})

    ws.set_column(0, n - 1, 4.0)                     # ~34px columns
    ws.set_default_row(12)
    ws.freeze_panes(HDR_ROWS, 0)

    # format cache (constant_memory writes row-major; formats are reusable)
    fmt_cache: dict[tuple, object] = {}

    # header rows (0,1,2) + optional label row (3)
    n_val = 0
    for j in range(n):
        ws.write_string(0, j, f"D{recs[j]['draw']}", hdr_id)
        ws.write_string(1, j, recs[j]["date"] or "", hdr_date)
        ws.write_string(2, j, f"{grps[j]} grp", hdr_grp)
        if labeled:
            is_val = int(recs[j]["draw"]) >= cutoff
            n_val += is_val
            ws.write_string(3, j, "validated" if is_val else "extrapolated",
                            hdr_val if is_val else hdr_ext)

    # body — row-major so constant_memory can flush each row as it goes
    written = 0
    for r in range(height):
        row = HDR_ROWS + r
        for j in range(n):
            si = r - pads[j]
            if si < 0 or si >= len(cols[j]):
                continue                            # top pad / below column
            style = cell_style(cols[j][si], rails[j][si])
            if style is None:
                continue                            # spacer → transparent
            key = _fmt_key(style)
            fmt = fmt_cache.get(key)
            if fmt is None:
                fmt = fmt_cache[key] = _make_format(wb, style)
            if style["text"] is not None:
                ws.write_number(row, j, style["text"], fmt)
            else:
                ws.write_blank(row, j, None, fmt)
            written += 1
        if r % 1000 == 0:
            print(f"[write] row {r}/{height} · {written} cells · {time.time()-t0:.1f}s")

    wb.close()
    return {"n_cols": n, "height": height, "written": written,
            "formats": len(fmt_cache), "report": rep, "out": out_path,
            "recs": recs, "cols": cols, "rails": rails, "pads": pads, "grps": grps,
            "pool": pool, "labeled": labeled, "cutoff": cutoff,
            "n_validated": n_val if labeled else None,
            "n_extrapolated": (n - n_val) if labeled else None,
            "hdr_rows": HDR_ROWS}


if __name__ == "__main__":
    argv = sys.argv[1:]
    labeled = "--labeled" in argv
    pos = [a for a in argv if not a.startswith("--")]
    game = pos[0] if len(pos) > 0 else "sat"
    default_name = f"blocked_flat_full_range_{game}{'_labeled' if labeled else ''}.xlsx"
    out = Path(pos[1]) if len(pos) > 1 else ROOT / "exports" / default_name
    t = time.time()
    info = build_export(game, out, labeled=labeled)
    sz = info["out"].stat().st_size / 1e6
    if labeled:
        print(f"[label] cutoff D{info['cutoff']} · validated {info['n_validated']} · "
              f"extrapolated {info['n_extrapolated']}")
    print(f"[done] {info['out']}  ({sz:.1f} MB) · {info['n_cols']} cols × "
          f"{info['height']} rows · {info['written']} filled cells · "
          f"{info['formats']} formats · labeled={labeled} · {time.time()-t:.1f}s total")
