"""
syndicate_core/check_config.py
Verify that each GAMES_CFG entry's lottolyzer URL serves the right game.

Two checks per game:
  1. Pool   — frequency table row count == config["pool"]
  2. Day    — recent draw dates match config["draw_day"]

Usage:
    cd /path/to/o_Automation_Suite
    python3 -m syndicate_core.check_config
"""

from __future__ import annotations

import sys
import pathlib
from datetime import datetime
from typing import Optional

# Allow running from any cwd — insert the suite root so syndicate_core is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from syndicate_core.config import GAMES_CFG
from syndicate_core.scraping import fetch_number_frequencies, fetch_draw_history

_DAY_ABBR = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
    "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
}
_WEEKDAY_NAMES = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]


# ── date parsing ─────────────────────────────────────────────────────────────

def _parse_date(s: str) -> Optional[datetime]:
    if not s or s.strip() in ("nan", "None", ""):
        return None
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d",
                "%d %b %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        import pandas as pd
        return pd.to_datetime(s).to_pydatetime()
    except Exception:
        return None


def _dates_from_history(game_key: str) -> list[datetime]:
    """Fetch 2 pages of draw history and return parsed draw dates."""
    df = fetch_draw_history(game_key, pages=2)
    if df is None or df.empty:
        return []

    dates: list[datetime] = []
    for _, row in df.head(30).iterrows():
        dt: Optional[datetime] = None

        # 1. Try the date column directly
        date_str = str(row.get("date", "")).strip()
        if date_str and date_str not in ("nan", "None", ""):
            dt = _parse_date(date_str)

        # 2. For non-PB games the draw column is YYYYMMDD; use it as a fallback
        if dt is None and game_key != "pb":
            try:
                draw_int = int(float(str(row.get("draw", 0))))
                if 19_900_101 <= draw_int <= 20_991_231:
                    dt = datetime.strptime(str(draw_int), "%Y%m%d")
            except (ValueError, TypeError):
                pass

        if dt:
            dates.append(dt)

    return dates


# ── per-check helpers ─────────────────────────────────────────────────────────

def _check_pool(game_key: str, cfg: dict) -> tuple[bool, str]:
    pool = cfg["pool"]
    url  = cfg["lottolyzer"]
    df   = fetch_number_frequencies(url, pool)
    if df is None:
        return False, "fetch failed (network or wrong URL?)"
    count = len(df)
    if count == pool:
        return True, f"table has {count} numbers == pool={pool}"
    return False, f"table has {count} numbers, expected pool={pool}"


def _check_draw_day(game_key: str, cfg: dict) -> tuple[bool, str]:
    draw_day = cfg["draw_day"]
    dates    = _dates_from_history(game_key)

    if not dates:
        return False, "no parseable dates from history (network or wrong URL?)"

    # Build weekday count
    counts: dict[str, int] = {}
    for dt in dates:
        name = _WEEKDAY_NAMES[dt.weekday()]
        counts[name] = counts.get(name, 0) + 1

    total = sum(counts.values())

    # ── "Daily" ──────────────────────────────────────────────────────────────
    if draw_day == "Daily":
        n_days = len(counts)
        if n_days >= 4:
            top = sorted(counts.items(), key=lambda x: -x[1])
            return True, f"draws on {n_days} weekdays as expected — {dict(top[:4])}"
        return False, f"only {n_days} distinct weekday(s) in {total} draws — {counts}"

    # ── "Mon, Wed, Fri" (multi-day) ───────────────────────────────────────────
    if "," in draw_day:
        expected = {_DAY_ABBR.get(p.strip(), p.strip()) for p in draw_day.split(",")}
        on_expected  = {k: v for k, v in counts.items() if k in expected}
        off_expected = {k: v for k, v in counts.items() if k not in expected}
        if on_expected and not off_expected:
            return True, f"all {total} draws on {draw_day} — {counts}"
        if on_expected and off_expected:
            return False, (f"unexpected draw days {off_expected} "
                           f"(expected only {draw_day})")
        return False, f"no draws on {draw_day} in {total} rows — got {counts}"

    # ── single named day ──────────────────────────────────────────────────────
    on_day = counts.get(draw_day, 0)
    pct    = 100 * on_day / total if total else 0
    if pct >= 85:
        return True, f"{on_day}/{total} draws on {draw_day} ({pct:.0f}%)"
    return False, (f"only {on_day}/{total} draws on {draw_day} ({pct:.0f}%) "
                   f"— weekdays found: {counts}")


# ── main ──────────────────────────────────────────────────────────────────────

GAME_ORDER = ["pb", "oz", "sat", "sfl", "mwf"]


def main() -> None:
    results: dict = {}

    for gk in GAME_ORDER:
        cfg   = GAMES_CFG[gk]
        label = cfg["label"]
        print(f"  checking {label} ({gk}) …", flush=True)
        pool_ok,  pool_msg  = _check_pool(gk, cfg)
        day_ok,   day_msg   = _check_draw_day(gk, cfg)
        results[gk] = dict(label=label, cfg=cfg,
                           pool_ok=pool_ok,  pool_msg=pool_msg,
                           day_ok=day_ok,    day_msg=day_msg)

    # ── summary table ────────────────────────────────────────────────────────
    W = 90
    print()
    print("=" * W)
    print(f"{'GAME':<6}  {'LABEL':<16}  {'POOL':^6}  {'DAY':^5}  DETAILS")
    print("-" * W)

    any_fail = False
    for gk in GAME_ORDER:
        r  = results[gk]
        ps = "PASS" if r["pool_ok"] else "FAIL"
        ds = "PASS" if r["day_ok"]  else "FAIL"
        if not (r["pool_ok"] and r["day_ok"]):
            any_fail = True
        print(f"{gk:<6}  {r['label']:<16}  {ps:^6}  {ds:^5}  "
              f"pool: {r['pool_msg']}")
        print(f"{'':6}  {'':16}  {'':6}  {'':5}  day:  {r['day_msg']}")
        print()

    print("=" * W)

    # ── failure detail ────────────────────────────────────────────────────────
    if any_fail:
        print("\nFAILED CHECKS — details:")
        for gk in GAME_ORDER:
            r   = results[gk]
            cfg = r["cfg"]
            if not r["pool_ok"]:
                print(f"\n  [{gk}] POOL FAIL: {r['pool_msg']}")
                print(f"         frequency URL: {cfg['lottolyzer']}")
            if not r["day_ok"]:
                hist = cfg["lottolyzer"].replace("/number-frequencies/", "/history/")
                print(f"\n  [{gk}] DAY FAIL: {r['day_msg']}")
                print(f"         history URL: {hist}/page/1/per-page/50/summary-view")
        print()
        sys.exit(1)
    else:
        print("\nALL 5 GAMES PASSED\n")


if __name__ == "__main__":
    main()
