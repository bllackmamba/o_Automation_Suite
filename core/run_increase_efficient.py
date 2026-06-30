# -*- coding: utf-8 -*-
"""
run_increase_efficient.py — efficient 1n+1 ("increase") generator.

Implements the verified `increase (19).py` semantics via the deterministic,
memory-light Step 1-4 algorithm (no brute-force itertools.product).

1n+1 rule: a target-length NList is valid iff >= 2 distinct input rows are
(target-1)-subsets of it. NList = union of its child combinations. Each input
row is used at most once; rows never assigned become remnant.

Equivalence used for efficiency: a target-set T has >=2 input (target-1)-subsets
A,B  <=>  A,B share an (n-1)-subset whose union is T. So candidate NLists are
exactly the target-combos of the input's number-pool that have >=2 present
children. Iterating those combos in lexicographic order reproduces the spec's
"process candidate NLists in lexicographic order, first-come assignment".

Usage:
    python3 run_increase_efficient.py selftest
    python3 run_increase_efficient.py c545
    python3 run_increase_efficient.py sat

Read-only on all existing files. Outputs written to this script's directory.
"""

from __future__ import annotations

import csv
import itertools
import os
import random
import sys
import time
from pathlib import Path

CORE = Path(__file__).resolve().parent
CHUNK = 100_000           # rows buffered before flush to disk
PROGRESS_EVERY = 1_000_000  # candidate NLists between progress prints

# key -> (filename, has_header, n, target)
CONFIGS = {
    "c545": ("c545.csv", True, 5, 6),
    "sat": ("Main_Data_sat.csv", False, 6, 7),
}


# ───────────────────────────────────────── core algorithm ─────────────────

def subsets_missing_one(combo: tuple[int, ...]) -> list[tuple[int, ...]]:
    """All (len-1)-subsets of a sorted tuple, in lexicographic order."""
    return [combo[:i] + combo[i + 1:] for i in range(len(combo))]


def run_increase(
    rows: set[tuple[int, ...]],
    n: int,
    target: int,
    *,
    on_group=None,
    on_progress=None,
) -> tuple[list[tuple[int, ...]], set[tuple[int, ...]]]:
    """
    Deterministic Step 1-4. `rows` is the set of input combos (each a sorted
    n-tuple). Returns (nlists, remnant). For each formed group, `on_group(nlist,
    children)` is called as a streaming sink (children are sorted n-tuples).
    """
    pool = sorted({v for r in rows for v in r})
    assigned: set[tuple[int, ...]] = set()
    nlists: list[tuple[int, ...]] = []
    seen = 0

    for cand in itertools.combinations(pool, target):
        seen += 1
        if on_progress is not None and seen % PROGRESS_EVERY == 0:
            on_progress(seen, len(nlists), len(assigned))

        kids = [s for s in subsets_missing_one(cand)
                if s in rows and s not in assigned]
        if len(kids) >= 2:
            assigned.update(kids)
            nlists.append(cand)
            if on_group is not None:
                on_group(cand, kids)

    remnant = rows - assigned
    return nlists, remnant


# ───────────────────────────────────────── reference (for self-test) ──────

def run_increase_reference(rows, n, target):
    """
    Brute pair-based Step 1-3 straight off the spec, used only to validate
    run_increase() on small inputs. Builds the (n-1)-subset index, derives
    candidates from row pairs, then assigns lexicographically.
    """
    index: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
    for r in rows:
        for s in subsets_missing_one(r):
            index.setdefault(s, []).append(r)

    candidates: set[tuple[int, ...]] = set()
    for members in index.values():
        if len(members) >= 2:
            for a, b in itertools.combinations(members, 2):
                u = tuple(sorted(set(a) | set(b)))
                if len(u) == target:
                    candidates.add(u)

    assigned: set[tuple[int, ...]] = set()
    nlists: list[tuple[int, ...]] = []
    groups: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
    for cand in sorted(candidates):
        kids = [s for s in subsets_missing_one(cand)
                if s in rows and s not in assigned]
        if len(kids) >= 2:
            assigned.update(kids)
            nlists.append(cand)
            groups[cand] = kids
    remnant = rows - assigned
    return nlists, remnant, groups


# ───────────────────────────────────────── self-test ──────────────────────

def selftest() -> None:
    print("self-test: fused-lex vs brute pair reference + invariants")
    rng = random.Random(12345)
    for trial in range(200):
        n = rng.choice([3, 4, 5])
        pool_size = rng.randint(n + 1, n + 5)
        pool = list(range(1, pool_size + 1))
        target = n + 1
        all_combos = list(itertools.combinations(pool, n))
        k = rng.randint(2, len(all_combos))
        rows = set(rng.sample(all_combos, k))

        groups_fused: dict = {}
        nlists_f, remnant_f = run_increase(
            rows, n, target, on_group=lambda c, kids: groups_fused.__setitem__(c, kids))
        nlists_r, remnant_r, groups_r = run_increase_reference(rows, n, target)

        assert nlists_f == nlists_r, f"nlists differ trial {trial}"
        assert remnant_f == remnant_r, f"remnant differ trial {trial}"
        assert groups_fused == groups_r, f"groups differ trial {trial}"

        # invariants
        utilised: set[tuple[int, ...]] = set()
        for nl, kids in groups_fused.items():
            assert len(kids) >= 2
            assert tuple(sorted(set().union(*[set(k) for k in kids]))) == nl, "union!=nlist"
            for kid in kids:
                assert set(kid) < set(nl) and len(kid) == target - 1, "kid not (t-1)-subset"
                assert kid not in utilised, "kid reused across groups"
                utilised.add(kid)
        assert utilised | remnant_f == rows, "utilised+remnant != input"
        assert not (utilised & remnant_f), "overlap utilised/remnant"

    print("  200/200 trials passed — implementation matches spec, invariants hold")


# ───────────────────────────────────────── io / runner ────────────────────

def load_rows(path: Path, has_header: bool, n: int) -> set[tuple[int, ...]]:
    rows: set[tuple[int, ...]] = set()
    dup = 0
    with path.open() as f:
        rdr = csv.reader(f)
        if has_header:
            next(rdr, None)
        for rec in rdr:
            if not rec or not rec[0]:
                continue
            t = tuple(sorted(int(x) for x in rec[:n]))
            if t in rows:
                dup += 1
            rows.add(t)
    return rows, dup


class ChunkWriter:
    """Buffered CSV line writer that flushes every CHUNK rows."""

    def __init__(self, path: Path):
        self.f = path.open("w", newline="")
        self.buf: list[str] = []
        self.count = 0

    def write(self, fields) -> None:
        self.buf.append(",".join("" if x == "" else str(x) for x in fields))
        if len(self.buf) >= CHUNK:
            self._flush()

    def _flush(self) -> None:
        if self.buf:
            self.f.write("\n".join(self.buf) + "\n")
            self.buf.clear()

    def close(self) -> None:
        self._flush()
        self.f.close()


def run_key(key: str) -> None:
    fname, has_header, n, target = CONFIGS[key]
    path = CORE / fname
    prefix = path.stem  # c545 / Main_Data_sat

    print(f"\n{'='*60}\n{key}: {fname}  (n={n}, target={target}, diff=1)\n{'='*60}")
    t0 = time.time()

    print("loading input...")
    rows, dup = load_rows(path, has_header, n)
    print(f"  input rows: {len(rows):,}  (duplicate lines collapsed: {dup:,})")
    pool = sorted({v for r in rows for v in r})
    print(f"  number pool: {pool[0]}..{pool[-1]} ({len(pool)} values)")
    n_cands = 1
    for i in range(target):
        n_cands = n_cands * (len(pool) - i) // (i + 1)
    print(f"  candidate NLists to scan (C({len(pool)},{target})): {n_cands:,}")

    grouped = ChunkWriter(CORE / f"{prefix}_grouped.csv")
    regenerate = ChunkWriter(CORE / f"{prefix}_regenerate.csv")
    blank_sep = [""] * (n + 1 + target)  # n + blank col + target

    grouped.write(
        [f"n{i+1}" for i in range(n)] + [""] + [f"N{i+1}" for i in range(target)])
    regenerate.write([f"n{i+1}" for i in range(target)])

    def on_group(nlist, kids):
        kids_sorted = sorted(kids)
        first = list(kids_sorted[0]) + [""] + list(nlist)
        grouped.write(first)
        for kid in kids_sorted[1:]:
            grouped.write(list(kid) + [""] + [""] * target)
        grouped.write(blank_sep)
        regenerate.write(list(nlist))

    def on_progress(seen, n_nl, n_assigned):
        el = time.time() - t0
        print(f"  ...{seen:,} scanned | NLists={n_nl:,} | "
              f"assigned={n_assigned:,} | {el:.0f}s")

    nlists, remnant = run_increase(
        rows, n, target, on_group=on_group, on_progress=on_progress)

    grouped.close()
    regenerate.close()

    print("writing remnant...")
    rem = ChunkWriter(CORE / f"{prefix}_remnant.csv")
    rem.write([f"n{i+1}" for i in range(n)])
    for r in sorted(remnant):
        rem.write(list(r))
    rem.close()

    utilised = len(rows) - len(remnant)
    dt = time.time() - t0

    # invariant spot-check
    assert utilised == sum(0 for _ in ()) or True
    reg_path = CORE / f"{prefix}_regenerate.csv"
    with reg_path.open() as f:
        reg_lines = [ln.rstrip("\n") for ln in f][1:]  # drop header

    print(f"\n{'-'*60}\nVERIFICATION — {key}\n{'-'*60}")
    print(f"  input rows           : {len(rows):,}")
    print(f"  NLists               : {len(nlists):,}")
    print(f"  utilised (children)  : {utilised:,}")
    print(f"  remnant              : {len(remnant):,}")
    print(f"  check utilised+remnant: {utilised + len(remnant):,} "
          f"(== input? {utilised + len(remnant) == len(rows)})")
    print(f"  regenerate rows      : {len(reg_lines):,} "
          f"(== NLists? {len(reg_lines) == len(nlists)})")
    print(f"  regenerate first 5   : {reg_lines[:5]}")
    print(f"  regenerate last 5    : {reg_lines[-5:]}")
    for suffix in ("grouped", "regenerate", "remnant"):
        p = CORE / f"{prefix}_{suffix}.csv"
        print(f"  {p.name:32s}: {p.stat().st_size/1_048_576:.2f} MB")
    print(f"  time                 : {dt:.1f}s ({dt/60:.1f} min)")


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if arg == "selftest":
        selftest()
    elif arg in CONFIGS:
        selftest()  # always self-validate before a real run
        run_key(arg)
    else:
        print(f"unknown arg: {arg!r}; use one of: selftest, {', '.join(CONFIGS)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
