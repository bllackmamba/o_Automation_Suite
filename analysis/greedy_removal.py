"""
Order-independence of R's sequential-intersection REMOVAL filter (read-only).

Different question from analysis/greedy_cover.py (union coverage, unique 4,368).
Here each step INTERSECTS the Repeat pool with a chosen R row's match-set and we
watch the size trajectory for a plateau-then-cliff, and whether that shape is the
same regardless of tie-break order.

Definitions (locked with Tai, 2026-08-08):
  - Universe = the 4,882,437 Repeat-pool combos (match_count(combo, D4687) >= 1).
  - covered(R) = NON-D4687 OVERLAP >=1: combo e is covered iff it shares >=1
    number with (set(R) minus D4687) — i.e. overlap on the DISCRIMINATING numbers,
    factoring out the guaranteed D4687 hit. (Plain match>=1 is a structural no-op
    here: every Repeat_R row contains all of D4687, so every U-combo trivially
    matches it >=1. Verified: |row ∩ D4687| == 6 for all 6,885 rows.)
    Pure-D4687 rows (empty discriminating set) are excluded as non-filters.
  - Step: pool = pool ∩ covered(R). Objective REMOVE-MOST: pick the row that
    shrinks the pool furthest, i.e. maximizes removed(R) = #pool combos sharing 0
    with R (= min surviving |pool ∩ covered(R)|).
  - No preset stop: run until no row removes anything (or pool empties); record
    the pool size after EVERY step.

Combos are 45-bit uint64 masks: removed(R) = #{pool_masks & R_mask == 0}.
Every step calls the standing Rule-1 checker (analysis.pool_invariant).
Gate: match_count>=1 reproduces Match_Matrix_969 on the 969 real draws first.

Read-only. `python3 -m analysis.greedy_removal`.
"""
from __future__ import annotations

import csv
import heapq
import math
import random
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import openpyxl

from analysis.greedy_cover import load_repeat_r, RXLSX, POOL, PICK, N
from analysis.pool_invariant import (assert_pool_invariant_array,
                                     REFGROUP_D4687, PoolInvariantViolation)

REPO = Path(__file__).resolve().parent.parent
B1 = REPO / "Games/SAT/Variable_inputs_sat/Base_sat/B1_sat_updated.csv"
MATRIX = REPO.parent / "info" / "Match_Matrix_969.xlsx"
D4687 = sorted(REFGROUP_D4687)
SAMPLE_INV = 2000


def numbers_to_mask(nums) -> int:
    m = 0
    for n in nums:
        m |= (1 << (int(n) - 1))
    return m


# ── validation gate: match>=1 reproduces Match_Matrix_969 on the 969 draws ────
def validate_match_ge1() -> bool:
    rows = load_repeat_r_with_id()
    b1 = []
    for r in csv.DictReader(B1.open()):
        b1.append([int(r[f"pos_{i}"]) for i in range(1, 7) if r.get(f"pos_{i}")])
    draws = np.array(b1[1:970], dtype=np.int64)              # W1..W969 = w2..w970
    wb = openpyxl.load_workbook(MATRIX, read_only=True, data_only=True)
    ws = wb["Repeat_MatchMatrix"]
    mh = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    wcol = [i for i, h in enumerate(mh) if isinstance(h, str) and h.startswith("W")]
    mid = mh.index("Row_ID")
    mism = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        rid = r[mid]
        stored = np.array([int(r[i] or 0) for i in wcol])      # full match count 0-6
        S = set(rows[rid])
        mask = np.zeros(46, dtype=bool)
        for n in S:
            mask[n] = True
        got = mask[draws].sum(axis=1)
        mism += int((got != stored).sum())
    wb.close()
    print(f"[GATE full match] mismatches vs Match_Matrix_969 (Repeat, 6885x969): "
          f"{mism} -> {mism == 0}  (non-D4687-overlap relation derived from this)",
          flush=True)
    return mism == 0


def load_repeat_r_with_id():
    wb = openpyxl.load_workbook(RXLSX, read_only=True, data_only=True)
    ws = wb["Repeat_R"]
    hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    ix = {h: i for i, h in enumerate(hdr)}
    pos = [i for h, i in ix.items() if isinstance(h, str) and h.startswith("pos_")]
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        out[r[ix["Row_ID"]]] = sorted({int(r[i]) for i in pos
                                       if r[i] not in (None, "", "None")})
    wb.close()
    return out


# ── build the Repeat pool as uint64 masks + number arrays ─────────────────────
def build_pool():
    d4687_mask = numbers_to_mask(D4687)
    masks = np.empty(N, dtype=np.uint64)
    nums = np.empty((N, 6), dtype=np.uint8)
    t0 = time.time()
    i = 0
    for c in combinations(range(1, POOL + 1), 6):
        m = ((1 << (c[0]-1)) | (1 << (c[1]-1)) | (1 << (c[2]-1))
             | (1 << (c[3]-1)) | (1 << (c[4]-1)) | (1 << (c[5]-1)))
        masks[i] = m
        nums[i] = c
        i += 1
    inU = (masks & np.uint64(d4687_mask)) != 0
    pm, pn = masks[inU], nums[inU]
    print(f"  pool built: {pm.size:,} U-combos in {time.time()-t0:.0f}s", flush=True)
    return pm, pn


# ── tie-break variants (same as greedy_cover + 3 random seeds) ────────────────
def tiebreak_keys(rows):
    n = len(rows)
    order_numlex = sorted(range(n), key=lambda i: rows[i]["nums"])
    numlex = [0]*n
    for p, i in enumerate(order_numlex):
        numlex[i] = p
    keys = {
        "V1_gen_rainbow":     [rows[i]["wnum"] for i in range(n)],
        "V2_gen_rainbow_rev": [-rows[i]["wnum"] for i in range(n)],
        "V3_len_asc_then_w":  [rows[i]["len"]*10**7 + rows[i]["wnum"] for i in range(n)],
        "V4_numbers_lex":     [numlex[i] for i in range(n)],
    }
    for seed in (1, 7, 42):
        perm = list(range(n)); random.Random(seed).shuffle(perm)
        keys[f"R{seed}_random"] = perm
    return keys


# ── lazy greedy remove-most under one tie-break ───────────────────────────────
def removal_chain(pool_masks, pool_nums, Rmask, tb, rem0, variant, cand):
    pm = pool_masks.copy(); pn = pool_nums.copy()
    heap = [(-rem0[i], tb[i], i) for i in cand]
    heapq.heapify(heap)
    applied = set(); order = []; traj = [int(pm.size)]
    t0 = time.time()
    while heap:
        neg, tbv, i = heapq.heappop(heap)
        if i in applied:
            continue
        rem = int(((pm & Rmask[i]) == np.uint64(0)).sum())   # #pool combos sharing 0 with row i
        entry = (-rem, tbv, i)
        if heap and entry > heap[0]:
            heapq.heappush(heap, entry); continue
        if rem == 0:
            break                                   # nothing removes anything → stable
        # SELECT i: keep combos sharing >=1 with row i
        surv = (pm & Rmask[i]) != np.uint64(0)
        pm = pm[surv]; pn = pn[surv]
        applied.add(i); order.append(i); traj.append(int(pm.size))
        # standing Rule-1 invariant on the SURVIVING pool (Repeat stream)
        if pn.size:
            smp = pn if pn.shape[0] <= SAMPLE_INV else \
                pn[np.linspace(0, pn.shape[0]-1, SAMPLE_INV).astype(int)]
            assert_pool_invariant_array(
                smp.astype(np.int32), "Repeat",
                step_label=f"{variant} step {len(order)} (row {i})")
        if pm.size == 0:
            break
    return {"traj": traj, "order": order, "final": int(pm.size),
            "steps": len(order), "secs": time.time()-t0}


def removal_chain_least(pool_masks, pool_nums, Rmask, tb, rem0, variant, cand):
    """REMOVE-LEAST (gentlest filter): each step apply the row that removes the
    FEWEST combos while still removing >0 (= max survivors with removed>0). CELF
    on survivors (monotone decreasing as pool shrinks). Rows whose covered-set
    already contains the whole pool (removed==0) are permanent no-ops → discarded.
    At most len(cand) steps (each row applied once)."""
    pm = pool_masks.copy(); pn = pool_nums.copy()
    Nfull = int(pm.size)
    # key = (-survivors, tb, i); survivors0 = Nfull - rem0
    heap = [(-(Nfull - int(rem0[i])), tb[i], i) for i in cand]
    heapq.heapify(heap)
    applied = set(); order = []; traj = [int(pm.size)]
    t0 = time.time()
    while heap:
        neg, tbv, i = heapq.heappop(heap)
        if i in applied:
            continue
        surv = int(((pm & Rmask[i]) != np.uint64(0)).sum())
        entry = (-surv, tbv, i)
        if heap and entry > heap[0]:                 # survivors dropped → stale
            heapq.heappush(heap, entry); continue
        removed = int(pm.size) - surv
        if removed == 0:
            continue                                 # permanent no-op → discard
        # SELECT i (gentlest real filter): keep combos sharing >=1 non-D4687 with i
        keep = (pm & Rmask[i]) != np.uint64(0)
        pm = pm[keep]; pn = pn[keep]
        applied.add(i); order.append(i); traj.append(int(pm.size))
        if pn.size:
            smp = pn if pn.shape[0] <= SAMPLE_INV else \
                pn[np.linspace(0, pn.shape[0]-1, SAMPLE_INV).astype(int)]
            assert_pool_invariant_array(
                smp.astype(np.int32), "Repeat",
                step_label=f"{variant}(least) step {len(order)} (row {i})")
        if pm.size == 0:
            break
    return {"traj": traj, "order": order, "final": int(pm.size),
            "steps": len(order), "secs": time.time()-t0}


def plateau_report(traj):
    """Describe the shape: biggest single-step drop (cliff) and longest near-flat
    run (plateau, <1% relative change)."""
    drops = [(traj[k]-traj[k+1], k+1) for k in range(len(traj)-1)]
    cliff = max(drops) if drops else (0, 0)
    # longest plateau: consecutive steps where relative shrink < 1%
    best_len = cur = 0; best_start = 0; start = 0
    for k in range(len(traj)-1):
        rel = (traj[k]-traj[k+1]) / traj[k] if traj[k] else 0
        if rel < 0.01:
            if cur == 0:
                start = k
            cur += 1
            if cur > best_len:
                best_len, best_start = cur, start
        else:
            cur = 0
    return cliff, (best_start, best_len)


def main():
    print("Validating match>=1 covered-set vs Match_Matrix_969 …", flush=True)
    if not validate_match_ge1():
        print("GATE FAILED — aborting."); return
    rows = load_repeat_r()
    d4687 = set(D4687)
    # DISCRIMINATING covered-set: overlap on NON-D4687 numbers only (match>=2).
    # Rows whose numbers are exactly D4687 (no discriminating numbers) are
    # excluded — their covered-set is empty and would annihilate the pool.
    Rmask = np.array([numbers_to_mask(set(r["nums"]) - d4687) for r in rows],
                     dtype=np.uint64)
    cand = [i for i in range(len(rows)) if Rmask[i] != np.uint64(0)]
    print(f"discriminating rows (non-empty set(R)\\D4687): {len(cand)}/{len(rows)} "
          f"(excluded {len(rows)-len(cand)} pure-D4687 row(s))", flush=True)
    print("Building Repeat pool (uint64 masks) …", flush=True)
    pool_masks, pool_nums = build_pool()
    print("Computing initial removed(R) on full pool …", flush=True)
    t0 = time.time()
    rem0 = np.zeros(len(rows), dtype=np.int64)
    for i in cand:
        rem0[i] = int(((pool_masks & Rmask[i]) == np.uint64(0)).sum())
    print(f"  rem0 in {time.time()-t0:.0f}s; max removable step-1 = {rem0.max():,}",
          flush=True)

    mode = sys.argv[1] if len(sys.argv) > 1 else "most"
    chain = removal_chain_least if mode == "least" else removal_chain
    print(f"\n### OBJECTIVE: remove-{mode} ###", flush=True)
    keys = tiebreak_keys(rows)
    results = {}
    for variant, tb in keys.items():
        print(f"\n── removal variant {variant} (remove-{mode}) ──", flush=True)
        try:
            res = chain(pool_masks, pool_nums, Rmask, tb, rem0, variant, cand)
        except PoolInvariantViolation as e:
            print(f"  !!! INVARIANT VIOLATION: {e}", flush=True)
            results[variant] = {"violation": str(e)}; continue
        cliff, plat = plateau_report(res["traj"])
        print(f"  steps={res['steps']}  final_pool={res['final']:,}  {res['secs']:.0f}s")
        print(f"  biggest drop (cliff)={cliff[0]:,} at step {cliff[1]}; "
              f"longest plateau (<1%/step): {plat[1]} steps from step {plat[0]}")
        tail = res["traj"][-30:]
        print(f"  trajectory tail (last {len(tail)}): {tail}")
        for tgt in (661, 211, 20):
            hits = [k for k, v in enumerate(res["traj"]) if v == tgt]
            if hits:
                print(f"    ** pool == {tgt} at step(s) {hits}", flush=True)
        results[variant] = res

    # ── cross-variant comparison ──
    print("\n" + "=" * 70)
    print("CROSS-VARIANT (removal chain)")
    good = {v: r for v, r in results.items() if "violation" not in r}
    print("final pool sizes:", {v: r["final"] for v, r in good.items()})
    print("step counts:     ", {v: r["steps"] for v, r in good.items()})
    vs = list(good)
    print("\npairwise APPLIED-ROW-set Jaccard (which rows got used):")
    for a in range(len(vs)):
        for b in range(a+1, len(vs)):
            A, B = set(good[vs[a]]["order"]), set(good[vs[b]]["order"])
            j = len(A & B)/len(A | B) if (A | B) else 1.0
            print(f"  {vs[a]} vs {vs[b]}: |A|={len(A)} |B|={len(B)} "
                  f"∩={len(A&B)} Jaccard={j:.3f}")
    # save trajectories
    out = REPO / "analysis" / f"greedy_removal_{mode}_trajectories.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["variant", "step", "pool_size"])
        for v, r in good.items():
            for k, s in enumerate(r["traj"]):
                w.writerow([v, k, s])
    print(f"\ntrajectories → {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
