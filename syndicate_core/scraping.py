import json, re, time, random
import ssl as _ssl
import urllib.request as _urlreq
import threading as _threading
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor, as_completed as _as_completed
import csv as _csv
from pathlib import Path
import pandas as pd

try:
    import requests
    from bs4 import BeautifulSoup
    REQ_OK = True
except ImportError:
    REQ_OK = False

from syndicate_core.config import DIRS, GAMES_CFG, STATE_POSTCODES

__all__ = [
    # thelott API
    "_ssl_ctx", "_api_get", "_is_online",
    "_fetch_outlets", "_fetch_syndicates_batch", "_sweep_state_thelott",
    # picks scraper (public entry point)
    "sweep_state_picks",
    # lottolyzer scraping
    "_fetch_html", "_bs4_find_tables",
    "fetch_number_frequencies", "fetch_draw_history", "fetch_since_last",
    # draw number scraping
    "fetch_current_draw_number",
]

# ═══════════════════════════════════════════════════════════════════════════════
# THELOTT CONFIRMED API — two-step outlet → syndicate scraper
# ═══════════════════════════════════════════════════════════════════════════════

# Company IDs confirmed by testing (NT=no syndicates, WA=Lotterywest no API)
_STATE_COMPANY = {"NSW": 3, "ACT": 3, "VIC": 1, "TAS": 1, "QLD": 2, "SA": 6}

_TLOTT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Origin":  "https://www.thelott.com",
    "Referer": "https://www.thelott.com/",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "Connection": "keep-alive",
}

def _ssl_ctx():
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    return ctx

def _api_get(url: str, _retries: int = 4):
    """Raw GET with SSL bypass and exponential backoff. Returns parsed JSON or None."""
    import gzip as _gz
    for attempt in range(_retries):
        try:
            req = _urlreq.Request(url, headers=_TLOTT_HEADERS)
            with _urlreq.urlopen(req, timeout=15, context=_ssl_ctx()) as r:
                body = r.read()
                try:
                    body = _gz.decompress(body)
                except Exception:
                    pass
                return json.loads(body.decode("utf-8"))
        except Exception as exc:
            if attempt == _retries - 1:
                return None
            wait = (2 ** attempt) + random.uniform(0.1, 0.5)
            time.sleep(wait)
    return None

def _is_online() -> bool:
    """Quick connectivity check to thelott API."""
    try:
        req = _urlreq.Request(
            "https://api.thelott.com/outlet/outlets?state=NSW&postcode_or_locality=2000",
            headers=_TLOTT_HEADERS)
        with _urlreq.urlopen(req, timeout=8, context=_ssl_ctx()):
            return True
    except Exception:
        return False

def _fetch_outlets(state: str, postcode: int) -> list:
    """Step 1: Get all outlet IDs for a postcode."""
    url = (f"https://api.thelott.com/outlet/outlets"
           f"?state={state}&postcode_or_locality={postcode}")
    data = _api_get(url)
    if not data:
        return []
    # API returns {"locality_outlets": [{"locality": "...", "outlets": [...]}]}
    # Fall back to flat list or top-level "outlets" for forward-compat
    if isinstance(data, list):
        flat = data
    elif "locality_outlets" in data:
        flat = [o for loc in data["locality_outlets"]
                for o in loc.get("outlets", [])]
    else:
        flat = data.get("outlets", [])
    ids = []
    for o in flat:
        oid = str(o.get("outlet_id") or o.get("id") or o.get("outletId") or "").strip()
        if oid:
            ids.append(oid)
    return ids

def _fetch_syndicates_batch(company: int, outlet_ids: list) -> list:
    """Step 2: Get syndicates for a comma-separated batch of outlet IDs."""
    if not outlet_ids:
        return []
    url = (f"https://api.thelott.com/syndicates/api/search"
           f"?company={company}&outlets={','.join(outlet_ids)}&limit=100")
    data = _api_get(url)
    if not data:
        return []
    items = (data if isinstance(data, list)
             else data.get("syndicates", data.get("items", data.get("data", []))))
    return items if isinstance(items, list) else []

def _parse_syndicate_row(syn: dict, postcode: int, state: str) -> dict:
    """Map a thelott syndicate API object to the standard CSV schema."""
    def g(*keys):
        for k in keys:
            v = syn.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""
    outlet = syn.get("outlet") or syn.get("store") or {}
    if not isinstance(outlet, dict):
        outlet = {}
    # Collect draw number strings from games/combinations arrays
    draw_numbers = ""
    for gkey in ("games", "combinations", "entries"):
        games = syn.get(gkey, [])
        if isinstance(games, list) and games:
            parts = []
            for gm in games:
                nums = (gm.get("numbers") or gm.get("selections") or []
                        if isinstance(gm, dict) else gm if isinstance(gm, list) else [])
                if nums:
                    parts.append(" ".join(str(n) for n in sorted(nums)))
            if parts:
                draw_numbers = " | ".join(parts)
            break
    return {
        "Postcode":         postcode,
        "State":            state,
        "Syndicate_ID":     g("syndicateId", "id", "syndicateNumber"),
        "Syndicate_Name":   g("syndicateName", "title", "name", "description"),
        "Draw_Date":        g("syndicateDate", "drawDate", "draw_date", "scheduledDate", "closeDate"),
        "Share_Cost":       g("sharePrice", "price", "costPerShare", "shareCost"),
        "Available_Shares": g("availableShares", "sharesAvailable", "sharesRemaining"),
        "Total_Shares":     g("totalShares", "shareCount", "shares"),
        "Games":            g("gameType", "gameName", "product", "type"),
        "Draw_Numbers":     draw_numbers,
        "Outlet_ID":        g("outletId") or str(outlet.get("id", "")),
        "Outlet_Name":      g("agentName", "storeName") or str(outlet.get("name", "")),
        "Address":          str(outlet.get("address", g("address"))),
        "Suburb":           str(outlet.get("suburb", g("suburb"))),
    }

def _sweep_state_thelott(state: str, postcodes: list,
                          pb, stx) -> pd.DataFrame:
    """
    Full sweep for one state using confirmed two-step thelott API.
    Deduplicates by Syndicate_ID. Returns DataFrame.
    """
    company = _STATE_COMPANY.get(state)
    if company is None:
        return pd.DataFrame()

    seen_ids = {}   # syndicate_id → row dict
    total = len(postcodes)

    for i, pc in enumerate(postcodes):
        pb.progress(
            (i + 1) / total,
            text=f"[{state}] {pc}  ({i+1}/{total}) — {len(seen_ids)} syndicates so far"
        )
        stx.caption(f"🔍 {state} · postcode {pc}")

        outlet_ids = _fetch_outlets(state, pc)
        if not outlet_ids:
            time.sleep(random.uniform(0.1, 0.25))
            continue

        # Batch outlets in groups of 20 (comma-separated — critical format)
        for b in range(0, len(outlet_ids), 20):
            batch = outlet_ids[b:b + 20]
            syns  = _fetch_syndicates_batch(company, batch)
            for syn in syns:
                row = _parse_syndicate_row(syn, pc, state)
                sid = row["Syndicate_ID"] or f"{pc}_{b}_{syns.index(syn)}"
                if sid not in seen_ids:
                    seen_ids[sid] = row
            time.sleep(random.uniform(0.08, 0.20))

        time.sleep(random.uniform(0.20, 0.55))

    stx.empty()
    return pd.DataFrame(list(seen_ids.values())) if seen_ids else pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# PICKS SCRAPER — full syndicate picks via thelott details API
#     (previously thelott_picks_scraper.py — now inlined, no external file needed)
#     Output: w1..wN columns per game line, saved to Global_Scraper/D_{STATE}.csv
# ═══════════════════════════════════════════════════════════════════════════════

_PICKS_MAX_WORKERS    = 6
_PICKS_PER_REQ_PAUSE  = 0.12
_PICKS_RETRY_TIMES    = 4
_PICKS_RETRY_BACKOFF  = 1.5
_PICKS_THROTTLE_CD    = 20
_picks_print_lock     = _threading.Lock()
_picks_throttle_lock  = _threading.Lock()
_picks_throttle_hits  = 0

_GAME_BY_COMPANY_PRODUCT = {
    (3, 6): "sat", (3, 22): "sat", (3, 7): "mwf", (3, 25): "mwf",
    (3, 8): "oz",  (3, 23): "oz",  (3, 9): "pb",  (3, 24): "pb",
    (3, 10): "sfl", (3, 27): "sfl", (3, 37): "sat", (3, 1): "sat",
    (3, 2): "oz", (3, 3): "pb", (3, 4): "mwf", (3, 5): "sfl",
    (1, 1): "sat", (1, 2): "oz", (1, 3): "pb", (1, 4): "mwf", (1, 5): "sfl",
    (2, 14): "sat", (2, 19): "sat", (2, 15): "oz", (2, 20): "oz",
    (2, 16): "pb",  (2, 21): "pb",  (2, 17): "mwf", (2, 18): "sfl", (2, 3): "pb",
    (6, 22): "sat", (6, 14): "sat", (6, 15): "oz", (6, 16): "pb",
    (6, 17): "mwf", (6, 18): "sfl", (6, 19): "sat",
}

_GAME_KEY_TO_NAME = {
    "pb": "Powerball", "oz": "Oz Lotto", "sat": "Saturday Lotto",
    "mwf": "Monday & Wednesday Lotto", "sfl": "Set for Life",
}

_PICKS_POOL_MAX = {gk: cfg["pool"] for gk, cfg in GAMES_CFG.items()}

_PICKS_DRAW_RANGES = {
    "pb":  (1400, 1900), "oz":  (1500, 1900),
    "sat": (4400, 4900), "mwf": (4400, 4900), "sfl": (1, 99999),
}

_PICKS_STATE_COMPANY = {"NSW": 3, "ACT": 3, "VIC": 1, "TAS": 1, "QLD": 2, "SA": 6}


def _picks_api_get(url: str) -> dict:
    import urllib.request as _ur, ssl as _ssl2
    ctx = _ssl2.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl2.CERT_NONE
    req = _ur.Request(url, headers={
        "Accept": "application/json",
        "Origin": "https://www.thelott.com",
        "Referer": "https://www.thelott.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })
    with _ur.urlopen(req, timeout=15, context=ctx) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def _picks_outlets(postcode: str, state: str) -> list:
    data = _picks_api_get(
        f"https://api.thelott.com/outlet/outlets"
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


def _picks_syndicate_ids(outlet_ids: list, company: int, batch: int = 20) -> list:
    seen = set()
    for i in range(0, len(outlet_ids), batch):
        csv_ids = ",".join(str(o) for o in outlet_ids[i:i + batch])
        try:
            data = _picks_api_get(
                f"https://api.thelott.com/syndicates/api/search"
                f"?company={company}&outlets={csv_ids}&limit=100")
            for s in data.get("data", []):
                seen.add(s["syndicateId"])
        except Exception as ex:
            print(f"    [warn] search batch: {ex}")
        time.sleep(0.15)
    return sorted(seen)


def _game_for(company, product, draw_number):
    g = _GAME_BY_COMPANY_PRODUCT.get((company, product))
    if g and draw_number:
        lo, hi = _PICKS_DRAW_RANGES.get(g, (1, 99999))
        if not (lo <= int(draw_number) <= hi):
            return g, f"CHECK(draw {draw_number} out of {g} range)"
    return (g or f"unknown_c{company}_p{product}"), ""


def _resolve_game(company, product, draw_number, selections):
    g, note = _game_for(company, product, draw_number)
    mx = max(int(n) for n in selections) if selections else 0
    pool = _PICKS_POOL_MAX.get(g)
    if pool is not None and mx <= pool and g in _PICKS_POOL_MAX:
        return g, note
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
        for gk in ("pb", "sfl", "sat", "mwf", "oz"):
            if _PICKS_POOL_MAX.get(gk, 0) >= mx:
                inferred = gk; break
    if inferred and _PICKS_POOL_MAX.get(inferred, 0) >= mx:
        tag = "retagged" if g in _PICKS_POOL_MAX else "inferred"
        return inferred, f"{tag} {g}->{inferred} (max {mx}, draw {dn})"
    return (g or "unknown"), f"UNRESOLVED (max {mx})"


def _picks_fetch_details(syndicate_id: int, company: int) -> list:
    try:
        b = _picks_api_get(
            f"https://api.thelott.com/syndicates/api/details"
            f"?syndicateId={syndicate_id}&companyId={company}")
    except Exception as ex:
        print(f"    [warn] details {syndicate_id}: {ex}"); return []
    name  = (b.get("syndicateName") or "").strip()
    cost  = b.get("shareCost", "")
    avail = b.get("availableShares", "")
    total = b.get("totalShares", "")
    outlets = b.get("outlets", [])
    outlet_id = ""
    if isinstance(outlets, list) and outlets:
        outlet_id = (outlets[0].get("outletId") if isinstance(outlets[0], dict) else "") or ""
    rows = []
    for bet in b.get("syndicateBets", []):
        product    = bet.get("product")
        draws      = bet.get("draws", [])
        draw_no    = draws[0].get("drawNumber") if draws else ""
        draw_dt    = (draws[0].get("drawDate", "")[:10]) if draws else ""
        entries    = bet.get("entries", [])
        entry_type = entries[0].get("entryType", "") if entries else ""
        for g in bet.get("games", []):
            sels = g.get("selections", []) or []
            if not sels:
                continue
            game, warn = _resolve_game(company, product, draw_no, sels)
            mx = max(int(n) for n in sels)
            if mx > max(_PICKS_POOL_MAX.values()) or mx < 1:
                continue
            pb_raw = g.get("powerball", "")
            if game != "pb":
                pb_val = ""
            elif g.get("powerHit") and (pb_raw in (0, "0", None, "")):
                pb_val = "PH"
            elif pb_raw in (0, "0", None, ""):
                pb_val = ""
            else:
                pb_val = pb_raw
            row = {
                "Syndicate_ID": syndicate_id, "Syndicate_Name": name,
                "Game": game, "Games": _GAME_KEY_TO_NAME.get(game, game),
                "Game_Check": warn, "Product": product, "CompanyId": company,
                "Draw_Number": draw_no, "Draw_Date": draw_dt,
                "Entry_Type": entry_type, "System_Number": g.get("systemNumber", ""),
                "PowerHit": g.get("powerHit", ""), "Share_Cost": cost,
                "Available_Shares": avail, "Total_Shares": total,
                "Outlet_ID": outlet_id, "PB": pb_val,
            }
            for i, n in enumerate(sorted(int(x) for x in sels), 1):
                row[f"w{i}"] = n
            rows.append(row)
    return rows


def _picks_fetch_retry(syndicate_id: int, company: int) -> list:
    global _picks_throttle_hits
    import urllib.error as _urlerr2
    for attempt in range(1, _PICKS_RETRY_TIMES + 1):
        try:
            rows = _picks_fetch_details(syndicate_id, company)
            time.sleep(_PICKS_PER_REQ_PAUSE)
            return rows
        except _urlerr2.HTTPError as ex:
            if ex.code == 403:
                with _picks_throttle_lock:
                    _picks_throttle_hits += 1
                    first = (_picks_throttle_hits == 1)
                if first:
                    with _picks_print_lock:
                        print("    [throttle] 403 rate limit — cooling down and retrying")
                if attempt == _PICKS_RETRY_TIMES:
                    return []
                time.sleep(_PICKS_THROTTLE_CD * attempt)
            else:
                if attempt == _PICKS_RETRY_TIMES:
                    return []
                time.sleep(_PICKS_RETRY_BACKOFF * attempt)
        except Exception:
            if attempt == _PICKS_RETRY_TIMES:
                return []
            time.sleep(_PICKS_RETRY_BACKOFF * attempt)
    return []


def _picks_collect_ids(state: str, company: int) -> dict:
    """Phase 1 (sequential): collect unique syndicate IDs across all postcodes."""
    pcs = [str(p) for p in STATE_POSTCODES.get(state, [])]
    seen: dict = {}
    for i, pc in enumerate(pcs):
        try:
            outlets = _picks_outlets(pc, state)
        except Exception as ex:
            print(f"  [{i+1}/{len(pcs)}] {pc} outlet error: {ex}"); continue
        if not outlets:
            continue
        ids = _picks_syndicate_ids(outlets, company)
        new = sum(1 for sid in ids if sid not in seen)
        for sid in ids:
            if sid not in seen:
                seen[sid] = pc
        print(f"  [{i+1}/{len(pcs)}] {pc}: {len(ids)} here, +{new} new (unique: {len(seen)})")
        time.sleep(0.1)
    return seen


def _picks_dedup(rows: list) -> list:
    seen: set = set()
    out = []
    for r in rows:
        wkey = tuple(r.get(f"w{i}") for i in range(1, 40) if r.get(f"w{i}") is not None)
        key = (r.get("Syndicate_ID"), r.get("Draw_Number"), r.get("Game"), wkey, r.get("PB"))
        if key not in seen:
            seen.add(key); out.append(r)
    return out


def _picks_columns(rows: list) -> list:
    preferred = ["Syndicate_ID", "Syndicate_Name", "Game", "Games", "Game_Check",
                 "Product", "CompanyId", "Draw_Number", "Draw_Date", "Entry_Type",
                 "System_Number", "PowerHit", "Share_Cost", "Available_Shares",
                 "Total_Shares", "Outlet_ID", "Postcode", "State", "PB"]
    keys: set = set()
    for r in rows:
        keys.update(r.keys())
    wcols = sorted((k for k in keys if len(k) > 1 and k[0] == "w" and k[1:].isdigit()),
                   key=lambda x: int(x[1:]))
    ordered = [c for c in preferred if c in keys]
    rest = sorted(k for k in keys if k not in ordered
                  and not (len(k) > 1 and k[0] == "w" and k[1:].isdigit()))
    return ordered + rest + wcols


def sweep_state_picks(state: str, workers: int = _PICKS_MAX_WORKERS,
                      save_path: "Path | None" = None) -> list:
    """Two-phase dedup-first sweep — returns rows with w1..wN actual picks.
    Saves to Global_Scraper/D_{state}.csv (or override with save_path).

    Replaces: python3 thelott_picks_scraper.py sweep {state}
    Now call:  from syndicate_core.scraping import sweep_state_picks; sweep_state_picks('NSW')
    """
    global _picks_throttle_hits
    _picks_throttle_hits = 0
    company = _PICKS_STATE_COMPANY.get(state)
    if company is None:
        print(f"  no company id for {state}"); return []

    print(f"--- Phase 1: collecting unique syndicate IDs for {state} ---")
    t0 = time.time()
    id_map = _picks_collect_ids(state, company)
    ids = list(id_map.keys())
    print(f"--- Phase 1 done: {len(ids)} unique syndicates in {time.time()-t0:.0f}s ---")
    if not ids:
        print("  no syndicates found."); return []

    print(f"--- Phase 2: fetching details ({workers} workers) ---")
    t1 = time.time()
    all_rows: list = []
    done = 0
    with _ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_picks_fetch_retry, sid, company): sid for sid in ids}
        for fut in _as_completed(futures):
            sid = futures[fut]
            recs = fut.result() or []
            pc = id_map.get(sid, "")
            for r in recs:
                r["Postcode"] = pc; r["State"] = state
            all_rows.extend(recs)
            done += 1
            if done % 50 == 0 or done == len(ids):
                with _picks_print_lock:
                    print(f"    details {done}/{len(ids)} ({len(all_rows)} rows so far)")
    print(f"--- Phase 2 done in {time.time()-t1:.0f}s ---")

    before = len(all_rows)
    all_rows = _picks_dedup(all_rows)
    if not all_rows:
        print("  (no rows)"); return []
    out_path = save_path or (DIRS["Global_Scraper"] / f"D_{state}.csv")
    cols = _picks_columns(all_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import os as _os
    tmp_path = out_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(all_rows)
        _os.replace(tmp_path, out_path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    print(f"  saved {len(all_rows)} unique rows (deduped from {before}) -> {out_path}")
    return all_rows


# ═══════════════════════════════════════════════════════════════════════════════
# LOTTOLYZER SCRAPING — number frequencies, draw history, since-last
# ═══════════════════════════════════════════════════════════════════════════════

# ── Shared fetch helper: urllib (SSL-bypass) → requests fallback ─────────────
_FETCH_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

def _fetch_html(url: str, timeout: int = 30) -> str | None:
    """Fetch URL as text using urllib with SSL bypass; falls back to requests.

    Returns HTML string or None on failure.
    """
    import urllib.request as _ur
    # ── attempt 1: urllib + SSL bypass (handles Mac cert issues) ────────────
    try:
        req = _ur.Request(url, headers={"User-Agent": _FETCH_UA})
        return _ur.urlopen(req, timeout=timeout, context=_ssl_ctx()).read().decode("utf-8", "ignore")
    except Exception:
        pass
    # ── attempt 2: requests with SSL verification disabled ───────────────────
    if REQ_OK:
        try:
            import warnings, urllib3
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    urllib3.disable_warnings()
                except Exception:
                    pass
                resp = requests.get(url, headers={"User-Agent": _FETCH_UA},
                                    timeout=timeout, verify=False)
                resp.raise_for_status()
                return resp.text
        except Exception:
            pass
    return None


def fetch_current_draw_number(game_key: str) -> int | None:
    """Scrape thelott.com play page to get the current selling draw number.

    Returns the draw number as int, or None if scraping fails.
    Uses SSL bypass already established in this module.
    """
    import re
    urls = {
        "sat": "https://www.thelott.com/saturday-lotto/play",
        "pb":  "https://www.thelott.com/powerball/play",
        "oz":  "https://www.thelott.com/oz-lotto/play",
        "sfl": "https://www.thelott.com/set-for-life/play",
        "mwf": "https://www.thelott.com/monday-wednesday-lotto/play",
    }
    url = urls.get(game_key)
    if not url:
        return None
    try:
        html = _fetch_html(url, timeout=10)
        if not html:
            return None
        m = re.search(r'[Dd]raw\s+(\d{4,5})', html)
        if m:
            return int(m.group(1))
        return None
    except Exception:
        return None


def _bs4_find_tables(html: str):
    """Parse HTML with BeautifulSoup and return list of (headers_lower, rows).

    headers_lower : list[str]   — column header text, lowercased
    rows          : list[list[str]] — cell text per body row
    Falls back gracefully if bs4 unavailable.
    """
    result = []
    if not REQ_OK:
        return result
    try:
        soup = BeautifulSoup(html, "html.parser")
        for table in soup.find_all("table"):
            # Collect header row(s)
            headers = []
            thead = table.find("thead")
            if thead:
                for th in thead.find_all(["th", "td"]):
                    headers.append(th.get_text(strip=True).lower())
            if not headers:
                first_row = table.find("tr")
                if first_row:
                    headers = [c.get_text(strip=True).lower()
                               for c in first_row.find_all(["th", "td"])]
            # Collect data rows
            body_rows = []
            tbody = table.find("tbody")
            src = tbody if tbody else table
            for tr in src.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells and any(c for c in cells):
                    body_rows.append(cells)
            if headers and body_rows:
                # Drop header row if it accidentally ended up in body_rows
                if body_rows and [c.lower() for c in body_rows[0]] == headers:
                    body_rows = body_rows[1:]
                result.append((headers, body_rows))
    except Exception:
        pass
    return result


def fetch_number_frequencies(url: str, pool: int):
    """Scrape the full number-frequency table from a lottolyzer frequencies page.

    Returns a DataFrame with columns:
        number, winning_no, powerball, overall, from_last, since_last, avg_draw
    Numbers outside 1..pool are dropped.  Returns None on failure.
    Tries pd.read_html first; falls back to BeautifulSoup direct parsing.
    """
    html = _fetch_html(url)
    if not html:
        return None

    COL_MAP = {
        "number":     ["number", "no", "no.", "ball"],
        "winning_no": ["winning no", "winning no.", "winning", "wins", "times drawn", "drawn"],
        "powerball":  ["powerball", "pb"],
        "overall":    ["overall", "total", "total drawn"],
        "from_last":  ["from last", "last drawn", "from last draw"],
        "since_last": ["since last", "since", "games since", "last seen", "draws since"],
        "avg_draw":   ["avg draw", "average", "avg", "avg gap"],
    }

    def _find_col(cols_lower, keys):
        for c_lower, c_orig in cols_lower.items():
            for k in keys:
                if k in c_lower:
                    return c_orig
        return None

    def _parse_pd_tables(tables):
        for t in tables:
            cols_lower = {str(c).strip().lower(): c for c in t.columns}
            num_c = _find_col(cols_lower, COL_MAP["number"])
            sl_c  = _find_col(cols_lower, COL_MAP["since_last"])
            if not (num_c and sl_c):
                continue
            rows = []
            for _, row in t.iterrows():
                try:
                    n = int(float(str(row[num_c]).strip()))
                    if not (1 <= n <= pool):
                        continue
                    def _get(key, _cl=cols_lower, _r=row):
                        c = _find_col(_cl, COL_MAP[key])
                        if c is None:
                            return None
                        try:
                            return int(float(str(_r[c]).strip()))
                        except Exception:
                            return None
                    rows.append({
                        "number":     n,
                        "winning_no": _get("winning_no"),
                        "powerball":  _get("powerball"),
                        "overall":    _get("overall"),
                        "from_last":  _get("from_last"),
                        "since_last": _get("since_last"),
                        "avg_draw":   _get("avg_draw"),
                    })
                except Exception:
                    pass
            if rows:
                return pd.DataFrame(rows).sort_values("number").reset_index(drop=True)
        return None

    # ── primary: pd.read_html ───────────────────────────────────────────────
    try:
        result = _parse_pd_tables(pd.read_html(html))
        if result is not None:
            return result
    except Exception:
        pass

    # ── fallback: BeautifulSoup direct parse ────────────────────────────────
    for headers, body_rows in _bs4_find_tables(html):
        def _col_idx(keys):
            for i, h in enumerate(headers):
                for k in keys:
                    if k in h:
                        return i
            return None
        num_i = _col_idx(COL_MAP["number"])
        sl_i  = _col_idx(COL_MAP["since_last"])
        if num_i is None or sl_i is None:
            continue
        rows = []
        for cells in body_rows:
            try:
                n = int(float(cells[num_i]))
                if not (1 <= n <= pool):
                    continue
                def _geti(i, _cells=cells):
                    try:
                        return int(float(_cells[i])) if i < len(_cells) else None
                    except Exception:
                        return None
                rows.append({
                    "number":     n,
                    "winning_no": _geti(_col_idx(COL_MAP["winning_no"]) or -1),
                    "powerball":  _geti(_col_idx(COL_MAP["powerball"]) or -1),
                    "overall":    _geti(_col_idx(COL_MAP["overall"]) or -1),
                    "from_last":  _geti(_col_idx(COL_MAP["from_last"]) or -1),
                    "since_last": _geti(sl_i),
                    "avg_draw":   _geti(_col_idx(COL_MAP["avg_draw"]) or -1),
                })
            except Exception:
                pass
        if rows:
            return pd.DataFrame(rows).sort_values("number").reset_index(drop=True)
    return None


def fetch_draw_history(game_key: str, pages: int = 3):
    """Scrape draw-history pages from lottolyzer for the given game.

    Returns a DataFrame with columns: draw, date, numbers (sorted), powerball.
    Rows are newest first.  Returns None if unreachable or can't be parsed.
    Tries pd.read_html first; falls back to BeautifulSoup direct parsing.
    """
    gcfg = GAMES_CFG.get(game_key, {})
    freq_url = gcfg.get("lottolyzer", "")
    if not freq_url:
        return None
    # Use explicit history_url if provided; otherwise derive it from the
    # frequency URL by substituting /number-frequencies/ → /history/.
    hist_base = gcfg.get("history_url") or freq_url.replace("/number-frequencies/", "/history/")
    all_rows = []

    _DRAW_KEYS  = ("draw", "draw no", "draw no.", "draw number")
    _NUM_KEYS   = lambda k: "winning" in k or k == "numbers"
    _DATE_KEYS  = lambda k: "date" in k
    _PB_KEYS    = lambda k: "powerball" in k or k == "pb"

    def _extract_rows_from_pd_table(t):
        cols_lower = {str(c).strip().lower(): c for c in t.columns}
        draw_c = next((cols_lower[k] for k in cols_lower if k in _DRAW_KEYS), None)
        num_c  = next((cols_lower[k] for k in cols_lower if _NUM_KEYS(k)), None)
        date_c = next((cols_lower[k] for k in cols_lower if _DATE_KEYS(k)), None)
        pb_c   = next((cols_lower[k] for k in cols_lower if _PB_KEYS(k)), None)
        if not num_c:
            return []
        found = []
        for _, row in t.iterrows():
            try:
                raw_nums = str(row[num_c]).strip()
                # Skip header-repeat rows (lottolyzer repeats <thead> content as
                # <td> rows in <tbody>). If the "winning numbers" cell contains no
                # digits at all it must be a header row — skip it.
                if not re.search(r'\d', raw_nums):
                    continue
                nums = sorted([int(x) for x in re.split(r"[,\s]+", raw_nums)
                               if x.strip().isdigit()])
                if not nums:
                    continue
                date_str = str(row[date_c]).strip() if date_c else ""
                # Derive draw number.
                # Powerball: lottolyzer "Draw" column is a real sequential integer.
                # All other games: "Draw" column contains a date (MM/DD/YYYY).
                # For non-Powerball we derive draw_no as YYYYMMDD from the date value
                # so we get a stable, unique key that sorts chronologically.
                draw_val = str(row[draw_c]).strip() if draw_c else ""
                if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', draw_val) or \
                        re.match(r'^\d{4}-\d{2}-\d{2}$', draw_val):
                    # Date string in the Draw column → derive YYYYMMDD
                    try:
                        _dt = pd.to_datetime(draw_val, dayfirst=False)
                        draw_no = int(_dt.strftime("%Y%m%d"))
                    except Exception:
                        if date_str:
                            try:
                                _dt = pd.to_datetime(date_str)
                                draw_no = int(_dt.strftime("%Y%m%d"))
                            except Exception:
                                continue
                        else:
                            continue
                else:
                    try:
                        draw_no = int(float(draw_val))
                    except Exception:
                        # Fallback: use date column if draw column is unusable
                        if date_str:
                            try:
                                _dt = pd.to_datetime(date_str)
                                draw_no = int(_dt.strftime("%Y%m%d"))
                            except Exception:
                                continue
                        else:
                            continue
                pb = None
                if pb_c:
                    try:
                        pb = int(float(str(row[pb_c]).strip()))
                    except Exception:
                        pass
                found.append({"draw": draw_no, "date": date_str,
                              "numbers": nums, "powerball": pb})
            except Exception:
                pass
        return found

    def _extract_rows_from_bs4_table(headers, body_rows):
        def _ci(pred):
            return next((i for i, h in enumerate(headers) if pred(h)), None)
        draw_i = _ci(lambda h: h in _DRAW_KEYS)
        num_i  = _ci(lambda h: _NUM_KEYS(h))
        date_i = _ci(lambda h: _DATE_KEYS(h))
        pb_i   = _ci(lambda h: _PB_KEYS(h))
        if num_i is None:
            return []
        found = []
        for cells in body_rows:
            try:
                raw_nums = cells[num_i] if num_i < len(cells) else ""
                # Skip header-repeat rows — winning numbers cell must contain digits
                if not re.search(r'\d', raw_nums):
                    continue
                nums = sorted([int(x) for x in re.split(r"[,\s]+", raw_nums)
                               if x.strip().isdigit()])
                if not nums:
                    continue
                date_str = cells[date_i] if date_i is not None and date_i < len(cells) else ""
                # Derive draw number (same logic as pd path above)
                draw_val = cells[draw_i] if draw_i is not None and draw_i < len(cells) else ""
                if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', draw_val) or \
                        re.match(r'^\d{4}-\d{2}-\d{2}$', draw_val):
                    try:
                        _dt = pd.to_datetime(draw_val, dayfirst=False)
                        draw_no = int(_dt.strftime("%Y%m%d"))
                    except Exception:
                        if date_str:
                            try:
                                _dt = pd.to_datetime(date_str)
                                draw_no = int(_dt.strftime("%Y%m%d"))
                            except Exception:
                                continue
                        else:
                            continue
                else:
                    try:
                        draw_no = int(float(draw_val))
                    except Exception:
                        if date_str:
                            try:
                                _dt = pd.to_datetime(date_str)
                                draw_no = int(_dt.strftime("%Y%m%d"))
                            except Exception:
                                continue
                        else:
                            continue
                pb = None
                if pb_i is not None and pb_i < len(cells):
                    try:
                        pb = int(float(cells[pb_i]))
                    except Exception:
                        pass
                found.append({"draw": draw_no, "date": date_str,
                              "numbers": nums, "powerball": pb})
            except Exception:
                pass
        return found

    for pg in range(1, pages + 1):
        url = f"{hist_base}/page/{pg}/per-page/50/summary-view"
        html = _fetch_html(url)
        if not html:
            break

        # ── primary: pd.read_html ─────────────────────────────────────────
        page_found = False
        try:
            for t in pd.read_html(html):
                rows = _extract_rows_from_pd_table(t)
                if rows:
                    all_rows.extend(rows)
                    page_found = True
                    break
        except Exception:
            pass

        # ── fallback: BeautifulSoup ───────────────────────────────────────
        if not page_found:
            for headers, body_rows in _bs4_find_tables(html):
                rows = _extract_rows_from_bs4_table(headers, body_rows)
                if rows:
                    all_rows.extend(rows)
                    page_found = True
                    break

    if not all_rows:
        return None
    df = pd.DataFrame(all_rows).drop_duplicates(subset=["draw"]).sort_values(
        "draw", ascending=False).reset_index(drop=True)
    return df


def fetch_since_last(url: str, pool: int) -> dict | None:
    """Best-effort scrape of a lottolyzer number-frequencies page.

    Returns {number: since_last} for numbers 1..pool, or None if the page
    can't be parsed (in which case the caller falls back to manual upload).
    Tries urllib+SSL-bypass first, then requests fallback; parses with
    pd.read_html first, then BeautifulSoup fallback.
    """
    html = _fetch_html(url)
    if not html:
        return None

    _NUM_KEYS = ("number", "no", "no.", "ball")
    _SL_KEYS  = ("since", "games since", "last seen", "draws since")

    def _dict_from_pd(tables):
        for t in tables:
            cols = {str(c).strip().lower(): c for c in t.columns}
            num_c = next((cols[k] for k in cols
                          if k in _NUM_KEYS or "number" in k), None)
            sl_c  = next((cols[k] for k in cols
                          if any(sk in k for sk in _SL_KEYS)), None)
            if not (num_c and sl_c):
                continue
            d = {}
            for _, row in t.iterrows():
                try:
                    n = int(float(str(row[num_c]).strip()))
                    s = int(float(str(row[sl_c]).strip()))
                    if 1 <= n <= pool:
                        d[n] = s
                except (ValueError, TypeError):
                    pass
            if d:
                return d
        return None

    def _dict_from_bs4(tables):
        for headers, body_rows in tables:
            num_i = next((i for i, h in enumerate(headers)
                          if h in _NUM_KEYS or "number" in h), None)
            sl_i  = next((i for i, h in enumerate(headers)
                          if any(sk in h for sk in _SL_KEYS)), None)
            if num_i is None or sl_i is None:
                continue
            d = {}
            for cells in body_rows:
                try:
                    n = int(float(cells[num_i]))
                    s = int(float(cells[sl_i]))
                    if 1 <= n <= pool:
                        d[n] = s
                except (ValueError, TypeError, IndexError):
                    pass
            if d:
                return d
        return None

    # ── primary: pd.read_html ───────────────────────────────────────────────
    try:
        result = _dict_from_pd(pd.read_html(html))
        if result:
            return result
    except Exception:
        pass

    # ── fallback: BeautifulSoup direct parse ────────────────────────────────
    return _dict_from_bs4(_bs4_find_tables(html))
