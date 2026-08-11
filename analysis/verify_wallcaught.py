"""Two verifications for the Blocked-flat trend analysis.

(2) decorate_newest vs the recursive on-screen render (render_columns) on real
    draws — confirm the docstring's agreement claim rather than trusting it.
(1) Matched-density test of the repeat>fresh catch gap: if local survivor
    density explains it, repeats and fresh matched on (block_size, n_survivors)
    should show equal catch rates. Residual repeat effect ⇒ "just geometry" is
    incomplete. Reports which outcome occurs.

Run: python3 -m analysis.verify_wallcaught
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from syndicate_core import stacked_blocks as sb
from syndicate_core.refgroup import parse_draw_numbers

ROOT = Path(__file__).resolve().parents[1]
DH = ROOT / "Games/SAT/SinceLast_sat/draw_history.csv"
POOL, PICK = 45, 6


def load_history() -> list[dict]:
    df = pd.read_csv(DH, dtype=str)
    return [{"draw": str(r.get("draw", "")).strip(),
             "nums": set(parse_draw_numbers(r.get("numbers", "")))}
            for _, r in df.iterrows() if parse_draw_numbers(r.get("numbers", ""))]


# ── (2) render agreement ──────────────────────────────────────────────────────

def winners_in_skeleton_order(j: int, hist: list[dict]) -> list[int]:
    """Winners of the newer draw (j), in the order they appear scanning the older
    draw's (j+1) block_layout — the same order holes appear in the rendered
    newer column."""
    N = hist[j]["nums"]
    order = []
    for blk in sb.block_layout(j + 1, hist, POOL):
        for num in blk:
            if num in N:
                order.append(num)
    return order


def verify_render(hist: list[dict], j: int) -> bool:
    """Compare the newer column's rendered hole kinds (from render_columns, the
    actual UI path) to decorate_newest's fills for the 2-column window [j, j+1]."""
    N = hist[j]["nums"]
    cols = sb.render_columns([j, j + 1], hist, POOL)   # what the UI draws
    render_holes = [c[1] for c in cols[0] if c[0] == "hole"]   # top→bottom
    order = winners_in_skeleton_order(j, hist)
    dec = sb.decorate_newest(sb.block_layout(j + 1, hist, POOL), N)
    dec_holes = ["wall" if dec["fills"][w] is None else "caught" for w in order]

    ok = (render_holes == dec_holes) and (len(render_holes) == len(N))
    print(f"  draw D{hist[j]['draw']} (vs older D{hist[j+1]['draw']}): "
          f"{len(N)} winners, {len(render_holes)} holes in render")
    print(f"    {'winner':>6} {'render':>7} {'decorate':>9}  match")
    for w, rh, dh in zip(order, render_holes, dec_holes):
        print(f"    {w:>6} {rh:>7} {dh:>9}  {'✓' if rh==dh else '✗ MISMATCH'}")
    print(f"    → {'AGREE' if ok else 'DISAGREE'}\n")
    return ok


# ── (1) matched-density test ──────────────────────────────────────────────────

def collect_slots(hist: list[dict]) -> list[dict]:
    """Per winner-slot: kind, caught, and the density of its block in the older
    skeleton (block_size, n survivors = non-winner numbers in the block)."""
    n = len(hist)
    slots = []
    for j in range(n - 1):
        N, O = hist[j]["nums"], hist[j + 1]["nums"]
        blocks = sb.block_layout(j + 1, hist, POOL)
        dec = sb.decorate_newest(blocks, N)
        # map number -> its block
        for blk in blocks:
            blkset = set(blk)
            survivors = [m for m in blk if m not in N]   # potential catchers
            for w in blk:
                if w not in N:
                    continue
                slots.append({
                    "kind": "repeat" if w in O else "fresh",
                    "caught": dec["fills"][w] is not None,
                    "block_size": len(blk),
                    "n_surv": len(survivors),
                })
    return slots


def rate(slots) -> tuple[float, int]:
    c = sum(1 for s in slots if s["caught"])
    return (c / len(slots), len(slots)) if slots else (float("nan"), 0)


def matched_test(hist: list[dict]) -> None:
    slots = collect_slots(hist)
    reps = [s for s in slots if s["kind"] == "repeat"]
    fresh = [s for s in slots if s["kind"] == "fresh"]

    rr, rn = rate(reps); fr, fn = rate(fresh)
    print(f"  RAW catch rate: repeat {rr:.1%} (n={rn}) | fresh {fr:.1%} (n={fn}) "
          f"| gap {100*(rr-fr):+.1f}pp")

    # Are the densities actually different? (the confound premise)
    def mean(xs, k): return sum(s[k] for s in xs) / len(xs)
    print(f"  density by kind: repeat mean block_size={mean(reps,'block_size'):.2f} "
          f"n_surv={mean(reps,'n_surv'):.2f} | fresh block_size={mean(fresh,'block_size'):.2f} "
          f"n_surv={mean(fresh,'n_surv'):.2f}")

    # Stratify on (block_size, n_surv). Standardise both groups to the SHARED
    # stratum distribution (only strata where BOTH groups appear).
    strata: dict[tuple, dict] = defaultdict(lambda: {"repeat": [], "fresh": []})
    for s in slots:
        strata[(s["block_size"], s["n_surv"])][s["kind"]].append(s["caught"])

    shared = {k: v for k, v in strata.items() if v["repeat"] and v["fresh"]}
    print(f"\n  strata (block_size,n_surv) with BOTH groups present: {len(shared)}")
    print(f"    {'stratum':>12} {'rep n':>6} {'rep%':>6} {'frsh n':>7} {'frsh%':>6}")
    W = num_r = num_f = 0.0
    rep_cov = fr_cov = 0
    for k in sorted(shared, key=lambda k: -(len(shared[k]['repeat'])+len(shared[k]['fresh']))):
        rc, fc = shared[k]["repeat"], shared[k]["fresh"]
        w = len(rc) + len(fc)                     # stratum weight
        rrate = sum(rc)/len(rc); frate = sum(fc)/len(fc)
        W += w; num_r += w*rrate; num_f += w*frate
        rep_cov += len(rc); fr_cov += len(fc)
        if w >= 8:
            print(f"    {str(k):>12} {len(rc):>6} {rrate:>5.0%} {len(fc):>7} {frate:>5.0%}")
    if W:
        print(f"\n  MATCHED (standardised to shared strata): "
              f"repeat {num_r/W:.1%} | fresh {num_f/W:.1%} | gap {100*(num_r-num_f)/W:+.1f}pp")
        print(f"  (covers {rep_cov}/{rn} repeats, {fr_cov}/{fn} fresh)")
        raw_gap = rr - fr
        matched_gap = (num_r - num_f) / W
        shrink = 100 * (1 - matched_gap/raw_gap) if raw_gap else 0
        print(f"\n  VERDICT: raw gap {100*raw_gap:+.1f}pp → matched gap "
              f"{100*matched_gap:+.1f}pp  ({shrink:.0f}% of the gap removed by "
              f"matching on density)")
        if abs(matched_gap) < 0.03:
            print("  ⇒ density/position ALONE explains the repeat>fresh catch gap "
                  "(geometry is sufficient).")
        else:
            print("  ⇒ a repeat effect REMAINS after matching density — the "
                  "'just geometry (density)' explanation is INCOMPLETE.")


def main():
    hist = load_history()
    # pick two real draws: the newest pair, and the transition with most repeats
    best_j, best_r = 0, -1
    for j in range(len(hist) - 1):
        r = len(hist[j]["nums"] & hist[j + 1]["nums"])
        if r > best_r:
            best_j, best_r = j, r

    print("== (2) decorate_newest vs recursive render (render_columns) ==")
    ok0 = verify_render(hist, 0)
    okR = verify_render(hist, best_j)
    print(f"  render-agreement: {'BOTH AGREE ✓' if ok0 and okR else 'DISAGREEMENT ✗'}\n")

    print("== (1) matched-density test of repeat>fresh catch gap ==")
    matched_test(hist)


if __name__ == "__main__":
    main()
