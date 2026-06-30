# -*- coding: utf-8 -*-
"""
run_combined_csv.py — single side-by-side combined CSV per game (635/644/c647),
mirroring the c545_combined.xlsx 5-section "All" layout but as one CSV (no
sheet-splitting; CSV has no row limit).

Reshape ONLY — never recompute. Reads the already-computed outputs:
  {name}_1nplus1_grouped.csv     -> Section 2 (Grouped n1-n6) + Section 3 (NList N1-N7)
  {name}_1nplus1_regenerate.csv  -> Section 4 (Regenerate N1-N7)
  {name}_1nplus1_remnant.csv     -> Section 5 (Remnant n1-n6)
Section 1 (Input n1-n6) = grouped non-blank child rows (group order) + remnant,
dense (the c545 grouped_nonblank pattern, extended to include the remnant rows
so Section 1 carries every input row).

Layout (36 cols, one blank col between sections):
  Input 0-5 | gap6 | Grouped 7-12 | gap13 | NList 14-20 | gap21 |
  Regenerate 22-28 | gap29 | Remnant 30-35

Global row index drives all sections. Total data rows = grouped_rows + remnant
(the remnant rows trail the Grouped section after the last group separator,
which is why a game with k remnant rows is grouped+k). Shorter sections blank
out once exhausted.

Written in 500,000-row chunks.
"""
from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path

from run_increase_efficient import CORE

CHUNK = 500_000
TOTAL_COLS = 36
# (label, start, width)
SEC1 = ("Input", 0, 6)        # n1-n6
SEC2 = ("Grouped", 7, 6)      # n1-n6
SEC3 = ("NList_Header", 14, 7)  # N1-N7
SEC4 = ("Regenerate", 22, 7)  # N1-N7
SEC5 = ("Remnant", 30, 6)     # n1-n6

# (name, has_input_header_unused) expected: total, input_nonblank, nlists, remnant
EXPECTED = {
    "635":  {"total": 2_359_736,  "input": 1_623_160,  "nlists": 736_576,   "remnant": 0},
    "644":  {"total": 10_333_246, "input": 7_059_052,  "nlists": 3_274_194, "remnant": 1},
    "c647": {"total": 15_744_190, "input": 10_737_573, "nlists": 5_006_617, "remnant": 0},
}


def grouped_all(path: Path):
    """Yield (n1-6 list[str], N1-7 list[str]) for every grouped row incl. separators."""
    with path.open() as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split(",")
            if len(parts) < 14:
                parts += [""] * (14 - len(parts))
            yield parts[0:6], parts[7:14]


def grouped_nonblank(path: Path):
    """Yield n1-6 list[str] for grouped rows carrying data (skip separators)."""
    with path.open() as f:
        next(f)
        for line in f:
            parts = line.rstrip("\n").split(",")
            n6 = parts[0:6] + [""] * max(0, 6 - len(parts))
            if any(x for x in n6[:6]):
                yield n6[:6]


def plain(path: Path):
    """Yield list[str] rows from a simple header+data csv (skip blank lines)."""
    with path.open() as f:
        next(f)
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split(",")
            if not any(x.strip() for x in parts):
                continue
            yield parts


_SENT = object()


def build(name: str) -> dict:
    exp = EXPECTED[name]
    g_path = CORE / f"{name}_1nplus1_grouped.csv"
    rg_path = CORE / f"{name}_1nplus1_regenerate.csv"
    rm_path = CORE / f"{name}_1nplus1_remnant.csv"
    out_path = CORE / f"{name}_combined.csv"

    print(f"\n=== building {out_path.name} ===", flush=True)
    t0 = time.time()

    remnant = list(plain(rm_path))            # tiny (0 or 1 here)
    n_rem = len(remnant)

    # Section 1 dense source: utilised children (grouped order) then remnant.
    def input_dense():
        yield from grouped_nonblank(g_path)
        yield from remnant
    sec1_it = input_dense()
    sec2_it = grouped_all(g_path)
    sec4_it = plain(rg_path)

    # title row + header row
    title = [""] * TOTAL_COLS
    header = [""] * TOTAL_COLS
    for label, start, width in (SEC1, SEC2, SEC3, SEC4, SEC5):
        title[start] = label
        names = ([f"n{i+1}" for i in range(width)] if label in ("Input", "Grouped", "Remnant")
                 else [f"N{i+1}" for i in range(width)])
        for i, nm in enumerate(names):
            header[start + i] = nm

    gi = 0
    sec1_nonblank = 0
    sec4_nonblank = 0
    sec4_dups = 0
    prev_regen = None
    first5: list[str] = []
    last5: deque[str] = deque(maxlen=5)
    buf: list[str] = [",".join(title), ",".join(header)]

    def emit(row_cells):
        nonlocal gi
        buf.append(",".join(row_cells))
        gi_local = gi
        if gi_local < 5:
            first5.append(",".join(row_cells))
        last5.append(",".join(row_cells))

    with out_path.open("w", newline="") as out:
        def flush():
            if buf:
                out.write("\n".join(buf) + "\n")
                buf.clear()

        def make_row(sec1, sec2, sec3, sec4, sec5):
            row = [""] * TOTAL_COLS
            if sec1 is not _SENT:
                row[SEC1[1]:SEC1[1] + 6] = sec1
            row[SEC2[1]:SEC2[1] + 6] = sec2
            row[SEC3[1]:SEC3[1] + 7] = sec3
            if sec4 is not _SENT:
                row[SEC4[1]:SEC4[1] + 7] = sec4
            if sec5 is not _SENT:
                row[SEC5[1]:SEC5[1] + 6] = sec5
            return row

        # main loop: driven by grouped_all (children + separators)
        for n6, N7 in sec2_it:
            s1 = next(sec1_it, _SENT)
            if s1 is not _SENT:
                sec1_nonblank += 1
            s4 = next(sec4_it, _SENT)
            if s4 is not _SENT:
                sec4_nonblank += 1
                if prev_regen is not None and s4 == prev_regen:
                    sec4_dups += 1
                prev_regen = s4
            s5 = remnant[gi] if gi < n_rem else _SENT
            emit(make_row(s1, n6, N7, s4, s5))
            gi += 1
            if len(buf) >= CHUNK:
                flush()

        # grouped-section tail: remnant rows trail after the last group separator
        for rrow in remnant:
            s1 = next(sec1_it, _SENT)
            if s1 is not _SENT:
                sec1_nonblank += 1
            s4 = next(sec4_it, _SENT)
            if s4 is not _SENT:
                sec4_nonblank += 1
                if prev_regen is not None and s4 == prev_regen:
                    sec4_dups += 1
                prev_regen = s4
            s5 = remnant[gi] if gi < n_rem else _SENT
            emit(make_row(_SENT, rrow, [""] * 7, s4, s5))
            gi += 1
            if len(buf) >= CHUNK:
                flush()

        flush()

    dt = time.time() - t0
    total = gi
    size_mb = out_path.stat().st_size / 1_048_576

    ok = (total == exp["total"] and sec1_nonblank == exp["input"] and
          sec4_nonblank == exp["nlists"] and sec4_dups == 0)

    print(f"  total data rows   : {total:,}   (expected {exp['total']:,}  "
          f"{'OK' if total == exp['total'] else 'MISMATCH'})", flush=True)
    print(f"  Section1 non-blank: {sec1_nonblank:,}   (expected input {exp['input']:,}  "
          f"{'OK' if sec1_nonblank == exp['input'] else 'MISMATCH'})", flush=True)
    print(f"  Section4 non-blank: {sec4_nonblank:,}   (expected NLists {exp['nlists']:,}  "
          f"{'OK' if sec4_nonblank == exp['nlists'] else 'MISMATCH'})", flush=True)
    print(f"  Section4 duplicates: {sec4_dups}   ({'OK' if sec4_dups == 0 else 'MISMATCH'})",
          flush=True)
    print(f"  file size         : {size_mb:.2f} MB", flush=True)
    print(f"  time              : {dt:.1f}s", flush=True)
    print(f"  header cols       : {TOTAL_COLS}", flush=True)
    print(f"  first 5 data rows :", flush=True)
    for r in first5:
        print(f"    {r}", flush=True)
    print(f"  last 5 data rows  :", flush=True)
    for r in last5:
        print(f"    {r}", flush=True)
    print(f"  RESULT            : {'PASS' if ok else 'FAIL'}", flush=True)

    if not ok:
        raise SystemExit(f"!!! STOP: {name} combined CSV verification mismatch")

    return {"name": name, "total": total, "input": sec1_nonblank,
            "nlists": sec4_nonblank, "dups": sec4_dups, "mb": size_mb, "dt": dt}


def main() -> None:
    names = sys.argv[1:] or ["635", "644", "c647"]
    g0 = time.time()
    results = []
    for nm in names:
        results.append(build(nm))
    print(f"\n{'#'*60}\nALL COMBINED CSVs DONE\n{'#'*60}")
    print(f"{'file':18s} {'rows':>13s} {'input':>13s} {'NLists':>12s} "
          f"{'dups':>5s} {'MB':>9s} {'s':>7s}")
    for r in results:
        print(f"{r['name']+'_combined.csv':18s} {r['total']:>13,} {r['input']:>13,} "
              f"{r['nlists']:>12,} {r['dups']:>5} {r['mb']:>9.2f} {r['dt']:>7.1f}")
    print(f"total wall: {time.time()-g0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
