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
| 2026-07-12 | **Stacked Draws — cascading (lineage) view + render fix** (`masterapp.py`, commits `3142026`, `1c5b3dd`) — new `sd_view_mode` radio in the R tab → 📊 Stacked Draws inner tab adds a **"Cascading (lineage)"** view alongside the untouched **"Flat rank"** view (and the separately-built "Blocked flat (all_wt)" view, commits `72e4553`/`8471efc`). Algorithm `_sd_cascading_order(history, pool)` (local to the tab, never leaks into `syndicate_core/`): seeds the deck from the OLDEST draw via the existing `_sd_present_order`, then walks forward chronologically — each draw's **fresh** winners (not in the previous draw) jump to the top ascending, **repeats** hold their exact prior row, everyone else shifts down by `len(fresh)`; `new_deck = sorted(fresh) + [x for x in deck if x not in fresh]`. Computed ONCE over the FULL `draw_history.csv` (all 150 rows, not the flat view's `head(_sd_n+_sd_pool)` window), then sliced to the slider's N. Verified in isolation against a hand-traced example (number 15 sinks exactly `len(fresh)` rows across D4689→D4691) and byte-exact permutation integrity across all 150 decks. Render: winner-cell-only (each column blanks every non-winner; colours just that draw's own winners via `_num_colour`; no SL sub-label since a visible cell ⇒ SL=0). **Render fix (`1c5b3dd`):** the cascading columns clustered every winner into rows 1-6 because each column was drawn against that draw's OWN post-update deck (winners just re-topped). Fixed by drawing each column against the deck it INHERITED from the previous/older draw (`_ord = _sd_casc[_di+1][2]`, oldest falls back to own) — winners now show at the depth they sank to since their last win (diagnostic over 150 draws: deepest winner deck-row 15→45, winners from rows>12 0.6%→74.8%), matching the reference sparse-block / diagonal-drift pattern. Rendering-only; `_sd_cascading_order`/`_sd_present_order` unchanged; Flat rank and Blocked flat unaffected. Isolated to the Stacked Draws tab (no writes to session state, `since_last.json`, or R/D/Ep/So/Sp/SC files). |
| 2026-07-21 | **variable_inputs subfolder suffix fix — all 5 games** (`syndicate_core/pipeline.py` `game_dirs()`) — the five per-category subfolders (`Base`, `Splits`, `Splits_Combi`, `Rainbow`, `ExcelPro`) were hardcoded WITHOUT the game-key suffix while their parent `variable_inputs_{gk}` was suffixed, so every `game_dirs()` call's `mkdir` loop recreated no-suffix folders (contradicting the docstring's "all subfolders suffixed with `_{game_key}`"). Fixed to `var_inputs / f"{Cat}_{gk}"` (5 lines) — one shared function, not five separate bugs; all 86 call sites use dict keys so they redirect automatically. Migrated every game's live data from the no-suffix folders into the suffixed twins (sat/oz/sfl/pb had partial manual twins; **mwf `Base_mwf` etc. were first-time creations**), archived the emptied no-suffix folders to `_deprecated_nosuffix_20260721/` per game (`Scraper` left unsuffixed — unpaired). **oz/pb B-workbook rename:** `B_oz.xlsx`→`Base_oz.xlsx`, `B_pb.xlsx`→`Base_pb.xlsx` to match the config `b_file` convention (`Base_{gk}.xlsx`) the other 3 games already follow; all 5 games' `b_file` now resolve. **B→B1/B2 split (sat):** `B_sat_updated.csv` verified as a lossless split into `B1_sat_updated.csv` (967 draw-history rows) + `B2_sat.csv` (42 syndicate rows) — reconciled by value (42/42 syndicate + 967/967 draw positions identical, 42+967=1009=B's data rows, no dups); original archived to `Base_sat/_archive/`, B1+B2 now the live inputs. Verified via real `game_dirs()` for all 5 games; 195/195 tests pass. Data files gitignored — folder moves/renames are filesystem-only. |
| 2026-07-21 | **B1 Parallel Main-Count (Step 5)** (`syndicate_core/pipeline.py` + `masterapp.py` + `tests/test_b1_parallel.py`) — a second, toggleable per-row breakdown in Container Dashboards that matches every CVI row against the **whole B1 source** (unfiltered — B1's `update` draw-number column is populated for only a handful of rows, so it can't be draw-scoped) using the **same** `_match_cvi_rows` engine as "🎯 Per-Row CVI Match", not the staged `run_matching` path. Renders directly below the Per-Row block, behind `st.expander("🅱️ B1 Parallel Main-Count", expanded=False)` + a compute button (nothing loads/computes until opened and clicked). Engine reused unchanged; its `Main_Count`/`Main_Breakdown` columns renamed to `B1_Count`/`B1_Breakdown` in the UI. Two new pure helpers in `pipeline.py` (kept out of UI so they're testable): `b1_path(game_key)` resolves via `game_dirs(gk)["Base"] / f"B1_{gk}_updated.csv"` (glob fallback `B1_{gk}*.csv`, `None` when absent) — game-agnostic, never a hardcoded sat path; `b1_ball_columns(df, pick)` detects ball columns by pattern+position (`pos_N` **or** `wN`/`w_N`, excluding the `w` label + `update` meta, numeric-only, capped at `pick`) so a future `pos_`→`w_row` rename of B-derived data can't break the reader. Only **sat** has a B1 today; other games show a graceful "no B1 source" info. **Verified live via Streamlit `AppTest`** (real sat data): booted → Container Dashboards → BRD CVI (23,357 rows) → clicked compute → matched all 23,357 rows against the 967-row B1 with **zero exceptions**, +1 result table and +1 download button rendered in situ. `tests/test_b1_parallel.py` adds 10 unit tests (path resolution incl. game-isolation, rename-proof detection under both `pos_N` and `wN` headers, `update` never mistaken for a ball, engine reuse vs hypergeometric closed form). Full suite **205 passed** (was 195). |
| 2026-08-05 | **Container Formula Registry — 4-group RefGroup-split restructure (steps 1–6)** (`syndicate_core/refgroup.py` + `main_split.py` + `escalation.py` + `config.py` + `collation.py` + `masterapp.py`; `docs/FORMULA_REGISTRY_PLAN.md`) — regroups the candidate-variable axis into **4 formula groups** (G1 `R` / G2 `D` / G3 `B1` / G4 `Ep+So+Sp+B2`), each matched against a Main Data pool **split into Repeat/No_Repeat** streams per RefGroup. Investigation + written plan first (`docs/FORMULA_REGISTRY_PLAN.md`), then TDD build, one commit per green step. **Split = Rule 1 (LOCKED doc), nonzero/zero — NOT Rule 2.** `refgroup.main_data_stream(shared)` defines the Rule 1 boundary once (`Repeat = shared>0`, `No_Repeat = shared==0`; sat = 4,882,437 / 3,262,623) beside the Rule 2 `{1..pick-3}` helpers, so the two never drift (they diverge on `{pick-2,pick-1,pick}` — locked by a test). `syndicate_core/main_split.py`: `split_streams` (vectorized `np.isin`, read-only) + `ref_key_of` + `load_or_build_split` — a **RefGroup-keyed parquet cache** (`main_data_{gk}/_split_cache/{Repeat|No_Repeat}__{ref_key}.parquet` + `_split_marker.json`) that **rebuilds only on rollover** to a new reference draw (stale parquets dropped; corrupt marker/unreadable parquet → safe rebuild) — net-new, since no persisted RefGroup marker existed before. `syndicate_core/escalation.py`: `EscalationContext` (frozen) + `ESCALATIONS` registry of **three pass-through stubs** — `spread3_borderline` (G1; LATER: `Constituent_Groups` spread, Rule 3), `rule9_boundary_aggressive` (G2/G4; **Rule 9 does not exist — nothing to reuse**), `shallow_anchor_exclude_hold` (G3; LATER: `stacked_blocks.block_layout`/`since_last_map` rolling own-era shallow list, Rule 4). Each logs "not yet tuned" and returns candidates untouched. `config.FormulaGroup` frozen dataclass + `FORMULA_GROUPS` (escalation referenced by **string name**, resolved via `ESCALATIONS`, so config imports no callables and the runner stays formula-agnostic); `target_range (10,20)` per-group. `collation._run_formula_groups(groups, collate_fn, split, n_cols, ctx, *, narrow_fn, escalations)`: registry-driven, skip-and-log runner mirroring `_run_sc_auto`. `collate_fn` is **injected** (`execute_collation` lives in the UI layer, not importable in `syndicate_core`); the split `_meta` key is ignored. Control flow: `narrow_fn` → if survivors **> hi** escalate (may land back in range, else flag `out_of_range_after_escalation`, **let through unblocked**); **< lo** → `below_target`, escalation never fires; one group's/stream's failure never blocks others. **`default_narrow` = pass-through seam** (decided 2026-08-05): the real survivor rule is an **OPEN question in the LOCKED rules** (Rule 2 w2+ undefined; Rule 6 boundary undecided), so narrowing is injected like the escalations — control flow is real and tested, the rule drops in later without signature churn. `masterapp.py`: lazy "🧩 Formula Groups (4-group · RefGroup split)" expander in Container Dashboards (after Per-Row CVI Match) — builds/loads the split, runs the 4 groups (`execute_collation` as `collate_fn`), renders a per-group×per-stream status table + CSV. **Verified end-to-end via Streamlit `AppTest`** (real sat data): navigated to Container Dashboards → clicked "Run 4 formula groups" → page auto-loaded the full 8,145,060-row pool → split **rebuilt Repeat 4,882,437 / No_Repeat 3,262,623**, all 4 groups ran, results table rendered, **zero exceptions**. Tests: `test_refgroup.py` +10 (`main_data_stream`), `test_main_split.py` 12 (incl. a real-data lock hitting the invariant counts on the actual 8.1M pool; `core/Main_Data_sat_plus.numbers` is NOT the pool — it's the 575,344-row diff=1 NList file in Apple Numbers format), `test_escalation.py` 10, `test_formula_groups.py` 20 (registry + runner). Full suite **258 passed** (was 205). **Escalation tuning + the default-narrow survivor rule remain deferred** — interfaces exist and pass through until designed. |
| 2026-08-05 | **Formula groups — per-group split/no-split toggle (plumbing)** (`config.py` + `collation.py` + `masterapp.py` + `tests/test_formula_groups.py`) — G1 (R) narrows against Main Data via the reference draw, never touching the Repeat/No_Repeat pool, so running it once-per-stream just computed the same result twice. Added `FormulaGroup.uses_main_data_split: bool = True` (G2/G3/G4 default True; **G1 default False**) as a per-group DEFAULT, plus a per-run override `_run_formula_groups(..., split_override={key: bool})` — `{"G1": True}` runs R against the split for research/tracing with **no config edit**; symmetric (can also force a split group off). Result shape stays uniform: split → `streams={"Repeat","No_Repeat"}`; no-split → single `streams={"no_split"}` (narrowed once with `stream_df=None`), plus a group-level `"mode": "split"|"no_split"`. `target_range`/escalation logic unchanged and applies in both modes; the step-6 table renders either shape unchanged (generic `streams.items()`). masterapp: a "🔬 Also run R (G1) against the split" checkbox in the Formula Groups expander feeds `split_override` per run. **Pure plumbing — `default_narrow` stays the pass-through stub; the R 6,885→18 convergence still does NOT exist as code (separate future task), confirmed by an exhaustive search — it lives only in `R_with_rules_applied_*.xlsx`.** Documented (no runtime guard) that a future no-split group whose narrow consumes Main Data would get `stream_df=None`. `test_formula_groups.py` +7 (defaults, single-entry+mode, None stream_df, override on/off both directions, override isolation, target_range in no-split). Verified end-to-end via `AppTest`: default → G1 `['no_split']`; checkbox on → G1 `['Repeat','No_Repeat']`; zero exceptions. Full suite **264 passed** (was 258). |
| 2026-08-05 | **Formula groups — G1 default correction + FIRST REAL narrowing (RefGroup_w1 pivot)** (`config.py` + `collation.py` + `masterapp.py` + `tests/test_formula_groups.py`) — **Correction:** the previous row got G1 backwards. G1's one-time Repeat/No_Repeat *classification* doesn't need Main Data, but R's *convergence* structurally REQUIRES the split (it narrows by filtering Main Data itself, R's rows as the filter sequence). Flipped `G1.uses_main_data_split` back to **True** (all four now default split); the generic `split_override` mechanism stays; the "🔬 research toggle" checkbox in masterapp was **removed** (its premise was wrong). **New real logic** (first non-stub narrowing in the system): `collation._refgroup_w1_pivot` — the RefGroup_w1 pivot stage, wired ONLY to G1's Repeat stream. Filters **Main Data ROWS** (not candidates): keeps rows sharing `{1..pick-3}` numbers with `ctx.ref_numbers`, drops the `{pick-2,pick-1,pick}` sliver; on the sat Rule-1 Repeat pool **4,882,437 → 4,871,087** (drops 11,350; `shared==0` can't occur here). Reuses `refgroup.selected_bands_for_pick` + vectorized `np.isin`. **Scope:** stage ONE only — the subsequent per-stage `{1,2,3,4,5}/{0,6}` rule and R's row-ordering/sequencing are BOTH still open, NOT built; No_Repeat + G2/G3/G4 stay pass-through. **Wiring is 100% data-driven, no hardcoded `G1`/`Repeat` branch in the runner** (verified): new `FormulaGroup.narrow: str = "default"` (G1 → `"refgroup_w1"`) + `config.NARROW_ROUTES {("refgroup_w1","Repeat"): "refgroup_w1_pivot"}` + `collation.NARROW_FNS` name→callable registry; the runner resolves `NARROW_FNS.get(NARROW_ROUTES.get((group.narrow, stream)), narrow_fn)`. **Unit safety (per Tai):** the pivot returns Main-Data-row counts, so stream results now carry `"unit": "main_data_rows"|"candidates"` + `"target_range_meaningful": bool` — a millions-scale pivot count is never conflated with a ~15 candidate count, and its structural `out_of_range_after_escalation` flag is labeled an artifact (`target n/a — main_data_rows`), not a real signal, until the per-row chain exists. Results table gained a **Unit** column + flag annotation. `test_formula_groups.py`: real-registry test updated (G1 split; Repeat pivot → 0 on non-matching synthetic rows; units), + synthetic pivot ({1,2,3} kept/{4,5,6} dropped) + **real-data lock (4,871,087 from the actual 8.1M Repeat pool)** + unit-declaration test. AppTest: checkbox gone; G1/Repeat renders `main_data_rows` / 4,871,087 / annotated flag; G1/No_Repeat `candidates`; zero exceptions. Full suite **267 passed** (was 264). |
| 2026-08-11 | **Blocked-flat (all_wt) full-range via B1 splice** (`syndicate_core/full_history.py` + `tests/test_full_history.py` + `scripts/build_full_range_history.py` + `masterapp.py`, commit `55b2a62` + scope follow-up) — The Stacked Draws "Blocked flat (all_wt)" view (and Flat-rank/Cascading) compute SL/lineage from the chronological draw list (`stacked_blocks.since_last_map`), **never** the lottolyzer R snapshot (`since_last.json`) — traced end-to-end: their only feed is `draw_history.csv` (lottolyzer `/history/`, ~150 draws), nothing between the read and `stacked_blocks` touches the R snapshot (the one R ref, `_sd_r_df`, is a red-outline decoration Blocked-flat disables). So feeding B1 is a clean drop-in. `full_history.py` splices **B1** (deep win history, 970 draws, reaches ~2761) with **draw_history** (top draw 4701 + explicit numbering): content-based `best_offset` alignment, **overlap sanity-check** (`overlap_agree` — shared draws must agree on number sets before the join is trusted), B1 rows numbered by extrapolating draw_history's step from a verified anchor, cross-checked vs B1's sparse `update` col. Real sat: **971 draws 2761→4701, 149 overlapping draws ALL AGREE, crosscheck clean**. masterapp Stacked Draws: "History source" radio (Lottolyzer recent | Full range B1 splice; refuses the join on overlap disagreement) + "Window start" slider so the fixed window slides across the whole range (SL still vs full history); offset threaded into all 3 views; dead `_sd_rows` removed. `scripts/build_full_range_history.py` prints the splice report + engine smoke test + writes `sincelast_sat/draw_history_full_sat.csv` (gitignored data). `test_full_history.py` +9 (incl. real-data lock). Full suite **285 passed**; py_compile OK; AppTest boots clean. **SCOPE (2026-08-11):** only the overlap-validated window (~4403→4701) is used for pattern-finding; the deeper B1-only tail (2761→4403) is real number data but its extrapolated draw-number **labels are NOT externally verified** — parked infrastructure, History source **defaults to "Lottolyzer (recent)"** (the validated window), splice opt-in. **Deferred follow-up: externally verify the deep draw-number labels** before using 2761→4403. |
| 2026-08-13 | **Blocked-flat space reclamation — window-global (replaces incremental drop_dead)** (`syndicate_core/stacked_blocks.py` + `scripts/export_blocked_flat_xlsx.py` + both `scripts/_spotcheck_blocked_flat*.py` + `tests/test_stacked_blocks.py` + `masterapp.py`, commit `c8c9e03`; supersedes the incremental `drop_dead` shipped in `7bf7bd6`) — The full-range Blocked-flat export dragged every terminated group's all-hole band into every newer column; a first fix (`7bf7bd6`, `drop_dead=True`) dropped a run as soon as it was dead in the **adjacent-older** column, but that compacted each column **independently** so numbers that had not moved landed at different absolute rows in adjacent columns — **9,306** adjacent-column row-position violations across the 971-col export. **Redesign:** `reclaim_window_dead_runs(cols, pads, display_cols) -> (cols, pads)` reclaims an SL run's shared-grid space **only if it is dead across the WHOLE displayed window**, evaluated once against the **oldest displayed column** (holes only grow toward newer, so dead-in-oldest ≡ dead-throughout), removed **uniformly by absolute row** from every column. A run alive anywhere in the window keeps full height everywhere (a stable hole) → **no surviving number ever shifts row** (alignment preserved, the invariant the incremental path broke), and **N-grp is untouched** (reclaimed runs hold no survivor, so `visible_group_count` never counted them). Incremental `drop_dead` path + `_split_child_runs` **removed**; `column_structures`/`render_columns` are aligned-only again. **export:** aligned build + reclaim over `display=all`; the full range's oldest column is the clean all_wt seed → nothing reclaimed → the export **is** the aligned view (**2,869,305 cells / 6.5 MB**, back to pre-`drop_dead` size, **0 row violations**). **masterapp Blocked-flat:** builds the full skeleton (seed = true oldest) then reclaims over the slider window, so a recent window compacts to just its live groups (**~98% fewer cells**) while staying aligned. **spot-checks** re-derive against the aligned view (`drop_dead` removed). **tests:** the 4 incremental `test_drop_dead_*` **replaced** by 5 `test_reclaim_*` (full = no-op, no row-drift full range, recent window saves + 0 drift + N-grp preserved, uniform removal = subsequence, empty window). **Verified on the regenerated 971-col export (read back from the xlsx):** row-position violations **9,306 → 0**; **N-grp D4701/D4699 = 18/18**; **26** stays a stable all-hole band at D4701 (excluded from the count, **not** excised); both spot-checks pass cell-for-cell; app 10-draw windows save ~98% with 0 violations. Full suite **290 passed**; py_compile OK; AppTest boots clean. |
| 2026-08-13 | **Blocked-flat wall/caught colour only in the exit column** (`syndicate_core/stacked_blocks.py` + `scripts/export_blocked_flat_xlsx.py` + `masterapp.py` + both `scripts/_spotcheck_blocked_flat*.py` + `tests/test_stacked_blocks.py`, commit `28349c4`) — A hole's `wall`/`caught` **kind** is decided once at creation (the exit column) and copied forward as a permanent record, but both renderers painted that colour in **every** column the hole persisted into, so one exit's colour smeared across all newer columns. **Fix:** `render_columns` now tags each hole `("hole", kind, origin)`; `origin` is True only where the exit actually happened — the aligned child cell `structs[j+1][p-offset]` is still a num — exactly mirroring how `deep` marks only the winner's own column (`offset = |winners_j| + 1`). The export (`cell_style`) and masterapp (`_bf_cell_html`) paint wall/caught **only for origin holes**; every inherited hole renders with **no fill** (transparent), keeping the group rail continuous (`_make_format` skips `bg_color` when `bg` is None; a railed inherited hole becomes a rail-only blank). Both spot-checks' `ui_truth` + comparisons updated to mirror this (None-safe bg, transparent = no `patternType`). **Structure untouched — purely a fill-colour change.** `column_structures` still stores 2-tuple holes (all structural tests unchanged); only render output holes became 3-tuples. **Verified on the regenerated 971-col export:** 5,820 painted holes across 5,820 distinct slots, **0** slots painted in >1 column, **0** adjacent-column painted pairs (exactly one coloured occurrence per hole). The 3 cited cases read back from the xlsx: `6` (row19/colA, white) and `22` (row22/colA, brown) unchanged single-column exits; `30` (row29) kept brown at col B (origin) and now **transparent** at col A (inherited). Alignment (**0** row-position violations) and **N-grp D4701/D4699 = 18/18** unaffected. Painted-cell count **2,869,305 → 104,060** (inherited holes no longer written; grid still full 971×6836, 6.5 MB → 0.3 MB). `tests`: +2 origin tests (`test_render_hole_origin_flag_matches_fresh_exit`, `test_render_hole_painted_in_exactly_one_column`); the incorrect "newest column all origin" assumption was dropped (the newest column also carries inherited holes from older exits). Full suite **292 passed**; both spot-checks pass cell-for-cell. |
| 2026-08-13 | **Blocked-flat wall hole colour white → red** (`scripts/export_blocked_flat_xlsx.py` + `masterapp.py` + both `scripts/_spotcheck_blocked_flat*.py`, commit `e3dcaa1`) — Pure colour-constant swap: `_WALL` `#FFFFFF` → **`#FF0000`** (pure red) in the export and masterapp constants, and the two spot-checks' independent `ui_truth` so they still match. **`_CATCH` (`#8B6F47`) is untouched**, and the origin-only painting from `28349c4` is unchanged (wall still painted only in its exit column, transparent where inherited). `stacked_blocks.py` carries no hex, so no change there. The wall hairline outline (once needed so white read on Excel's white sheet) is now redundant but retained unchanged. **Verified on a fresh 971-col export:** every wall-kind hole reads **`FFFF0000`**, every caught-kind still **`FF8B6F47`** (0 mismatches over 5,820 painted holes — 1,976 wall / 3,844 caught); origin-only invariant intact (**0** adjacent-column painted pairs); alignment (**0** row-position violations) and **N-grp D4701/D4699 = 18/18** unaffected. Full suite **292 passed**; both spot-checks pass cell-for-cell. |

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
| 2026-07-07 | **increase.py diff>1 generalization (1n+2/1n+3/1n+4)** — confirmed the diff-general algorithm exists in core/increase.py (mpcheckgroup: threshold is `>diff`, i.e. ≥2 for diff=1, ≥3 for diff=2, ≥4 for diff=3, ≥5 for diff=4 — NOT a fixed ≥2 for all diffs). The CSV runners (run_increase_efficient.py, run_1nplus1.py) are hardcoded diff=1-only and cannot be reused for diff>1. Real diff=2 work already exists — on a SEPARATE Windows machine (d:\Lo\tools\regenerate\increaseW.py), NOT on this Mac/repo, which is why tonight's exhaustive disk search and Mongo probe found nothing — they only covered this machine. increaseW.py is a DIFFERENT script from core/increase.py's canonical implementation; its exact threshold logic hasn't been read yet, only inferred from output. Verified anchor (from Tai's uploaded increase_output_4_to_6_copy.xlsx, extracted directly, not estimated): pool 35, diff=2 (4→6) produced **3,273 valid NLists** out of target space C(35,6)=1,623,160 (0.20% coverage — expected to be much lower than diff=1's ~7-11%, since a higher corroboration threshold is harder to satisfy; consistent with the math, not a red flag). Input block confirmed at 52,360 rows = C(35,4) exact, so this ran against the full input space. A second column-block in that output (49,088 rows) has unclear semantics — needs increaseW.py's real source to interpret correctly, don't guess. Diff=3 (4→7, same pool) crashed TWICE on that Windows machine at an identical intermediate shape (242,082,720 rows) during DataFrame construction — a memory ceiling, not a math failure. First attempt cast to complex128 (unusual for integer ball data — possibly a deliberate but failed encoding/dedup trick, worth checking); second attempt used plain object dtype and still exceeded available RAM (7.21GB). Still outstanding — the original full request, only 1 of 12 cases verified so far: oz (47): 3/47→7/47 (diff4), 4/47→7/47 (diff3), 5/47→7/47 (diff2); sfl (44): 3/44→7/44 (diff4), 4/44→7/44 (diff3), 5/44→7/44 (diff2); pb (35): 3/35→7/35 (diff4), 4/35→7/35 (diff3), 5/35→7/35 (diff2) [4/35→6/35 diff2 case DONE, above]; sat (45): 3/45→6/45 (diff3), 4/45→6/45 (diff2). Next steps, not yet started: (1) get increaseW.py's actual source reviewed — confirm its threshold matches core/increase.py's mpcheckgroup exactly, clarify Block B's meaning, diagnose the complex128 choice; (2) resolve the diff=3 memory ceiling (chunking, or a smarter non-Cartesian-product candidate generation) before attempting any of the remaining diff=3/diff=4 cases at these larger pool sizes; (3) once fixed, compute the remaining 11 cases with real, verified numbers — no estimating from the diff=1 pattern, each diff level has genuinely different coverage behavior. | **SUPERSEDED — ALGORITHM CLOSED 2026-07-09 (11/11 diff>1 verified); see the three 2026-07-09 rows + closure note below** |
| 2026-07-09 | **increase.py diff>1 — ALGORITHM/DEFINITION CLOSED (11/11 cases)** — The consuming definition is verified three independent ways: (a) a hand-constructed example (each width-k input row consumed by at most one NList, first-come in lexicographic order, no special-casing); (b) byte-exact vs c545_combined_copy.xlsx (5/45→6/45: 575,344 NLists, remnant = the single row (41,42,43,44,45)); (c) exact gate on 4/35→6/35 = **16,683 NLists**, sizes {3:15484, 4:691, 5:43, 6:435, 10:29, 15:1}, consumed 52,346, remnant 14. The canonical engine was generalized in `core/run_increase_efficient.py` `run_increase()` to arbitrary diff≥1 (child width k=target−diff; accept iff still-unconsumed children **> diff**; diff=1 path byte-unchanged; self-test 360/360 across diff=1,2,3; commit 9fb4c18). **RETIRE the superseded figures:** "3,273" (a per-file truncation artifact of increaseW.py's `safe_concat_rows` index-alignment bug — NOT a run total) and "1,623,160" (= C(35,6), the *non-consuming* wrong-semantics ceiling). Correct 4/35→6/35 = 16,683. All 11 diff>1 cases computed & verified (partition consumed+remnant == C(pool,k); min group size == diff+1) — per-case table in the closure note below; committed as core/increaseW_results/NLists_<game>/nlists_<code>.csv (commit c6f97b2, row counts == NList counts). Timing: pure-Python single-thread, largest case (oz, C(47,7)=62.9M candidates) ~2.2 min / ~22 MB; no inner-loop optimization needed. | **ALGORITHM CLOSED — 11/11 verified; research question (real draw data) OPEN** |
| 2026-07-09 | **main_data_<game>_plus.csv / Main_Data_sat_plus.csv (diff=1 "4th case") — PROVENANCE UNCONFIRMED** — These appeared during Tai's manual Finder reorg of core/increaseW_results/. Each is a plain one-row-per-NList table (header n1..n{target}, whole row = NList); rows: oz 5,006,617; sfl 3,274,194; pb 736,576; sat 575,344. Checked against our verified `run_increase()` **diff=1** output (6→7 for oz/sfl/pb; 5→6 for sat): **row counts match all four**; **for sat & pb a FULL acceptance-ordered content match was actually run** (`list(nlists) == file rows`, 575,344 and 736,576 rows compared element-by-element) = exact; **for oz & sfl ONLY ROW COUNTS were checked — full-sequence match was NOT verified**. So their content is consistent with the verified engine's diff=1 output, but WHAT generated these files / WHEN / whether the verified code produced them is **not confirmed by us** — treat as consistent-with, not proven-from, the verified pipeline. | **UNCONFIRMED provenance — content matches verified diff=1 (full-sequence sat/pb; count-only oz/sfl)** |
| 2026-07-09 | **Duplicate / overlap analysis of the NList result files** — No within-file duplicates in any of the 15 files. Within-game (tuples in 2+ of a game's files / distinct union): sat 13,360/612,883; oz 164,807/5,365,210; sfl 123,176/3,521,015; pb 44,004/801,958. Multiplicity (brace=2 / hat-trick=3 / four-fold=4): sat 12,540/820/—; oz 152,222/11,724/861; sfl 113,100/9,335/741; pb 39,403/4,166/435. Cross-game (target=7 only): near-total containment via pool nesting pb(1–35) ⊂ sfl(1–44) ⊂ oz(1–47) — pb ~99.9% ⊆ oz & sfl; sfl ~99.9% ⊆ oz; target-7 distinct union = 5,368,057 (only ~2,847 target-7 NLists outside oz — first-come consumption is near-nested, NOT perfectly nested). **sat (target=6) cannot overlap target=7 games** (structural — different tuple width, not scanned). Grand total distinct = 5,980,940. Derived files per game: duplicate_report_<game>.csv + nlists_<game>_deduped_union.csv (untracked). | **Analysis complete** |

**increase.py diff>1 — 2026-07-09 closure (results + still-open):**

| game | k→target | diff | NLists | consumed | remnant |
|------|----------|------|--------|----------|---------|
| oz  | 3→7 | 4 | 3,113   | 16,188    | 27  |
| oz  | 4→7 | 3 | 42,985  | 178,313   | 52  |
| oz  | 5→7 | 2 | 490,748 | 1,533,820 | 119 |
| sfl | 3→7 | 4 | 2,529   | 13,225    | 19  |
| sfl | 4→7 | 3 | 32,544  | 135,713   | 38  |
| sfl | 5→7 | 2 | 345,741 | 1,085,934 | 74  |
| pb  | 3→7 | 4 | 1,224   | 6,531     | 14  |
| pb  | 4→7 | 3 | 12,250  | 52,267    | 93  |
| pb  | 5→7 | 2 | 100,948 | 324,618   | 14  |
| sat | 3→6 | 3 | 3,480   | 14,190    | 0   |
| sat | 4→6 | 2 | 48,239  | 148,976   | 19  |

STILL OPEN (do NOT mark closed):
- **Research question unaddressed:** full-space input verifies the ALGORITHM, not lottery behavior. Running the consuming process on **real draw-history input** (vs the full combinatorial space) is the actual open research question — full-space results say nothing about lottery trends.
- **Five-block outputs deleted, not regenerated:** input.csv / grouped.csv / regenerate.csv / remnant.csv for the original 11 cases were removed during the manual reorg; only nlists survived (and are committed). Regenerable deterministically in ~12 min.
- **Committed but NOT pushed:** 3 commits (9fb4c18 generalize run_increase, 60f7085 reorg CONFIGS, c6f97b2 11 nlists files) are ahead of origin/main — committed, unpushed.
- **main_data_*_plus provenance** unconfirmed (see row above).
- **(8,10,13,15,30,34):** checked 2026-07-09 — absent from all 3 sat files (0/3). If acceptance against *real draw data* (not the full-space files) was intended, that variant is still open.

**Phase 1 — DONE (783deef + baf8add, 53/53):** `_compute_stage_present` and `_apply_stage_sc` extracted from `run_matching`'s loop body. `run_matching` output byte-identical (verified by `.equals()` on selected/unselected/fig9_table/breakdown across the full test suite).

**Phase 2a — DONE (4f8c154, 53/53):** `_prepare_matching_state(main_df, cvi_df, main_path) -> dict | None` and `_fill_exhausted_stages(w_cols, start_idx, M, carry_fwd, main_count_map, main_bd_map, sc_dict=None, *, n_cols=None) -> tuple[list, list]` extracted from `run_matching`. `run_matching` now delegates to both; all pre-loop setup and the exhaustion fill block live in the helpers. 53/53 byte-identical.

**Phase 2b — DONE (4f8c154, 67/67):** `run_matching_step(resume_state, sc_for_stage=None, *, main_df, cvi_df, carry_fwd, main_path) -> dict` implemented in `syndicate_core/matching.py`. Setup call (`resume_state=None`) runs `_prepare_matching_state`, then PHASE A — auto-advances through empty-CVI stages and pauses at the first real stage returning `{"paused": True, "awaiting_sc_for_stage": idx, "w": w, "count_dist": {"S0": n, "S1": n, ...}, "resume_state": {...}}`. Resume call restores frozen state, applies `sc_for_stage` via `_apply_stage_sc`, then re-enters PHASE A or fills exhausted stages and returns `{"paused": False, "selected", "unselected", "fig9_table", "breakdown", "debug_rows", "n_cols", "small_enough"}`. `tests/test_matching_step.py` added: `test_full_run_matches_run_matching` drives 3 pause/resume cycles and asserts `.equals()` on selected/unselected/fig9_table/breakdown against `run_matching` on the same inputs. 67/67 passing.

**Phase 3 — DONE (d7c71e6, 68/68):** Container Dashboards UI wired. SC=NO branch: START MATCHING → `run_matching_step(None, main_df, cvi_df, carry_fwd, main_path)`; on pause stores `step_state_{db}` / `step_pending_{db}` in S; pause screen shows `count_dist` table + `st.multiselect` keyed by `step_sc_choice_{db}_{stage_idx}`; Continue → `run_matching_step(resume_state, sc_for_stage=_sc_chosen)`; on `paused=False` stores result under `gkey("results")[db]` — same path as YES mode so existing rendering block is reused unchanged. Cancel clears step state. Toggle YES↔NO clears step keys. SC=YES branch: original `run_matching` button unchanged. `TestStepSupersetKeys` added — verifies step final result keys ⊇ `run_matching` keys. 68/68 passing.
