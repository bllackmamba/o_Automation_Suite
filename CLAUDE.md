# CLAUDE.md — o_Automation_Suite

## Canonical file

```
/Users/mamba/Desktop/Sika/o_Automation_Suite/masterapp.py
```

Do not search for, read, or edit `Sika.py`, copies elsewhere, or any backup file. All fixes go in masterapp.py or syndicate_core/.

---

## File structure (post-refactor)

```
o_Automation_Suite/
├── masterapp.py                     ← UI only (~5600 lines, Streamlit)
├── syndicate_core/
│   ├── __init__.py
│   ├── config.py                    ← GAMES_CFG, CF_ROWS, COMP_MAP, DASHBOARDS, CHUNK_SIZE
│   ├── scraping.py                  ← thelott + lottolyzer fetchers
│   ├── pipeline.py                  ← split_d_by_game, build pipeline helpers
│   ├── matching.py                  ← pandas + DuckDB intersection engine
│   ├── generators.py                ← _auto_wire_generators, Ep/Sp/So slicing
│   ├── collation.py                 ← _to_w_rows (universal transformer)
│   └── check_config.py              ← config self-test (python3 -m syndicate_core.check_config)
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   └── test_pipeline.py             ← 26 tests, all passing
├── .streamlit/config.toml           ← maxUploadSize=10000
├── Main_Data/                       ← raw scraper output
├── Variables/Variable_Elements/
│   ├── Base/f_rules_Gclaude.xlsx    ← B variable (DO NOT auto-modify)
│   ├── Direct/                      ← D variable CSVs
│   ├── Splits/                      ← Sp output
│   ├── Splits_Combi/                ← So output
│   ├── Rainbow/                     ← R output
│   └── ExcelPro/                    ← Ep output
└── Games/
    └── {GAME}/
        ├── Main_Data/
        ├── Outputs/
        ├── SinceLast/since_last.json
        └── Variables/Variable_Elements/
```

Run commands:
```bash
streamlit run ~/Desktop/Sika/o_Automation_Suite/masterapp.py
pytest tests/                                      # 26 tests
python3 -m syndicate_core.check_config             # config self-test
```

---

## Game keys

| Key | Game | Pool | Pick | Draw |
|-----|------|------|------|------|
| `pb`  | Powerball | 1–35 (+PB 1–20) | 7+1 | Thursday |
| `oz`  | Oz Lotto | 1–47 | 7 | Tuesday |
| `sat` | Saturday Lotto | 1–45 | 6 | Saturday |
| `sfl` | Set for Life | 1–44 | 7 | Daily |
| `mwf` | Mon/Wed/Fri | 1–45 | 6 | Mon/Wed/Fri |

**Brand name → key mapping (critical — API returns brand names):**
- `TattsLotto`, `Saturday Lotto`, `Gold Lotto`, `X Lotto`, `Lotto` → `sat`
- `Monday & Wednesday Lotto`, `Monday Lotto`, `Wednesday Lotto`, `Friday Lotto` → `mwf`
- `Powerball` → `pb` | `Oz Lotto` → `oz` | `Set for Life` → `sfl`
- `Super 66`, `Lucky Lotteries` → **skip** (not pipeline games)

---

## Variable engines

| Engine | Module | Input | Output |
|--------|--------|-------|--------|
| Ep (ExcelPro) | `excelpro.py` | Top 8 w-cols of D + B objects | `wt_ab..wt_cd` new w-sets |
| Sp (Splits) | `task1b.py` | Top 4 w-cols of D + 4 split points | split sets `a0,a1..d0,d1` |
| So (SplitsCombi) | `automation_vba.py` | Top 4 w-cols of D | union combinations |
| R (Rainbow) | `task2.py` | Since Last (lottolyzer) + `to_keep` | powerset combos filtered by Since Last |

**D** = Direct variable (scraped syndicates from thelott.com) — NOT Main Data. They INTERSECT in the matching engine; never join them.

---

## Container Formula — 17 rows + custom combos

```
1  BRD        6  BD         11 D1D2D3     16 RVI2
2  BSD        7  BSSoD      12 S1S2S3     17 Xnn
3  BSoD       8  BRDSSo     13 So1So2So3
4  SD         9  B1B2B3     14 Xn
5  SoD       10  R1R2R3     15 RVI1
```

- Rows 1–10, 12–17: use Ep, Sp, So, B, D
- Row 11: uses R (Rainbow/Since Last) + D
- **Custom combinations**: in addition to the 17 shortcuts, the Container Formula UI accepts user-typed combinations (e.g. `EpSpSo`) — the system tokenises the string using known variable names and routes to `execute_collation`.

---

## _to_w_rows — three-path routing (`syndicate_core/collation.py`)

Takes any variable DataFrame, returns a tall row-oriented DataFrame: `[Set_Label, w1, w2, …]`.

| Path | Trigger | Behaviour |
|------|---------|-----------|
| **B-style** | has `w` column + `pos_N` columns, `is_direct=False` | Row-oriented; `w` col → `Set_Label`, `pos_N` cols → data. No transpose. |
| **D-style** | `is_direct=True` OR has D metadata columns | Row-oriented; `Syndicate_ID` → `Set_Label`, w-columns → data. No transpose. |
| **Column-oriented** | R/Ep/So; or `force_column_oriented=True` (always used for Sp) | Transpose: each column becomes a row; original column name preserved as `Set_Label`. |

`execute_collation(components)` stacks blocks vertically and adds:
- Column 0: `Row_ID` (1-based integer)
- Column 1: `Source` (variable name string, e.g. `"B"`, `"D"`, `"Sp"`)
- Column 2: `Set_Label`
- Columns 3+: `w1, w2, …` (aligned to widest row)

---

## Active Draw — lock/unlock behaviour

Setting an **Active Draw** (CVI Matrix → Direct tab → Set Active Draw button):
1. Filters `D` in session state to that draw only.
2. **Invalidates** all stale `Sp`, `So`, `Ep` DataFrames in session state (set to empty).
3. **Clears** persisted split-point widget keys (`sp_split_*`, `so_split_*`).
4. Calls `_auto_wire_generators` to recompute from the filtered D.
5. **BUILD W-MATRIX** button respects Active Draw — always reads `gs("D")` first; falls back to raw CSV only if D is empty (first-time bootstrap).

Clearing Active Draw re-loads the full D and triggers the same invalidation cycle.

---

## Session state key convention

Game-specific data uses three helpers (top of SESSION STATE section, ~line 386):

```python
def gkey(name: str) -> str:
    return f"{name}__{active_game()}"   # double underscore

def gs(name: str, default=None):
    return st.session_state.get(gkey(name), default)

def gs_set(name: str, value):
    st.session_state[gkey(name)] = value
```

Key format: `"{name}__{game}"` e.g. `"B__sat"`, `"D__pb"`.

**Special cases:**
- `_auto_wire_generators(gdirs, gk)` — uses `gk` (not `active_game()`) → write `st.session_state[f"X__{gk}"]` directly.
- Game-selector button — uses `_gk` (clicked game) → direct `st.session_state[f"B__{_gk}"]`.
- `_d_full_key` / `_d_draw_key` — local vars set from `gkey(...)` then used with `st.session_state[...]`.

Unscoped keys live in `S` (= `st.session_state["S"]`): `cf_active`, `auto`, `scrape_log`, `confirmed_api_url`, `cookie_str`, `container_status`, `cvi_upload_v`, `md_upload_v`, `sc_upload_v`, `main_data_auto_loaded_game`, `carry_fwd_{db}`, `sc_avail_{db}`.

---

## Lottolyzer URLs (verified 2026-06-11)

| Game | URL |
|------|-----|
| `pb`  | `https://en.lottolyzer.com/number-frequencies/australia/powerball` |
| `oz`  | `https://en.lottolyzer.com/number-frequencies/australia/oz-lotto` |
| `sat` | `https://en.lottolyzer.com/number-frequencies/australia/tattslotto` |
| `sfl` | `https://en.lottolyzer.com/number-frequencies/australia/set-for-life` |
| `mwf` | `https://en.lottolyzer.com/number-frequencies/australia/weekday-windfall` |

History URL: auto-derived via `.replace("/number-frequencies/", "/history/")`.

**Never use:** `saturday-lotto` (DNE), `tatts-lotto` (serves SFL data).

---

## B variable

- `Variables/Variable_Elements/Base/f_rules_Gclaude.xlsx`
- Sheets: `w values Pb A (2)` (pb), `Ta (2)` (sat+mwf), `oz (2)` (oz), `sfl` (sfl)
- Row 0 = w-column headers, rows 1+ = number data
- Uploaded ONCE — **never auto-overwrite**

---

## Scraper — confirmed API

```
Step 1: GET https://api.thelott.com/outlet/outlets?state={STATE}&postcode_or_locality={POSTCODE}
Step 2: GET https://api.thelott.com/syndicates/api/search?company={INT}&outlets=ID1,ID2,ID3&limit=100
Company IDs: NSW/ACT=3, VIC/TAS=1, QLD=2, SA=6
CRITICAL: outlets = COMMA-SEPARATED (not repeated params)
SSL bypass required: ctx.verify_mode = ssl.CERT_NONE (intentional — do not remove)
```

Run sweeps from terminal (not Streamlit — SSL restrictions):
```bash
cd ~/Desktop/Sika/o_Automation_Suite
python3 thelott_syndicate_scraper.py sweep ALL
```

---

## Performance — pandas vs DuckDB

| Tool | When |
|------|------|
| pandas | All variable engine work, B/D/Ep/Sp/So/R, CVI w-matrix, pb/sat/mwf matching |
| DuckDB | Final matching for oz (63M rows) and sfl (44M rows) only — never load these fully into pandas |

CHUNK_SIZE = 500_000. Run ONE game at a time. Test with 100K rows first.

---

## Coding rules

1. `masterapp.py` = **UI only** after refactor. Logic lives in `syndicate_core/`. Do not collapse modules back into masterapp.
2. Preserve all `# ═══...` section separators and comment style.
3. Never modify `f_rules_Gclaude.xlsx` programmatically unless explicitly asked.
4. Game keys always lowercase: `pb`, `oz`, `sat`, `sfl`, `mwf`.
5. **D ≠ Main Data** — they INTERSECT; never join.
6. SSL bypass is intentional — do not remove.
7. Always use `GAMES_CFG` dict — do not hardcode game values.
8. Prefer `pathlib.Path` over `os.path`.
9. **Git commit after every working change.**

---

## Changelog

> Scan before making changes. Do not redo or revert completed work.

| Date | Change |
|------|--------|
| 2026-06 | **Scraping headers** — added `_TLOTT_HEADERS` with Accept, gzip, User-Agent to lottolyzer requests |
| 2026-06 | **gzip decompression** — `gzip.decompress()` fallback when urllib does not auto-decompress |
| 2026-06 | **Retry logic** — `_picks_fetch_retry()` retries on 403 with throttle/cooldown |
| 2026-06 | **Games column splitting** — multi-game rows split into one row per game |
| 2026-06 | **Postcode/State retention** — carried through from API fetch into every split/pick row |
| 2026-06 | **Dedup on Syndicate_ID** — `_merge_b()` deduplicates on Syndicate_ID |
| 2026-06 | **Logging instead of silent except** — bare `except: pass` replaced with scrape_log |
| 2026-06-11 | **sat lottolyzer URL** — `saturday-lotto` → `tattslotto`; stale cache cleared |
| 2026-06-11 | **mwf lottolyzer URL** — `tatts-lotto` → `weekday-windfall`; stale SFL-contaminated cache cleared |
| 2026-06-11 | **Game-scoped session state (phase 1)** — 11 keys renamed with `_{gkey}` suffix |
| 2026-06-12 | **Game-scoped session state (phase 2)** — `gkey()`/`gs()`/`gs_set()` helpers; game data moved to top-level `st.session_state` with `__{game}` separator |
| 2026-06-14 | **syndicate_core/ refactor** — extracted config, scraping, pipeline, matching, generators, collation, check_config into `syndicate_core/` package; masterapp.py now UI-only |
| 2026-06-14 | **tests/** — 26 tests, all passing (`pytest tests/`) |
| 2026-06-14 | **_to_w_rows in collation.py** — three-path routing: B row-style, D row-style, R/Ep/So/Sp column-oriented (Sp always uses `force_column_oriented=True`) |
| 2026-06-14 | **execute_collation output** — `Row_ID / Source / Set_Label / w1…wN` column format |
| 2026-06-14 | **Active Draw invalidation** — lock/unlock now clears Sp/So/Ep and recomputes from filtered D |
| 2026-06-14 | **BUILD W-MATRIX respects Active Draw** — reads `gs("D")` first; raw CSV fallback only on first boot |
| 2026-06-14 | **Container Formula custom combos** — accepts user-typed combinations (e.g. `EpSpSo`) in addition to the 17 predefined shortcuts |

---

## Known TODOs — Deferred

| # | Item | Status |
|---|------|--------|
| 1 | **CVI/Main filename naming scheme** — `CVI_<game>_<formula>_<draw>.csv` + `Main_<cluster>_<game>_D<draw>.csv` | Not implemented |
| 2 | **Dashboard redesign** — expanders for Selected/Unselected; per-row U/S dropdown | Not implemented |
| 3 | **So-engine filter** — additional filter pass on SplitsCombi engine | Not implemented |
| 4 | **`use_container_width` → `width='stretch'`** — Streamlit deprecated `use_container_width` | Deferred |
| 5 | **Add New Draw → B ordering bug** — new draws appended as "first" instead of "last"; `append_draw_to_b` needs ordering fix; B/draw history table scrolling also broken | Not implemented |
| 6 | **Manual-mode stage-by-stage matching (SC Available: NO)** — researcher sees `count_dist` for stage i BEFORE entering SC for stage i; engine pauses, then completes stage i's split and shows stage i+1's distribution. **Decided approach: Option A (decide-as-you-go).** **REFACTOR-FIRST rule:** do NOT duplicate `run_matching`'s stage-loop body into a new function (first attempt produced 200+ lines of drifting logic). Instead: (1) extract the stage-loop body into a shared helper (e.g. `_run_one_stage`, optionally split into count-dist sub-step and apply-SC sub-step), (2) verify `run_matching` output is byte-identical via the 26 existing tests, (3) build the resumable step function on top of that helper. Design discussion only — no code changes made. | Not implemented |
