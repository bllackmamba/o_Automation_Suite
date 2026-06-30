# -*- coding: utf-8 -*-
"""
derive_grouped_1nplus1.py — derive the {name}_1nplus1_grouped.csv blank-separator
file from already-computed outputs, WITHOUT recomputing the increase algorithm.

Method (same grouping as c545's grouped file): replay first-come exclusive
claiming over the NLists in {name}_1nplus1_regenerate.csv (already in
lexicographic / assignment order) against the canonicalized input set. Because
non-NList candidates in the original scan claimed nothing, replaying only over
the NLists reproduces the identical group membership the run produced — this is
a derivation from existing outputs, not a re-run of the C(n,target) search.

Output layout (mirrors c545_grouped.csv, widened to n=6 / target=7):
  header: n1,n2,n3,n4,n5,n6,,N1,N2,N3,N4,N5,N6,N7   (14 fields)
  per group: children (sorted asc) one per row, NList on the first child row;
             a fully-blank 14-field separator row after each group.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from run_increase_efficient import CORE, load_rows, subsets_missing_one

N, TARGET = 6, 7
WIDTH = N + 1 + TARGET  # 14

# (filename, has_header), expected (utilised, remnant, nlists)
FILES = {
    "635":  (("635.csv", False),  (1_623_160,  0, 736_576)),
    "644":  (("644.csv", False),  (7_059_051,  1, 3_274_194)),
    "c647": (("c647.csv", True),  (10_737_573, 0, 5_006_617)),
}
CHUNK = 200_000


def derive(name: str) -> None:
    (fname, has_header), (exp_util, exp_rem, exp_nl) = FILES[name]
    path = CORE / fname
    reg_path = CORE / f"{name}_1nplus1_regenerate.csv"
    out_path = CORE / f"{name}_1nplus1_grouped.csv"
    print(f"\n=== deriving grouped for {name} ===", flush=True)
    t0 = time.time()

    rows, dup = load_rows(path, has_header, N)          # canonical asc, deduped
    remaining = rows                                     # mutate: discard as claimed
    n_input = len(rows)
    print(f"  input rows (canonical): {n_input:,}  (dups collapsed: {dup:,})", flush=True)

    header = ",".join([f"n{i+1}" for i in range(N)] + [""] +
                      [f"N{i+1}" for i in range(TARGET)])
    sep = "," * (WIDTH - 1)                               # 14 empty fields

    buf: list[str] = [header]
    utilised = 0
    n_groups = 0
    with reg_path.open() as rf, out_path.open("w", newline="") as out:
        next(rf)  # regenerate header n1..n7
        for line in rf:
            line = line.rstrip("\n")
            if not line:
                continue
            nlist = tuple(int(x) for x in line.split(","))   # already asc
            kids = [s for s in subsets_missing_one(nlist) if s in remaining]
            if len(kids) < 2:
                raise SystemExit(
                    f"!!! {name}: NList {nlist} had <2 unclaimed children at "
                    f"replay — grouping diverged from the original run")
            kids.sort()
            for s in kids:
                remaining.discard(s)
            nl_str = ",".join(map(str, nlist))
            first = ",".join(map(str, kids[0])) + ",," + nl_str
            buf.append(first)
            blanks = "," * (TARGET + 1)  # sep col + 7 empty N cols
            for s in kids[1:]:
                buf.append(",".join(map(str, s)) + blanks)
            buf.append(sep)
            utilised += len(kids)
            n_groups += 1
            if len(buf) >= CHUNK:
                out.write("\n".join(buf) + "\n")
                buf.clear()
        if buf:
            out.write("\n".join(buf) + "\n")

    remnant = len(remaining)
    dt = time.time() - t0
    print(f"  groups written      : {n_groups:,}  (expected NLists {exp_nl:,} "
          f"{'OK' if n_groups == exp_nl else 'MISMATCH'})", flush=True)
    print(f"  children (utilised) : {utilised:,}  (expected {exp_util:,} "
          f"{'OK' if utilised == exp_util else 'MISMATCH'})", flush=True)
    print(f"  remnant (remaining) : {remnant:,}  (expected {exp_rem:,} "
          f"{'OK' if remnant == exp_rem else 'MISMATCH'})", flush=True)
    print(f"  utilised+remnant    : {utilised + remnant:,} "
          f"(== input? {utilised + remnant == n_input})", flush=True)
    sz = out_path.stat().st_size / 1_048_576
    print(f"  {out_path.name}: {sz:.2f} MB  in {dt:.1f}s", flush=True)

    if not (n_groups == exp_nl and utilised == exp_util and remnant == exp_rem):
        raise SystemExit(f"!!! STOP: {name} grouped derivation mismatch")


def main() -> None:
    names = sys.argv[1:] or ["635", "644", "c647"]
    g0 = time.time()
    for nm in names:
        derive(nm)
    print(f"\nall grouped derivations done in {time.time()-g0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
