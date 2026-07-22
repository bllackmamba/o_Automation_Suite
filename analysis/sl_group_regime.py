"""
Repeat / no-repeat regime vs SL-group contribution — read-only analysis.

Tests Tai's hypothesis (from a 10-column Stacked-Draws window) at full-history
scale, controlling for group SIZE:
  repeat draws   -> winners from SL groups 1–2 ?
  no-repeat draws-> winners from everywhere except group 2 ?

Definitions (reuse syndicate_core.stacked_blocks — no second SL/repeat impl):
- A winner's DECK GROUP is its BLOCK ORDINAL in P's frozen all_wt deck
  (block_layout(index_of_P)): the 1-based position of its SL block when the 45
  numbers are grouped by since-last value rel P and those groups are ordered
  ascending, with EMPTY SL values SKIPPED (gap-compressed — the deck-position
  sense, NOT the raw since-last distance). Group 1 = repeat winners (in P);
  group k = the k-th occupied SL block. This is the frozen-predecessor-deck rule
  (the block a number vacates when D is drawn), the same inherited-deck principle
  as the Stacked-Draws cascading fix (CLAUDE.md 2026-07-12). NB an earlier
  version keyed off the raw since_last_map distance, which over-counts groups
  above any empty SL slot (e.g. D4695's num 7 was labelled 20 instead of 16).
- Repeat draw: D shares >=1 number with P  <=>  deep_repeats(index_of_D) != {}.
- Group size at D = number of pool numbers in each occupied block rel P.
- "unseen": a number never seen in the pre-D history (from P backwards) has no
  real block rel P (it would fall in the deck's trailing sentinel block).
  Bucketed separately as deck_group="unseen" and flagged.

Output: analysis/sl_group_regime_contribution.csv + a printed summary.
Read-only: touches no tracked code/CSV.
"""
from __future__ import annotations

import csv
import ast
import math
from collections import defaultdict
from pathlib import Path

from syndicate_core.stacked_blocks import since_last_map, deep_repeats, block_layout
from syndicate_core.refgroup import classify_shared, selected_bands_for_pick

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
    """Deck group (block ordinal) rel predecessor P (history[p_idx]) for every
    pool number, with numbers never seen from P backwards bucketed as 'unseen'.

    The group is the number's 1-based BLOCK ORDINAL in P's frozen deck
    (block_layout): groups are the occupied SL blocks ordered ascending, so
    empty SL values are skipped (gap-compressed). Group 1 = numbers in P
    (repeats); group k = the k-th occupied block. This is the deck-position
    definition, NOT the raw since_last_map distance (which counts empty SL
    slots and so over-labels groups above any gap)."""
    blocks = block_layout(p_idx, history, POOL)   # SL-ascending, gap-compressed
    seen: set[int] = set()
    for q in range(p_idx, len(history)):
        seen |= history[q]["nums"]
    ordinal: dict[int, int] = {}
    for o, blk in enumerate(blocks, start=1):
        for num in blk:
            ordinal[num] = o
    return {n: (ordinal[n] if n in seen else "unseen") for n in range(1, POOL + 1)}


def per_draw_records(history: list[dict]) -> list[dict]:
    """One record per draw that has a predecessor (the oldest draw, index n-1,
    is excluded). Newest-first order preserved. Each record:
      {draw, index, repeat: bool, shared_count: int, regime_split: str,
       winner_groups: [(winner, deck_group), ...]}
    where deck_group is the winner's block ordinal in P's frozen deck (same
    convention/functions as the aggregate analysis; group 1 = repeat, 'unseen'
    bucketed). Reused by the presence/coverage follow-up so it shares this exact
    deck-group and repeat assignment rather than re-deriving from draw_history.csv.

    ``shared_count`` is how many numbers the draw shares with its immediately
    preceding draw (= ``len(deep_repeats(...))`` — the same repeat mechanism, no
    second classifier). ``regime_split`` re-expresses the regime under the LOCKED
    Repeat/No_repeat split (Selected = {1..PICK-3}): "Repeat" iff the shared
    count is a Selected band, else "No_repeat". This differs from the plain
    ``repeat`` binary (shares >=1) only in the extreme tail — a draw sharing
    >= PICK-2 numbers with its predecessor is No_repeat under the locked split.
    """
    n = len(history)
    records: list[dict] = []
    for i in range(0, n - 1):
        keys = group_key_map(i + 1, history)          # rel predecessor P
        wg = [(w, keys[w]) for w in sorted(history[i]["nums"])]
        shared = len(deep_repeats(i, history))        # vs immediate predecessor
        records.append({
            "draw": history[i]["draw"],
            "index": i,
            "repeat": bool(deep_repeats(i, history)),
            "shared_count": shared,
            "regime_split": classify_shared(shared, PICK),
            "winner_groups": wg,
        })
    return records


def validate(history: list[dict], idx: dict[str, int]) -> None:
    """Fixture-anchored sanity check: D4691's winners map to their known DECK
    GROUPS (block ordinals) rel D4689, and D4691 is a repeat. Expected values
    are the gap-compressed block ordinals hand-derived from D4689's frozen deck
    (occupied SL slots 0-4 then a gap, etc.), NOT the raw since-last distances
    (which would be {4:12, 8:4, 15:0, 32:6, 43:2, 44:3})."""
    if "4691" not in idx or "4689" not in idx:
        print("  [validate] D4691/D4689 not both present — skipping fixture check")
        return
    di = idx["4691"]
    keys = group_key_map(idx["4689"], history)   # rel predecessor D4689
    got = {w: keys[w] for w in sorted(history[di]["nums"])}
    expected = {4: 11, 8: 5, 15: 1, 32: 7, 43: 3, 44: 4}
    assert got == expected, f"validation mismatch: {got} != {expected}"
    assert bool(deep_repeats(di, history)) is True, "D4691 should be a repeat draw"
    print(f"  [validate] D4691 winners -> deck group rel D4689 = {got}  (repeat=True)  OK")


def main() -> None:
    history = load_history()
    idx = {r["draw"]: i for i, r in enumerate(history)}
    n = len(history)
    print(f"Loaded {n} draws from {HIST_PATH.name} "
          f"(newest D{history[0]['draw']} … oldest D{history[-1]['draw']}).")
    validate(history, idx)

    # aggregation keyed by (deck_group, regime)
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
                "deck_group": g,
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
        print(f"  {'Ggrp':>6} {'rate':>7} {'raw':>5} {'avgSize':>8} "
              f"{'exp':>7} {'nDraws':>7}")
        items = [r for r in rows_out if r["regime"] == regime]
        items.sort(key=lambda r: (r["deck_group"] == "unseen", r["deck_group"]))
        for r in items:
            flag = "  <-thin" if r["n_draws_group_present"] < THIN else ""
            rate = "nan" if math.isnan(r["normalized_rate"]) else f"{r['normalized_rate']:.2f}"
            print(f"  {str(r['deck_group']):>6} {rate:>7} {r['raw_winner_count']:>5} "
                  f"{r['avg_group_size']:>8.2f} {r['expected_winner_count_if_uniform']:>7.1f} "
                  f"{r['n_draws_group_present']:>7}{flag}")

    # explicit hypothesis tests
    print("\n" + "=" * 68)
    print("HYPOTHESIS CHECK")
    def rate_of(g, regime):
        for r in rows_out:
            if r["deck_group"] == g and r["regime"] == regime:
                return r["normalized_rate"], r["n_draws_group_present"]
        return None, 0
    # deck groups: 1 = repeat (SL0); 2,3 = the first two FRESH occupied blocks
    # (the old raw-SL "SL1"/"SL2" low groups, now gap-compressed).
    for g in (1, 2, 3):
        rr, rn = rate_of(g, "repeat")
        nr, nn = rate_of(g, "no_repeat")
        print(f"  G{g}: repeat rate={rr}  (n={rn}) | no_repeat rate={nr} (n={nn})")


if __name__ == "__main__":
    main()
