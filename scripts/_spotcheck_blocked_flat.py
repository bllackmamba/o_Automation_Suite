"""Spot-check: D2779->D2761 slice of the exported Blocked-flat xlsx must match
the live-view colour logic cell-for-cell. Independent re-derivation (does NOT
call export's cell_style) + physical read-back of the .xlsx fills/borders."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from syndicate_core.full_history import build_full_history
from syndicate_core.pipeline import b1_path, game_dirs, GAMES_CFG
from syndicate_core.stacked_blocks import render_columns, column_pads, group_rail_flags
from scripts.export_blocked_flat_xlsx import cell_style   # what was written

GAME, POOL, PICK = "sat", 45, 6
XLSX = ROOT / "exports" / f"blocked_flat_full_range_{GAME}.xlsx"


def ui_truth(cell, railed):
    """UI render truth, inlined verbatim from masterapp _bf_cell_html/_num_colour/_bf_deep."""
    k = cell[0]
    if k == "num":
        n, deep = cell[1], cell[2]
        bg = ("#FFFF00" if n <= 9 else "#00B0F0" if n <= 19 else
              "#A0A0A0" if n <= 29 else "#92D050" if n <= 39 else "#FF69B4")
        if deep:
            h = bg.lstrip("#"); r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            bg = "#%02X%02X%02X" % (int(r * .6), int(g * .6), int(b * .6)); fg = "#FFFFFF"
        else:
            fg = "#000000"
        return {"bg": bg, "fg": fg, "text": n, "railed": railed}
    if k == "hole":
        return {"bg": "#FFFFFF" if cell[1] == "wall" else "#8B6F47",
                "fg": None, "text": None, "railed": railed}
    return None


def main():
    recs, rep = build_full_history(pd.read_csv(b1_path(GAME), dtype=str),
                                   pd.read_csv(game_dirs(GAME)["SinceLast"]/"draw_history.csv", dtype=str), PICK)
    n = len(recs)
    # Full export = fully-aligned view (window-global reclamation is a no-op when
    # the whole range is displayed), so re-derive against the aligned columns.
    cols = render_columns(list(range(n)), recs, POOL)
    pads = column_pads(list(range(n)), recs)
    rails = [group_rail_flags(c) for c in cols]

    # target slice D2779..D2761 = indices 961..970
    lo = next(i for i in range(n) if recs[i]["draw"] == "2779")
    hi = next(i for i in range(n) if recs[i]["draw"] == "2761")
    slice_idx = list(range(lo, hi + 1))
    labels = [f"D{recs[i]['draw']}" for i in slice_idx]
    print(f"slice cols {slice_idx[0]}..{slice_idx[-1]} = {labels[0]}..{labels[-1]} ({len(slice_idx)} draws)")

    # (a) seed-anchored equivalence: full-export cols == isolated 10-draw window
    win = render_columns(slice_idx, recs, POOL)
    win_rails = [group_rail_flags(c) for c in win]
    eq = all(cols[slice_idx[m]] == win[m] and rails[slice_idx[m]] == win_rails[m]
             for m in range(len(slice_idx)))
    print(f"(a) full-export slice == isolated window render: {eq}")
    assert eq, "recursive slice diverges from isolated window"

    # (b) written style (cell_style) == independent UI truth, every cell
    mism_b = 0
    for j in slice_idx:
        for si, cell in enumerate(cols[j]):
            t = ui_truth(cell, rails[j][si])
            s = cell_style(cell, rails[j][si])
            if t is None:
                if s is not None:
                    mism_b += 1
                continue
            if not (s and s["bg"].upper() == t["bg"].upper() and s["font"] == t["fg"]
                    and s["text"] == t["text"] and s["railed"] == t["railed"]):
                mism_b += 1
    print(f"(b) cell_style vs UI-truth mismatches: {mism_b}")
    assert mism_b == 0

    # build expected physical map {(exrow,excol): (argb, value, railed)} for the slice
    HDR = 3
    expected = {}
    for j in slice_idx:
        excol = j + 1                        # 1-indexed
        for si, cell in enumerate(cols[j]):
            t = ui_truth(cell, rails[j][si])
            if t is None:
                continue                      # spacer -> empty cell, nothing to check
            exrow = HDR + pads[j] + si + 1    # 1-indexed body row
            expected[(exrow, excol)] = ("FF" + t["bg"].lstrip("#").upper(),
                                        t["text"], t["railed"])
    print(f"(c) physical cells to verify: {len(expected)}")

    # (c) read those cells back from the xlsx and compare fill/value/rail
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb.active
    min_c, max_c = slice_idx[0] + 1, slice_idx[-1] + 1
    checked = fill_mm = val_mm = rail_mm = 0
    seen = set()
    exrow = HDR  # will be incremented to HDR+1 on first row
    for row in ws.iter_rows(min_row=HDR + 1, min_col=min_c, max_col=max_c):
        exrow += 1
        for ci, c in enumerate(row):
            key = (exrow, min_c + ci)
            if key not in expected:
                continue
            argb, val, railed = expected[key]
            got_fill = c.fill.fgColor.rgb if (c.fill and c.fill.patternType) else None
            if got_fill != argb:
                fill_mm += 1
            if (c.value if c.value is not None else None) != val:
                val_mm += 1
            has_rail = bool(c.border and c.border.left and c.border.left.style
                            and c.border.left.color and str(c.border.left.color.rgb).endswith("777777"))
            if has_rail != railed:
                rail_mm += 1
            checked += 1
            seen.add(key)
    wb.close()
    missing = len(expected) - len(seen)
    print(f"    checked {checked} · fill_mm {fill_mm} · value_mm {val_mm} · rail_mm {rail_mm} · missing {missing}")
    assert fill_mm == 0 and val_mm == 0 and rail_mm == 0 and missing == 0
    print("SPOT-CHECK PASS: D2779->D2761 matches live-view colouring cell-for-cell.")


if __name__ == "__main__":
    main()
