# -*- coding: utf-8 -*-
"""
run_1nplus1.py — 1n+1 ("increase", target = input_length + 1) for the
635 / 644 / c647 files, reusing the VERIFIED efficient algorithm from
run_increase_efficient.py unchanged (candidate-target enumeration with
>=2 unclaimed children threshold, first-come exclusive claiming).

- Input rows are canonicalized to sorted-ascending by load_rows (handles the
  non-canonical 635/644 row order automatically).
- Outputs (core/), no "+" in names, "_1nplus1" infix:
    {name}_1nplus1_regenerate.csv  -> columns n1..n7, unique NLists
    {name}_1nplus1_remnant.csv     -> columns n1..n6, unassigned input rows
  (grouped/children file intentionally skipped)
- Each file is checked against independently pre-computed EXPECTED values.
  ANY mismatch -> hard stop (SystemExit), no further files processed.

Read-only on all existing inputs.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from run_increase_efficient import (
    CORE,
    ChunkWriter,
    load_rows,
    run_increase,
    selftest,
)

N = 6
TARGET = 7

# (filename, has_header)
FILES = [
    ("635.csv", False),
    ("644.csv", False),
    ("c647.csv", True),
]

# Independently pre-computed verification values — exact match required.
EXPECTED = {
    "635":  {"nlists": 736_576,   "utilised": 1_623_160,  "remnant": 0},
    "644":  {"nlists": 3_274_194, "utilised": 7_059_051,  "remnant": 1},
    "c647": {"nlists": 5_006_617, "utilised": 10_737_573, "remnant": 0},
}


def run_one(fname: str, has_header: bool) -> dict:
    path = CORE / fname
    prefix = path.stem
    exp = EXPECTED[prefix]

    print(f"\n{'='*64}\n{fname}  (n={N}, target={TARGET}, diff=1)\n{'='*64}")
    t0 = time.time()

    print("loading input (canonicalizing rows to sorted-ascending)...")
    rows, dup = load_rows(path, has_header, N)
    print(f"  input rows: {len(rows):,}  (duplicate lines collapsed: {dup:,})")
    pool = sorted({v for r in rows for v in r})
    print(f"  number pool: {pool[0]}..{pool[-1]} ({len(pool)} values)")
    n_cands = 1
    for i in range(TARGET):
        n_cands = n_cands * (len(pool) - i) // (i + 1)
    print(f"  candidate NLists to scan C({len(pool)},{TARGET}): {n_cands:,}")

    regenerate = ChunkWriter(CORE / f"{prefix}_1nplus1_regenerate.csv")
    regenerate.write([f"n{i+1}" for i in range(TARGET)])

    def on_group(nlist, kids):
        regenerate.write(list(nlist))

    def on_progress(seen, n_nl, n_assigned):
        el = time.time() - t0
        print(f"  ...{seen:,} scanned | NLists={n_nl:,} | "
              f"assigned={n_assigned:,} | {el:.0f}s", flush=True)

    nlists, remnant = run_increase(
        rows, N, TARGET, on_group=on_group, on_progress=on_progress)
    regenerate.close()

    print("writing remnant...")
    rem = ChunkWriter(CORE / f"{prefix}_1nplus1_remnant.csv")
    rem.write([f"n{i+1}" for i in range(N)])
    for r in sorted(remnant):
        rem.write(list(r))
    rem.close()

    utilised = len(rows) - len(remnant)
    dt = time.time() - t0

    reg_path = CORE / f"{prefix}_1nplus1_regenerate.csv"
    rem_path = CORE / f"{prefix}_1nplus1_remnant.csv"
    with reg_path.open() as f:
        reg_lines = [ln.rstrip("\n") for ln in f][1:]  # drop header

    got = {"nlists": len(nlists), "utilised": utilised, "remnant": len(remnant)}
    ok = got == exp

    print(f"\n{'-'*64}\nVERIFICATION — {prefix}\n{'-'*64}")
    print(f"  input rows            : {len(rows):,}")
    print(f"  NLists                : {got['nlists']:,}   "
          f"(expected {exp['nlists']:,}  {'OK' if got['nlists']==exp['nlists'] else 'MISMATCH'})")
    print(f"  utilised (children)   : {got['utilised']:,}   "
          f"(expected {exp['utilised']:,}  {'OK' if got['utilised']==exp['utilised'] else 'MISMATCH'})")
    print(f"  remnant               : {got['remnant']:,}   "
          f"(expected {exp['remnant']:,}  {'OK' if got['remnant']==exp['remnant'] else 'MISMATCH'})")
    print(f"  utilised+remnant      : {utilised+len(remnant):,} "
          f"(== input? {utilised+len(remnant)==len(rows)})")
    print(f"  regenerate rows       : {len(reg_lines):,} "
          f"(== NLists? {len(reg_lines)==len(nlists)})")
    print(f"  regenerate header     : n1..n{TARGET}")
    print(f"  regenerate first 3    : {reg_lines[:3]}")
    print(f"  regenerate last 3     : {reg_lines[-3:]}")
    print(f"  {reg_path.name:36s}: {reg_path.stat().st_size/1_048_576:.2f} MB")
    print(f"  {rem_path.name:36s}: {rem_path.stat().st_size/1_048_576:.2f} MB")
    print(f"  time                  : {dt:.1f}s ({dt/60:.1f} min)")
    print(f"  RESULT                : {'PASS' if ok else 'FAIL'}")

    if not ok:
        print(f"\n!!! STOP: {prefix} mismatch vs expected. got={got} expected={exp}",
              flush=True)
        raise SystemExit(2)

    return {"prefix": prefix, **got, "input": len(rows), "dt": dt,
            "reg_mb": reg_path.stat().st_size/1_048_576,
            "rem_mb": rem_path.stat().st_size/1_048_576}


def main() -> None:
    print("self-test: validating efficient algo vs brute reference...")
    selftest()
    results = []
    grand0 = time.time()
    for fname, has_header in FILES:
        results.append(run_one(fname, has_header))
    grand = time.time() - grand0

    print(f"\n{'#'*64}\nALL THREE PASSED — SUMMARY\n{'#'*64}")
    print(f"{'file':10s} {'input':>12s} {'NLists':>12s} {'utilised':>12s} "
          f"{'remnant':>8s} {'reg_MB':>9s} {'rem_MB':>8s} {'time_s':>8s}")
    for r in results:
        print(f"{r['prefix']:10s} {r['input']:>12,} {r['nlists']:>12,} "
              f"{r['utilised']:>12,} {r['remnant']:>8,} {r['reg_mb']:>9.2f} "
              f"{r['rem_mb']:>8.2f} {r['dt']:>8.1f}")
    print(f"total wall time: {grand:.1f}s ({grand/60:.1f} min)")


if __name__ == "__main__":
    main()
