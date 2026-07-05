# -*- coding: utf-8 -*-
"""
run_decrease_contributing.py — PART 1 (set-based, proven c745 approach).

For each parent row (file order), generate its child_k = parent_k-1 subsets
(canonicalized ascending). Under first-claim exclusivity, a child belongs to
the first parent that claims it. A parent that claims >=1 NEW child is
"contributing"; one that claims zero new children is non-contributing.

Outputs (core/):
  {name}_contributing_input.csv  — parent rows that claimed >=1 new child,
                                    original column format (input header kept)
Zero-claim rows are counted but not written (large; see report).

Read-only on all inputs.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

CORE = Path(__file__).resolve().parent
CHUNK = 200_000

# name -> (filename, parent_k, has_header, expected_total, expected_contributing)
CONFIGS = {
    "c745": ("c745.csv", 7, False, 45_379_620, 7_059_052),
    "combinations_8_35": ("combinations_8_35.csv", 8, True, 23_535_820, 5_379_616),
}


def run(name: str) -> dict:
    fname, parent_k, has_header, exp_total, exp_contrib = CONFIGS[name]
    src = CORE / fname
    out = CORE / f"{name}_contributing_input.csv"
    print(f"\n{'='*60}\n{name}: {fname}  (parent_k={parent_k}, child_k={parent_k-1})\n{'='*60}",
          flush=True)
    t0 = time.time()

    claimed: set[tuple[int, ...]] = set()
    total = 0
    contributing = 0
    zero = 0
    buf: list[str] = []

    with src.open() as f, out.open("w", newline="") as w:
        header = None
        if has_header:
            header = next(f).rstrip("\n")
            w.write(header + "\n")

        for line in f:
            raw = line.rstrip("\n")
            if not raw:
                continue
            total += 1
            p = tuple(sorted(int(x) for x in raw.split(",")))
            # child_k subsets = p with one element removed (stays sorted)
            new_claim = False
            for i in range(parent_k):
                child = p[:i] + p[i + 1:]
                if child not in claimed:
                    claimed.add(child)
                    new_claim = True
            if new_claim:
                contributing += 1
                buf.append(raw)
                if len(buf) >= CHUNK:
                    w.write("\n".join(buf) + "\n")
                    buf.clear()
            else:
                zero += 1
            if total % 5_000_000 == 0:
                print(f"  ...{total:,} parents | contributing={contributing:,} | "
                      f"claimed_children={len(claimed):,} | {time.time()-t0:.0f}s", flush=True)
        if buf:
            w.write("\n".join(buf) + "\n")

    dt = time.time() - t0
    size_mb = out.stat().st_size / 1_048_576
    ok = (total == exp_total and contributing == exp_contrib)

    print(f"\n{'-'*60}\nVERIFICATION — {name}\n{'-'*60}", flush=True)
    print(f"  total input rows    : {total:,}   (expected {exp_total:,}  "
          f"{'OK' if total == exp_total else 'MISMATCH'})", flush=True)
    print(f"  contributing parents: {contributing:,}   (expected {exp_contrib:,}  "
          f"{'OK' if contributing == exp_contrib else 'MISMATCH'})", flush=True)
    print(f"  zero-claim parents  : {zero:,}   (= total - contributing: "
          f"{total - contributing == zero})", flush=True)
    print(f"  distinct children   : {len(claimed):,}", flush=True)
    print(f"  {out.name}: {size_mb:.2f} MB", flush=True)
    print(f"  time                : {dt:.1f}s ({dt/60:.1f} min)", flush=True)
    print(f"  RESULT              : {'PASS' if ok else 'FAIL'}", flush=True)

    if not ok:
        raise SystemExit(f"!!! STOP: {name} mismatch — contributing={contributing} "
                         f"expected={exp_contrib}, total={total} expected={exp_total}")

    return {"name": name, "total": total, "contributing": contributing,
            "zero": zero, "mb": size_mb, "dt": dt}


def main() -> None:
    names = sys.argv[1:] or ["c745", "combinations_8_35"]
    g0 = time.time()
    results = [run(n) for n in names]
    print(f"\n{'#'*60}\nPART 1 SUMMARY\n{'#'*60}")
    print(f"{'file':22s} {'total':>13s} {'contributing':>13s} {'zero':>13s} "
          f"{'MB':>9s} {'s':>8s}")
    for r in results:
        print(f"{r['name']:22s} {r['total']:>13,} {r['contributing']:>13,} "
              f"{r['zero']:>13,} {r['mb']:>9.2f} {r['dt']:>8.1f}")
    print(f"total wall: {time.time()-g0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
