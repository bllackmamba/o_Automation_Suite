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

## Java accdb bridge

`core/lib_accdb/` holds the Java bridge used to read/write MS Access `.accdb`
files (`BuildAccdb`/`ReadAccdb`). It depends on **Jackcess 4.0.5** plus its
Apache Commons runtime deps:

- `jackcess-4.0.5.jar` — https://jackcess.sourceforge.io/ (Maven: `com.healthmarketscience.jackcess:jackcess:4.0.5`)
- `commons-lang3-3.12.0.jar` — `org.apache.commons:commons-lang3:3.12.0`
- `commons-logging-1.2.jar` — `commons-logging:commons-logging:1.2`

These JARs and the compiled `*.class` files are **git-ignored** (vendored
binaries, not source). To restore: download the three JARs from Maven Central
into `core/lib_accdb/`, then `javac -cp "core/lib_accdb/*" core/lib_accdb/*.java`.

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
| 2026-07-02 | **CVI language + orientation guard** (`matching.py`, commit `53a5400`) — renamed `_parse_cvi_col`→`_parse_cvi_row` (definition, 2 call sites, `__all__`, docstring); a CVI w-position is a stored pandas column but conceptually a "w-row" (all numbers at that position across every combination). Fixed "w-column"/"CVI column" language in 4 docstrings/comments (`w_cols` variable left unchanged). Added `_assert_cvi_orientation(cvi_df, caller)` — raises `ValueError` on a transposed CVI (guard: `n_wcols > n_rows and n_rows <= 50 and n_wcols >= 20`; the `>= 20` floor avoids false positives on legitimately small CVIs like 3 combos × w1–w4). Called first thing in `_prepare_matching_state`, `run_matching`, and `run_matching_step` (setup call only). 93/93 tests pass. |
| 2026-07-05 | **Per-row CVI match** (`matching.py` + `masterapp.py` + `scripts/`) — `_match_cvi_rows`/`_match_cvi_row_counts` engine: every CVI row matched independently against the full main-data set (no staging/carry-forward), orientation-guarded, carries Row_ID/Source/Set_Label; 8 unit tests vs hypergeometric closed form. Container Dashboards "🎯 Per-Row CVI Match" button: live compute ≤ 2000 rows (spinner + download), else shows the detached `nohup … & disown` command and offers the precomputed CSV. `scripts/per_row_cvi_match.py <game> <formula>` CLI builds `main_arr` without `np.clip` (out-of-range → 0, excluded, not fabricated). Validated vs baseline; full suite 101 passed. |
| 2026-07-06 | **CONSOLIDATED_UI_SPEC close-out** (`masterapp.py`, merge `546f5bd`) — Container Dashboards results/SC/direction pass. Removed the Row-by-Row Summary table (+ CSV/Excel downloads), the Inspect-a-Row panel, and the Final Stage Output tabs — all superseded by the Matching Table's per-row popovers. **Dir** column is now a popover toggle (shows U/S carry-forward pools and rewrites `S[carry_fwd_{db}][w]` for the next run), not plain text. SC panel: per-column SC grid collapsed behind one chevron (the two permanent copies printed identical `sc_auto` data — merged); Upload/Replace SC section un-collapsed to stay permanently visible beside the Method buttons. Removed the "Apply to all" button + per-row Direction override table (`cf_tbl_{db}`); kept only the "Default direction" dropdown — `carry_fwd = {w: S[cf_key].get(w, _gd)}` (Auto default + Dir-chevron overrides). Fixed SC preview mislabel `N w-columns → N rows`. Excel-export crash on "Breakdown (all stages)" (openpyxl 1,048,577-row overflow) resolved by deletion — every `to_styled_excel` call site lived in the removed panels, so `to_styled_excel` + `show_filtered_highlighted` deleted as dead code. Terminology: carry-forward caption now says `w_rows`, not `w-columns`. net −488/+62 lines; full suite 121 passed. **Part D (Active checkbox) — investigate-only:** `S["cf_active"]` (Container Formula page, `masterapp.py:4655–4673`) only gates the quick-pick formula buttons via `active_names` (line 4673); it does NOT gate collation/run/eligibility — effectively cosmetic. Write-back at 4669–4670 is correct so edits should persist statically; no fix applied pending a design decision (candidate: gate "collate this formula" for the future multi-select-and-collate feature). |

---

## Known TODOs — Deferred

| # | Item | Status |
|---|------|--------|
| 1 | **CVI/Main filename naming scheme** — `CVI_<game>_<formula>_<draw>.csv` + `Main_<cluster>_<game>_D<draw>.csv` | Not implemented |
| 2 | **Dashboard redesign** — expanders for Selected/Unselected; per-row U/S dropdown | Not implemented |
| 3 | **So-engine filter** — additional filter pass on SplitsCombi engine | Not implemented |
| 4 | **`use_container_width` → `width='stretch'`** — Streamlit deprecated `use_container_width` | Deferred |
| 5 | **Add New Draw → B ordering bug** — new draws appended as "first" instead of "last"; `append_draw_to_b` needs ordering fix; B/draw history table scrolling also broken | Not implemented |
| 6 | **Manual-mode stage-by-stage matching (SC Available: NO)** — researcher sees `count_dist` for stage i BEFORE entering SC for stage i; engine pauses, then completes stage i's split and shows stage i+1's distribution. **Decided approach: Option A (decide-as-you-go).** | **DONE (all phases)** |
| 7 | **`_match_cvi_rows` Step 4 ground-truth check** — engine added to `matching.py` (per-row CVI match: every CVI row vs the full 8.1M sat main-data set, own numbers, own distribution) + 6 unit tests validated against the hypergeometric closed form. Baseline `CVI_per_row_match_sat_FULL.csv` (23,674 rows) regenerated via a **detached** (`nohup … & disown`) checkpointing run after a prior session-tied run was lost. Step 4 done: first 50 engine rows match the baseline exactly (Row_Length, Main_Count, Main_Breakdown). NB main data uses combo `1,2,3,4,5,6` as its header, so M = C(45,6) − 1 = 8,145,059 (that single combo is excluded from matching). | **DONE** — engine validated vs baseline; Container Dashboard UI + `scripts/per_row_cvi_match.py` CLI added |
| 2026-07-07 | **Sat D-data misclassification** — 49 Super 66 / Lucky Lotteries syndicate rows (identified by Syndicate_Name — e.g. "SARINA LIVING DREAM", "SUPER 66") are mislabeled Games="Saturday Lotto" in D_ALL_sat.csv and all per-state sat D files. Root cause: scraping.py:_resolve_game() (line 318) force-infers "sat" for any unmapped company/product whose draw number falls in the 4400–4900 band — Super 66/Lucky Lotteries share that draw-number band with Saturday Lotto, so the heuristic can't distinguish them. The digit values themselves (0–9, e.g. Super 66 picks) are extracted correctly; only the game label is wrong. The per-row backstop at line 367 checks max<pool and min<1 but not distinctness or exact pick-size, so these rows pass through undetected. Confirmed present in raw pre-split scrape (not introduced by split_d_by_game or collation — both exonerated). 4 of these 49 rows were what looked like "corrupted" values in CVI_BRDEpSoSp during SC file verification (Row_IDs 22912, 22976, 22986, 23013) — they're not corrupted, they're valid Super 66 picks wearing a wrong game label. Three-way decision pending: (a) fix _resolve_game to disambiguate via company/product/name (GAME_NAME_MAP already marks Super 66/Lucky Lotteries as skip=None, resolve_game just never checks it) and/or add a real shape-validation backstop (distinct count == pick size, range 1..pool_max); (b) re-scrape sat cleanly; (c) purge the 49 already-mislabeled rows from existing sat D files. **Not yet decided — do not fix without a decision.** | **PENDING DECISION** — investigated only, root cause confirmed |
| 2026-07-07 | **increase.py Mongo URI is a placeholder on this machine — LOCATE/RESTORE the real Atlas string** — the `increase` DB (collections nlist/klist/ungrouped) holds the real output of `core/increase.py` runs, and Tai HAS run real increase.py jobs against a live Atlas cluster before, so a valid connection string DOES exist somewhere (Tai's own env / prior machine / password manager / Atlas account). It is simply **not populated in this repo's `.env`**, which currently ships only a placeholder: `mongodb+srv://<user:pass>@cluster0.xxxxx.mongodb.net/dbname` (literal `xxxxx` host + `dbname`). A read-only probe (2026-07-07) failed at **DNS resolution before any auth** — i.e. no real endpoint to reach, NOT an auth/credential rejection and NOT "DB empty". **Next step is to locate/restore the real URI** (export `MONGODB_URI` or fill `.env`), then re-run the read-only probe — do NOT read this as "credential missing/invalid" (which would imply rotating a key) or as "no 1n+2/1n+3 data found" (unverifiable from here — the query never reached the DB). Direct consequence: the open question of whether Tai's 1n+2/1n+3 (diff=2/3) runs live in Mongo remains **unverifiable until the real URI is restored** — including the width-4→width-6 diff=2 anchor check against `core/all regene/regeneratem/increase.csv`. | **BLOCKED — needs real Atlas URI restored** |

**Phase 1 — DONE (783deef + baf8add, 53/53):** `_compute_stage_present` and `_apply_stage_sc` extracted from `run_matching`'s loop body. `run_matching` output byte-identical (verified by `.equals()` on selected/unselected/fig9_table/breakdown across the full test suite).

**Phase 2a — DONE (4f8c154, 53/53):** `_prepare_matching_state(main_df, cvi_df, main_path) -> dict | None` and `_fill_exhausted_stages(w_cols, start_idx, M, carry_fwd, main_count_map, main_bd_map, sc_dict=None, *, n_cols=None) -> tuple[list, list]` extracted from `run_matching`. `run_matching` now delegates to both; all pre-loop setup and the exhaustion fill block live in the helpers. 53/53 byte-identical.

**Phase 2b — DONE (4f8c154, 67/67):** `run_matching_step(resume_state, sc_for_stage=None, *, main_df, cvi_df, carry_fwd, main_path) -> dict` implemented in `syndicate_core/matching.py`. Setup call (`resume_state=None`) runs `_prepare_matching_state`, then PHASE A — auto-advances through empty-CVI stages and pauses at the first real stage returning `{"paused": True, "awaiting_sc_for_stage": idx, "w": w, "count_dist": {"S0": n, "S1": n, ...}, "resume_state": {...}}`. Resume call restores frozen state, applies `sc_for_stage` via `_apply_stage_sc`, then re-enters PHASE A or fills exhausted stages and returns `{"paused": False, "selected", "unselected", "fig9_table", "breakdown", "debug_rows", "n_cols", "small_enough"}`. `tests/test_matching_step.py` added: `test_full_run_matches_run_matching` drives 3 pause/resume cycles and asserts `.equals()` on selected/unselected/fig9_table/breakdown against `run_matching` on the same inputs. 67/67 passing.

**Phase 3 — DONE (d7c71e6, 68/68):** Container Dashboards UI wired. SC=NO branch: START MATCHING → `run_matching_step(None, main_df, cvi_df, carry_fwd, main_path)`; on pause stores `step_state_{db}` / `step_pending_{db}` in S; pause screen shows `count_dist` table + `st.multiselect` keyed by `step_sc_choice_{db}_{stage_idx}`; Continue → `run_matching_step(resume_state, sc_for_stage=_sc_chosen)`; on `paused=False` stores result under `gkey("results")[db]` — same path as YES mode so existing rendering block is reused unchanged. Cancel clears step state. Toggle YES↔NO clears step keys. SC=YES branch: original `run_matching` button unchanged. `TestStepSupersetKeys` added — verifies step final result keys ⊇ `run_matching` keys. 68/68 passing.
