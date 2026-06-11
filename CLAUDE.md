# CLAUDE.md — o_Automation_Suite

## Canonical file

The one and only source file is:

```
/Users/mamba/Desktop/Sika/o_Automation_Suite/masterapp.py
```

Do not search for, read, or edit `Sika.py`, copies elsewhere on the filesystem, or any backup file. All fixes go here.

---

## Lottolyzer URLs (verified 2026-06-11)

| Game key | URL | Notes |
|----------|-----|-------|
| `pb`  | `https://en.lottolyzer.com/number-frequencies/australia/powerball` | Pool 35; historical draws pre-2018 had 1–40 |
| `oz`  | `https://en.lottolyzer.com/number-frequencies/australia/oz-lotto` | Pool 47; older-format draws may show higher numbers |
| `sat` | `https://en.lottolyzer.com/number-frequencies/australia/tattslotto` | Pool 45, Saturday draws ~4683+. `saturday-lotto` was WRONG |
| `sfl` | `https://en.lottolyzer.com/number-frequencies/australia/set-for-life` | Pool 44, daily draws |
| `mwf` | `https://en.lottolyzer.com/number-frequencies/australia/weekday-windfall` | Pool 45, Mon/Wed/Fri draws ~4692+. `tatts-lotto` was WRONG (served SFL data) |

History URL is auto-derived from the frequency URL via `.replace("/number-frequencies/", "/history/")` — no separate `history_url` override needed for any game.

Dead / wrong slugs never to use:
- `saturday-lotto` — does not exist on lottolyzer
- `tatts-lotto` (hyphenated) — redirects to / serves Set for Life data
- `tattslotto` is Saturday Lotto; `weekday-windfall` is Mon/Wed/Fri — they are distinct games

---

## Session state key convention

**Game-specific data lives in top-level `st.session_state` via three helpers defined at the top of the SESSION STATE section (~line 1149):**

```python
def gkey(name: str) -> str:
    """Return a session_state key scoped to the active game."""
    return f"{name}__{active_game()}"   # double underscore separator

def gs(name: str, default=None):
    """Get a game-scoped session_state value, with default."""
    return st.session_state.get(gkey(name), default)

def gs_set(name: str, value):
    """Set a game-scoped session_state value."""
    st.session_state[gkey(name)] = value
    return value
```

**Always use these helpers for game-scoped reads/writes:**
```python
# Read
df = gs("B", pd.DataFrame())
df = gs("D", pd.DataFrame())
d = gs("cvi", {})

# Write
gs_set("B", new_df)
gs_set("main_data", df)

# Sub-key assignment for dict values (cvi, results)
st.session_state.setdefault(gkey("cvi"), {})[formula_name] = result
st.session_state.setdefault(gkey("results"), {})[db] = res
```

The key format is `"{name}__{game}"` (double underscore), e.g. `"B__sat"`, `"D__pb"`.

**Special case: `_auto_wire_generators(gdirs, gk)`** — the `gk` parameter (renamed from `gkey` to avoid shadowing the global function) must use `st.session_state[f"X__{gk}"]` directly since the function accepts an explicit game argument rather than using `active_game()`.

**Special case: game selector button** — uses `st.session_state[f"B__{_gk}"]` directly because `_gk` is the clicked game, not the currently active game.

**Special case: `_d_full_key` / `_d_draw_key`** — local vars set to `gkey("D_full")` and `gkey("active_draw")`, then accessed via `st.session_state[_d_full_key]` / `st.session_state.pop(_d_draw_key, None)` etc.

**Unscoped keys remain in `S` (st.session_state.S) — infrastructure/UI only:**
```python
S["cf_active"]                # formula UI preferences
S["auto"]                     # UI automation flags
S["scrape_log"]               # global scrape log
S["confirmed_api_url"]        # global scraper config
S["cookie_str"]               # global scraper config
S["container_status"]         # container progress tracking
S["cvi_upload_v"]             # widget version counters
S["md_upload_v"]
S["sc_upload_v"]
S["main_data_auto_loaded_game"]   # sentinel for last auto-loaded game
S["carry_fwd_{db}"]           # per-dashboard, not per-game
S["sc_avail_{db}"]            # per-dashboard, not per-game
```

**`_init_state()` guard:** `if "S" in st.session_state and gkey("B") in st.session_state: return`

---

## Changelog

> Before making changes, scan this list. Do not redo or revert completed fixes.

| Date | Fix |
|------|-----|
| 2026-06 | **Scraping headers** — added `_TLOTT_HEADERS` with `Accept`, `Accept-Encoding: gzip`, `User-Agent` to all lottolyzer HTTP requests to avoid 403/empty responses |
| 2026-06 | **gzip decompression** — lottolyzer responses are gzip-compressed; added `gzip.decompress()` fallback when `urllib` does not auto-decompress |
| 2026-06 | **Retry logic** — `_picks_fetch_retry()` retries on 403 rate-limit with throttle/cooldown before giving up |
| 2026-06 | **Games column splitting** — when a row's `Games` cell lists multiple game names, the scraper splits it into one row per game so each B-file row belongs to exactly one game |
| 2026-06 | **Postcode/State retention** — `Postcode` and `State` are carried through from the API fetch row into every split/pick row; listed as preferred columns in `_picks_columns()` |
| 2026-06 | **Dedup on Syndicate_ID** — `_merge_b()` deduplicates combined B DataFrames on `Syndicate_ID` only, guarding against accidental re-runs appending duplicate rows |
| 2026-06 | **Logging instead of silent except** — bare `except: pass` blocks replaced with explicit logging to `scrape_log` so failures are visible in the UI |
| 2026-06-11 | **sat lottolyzer URL** — `saturday-lotto` → `tattslotto`; deleted stale `Games/SAT/sincelast_sat/` cache files |
| 2026-06-11 | **mwf lottolyzer URL** — `tatts-lotto` → `weekday-windfall`; deleted stale `Games/MWF/sincelast_mwf/` cache files (contained Set for Life data) |
| 2026-06-11 | **Game-scoped session state (phase 1)** — renamed 11 keys in S dict to `_{gkey}` suffix; `_gkey` hoisted to top level |
| 2026-06-12 | **Game-scoped session state (phase 2)** — introduced `gkey()`/`gs()`/`gs_set()` helpers; game data moved from `S` dict to top-level `st.session_state` with `__{game}` double-underscore separator; `_auto_wire_generators` param renamed `gkey→gk` to avoid shadowing global; broken base-var lookups in formula join preview fixed (`S.get(b)` → `gs(b)`) |

---

## Known TODOs — Deferred Features

These are pre-existing unfinished items, not regressions. Address AFTER the `syndicate_core/` refactor is complete.

| # | Item | Source | Status |
|---|------|--------|--------|
| 1 | **CVI/Main filename naming scheme** — output files should be named `CVI_<game>_<formula>_<draw>.csv` and `Main_<cluster>_<game>_D<draw>.csv`. Requires touching `parse_cvi_filename`, collation save, and dashboard outputs. | §7u.A | Not implemented |
| 2 | **Dashboard redesign** — collapse Selected/Unselected/breakdown panels behind expanders; add a per-row U/S dropdown sized to the SC length instead of the current static layout. | §7u.B | Not implemented |
| 3 | **So-engine filter** — additional filter pass on the SplitsCombi (So) engine, noted as a separate known issue. No code exists for this yet. | §5, §7u | Not implemented |
| 4 | **`use_container_width` → `width='stretch'`** — Streamlit deprecated `use_container_width` (removal after 2025-12-31). Low-priority cleanup; ~10 occurrences throughout masterapp.py. | §7y | Deferred |
