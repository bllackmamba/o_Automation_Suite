"""
Hard PRESENCE count (not rate): in how many draws does an SL group actually
show up among the winners? Read-only follow-up to sl_group_regime.py.

Reuses per_draw_records() from analysis.sl_group_regime (same repeat /
no-repeat definition, same "SL group rel predecessor P" winner assignment) —
no second SL/repeat pipeline.

Two lenses:
  no_repeat    : of all no-repeat draws, how many have >=1 winner in group g?
  repeat_fresh : of all repeat draws, how many have >=1 FRESH winner
                 (deck group != 1) in group g? (group 1 = repeat is excluded
                 because a repeat draw guarantees a group-1 winner by
                 definition — the question is the rest.)

NB groups are block ordinals from per_draw_records (group 1 = repeat), NOT raw
since-last distances. The low-group probe indices below were remapped when the
labeling was corrected: old raw-SL {SL1, SL2, SL3} -> deck ordinals {2, 3, 4}
(old SL0 repeat -> ordinal 1). Confirm these are the ordinals you want.

Outputs:
  analysis/sl_group_presence_coverage.csv
  analysis/sl_group_covering_sets.csv
plus a printed summary answering the group-1 / group-2 question directly.
"""
from __future__ import annotations

import csv
from pathlib import Path

from analysis.sl_group_regime import load_history, per_draw_records, THIN

REPO = Path(__file__).resolve().parent.parent
OUT_PRESENCE = REPO / "analysis" / "sl_group_presence_coverage.csv"
OUT_COVER = REPO / "analysis" / "sl_group_covering_sets.csv"


def _sort_key(g):
    return (1, 0) if g == "unseen" else (0, g)


def presence_table(draws: list[dict], fresh_only: bool) -> dict:
    """group -> number of draws in which >=1 winner is in that group.
    fresh_only drops group-1 (repeat) winners before checking."""
    counts: dict = {}
    for r in draws:
        groups = {g for (_w, g) in r["winner_groups"] if not (fresh_only and g == 1)}
        for g in groups:
            counts[g] = counts.get(g, 0) + 1
    return counts


def draw_group_sets(draws: list[dict], fresh_only: bool) -> list[set]:
    """Per-draw set of deck groups present among its (optionally fresh) winners."""
    out = []
    for r in draws:
        out.append({g for (_w, g) in r["winner_groups"]
                    if not (fresh_only and g == 1)})
    return out


def greedy_cover(draw_sets: list[set], max_sets: int = 8) -> list[tuple]:
    """Greedy set-cover: repeatedly add the SL group covering the most
    still-uncovered draws. Returns [(chosen_list, coverage_pct, gain_pct), …]."""
    total = len(draw_sets)
    remaining = set(range(total))
    candidates = set().union(*draw_sets) if draw_sets else set()
    chosen: list = []
    rows = []
    while candidates and len(chosen) < max_sets and remaining:
        best, best_gain = None, -1
        for g in candidates:
            if g in chosen:
                continue
            gain = sum(1 for d in remaining if g in draw_sets[d])
            if gain > best_gain:
                best, best_gain = g, gain
        if best is None or best_gain == 0:
            break
        chosen.append(best)
        remaining -= {d for d in remaining if best in draw_sets[d]}
        covered = total - len(remaining)
        rows.append((list(chosen), 100 * covered / total, 100 * best_gain / total))
    return rows


def coverage_of(draw_sets: list[set], groups: set) -> float:
    total = len(draw_sets)
    if not total:
        return 0.0
    hit = sum(1 for s in draw_sets if s & groups)
    return 100 * hit / total


def _fmt_set(groups) -> str:
    return "{" + ", ".join(str(g) for g in sorted(groups, key=_sort_key)) + "}"


def main() -> None:
    history = load_history()
    records = per_draw_records(history)
    norepeat = [r for r in records if not r["repeat"]]
    repeat = [r for r in records if r["repeat"]]
    n_nr, n_rp = len(norepeat), len(repeat)
    print(f"Draws with a predecessor: {len(records)}  "
          f"(no_repeat={n_nr}, repeat={n_rp})")

    lenses = [
        ("no_repeat", norepeat, False, n_nr),
        ("repeat_fresh", repeat, True, n_rp),
    ]

    # ── presence table CSV ──
    presence_rows = []
    tables = {}
    for regime, draws, fresh, n_reg in lenses:
        counts = presence_table(draws, fresh)
        tables[regime] = counts
        for g in sorted(counts, key=_sort_key):
            present = counts[g]
            presence_rows.append({
                "deck_group": g,
                "regime": regime,
                "n_draws_in_regime": n_reg,
                "n_draws_group_present": present,
                "presence_pct": round(100 * present / n_reg, 1),
            })
    with OUT_PRESENCE.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(presence_rows[0].keys()))
        w.writeheader()
        w.writerows(presence_rows)
    print(f"Wrote {len(presence_rows)} rows -> {OUT_PRESENCE.relative_to(REPO)}")

    # ── covering sets CSV ──
    cover_rows = []
    cover_by_regime = {}
    for regime, draws, fresh, n_reg in lenses:
        dsets = draw_group_sets(draws, fresh)
        chain = greedy_cover(dsets)
        cover_by_regime[regime] = (dsets, chain)
        prev = 0.0
        for chosen, cov, _gain in chain:
            cover_rows.append({
                "candidate_set": _fmt_set(chosen),
                "regime": regime,
                "coverage_pct": round(cov, 1),
                "incremental_gain_pct": round(cov - prev, 1),
            })
            prev = cov
    with OUT_COVER.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cover_rows[0].keys()))
        w.writeheader()
        w.writerows(cover_rows)
    print(f"Wrote {len(cover_rows)} rows -> {OUT_COVER.relative_to(REPO)}")

    # ── printed summary ──
    for regime, draws, fresh, n_reg in lenses:
        counts = tables[regime]
        print("\n" + "-" * 64)
        label = "no-repeat draws" if regime == "no_repeat" else "repeat draws (FRESH winners, group 1 excluded)"
        print(f"{regime.upper()} — presence per draw, n={n_reg} {label}")
        print(f"  {'Ggrp':>6} {'present':>8} {'pct':>7}")
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], _sort_key(kv[0])))
        for g, c in ranked:
            flag = "  <-thin base" if c < THIN else ""
            print(f"  {str(g):>6} {c:>8} {100*c/n_reg:>6.1f}%{flag}")

    # ── direct answers ──
    print("\n" + "=" * 64)
    print("DIRECT ANSWERS")
    nr_counts = tables["no_repeat"]
    for g in (2, 3):   # deck ordinals: old raw-SL {1,2} -> {2,3} (repeat=1)
        c = nr_counts.get(g, 0)
        pct = 100 * c / n_nr
        verdict = "close to guaranteed" if pct >= 90 else ("a strong lean" if pct >= 66 else "a lean, not a guarantee")
        print(f"  Group {g} appears in >=1 winner of a NO-REPEAT draw "
              f"{pct:.1f}% of the time (n={c}/{n_nr}) — {verdict}.")
    rf_counts = tables["repeat_fresh"]
    for g in (2, 3):   # deck ordinals: old raw-SL {1,2} -> {2,3} (repeat=1)
        c = rf_counts.get(g, 0)
        pct = 100 * c / n_rp
        verdict = "close to guaranteed" if pct >= 90 else ("a strong lean" if pct >= 66 else "a lean, not a guarantee")
        print(f"  Group {g} appears among the FRESH winners of a REPEAT draw "
              f"{pct:.1f}% of the time (n={c}/{n_rp}) — {verdict}.")

    # ── covering-set callouts incl. Tai's {2},{2,3},{2,3,4} ──
    print("\n" + "=" * 64)
    print("COVERING SETS (smallest groups covering the most draws)")
    for regime in ("no_repeat", "repeat_fresh"):
        dsets, chain = cover_by_regime[regime]
        print(f"\n  {regime} — greedy chain:")
        for chosen, cov, gain in chain:
            print(f"    {_fmt_set(chosen):<20} {cov:5.1f}%  (+{gain:.1f})")
        print(f"  {regime} — Tai's low-group sequence:")
        # deck ordinals: old raw-SL {2},{2,3},{2,3,4},{1,2,3,4} -> +1 (repeat=1)
        for gs in ({3}, {3, 4}, {3, 4, 5}, {2, 3, 4, 5}):
            print(f"    {_fmt_set(gs):<20} {coverage_of(dsets, gs):5.1f}%")


if __name__ == "__main__":
    main()
