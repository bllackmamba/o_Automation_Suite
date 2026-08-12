"""Trend analysis of Blocked-flat / Cascading over the validated sat window.

Uses the SAME engine the UI renders with (syndicate_core.stacked_blocks) so the
stats are faithful, not a re-derivation. Scope = the externally validated window
only (draw_history.csv, sat ~4403->4701); the parked deep B1 tail is NOT used.

For each transition older draw O = history[j+1]  ->  newer "RefGroup" N = history[j]
(newest-first list), we record, for every winning number of N:
  * fresh vs repeat  (repeat = also won O)
  * SL-at-O          (draws since it last won, measured at O; repeat => 0)
  * wall vs caught   (decorate_newest: the hole it leaves in O's all_wt skeleton
                      has no contrasting-band survivor [wall] or one [caught])
  * band             (1-9,10-19,20-29,30-39,40-45)

Run: python3 -m analysis.blocked_flat_trends
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from syndicate_core import stacked_blocks as sb
from syndicate_core.refgroup import parse_draw_numbers

ROOT = Path(__file__).resolve().parents[1]
DH = ROOT / "Games/SAT/SinceLast_sat/draw_history.csv"
POOL, PICK = 45, 6
BAND_LABELS = ["1-9", "10-19", "20-29", "30-39", "40-45"]
BAND_SIZES = [9, 10, 10, 10, 6]


def load_history() -> list[dict]:
    df = pd.read_csv(DH, dtype=str)
    hist = []
    for _, r in df.iterrows():
        nums = set(parse_draw_numbers(r.get("numbers", "")))
        if nums:
            hist.append({"draw": str(r.get("draw", "")).strip(), "nums": nums})
    return hist  # newest-first


def pct(a, b):
    return f"{100*a/b:.1f}%" if b else "n/a"


def main():
    hist = load_history()
    n = len(hist)
    draws = [int(h["draw"]) for h in hist if h["draw"].lstrip("-").isdigit()]
    print(f"Validated window: {min(draws)}->{max(draws)}  ({n} draws, "
          f"{n-1} transitions)\n")

    fresh_counts = Counter()          # per-transition fresh count (0..6)
    repeat_counts = Counter()         # per-transition repeat count
    wall_caught = Counter()           # ('fresh'|'repeat', 'wall'|'caught')
    band_win = Counter()              # winners by band
    band_wallcaught = defaultdict(Counter)   # band -> {'wall','caught'}
    sl_at_O_fresh = Counter()         # SL-at-O for fresh winners (return gap)
    sl_sentinel = 0
    per_num = defaultdict(lambda: Counter())  # number -> counts
    repeat_streaks = []               # length of consecutive-win runs per number

    # transitions: j newer, j+1 older
    for j in range(n - 1):
        N, O = hist[j]["nums"], hist[j + 1]["nums"]
        fresh = N - O
        repeat = N & O
        fresh_counts[len(fresh)] += 1
        repeat_counts[len(repeat)] += 1
        sl_O = sb.since_last_map(j + 1, hist, POOL)
        dec = sb.decorate_newest(sb.block_layout(j + 1, hist, POOL), N)
        sentinel = n - (j + 1)
        for w in N:
            b = sb.band_of(w)
            band_win[b] += 1
            kind = "repeat" if w in O else "fresh"
            fill = dec["fills"].get(w)          # None => wall
            wc = "wall" if fill is None else "caught"
            wall_caught[(kind, wc)] += 1
            band_wallcaught[b][wc] += 1
            per_num[w][kind] += 1
            per_num[w][wc] += 1
            per_num[w]["win"] += 1
            if kind == "fresh":
                sl = sl_O[w]
                if sl >= sentinel:
                    sl_sentinel += 1
                else:
                    sl_at_O_fresh[sl] += 1

    # consecutive-win (repeat) streaks per number, over the whole window
    for num in range(1, POOL + 1):
        run = 0
        for h in hist:               # newest-first; order irrelevant for run lengths
            if num in h["nums"]:
                run += 1
            else:
                if run:
                    repeat_streaks.append(run)
                run = 0
        if run:
            repeat_streaks.append(run)

    T = n - 1
    W = T * PICK   # total winner-slots analysed

    print("== FRESH vs REPEAT (per successive draw) ==")
    print(f"  mean repeats/draw : {sum(k*v for k,v in repeat_counts.items())/T:.2f} "
          f"of {PICK}  (mean fresh {sum(k*v for k,v in fresh_counts.items())/T:.2f})")
    print("  repeat-count distribution (how many of a draw's 6 also won the prior draw):")
    for k in range(PICK + 1):
        if repeat_counts[k]:
            print(f"    {k} repeats : {repeat_counts[k]:3d} draws ({pct(repeat_counts[k],T)})")
    tot_rep = sum(k*v for k,v in repeat_counts.items())
    print(f"  overall: {tot_rep}/{W} winner-slots are repeats ({pct(tot_rep,W)}); "
          f"draws with >=1 repeat: {pct(T - repeat_counts[0], T)}")

    print("\n== WALL vs CAUGHT ==")
    tot_wall = sum(v for (k,wc),v in wall_caught.items() if wc=="wall")
    tot_caught = W - tot_wall
    print(f"  overall: wall {tot_wall} ({pct(tot_wall,W)})  |  caught {tot_caught} ({pct(tot_caught,W)})")
    for kind in ("fresh", "repeat"):
        kt = sum(v for (k,wc),v in wall_caught.items() if k==kind)
        kw = wall_caught[(kind,"wall")]
        print(f"    {kind:6}: {kt:4d} slots -> wall {pct(kw,kt)} | caught {pct(kt-kw,kt)}")

    print("\n== BAND behaviour (band size in parens) ==")
    print("  band      wins   share  exp%   wall%  caught%")
    for b, lab in enumerate(BAND_LABELS):
        wins = band_win[b]
        wall = band_wallcaught[b]["wall"]
        caught = band_wallcaught[b]["caught"]
        exp = 100*BAND_SIZES[b]/POOL
        print(f"  {lab:8}({BAND_SIZES[b]:2d}) {wins:4d}  {pct(wins,W):>6} {exp:4.1f}%  "
              f"{pct(wall,wins):>6} {pct(caught,wins):>7}")

    print("\n== RETURN GAP (SL-at-O of FRESH winners = draws since last win) ==")
    tot_fresh_meas = sum(sl_at_O_fresh.values())
    cum = 0
    for sl in sorted(sl_at_O_fresh):
        cum += sl_at_O_fresh[sl]
        if sl <= 12 or sl_at_O_fresh[sl] >= 5:
            print(f"    gap {sl:2d} draws : {sl_at_O_fresh[sl]:3d} ({pct(sl_at_O_fresh[sl],tot_fresh_meas)})  "
                  f"cum {pct(cum,tot_fresh_meas)}")
    med = None
    cum = 0
    for sl in sorted(sl_at_O_fresh):
        cum += sl_at_O_fresh[sl]
        if med is None and cum >= tot_fresh_meas/2:
            med = sl
    print(f"  median return gap: {med} draws; beyond-window (cold) fresh: {sl_sentinel}")

    print("\n== CONSECUTIVE-WIN STREAKS (any number winning N draws in a row) ==")
    sc = Counter(repeat_streaks)
    for k in sorted(sc):
        print(f"    run of {k}: {sc[k]} occurrences")

    print("\n== PER-NUMBER extremes ==")
    wins_by_num = {num: per_num[num]["win"] for num in range(1, POOL+1)}
    hot = sorted(wins_by_num.items(), key=lambda x:-x[1])[:6]
    cold = sorted(wins_by_num.items(), key=lambda x:x[1])[:6]
    exp_wins = W/POOL
    print(f"  expected wins/number over window: {exp_wins:.1f}")
    print("  hottest:", ", ".join(f"{k}({v})" for k,v in hot))
    print("  coldest:", ", ".join(f"{k}({v})" for k,v in cold))
    # numbers that skew wall vs caught
    skew = []
    for num in range(1, POOL+1):
        w, c = per_num[num]["wall"], per_num[num]["caught"]
        if w+c >= 8:
            skew.append((num, w, c, w/(w+c)))
    skew.sort(key=lambda x:-x[3])
    print("  most WALL-prone (wall/[wall+caught], >=8 exits):",
          ", ".join(f"{n}:{r:.0%}" for n,w,c,r in skew[:6]))
    print("  most CAUGHT-prone:",
          ", ".join(f"{n}:{1-r:.0%}" for n,w,c,r in sorted(skew,key=lambda x:x[3])[:6]))

    # write per-winner CSV for the record
    out = ROOT / "analysis" / "blocked_flat_trends_sat.csv"
    rows = []
    for j in range(n - 1):
        N, O = hist[j]["nums"], hist[j + 1]["nums"]
        sl_O = sb.since_last_map(j + 1, hist, POOL)
        dec = sb.decorate_newest(sb.block_layout(j + 1, hist, POOL), N)
        for w in sorted(N):
            rows.append({
                "draw": hist[j]["draw"], "number": w,
                "band": BAND_LABELS[sb.band_of(w)],
                "kind": "repeat" if w in O else "fresh",
                "sl_at_prev": sl_O[w],
                "hole": "wall" if dec["fills"].get(w) is None else "caught",
                "caught_by": dec["fills"].get(w) or "",
            })
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nper-winner detail -> {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
