"""
Repeat / no-repeat regime vs SL-group contribution — read-only analysis.

Tests Tai's hypothesis (from a 10-column Stacked-Draws window) at full-history
scale, controlling for group SIZE:
  repeat draws   -> winners from SL groups 1–2 ?
  no-repeat draws-> winners from everywhere except group 2 ?

Definitions (reuse syndicate_core.stacked_blocks — no second SL/repeat impl):
- A winner's SL group is its since-last value RELATIVE TO THE PREDECESSOR draw
  P (the block it vacates in P's all_wt skeleton when D is drawn — the
  Blocked-flat "newest column" sense). So repeat winners (in P) sit in SL0,
  fresh winners in SL>=1. This is since_last_map(index_of_P).
- Repeat draw: D shares >=1 number with P  <=>  deep_repeats(index_of_D) != {}.
- Group size at D = number of pool numbers sharing each SL value rel P.
- "unseen": a number never seen in the pre-D history (from P backwards) has no
  real SL rel P (since_last_map would give a P-position-dependent sentinel that
  contaminates numeric buckets for the oldest, thin-history draws). Bucketed
  separately as sl_group="unseen" and flagged.

Output: analysis/sl_group_regime_contribution.csv + a printed summary.
Read-only: touches no tracked code/CSV.
"""
from __future__ import annotations

import csv
import ast
import math
from collections import defaultdict
from pathlib import Path

from syndicate_core.stacked_blocks import since_last_map, deep_repeats

REPO = Path(__file__).resolve().parent.parent
HIST_PATH = REPO / "Games" / "SAT" / "SinceLast_sat" / "draw_history.csv"
OUT_CSV = REPO / "analysis" / "sl_group_regime_contribution.csv"
POOL = 45
PICK = 6
THIN = 20  # flag SL groups whose rate rests on fewer than this many draws


def load_history() -> list[dict]:
    """Newest-first list of {draw, nums} (same shape stacked_blocks expects)."""
    rows: list[dict] = []
    with HIST_PATH.open() as f:
        for r in csv.DictReader(f):
            rows.append({"draw": r["draw"].strip(),
                         "nums": set(ast.literal_eval(r["numbers"]))})
    return rows


def group_key_map(p_idx: int, history: list[dict]) -> dict[int, object]:
    """SL group rel predecessor P (history[p_idx]) for every pool number, with
    numbers never seen from P backwards bucketed as 'unseen'."""
    slmap = since_last_map(p_idx, history, POOL)
    seen: set[int] = set()
    for q in range(p_idx, len(history)):
        seen |= history[q]["nums"]
    return {n: (slmap[n] if n in seen else "unseen") for n in range(1, POOL + 1)}


def validate(history: list[dict], idx: dict[str, int]) -> None:
    """Fixture-anchored sanity check: D4691's winners map to their known SL
    groups rel D4689 (from verified fixtures 8.1/8.3), and D4691 is a repeat."""
    if "4691" not in idx or "4689" not in idx:
        print("  [validate] D4691/D4689 not both present — skipping fixture check")
        return
    di = idx["4691"]
    keys = group_key_map(idx["4689"], history)   # rel predecessor D4689
    got = {w: keys[w] for w in sorted(history[di]["nums"])}
    expected = {4: 12, 8: 4, 15: 0, 32: 6, 43: 2, 44: 3}
    assert got == expected, f"validation mismatch: {got} != {expected}"
    assert bool(deep_repeats(di, history)) is True, "D4691 should be a repeat draw"
    print(f"  [validate] D4691 winners -> SL rel D4689 = {got}  (repeat=True)  OK")


def main() -> None:
    history = load_history()
    idx = {r["draw"]: i for i, r in enumerate(history)}
    n = len(history)
    print(f"Loaded {n} draws from {HIST_PATH.name} "
          f"(newest D{history[0]['draw']} … oldest D{history[-1]['draw']}).")
    validate(history, idx)

    # aggregation keyed by (sl_group, regime)
    raw_winners: dict = defaultdict(int)       # winners landing in group
    sum_gsize: dict = defaultdict(int)         # Σ group size over draws present
    n_present: dict = defaultdict(int)         # # draws where group is non-empty
    regime_draws = {"repeat": 0, "no_repeat": 0}

    # walk oldest->newest; every draw except the oldest (index n-1) has a
    # predecessor at index+1 (older neighbour in newest-first history).
    for i in range(0, n - 1):
        p_idx = i + 1
        regime = "repeat" if deep_repeats(i, history) else "no_repeat"
        regime_draws[regime] += 1

        keys = group_key_map(p_idx, history)
        gsize: dict = defaultdict(int)
        for n_ in range(1, POOL + 1):
            gsize[keys[n_]] += 1
        for g, sz in gsize.items():
            sum_gsize[(g, regime)] += sz
            n_present[(g, regime)] += 1
        for w in history[i]["nums"]:
            raw_winners[(keys[w], regime)] += 1

    # sanity: every winner counted once
    total_winners = sum(raw_winners.values())
    assert total_winners == PICK * (n - 1), (total_winners, PICK * (n - 1))

    # ── write CSV ──
    def sort_key(g):
        return (1, 0) if g == "unseen" else (0, g)

    all_keys = sorted({g for (g, _r) in sum_gsize}, key=sort_key)
    rows_out = []
    for regime in ("repeat", "no_repeat"):
        for g in all_keys:
            if (g, regime) not in sum_gsize:
                continue
            present = n_present[(g, regime)]
            ssize = sum_gsize[(g, regime)]
            raw = raw_winners[(g, regime)]
            avg_gsize = ssize / present if present else 0.0
            expected = PICK * ssize / POOL          # Σ_D 6·size/45
            rate = raw / expected if expected else float("nan")
            rows_out.append({
                "sl_group": g,
                "regime": regime,
                "n_draws_in_regime": regime_draws[regime],
                "raw_winner_count": raw,
                "avg_group_size": round(avg_gsize, 3),
                "expected_winner_count_if_uniform": round(expected, 3),
                "normalized_rate": round(rate, 3),
                "n_draws_group_present": present,
            })

    OUT_CSV.parent.mkdir(exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nWrote {len(rows_out)} rows -> {OUT_CSV.relative_to(REPO)}")

    # ── printed summary ──
    n_draws = n - 1
    p_norepeat_theo = math.comb(POOL - PICK, PICK) / math.comb(POOL, PICK)
    obs_norepeat = regime_draws["no_repeat"] / n_draws
    print("\n" + "=" * 68)
    print("REGIME SPLIT (draws with a predecessor: %d)" % n_draws)
    print(f"  repeat   : {regime_draws['repeat']:3d}  ({regime_draws['repeat']/n_draws:.1%})")
    print(f"  no_repeat: {regime_draws['no_repeat']:3d}  ({obs_norepeat:.1%})")
    print(f"  theoretical no-repeat P(0 shared) = C(39,6)/C(45,6) = {p_norepeat_theo:.2%}")

    def top(regime, over=True):
        items = [r for r in rows_out if r["regime"] == regime
                 and not math.isnan(r["normalized_rate"])]
        items.sort(key=lambda r: r["normalized_rate"], reverse=over)
        return items[:5]

    for regime in ("repeat", "no_repeat"):
        print("\n" + "-" * 68)
        print(f"{regime.upper()} — normalized contribution rate (1.0 = size-neutral)")
        print(f"  {'SLgrp':>6} {'rate':>7} {'raw':>5} {'avgSize':>8} "
              f"{'exp':>7} {'nDraws':>7}")
        items = [r for r in rows_out if r["regime"] == regime]
        items.sort(key=lambda r: (r["sl_group"] == "unseen", r["sl_group"]))
        for r in items:
            flag = "  <-thin" if r["n_draws_group_present"] < THIN else ""
            rate = "nan" if math.isnan(r["normalized_rate"]) else f"{r['normalized_rate']:.2f}"
            print(f"  {str(r['sl_group']):>6} {rate:>7} {r['raw_winner_count']:>5} "
                  f"{r['avg_group_size']:>8.2f} {r['expected_winner_count_if_uniform']:>7.1f} "
                  f"{r['n_draws_group_present']:>7}{flag}")

    # explicit hypothesis tests
    print("\n" + "=" * 68)
    print("HYPOTHESIS CHECK")
    def rate_of(g, regime):
        for r in rows_out:
            if r["sl_group"] == g and r["regime"] == regime:
                return r["normalized_rate"], r["n_draws_group_present"]
        return None, 0
    for g in (1, 2, 3):
        rr, rn = rate_of(g, "repeat")
        nr, nn = rate_of(g, "no_repeat")
        print(f"  SL{g}: repeat rate={rr}  (n={rn}) | no_repeat rate={nr} (n={nn})")


if __name__ == "__main__":
    main()
