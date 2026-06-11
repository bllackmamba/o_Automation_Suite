#!/usr/bin/env python3
"""
thelott_picks_scraper.py  —  REAL syndicate combinations, fast, no browser
==========================================================================
Pipeline (all plain GET on api.thelott.com — no bot wall):
  1. outlets : /outlet/outlets?state=..&postcode_or_locality=..
  2. search  : /syndicates/api/search?company=..&outlets=ID,ID,..&limit=100   (syndicate IDs)
  3. details : /syndicates/api/details?syndicateId=..&companyId=..             (THE PICKS)

Output: ONE ROW PER GAME LINE, columns:
  Syndicate_ID, Syndicate_Name, Game, Product, CompanyId, Draw_Number, Draw_Date,
  Entry_Type, System_Number, Share_Cost, Available_Shares, Total_Shares,
  Outlet_ID, Postcode, State, PB, w1, w2, ... wN
(w1..wN = the picked numbers — per the project convention. Main Data stays n1..nN.)

Usage:
  python3 thelott_picks_scraper.py 2000              # one postcode (test)
  python3 thelott_picks_scraper.py 2000 4000 3000    # several
  python3 thelott_picks_scraper.py sweep NSW         # full state sweep (parallel)
  python3 thelott_picks_scraper.py sweep NSW 10      # ...with 10 workers
  python3 thelott_picks_scraper.py sweep ALL         # all states, one after another

Sweeps are DEDUP-FIRST + BOUNDED-PARALLEL:
  Phase 1 collects unique syndicate IDs (so each syndicate is fetched once),
  Phase 2 fetches details with a small thread pool (default 8 workers) + retries.
  Polite pacing throughout — fast but not reckless, to avoid rate-limit/blocks.
"""
import urllib.request, urllib.error, json, ssl, time, csv, os, sys, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Politeness / concurrency knobs (safe defaults — tweak with care) ─────────
MAX_WORKERS   = 6       # parallel detail fetches; lowered from 8 to avoid 403 throttling
PER_REQ_PAUSE = 0.12    # small pause inside each worker after a call
RETRY_TIMES   = 4       # retry a failed detail fetch this many times
RETRY_BACKOFF = 1.5     # seconds * attempt between retries (network blips)
THROTTLE_COOLDOWN = 20  # seconds to wait when the API returns 403 (rate-limited)
_print_lock   = threading.Lock()  # keep parallel progress prints tidy
_throttle_lock = threading.Lock()
_throttle_hits = 0      # rolling count of 403s, for a one-time heads-up

# ── SSL bypass (macOS) ───────────────────────────────────────────────────────
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

STATE_COMPANY = {"NSW": 3, "ACT": 3, "VIC": 1, "TAS": 1, "QLD": 2, "SA": 6}

# (companyId, product) -> canonical game key used by the rest of the pipeline.
# Based on thelott_syndicate_scraper.py PRODUCT_NAMES, collapsed to pb/oz/sat/sfl/mwf.
# NOTE: product is only meaningful WITH companyId. Draw-range check below verifies.
GAME_BY_COMPANY_PRODUCT = {
    # NSW / ACT  (company 3)
    (3, 6): "sat", (3, 22): "sat", (3, 7): "mwf", (3, 25): "mwf",
    (3, 8): "oz",  (3, 23): "oz",  (3, 9): "pb",  (3, 24): "pb",
    (3, 10): "sfl", (3, 27): "sfl", (3, 37): "sat", (3, 1): "sat",
    # NSW also reuses low product IDs (confirmed live): 1=sat, 2=oz, 3=pb
    (3, 2): "oz", (3, 3): "pb", (3, 4): "mwf", (3, 5): "sfl",
    # VIC / TAS  (company 1)
    (1, 1): "sat", (1, 2): "oz", (1, 3): "pb", (1, 4): "mwf", (1, 5): "sfl",
    # QLD  (company 2)
    (2, 14): "sat", (2, 19): "sat", (2, 15): "oz", (2, 20): "oz",
    (2, 16): "pb",  (2, 21): "pb",  (2, 17): "mwf", (2, 18): "sfl", (2, 3): "pb",
    # SA  (company 6) — observed product 22 = Weekday/Sat-family
    (6, 22): "sat", (6, 14): "sat", (6, 15): "oz", (6, 16): "pb",
    (6, 17): "mwf", (6, 18): "sfl", (6, 19): "sat",
}

# Canonical game NAME per game key — these are names that masterapp's
# GAME_NAME_MAP already understands, so split_d_by_game works UNCHANGED.
GAME_KEY_TO_NAME = {
    "pb":  "Powerball",
    "oz":  "Oz Lotto",
    "sat": "Saturday Lotto",
    "mwf": "Monday & Wednesday Lotto",
    "sfl": "Set for Life",
}

# Per-game number POOL (max valid main number). Used to validate selections:
# a pb pick must be 1..35, sat/mwf 1..45, oz 1..47, sfl 1..44. Anything outside
# means a mis-tagged game or bad source row — we drop & count those.
POOL_MAX = {"pb": 35, "oz": 47, "sat": 45, "mwf": 45, "sfl": 44}

# Draw-number ranges per game (sanity cross-check; widen if needed).
DRAW_RANGES = {
    "pb":  (1400, 1900),   # Powerball  (~1568)
    "oz":  (1500, 1900),   # Oz Lotto   (~1686)
    "sat": (4400, 4900),   # Saturday family (~4681-4713)
    "mwf": (4400, 4900),   # Mon/Wed/Fri shares Sat-family draw range
    "sfl": (1, 99999),     # Set for Life — unknown range, accept
}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Origin": "https://www.thelott.com",
        "Referer": "https://www.thelott.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def postcode_to_state(pc: str) -> str:
    n = int(pc)
    if 200 <= n <= 299:                        return "ACT"
    if 1000 <= n <= 2999:                      return "NSW"
    if 3000 <= n <= 3999 or 8000 <= n <= 8999: return "VIC"
    if 4000 <= n <= 4999 or 9000 <= n <= 9999: return "QLD"
    if 5000 <= n <= 5999:                      return "SA"
    if 7000 <= n <= 7999:                      return "TAS"
    return "NSW"


STATE_POSTCODES = {
    "NSW": [str(p) for p in range(2000, 3000)] + [str(p) for p in range(200, 300)],
    "VIC": [str(p) for p in range(3000, 4000)] + [str(p) for p in range(8000, 9000)],
    "QLD": [str(p) for p in range(4000, 5000)] + [str(p) for p in range(9000, 10000)],
    "SA":  [str(p) for p in range(5000, 6000)],
    "TAS": [str(p) for p in range(7000, 8000)],
    "ACT": [str(p) for p in range(200,  300)],
}


def get_outlets(postcode: str, state: str) -> list:
    data = get(f"https://api.thelott.com/outlet/outlets"
               f"?state={state}&postcode_or_locality={postcode}")
    if data.get("is_out_of_jurisdiction"):
        return []
    seen, ids = set(), []
    for loc in data.get("locality_outlets", []):
        for o in loc.get("outlets", []):
            oid = o["outlet_id"]
            if oid not in seen:
                seen.add(oid); ids.append(oid)
    return ids


def get_syndicate_ids(outlet_ids: list, company: int, batch=20) -> list:
    seen = set()
    for i in range(0, len(outlet_ids), batch):
        csv_ids = ",".join(str(o) for o in outlet_ids[i:i + batch])
        try:
            data = get(f"https://api.thelott.com/syndicates/api/search"
                       f"?company={company}&outlets={csv_ids}&limit=100")
            for s in data.get("data", []):
                seen.add(s["syndicateId"])
        except Exception as ex:
            print(f"    [warn] search batch: {ex}")
        time.sleep(0.15)
    return sorted(seen)


def game_for(company, product, draw_number):
    """Map (company, product) -> game key, then sanity-check vs draw range."""
    g = GAME_BY_COMPANY_PRODUCT.get((company, product))
    if g and draw_number:
        lo, hi = DRAW_RANGES.get(g, (1, 99999))
        if not (lo <= int(draw_number) <= hi):
            # mapping & draw range disagree — flag, keep the mapping but mark it
            return g, f"CHECK(draw {draw_number} out of {g} range)"
    return (g or f"unknown_c{company}_p{product}"), ""


def resolve_game(company, product, draw_number, selections):
    """Decide the TRUE game for one game-line and KEEP it (re-tag instead of drop).

    Start from the (company, product) mapping. If the mapped game's pool can't hold
    the actual picks (e.g. tagged 'pb' but a pick is 40), the label is wrong — infer
    the real game from the DRAW RANGE (most reliable) plus the max pick:
      • draw 4400–4900  → Saturday family → 'mwf' only if it was already mwf, else 'sat'
      • draw 1400–1900  → pb/oz family → pb if max≤35 else oz
      • max ≥ 46        → oz (only oz reaches 46–47)
      • max == 45       → sat family (mwf if it was mwf, else sat)
      • max ≤ 44 & sfl  → keep sfl
      • else            → tightest pool that still fits
    Returns (game_key, note). Only a pick > 47 (beyond every pool) is unkeepable.
    """
    g, note = game_for(company, product, draw_number)
    mx = max(int(n) for n in selections) if selections else 0
    pool = POOL_MAX.get(g)
    if pool is not None and mx <= pool and g in POOL_MAX:
        return g, note                      # mapped game is consistent — keep it

    dn = int(draw_number) if str(draw_number).isdigit() else 0
    inferred = None
    if 4400 <= dn <= 4900:
        inferred = "mwf" if g == "mwf" else "sat"
    elif 1400 <= dn <= 1900:
        inferred = "pb" if mx <= 35 else "oz"
    elif mx >= 46:
        inferred = "oz"
    elif mx == 45:
        inferred = "mwf" if g == "mwf" else "sat"
    elif mx <= 44 and g == "sfl":
        inferred = "sfl"
    else:
        for gk in ("pb", "sfl", "sat", "mwf", "oz"):   # tightest pool first
            if POOL_MAX[gk] >= mx:
                inferred = gk
                break

    if inferred and POOL_MAX.get(inferred, 0) >= mx:
        tag = "retagged" if g in POOL_MAX else "inferred"
        return inferred, f"{tag} {g}->{inferred} (max {mx}, draw {dn})"
    return (g or "unknown"), f"UNRESOLVED (max {mx})"


def fetch_details(syndicate_id: int, company: int) -> list:
    """Return list of per-game-line rows for one syndicate."""
    try:
        b = get(f"https://api.thelott.com/syndicates/api/details"
                f"?syndicateId={syndicate_id}&companyId={company}")
    except Exception as ex:
        print(f"    [warn] details {syndicate_id}: {ex}")
        return []

    name   = (b.get("syndicateName") or "").strip()
    cost   = b.get("shareCost", "")
    avail  = b.get("availableShares", "")
    total  = b.get("totalShares", "")
    outlets = b.get("outlets", [])
    outlet_id = ""
    if isinstance(outlets, list) and outlets:
        outlet_id = (outlets[0].get("outletId") if isinstance(outlets[0], dict) else "") or ""

    rows = []
    for bet in b.get("syndicateBets", []):
        product = bet.get("product")
        draws = bet.get("draws", [])
        draw_no = draws[0].get("drawNumber") if draws else ""
        draw_dt = (draws[0].get("drawDate", "")[:10]) if draws else ""
        entries = bet.get("entries", [])
        entry_type = entries[0].get("entryType", "") if entries else ""
        for g in bet.get("games", []):
            sels = g.get("selections", []) or []
            if not sels:
                continue
            # Re-tag this line to its TRUE game (keep the data) instead of dropping
            # a mislabeled row. Only a pick beyond EVERY pool (>47) is unkeepable.
            game, warn = resolve_game(company, product, draw_no, sels)
            mx = max(int(n) for n in sels)
            if mx > max(POOL_MAX.values()) or mx < 1:
                with _throttle_lock:
                    fetch_details._dropped = getattr(fetch_details, "_dropped", 0) + 1
                continue
            # Powerball value: chosen PB is 1..20. powerHit entries have no chosen
            # PB (system guarantees it) -> label "PH". Non-Powerball games have no
            # PB at all -> leave BLANK (not 0, which was misleading).
            pb_raw = g.get("powerball", "")
            if game != "pb":
                pb_val = ""                       # Saturday/Oz/etc. have no powerball
            elif g.get("powerHit") and (pb_raw in (0, "0", None, "")):
                pb_val = "PH"
            elif pb_raw in (0, "0", None, ""):
                pb_val = ""                       # pb row with no chosen number
            else:
                pb_val = pb_raw
            row = {
                "Syndicate_ID": syndicate_id,
                "Syndicate_Name": name,
                "Game": game,
                "Games": GAME_KEY_TO_NAME.get(game, game),  # name the app's splitter understands
                "Game_Check": warn,
                "Product": product,
                "CompanyId": company,
                "Draw_Number": draw_no,
                "Draw_Date": draw_dt,
                "Entry_Type": entry_type,
                "System_Number": g.get("systemNumber", ""),
                "PowerHit": g.get("powerHit", ""),
                "Share_Cost": cost,
                "Available_Shares": avail,
                "Total_Shares": total,
                "Outlet_ID": outlet_id,
                "PB": pb_val,
            }
            for i, n in enumerate(sels, 1):
                row[f"w{i}"] = n
            rows.append(row)
        time.sleep(0)  # placeholder; pacing handled at syndicate level
    return rows


def scrape_postcode(postcode: str) -> list:
    state = postcode_to_state(postcode)
    company = STATE_COMPANY.get(state)
    if company is None:
        return []
    fetch_details._dropped = 0   # per-run drop count (see sweep_state)
    try:
        outlets = get_outlets(postcode, state)
    except Exception as ex:
        print(f"  [{postcode}] outlet error: {ex}")
        return []
    if not outlets:
        return []
    ids = get_syndicate_ids(outlets, company)
    rows = []
    for j, sid in enumerate(ids):
        recs = fetch_details(sid, company)
        for r in recs:
            r["Postcode"] = postcode
            r["State"] = state
        rows.extend(recs)
        time.sleep(0.15)   # be polite to the API
    return rows


def fetch_details_retry(syndicate_id: int, company: int) -> list:
    """fetch_details with retries + backoff. A network blip retries quickly; an
    HTTP 403 means the API is rate-limiting us, so we wait a longer cooldown and
    retry (the data IS there — we just need to slow down). Only after exhausting
    retries do we drop the syndicate."""
    global _throttle_hits
    for attempt in range(1, RETRY_TIMES + 1):
        try:
            rows = fetch_details(syndicate_id, company)
            time.sleep(PER_REQ_PAUSE)
            return rows
        except urllib.error.HTTPError as ex:
            if ex.code == 403:
                # Rate-limited. Heads-up once, then cool down (longer each time).
                with _throttle_lock:
                    _throttle_hits += 1
                    first = _throttle_hits == 1
                if first:
                    with _print_lock:
                        print("    [throttle] API returned 403 (rate limit) — "
                              "cooling down and retrying; the sweep will continue.")
                if attempt == RETRY_TIMES:
                    with _print_lock:
                        print(f"    [drop] syndicate {syndicate_id} still 403 "
                              f"after {RETRY_TIMES} tries.")
                    return []
                time.sleep(THROTTLE_COOLDOWN * attempt)   # 20s, 40s, 60s…
            else:
                if attempt == RETRY_TIMES:
                    with _print_lock:
                        print(f"    [drop] syndicate {syndicate_id}: HTTP {ex.code}")
                    return []
                time.sleep(RETRY_BACKOFF * attempt)
        except Exception as ex:
            if attempt == RETRY_TIMES:
                with _print_lock:
                    print(f"    [drop] syndicate {syndicate_id} after "
                          f"{RETRY_TIMES} tries: {ex}")
                return []
            time.sleep(RETRY_BACKOFF * attempt)
    return []


def collect_syndicate_ids(state: str, company: int):
    """PHASE 1 (cheap, sequential): walk all postcodes, collect the UNIQUE set
    of syndicate IDs. The same syndicate sells at many outlets/postcodes, so this
    avoids fetching its details dozens of times. Returns {syndicate_id: postcode}
    (first postcode it was seen at, for reference only)."""
    pcs = STATE_POSTCODES.get(state, [])
    seen = {}
    for i, pc in enumerate(pcs):
        try:
            outlets = get_outlets(pc, state)
        except Exception as ex:
            with _print_lock:
                print(f"  [{i+1}/{len(pcs)}] {pc} outlet error: {ex}")
            continue
        if not outlets:
            continue
        ids = get_syndicate_ids(outlets, company)
        new = 0
        for sid in ids:
            if sid not in seen:
                seen[sid] = pc
                new += 1
        with _print_lock:
            print(f"  [{i+1}/{len(pcs)}] {pc}: {len(ids)} here, +{new} new "
                  f"(unique so far: {len(seen)})")
        time.sleep(0.1)
    return seen
    base = ["Syndicate_ID", "Syndicate_Name", "Game", "Games", "Game_Check", "Product",
            "CompanyId", "Draw_Number", "Draw_Date", "Entry_Type", "System_Number",
            "PowerHit", "Share_Cost", "Available_Shares", "Total_Shares",
            "Outlet_ID", "Postcode", "State", "PB"]
    max_w = 0
    for r in rows:
        for k in r:
            if k.startswith("w") and k[1:].isdigit():
                max_w = max(max_w, int(k[1:]))
    return base + [f"w{i}" for i in range(1, max_w + 1)]


def _dedup(rows):
    """Collapse identical game-lines. A line is unique by (Syndicate_ID,
    Draw_Number, Game, the selections tuple, PB). The same syndicate is sold at
    many outlets and returned for many postcodes, so without this one state
    sweep produces massive duplication."""
    seen, out = set(), []
    for r in rows:
        wkey = tuple(r.get(f"w{i}") for i in range(1, 40) if r.get(f"w{i}") is not None)
        key = (r.get("Syndicate_ID"), r.get("Draw_Number"), r.get("Game"),
               wkey, r.get("PB"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _columns(rows):
    """Stable, ordered CSV header for the scraped rows: known metadata columns
    first (only those actually present), then PB, then w1..wN sorted by their
    numeric index, then any leftover keys. (This was referenced by save() but the
    definition was lost in an edit — restored here.)"""
    def _is_wcol(k):
        return len(k) > 1 and k[0] == "w" and k[1:].isdigit()

    preferred = ["Syndicate_ID", "Syndicate_Name", "Game", "Games", "Game_Check",
                 "Product", "CompanyId", "Draw_Number", "Draw_Date", "Entry_Type",
                 "System_Number", "PowerHit", "Share_Cost", "Available_Shares",
                 "Total_Shares", "Outlet_ID", "Postcode", "State", "PB"]
    keys = set()
    for r in rows:
        keys.update(r.keys())
    wcols = sorted((k for k in keys if _is_wcol(k)), key=lambda x: int(x[1:]))
    ordered = [c for c in preferred if c in keys]
    rest = sorted(k for k in keys if k not in ordered and not _is_wcol(k))
    return ordered + rest + wcols


def save(rows, path):
    if not rows:
        print("  (no rows)"); return
    before = len(rows)
    rows = _dedup(rows)
    cols = _columns(rows)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  saved {len(rows)} unique game-line rows "
          f"(deduped from {before}) -> {path}")
    dropped = getattr(fetch_details, "_dropped", 0)
    if dropped:
        print(f"  note: {dropped} game-line(s) had a pick beyond every pool (>47) "
              f"and were unkeepable; everything else was re-tagged to its true game.")


def sweep_state(state, label=None, workers=MAX_WORKERS):
    """Two-phase, dedup-first, bounded-parallel state sweep.

    PHASE 1 (sequential, cheap): collect every UNIQUE syndicate ID in the state.
    PHASE 2 (parallel, bounded): fetch each unique syndicate's details ONCE,
             using a small thread pool (default 8). Polite pacing + retries.
    This is both faster AND lighter on thelott than re-fetching duplicates.
    """
    label = label or state
    company = STATE_COMPANY.get(state)
    if company is None:
        print(f"  no company id for {state}"); return []

    # Reset the out-of-pool drop counter so each state reports its OWN count
    # (it's a function attribute that would otherwise accumulate across states).
    fetch_details._dropped = 0

    print(f"--- Phase 1: collecting unique syndicate IDs for {state} ---")
    t0 = time.time()
    id_map = collect_syndicate_ids(state, company)
    ids = list(id_map.keys())
    print(f"--- Phase 1 done: {len(ids)} unique syndicates "
          f"in {time.time()-t0:.0f}s ---")

    if not ids:
        print("  no syndicates found."); return []

    print(f"--- Phase 2: fetching details with {workers} parallel workers ---")
    t1 = time.time()
    all_rows = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_details_retry, sid, company): sid
                   for sid in ids}
        for fut in as_completed(futures):
            sid = futures[fut]
            recs = fut.result() or []
            pc = id_map.get(sid, "")
            for r in recs:
                r["Postcode"] = pc
                r["State"] = state
            all_rows.extend(recs)
            done += 1
            if done % 50 == 0 or done == len(ids):
                with _print_lock:
                    print(f"    details {done}/{len(ids)} "
                          f"({len(all_rows)} rows so far)")
    print(f"--- Phase 2 done in {time.time()-t1:.0f}s ---")

    # Raw, unprocessed scrape lives in Global_Scraper/ — NOT Main_Data/
    # (Main_Data is reserved for the user's own historical draw data).
    save(all_rows, f"Global_Scraper/D_{state}.csv")
    return all_rows


if __name__ == "__main__":
    args = sys.argv[1:] or ["2000"]
    if args[0] == "sweep":
        target = args[1] if len(args) > 1 else "NSW"
        # optional trailing integer = worker count, e.g. "sweep NSW 10"
        workers = MAX_WORKERS
        if len(args) > 2 and args[2].isdigit():
            workers = int(args[2])
        states = list(STATE_COMPANY) if target == "ALL" else [target]
        for s in states:
            print(f"=== sweeping {s} (workers={workers}) ===")
            sweep_state(s, workers=workers)
    else:
        all_rows = []
        for pc in args:
            print(f"Scraping {pc}...")
            rows = scrape_postcode(pc)
            print(f"  -> {len(rows)} game-line rows")
            for r in rows[:5]:
                ws = [r.get(f"w{i}") for i in range(1, 12) if r.get(f"w{i}") is not None]
                print(f"     {str(r['Syndicate_Name'])[:18]:<18} {r['Game']:<4} "
                      f"draw {r['Draw_Number']} PB={r['PB']} {ws}")
            all_rows.extend(rows)
        out = f"syndicate_picks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        save(all_rows, out)
