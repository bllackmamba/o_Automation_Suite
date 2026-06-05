# Syndicate System — Working Summary & Action Plan
**Owner:** mamba · **Project:** `~/Desktop/Sika/o_Automation_Suite/`
**Status of this doc:** living summary — updated as we go. Last update: initial build.

---

## 0. THE ONE-LINE TRUTH (what days of work proved)
The syndicate **picked numbers are NOT in the fast search API.** They live only
in the **detail view** (the page you see when you open a syndicate). The
intended way to capture them is the **Camoufox browser scraper** — BUT as of the
latest review this scraper is **UNVERIFIED** (we do not yet have a single
confirmed-correct scrape). The only thing proven to contain real numbers is the
**live thelott website detail view** (the screenshots). Next required step:
produce ONE clean Camoufox capture and verify it by eye against the website.

⚠️ DATA TRUST WARNING: existing CSV files in this project are a mix of real,
test, and possibly mock/buggy data and CANNOT currently be trusted. See §1f.

⚠️ COLUMN-NAMING CONVENTION (corrected by user — CRITICAL):
- SYNDICATE data (scraped picks)  → columns are **w1, w2, … wN** (+ `PB` for Powerball).
- MAIN DATA (historical drawn combos, user-supplied) → columns are **n1, n2, … nN**.
- The app's build_w_matrix() / CVI builder look for **w**-columns. Any syndicate
  scraper MUST output w1…wN, NOT n1…nN. (Older parse code wrote n1…nN — wrong —
  which would make the matrix miss the numbers even if captured correctly.)

---

## 1. WHAT IS PROVEN (do not re-litigate — settled with real output)

### 1a. The search API returns STRUCTURE, not numbers — CONFIRMED
Real, untruncated response from `/syndicates/api/search` (NSW, postcode 2000):
```json
{
  "syndicateId": 22195324,
  "syndicateName": "OZ 10S8",
  "shareCost": 1.0, "availableShares": 1, "totalShares": 117,
  "syndicateBets": [
    {
      "betNumber": 1, "product": 2, "gameCount": 10,
      "draws":   [ { "drawNumber": 1685, "drawDate": "2026-06-02T..." } ],
      "entries": [ { "systemNumber": 8, "games": 10,
                     "entryType": "10 Game System 8", "powerHit": false } ]
    }
  ],
  "outletId": 1403519, "totalCost": 117.0
}
```
- `entries[].entryType` = **"10 Game System 8"** → tells you the *system type*, NOT the 8 chosen balls.
- `draws[]` = only `drawNumber` + date.
- **There is no numbers / selections / picks array anywhere in this response.**

### 1b. No simple detail endpoint exists — CONFIRMED (probe `find_detail_endpoint.py`)
All 13 likely detail URLs returned 404/400. There is no clean per-ID API call
that returns the numbers. → The numbers are only reachable via the rendered
page (browser).

### 1c. The numbers ARE obtainable from the live site — CONFIRMED
- thelott's **Syndicate details** modal (the real website) shows "Numbers
  picked" per game (e.g. Oz Lotto Gm1: 8,16,17,21,27,28,32,41 /
  Gm2: 12,21,26,27,34,38,41,44). This is the live site, not a file — so the
  numbers definitely exist and are reachable through the rendered page.
- `thelott_camoufox_scraper.py` is DESIGNED to load
  `thelott.com/play/syndicates?postcode=XXXX` in a stealth browser, capture the
  JSON behind it, and write one row per game line with `n1, n2, … (+PB)`.
  ⚠️ NOT YET VERIFIED that it actually produces correct numbers — see §1f.

### 1f. `Direct_D_NSW.csv` is NOT trustworthy — DO NOT USE (mock / parse artifact)
The uploaded `Direct_D_NSW.csv` is almost certainly fake or corrupted:
```
1,NSW,"10,23,34,36,42,45"
2,NSW,"7,24,29,36,42,45"
...
6,NSW,"10,22,25,36,42,45"
```
- Every row ends in the SAME three numbers (36,42,45) — impossible for real
  independent picks; ~18 distinct numbers across rows rules out one System entry.
  → the tail is hardcoded/templated or a parser bug.
- Only 6 rows; a real NSW scrape would be thousands.
- Columns (`Index, Source_State, Raw_Combination_String`) DO NOT match the
  Camoufox output schema (`Postcode, State, Syndicate_Number, …, n1, n2, … PB`),
  so this file did not even come from the Camoufox scraper.
- CORRECTION: earlier in chat this file was wrongly cited as proof the Camoufox
  scraper works. It is not. No verified real scrape exists yet.

### 1d. Why the current bulk D files / CVI are garbage — CONFIRMED (wiring bug)
- The bulk `D_*.csv` were made by `thelott_syndicate_scraper.py` (the **search**
  scraper). Its `flatten()` outputs metadata + `Draw_Numbers` (draw IDs) and
  **zero `n`-columns**.
- The app's `build_w_matrix()` only looks for `n1, n2, …` columns. For D it
  finds none, so the CVI collation falls back to lining up D's leftover columns
  (Syndicate_ID, Share_Cost, Outlet_ID…) as `w1, w2, w3` → the nonsense seen in
  `CVI_BRD`.
- **Conclusion:** not a data problem — the app was fed by the wrong scraper.

### 1e. False alarms (so we don't chase them again)
- `{"syndicates":[{"numbers":[3,6,7,11...` seen in old chat = an *illustrative
  example* typed by the assistant ("it will print something like"), **not** a
  real capture.
- "Fields that may hold numbers: number/game/entry" from `dump_one_syndicate.py`
  = matched on `drawNumber`, `games`, `entries` — **none are real picks.**

---

## 2. THE FILES — what to keep, what to ignore
**KEEP (the only two that matter):**
- `thelott_camoufox_scraper.py` — the real picks extractor (browser; outputs `n`-cols). **This becomes the D source.**
- `masterapp.py` — the app. Needs D rewired to the camoufox output (see §3).

**SUPPORT / UTILITY:**
- `f_rules_Gclaude.xlsx` — the B variable (real number sets). Fine as-is.
- `check_syndicates.py` — small lookup helper.

**IGNORE (older / duplicate / superseded):**
- `thelott_syndicate_scraper.py` (search-only; the cause of the garbage D) —
  keep ONLY as a fast source of syndicate *metadata* if ever wanted; it cannot
  give numbers.
- `scraperFG.py`, `Scraper_fix.py` (older Playwright versions of camoufox)
- `scraperC.py`, `thelott_scraper.py` (older browser/HTML walkers; scraperC also does WA)
- `masterappo.py` (old copy of the app)
- `scraping_dashboard.py` (UI shell)
- `find_endpoints.py`, `wa_probe.py`, `wa_probe2.py`, `lottolyzer_scraper.py` (probes/aux)

---

## 3. THE PLAN (what we are building now)

**Goal:** D variable per game = real syndicate combinations (`n1…nN`), so
`build_w_matrix → CVI → matching` run on real numbers and BRD stops being garbage.

**Step A — Camoufox is the D source.**
Use `thelott_camoufox_scraper.py` to produce per-game-line rows with `n1…nN (+PB)`.
Integration hook already exists: `scrape_state_for_masterapp(state, postcodes, save_path, ...)`.

**Step B — Bridge the one seam: `Game_Type` → `Games`.**
- Camoufox labels each row with `Game_Type` (e.g. "System 8") and `product`/game.
- The pipeline's `split_d_by_game()` keys off a `Games` column.
- FIX: add a `Games` column to camoufox output (map product/game name → canonical
  game: pb / oz / sat / sfl / mwf), so the existing splitter works unchanged.

**Step C — Make the D loader prefer the `n`-column file.**
- When loading the D variable for a game, prefer a file that has `n1…nN`
  (camoufox output) over the metadata-only search file.

**Step D — Verify end to end on ONE small sample.**
- Scrape one postcode → confirm rows have real `n1…nN`.
- Build W-matrix for one game → confirm `w`-columns are real number sets (1–47),
  NOT 8-digit IDs / dollar costs.
- Collate `BRD` → confirm CVI numbers look like real lotto numbers.

**Step E (optional later):** harden camoufox (concurrency, retries, nightly cron).

---

## 4. CONFIRMED API REFERENCE (for the scraper)
```
Outlets:    GET https://api.thelott.com/outlet/outlets?state={STATE}&postcode_or_locality={PC}
Search:     GET https://api.thelott.com/syndicates/api/search?company={INT}&outlets=ID1,ID2,...&limit=100
            (outlets MUST be comma-separated; SSL verify off on macOS)
Company ID: NSW/ACT=3, VIC/TAS=1, QLD=2, SA=6
Numbers:    NOT in search. Only via page: https://www.thelott.com/play/syndicates?postcode={PC} (browser)
Detail API: none found (all candidates 404/400)
```

---

## 5. OPEN QUESTIONS / TODO (update as we go)
- [ ] Confirm exact game mapping from camoufox `product`/icon → canonical game keys.
- [ ] Decide: scrape per-state (camoufox) cadence; nightly cron vs manual.
- [ ] After D is real: re-check the So (SplitsCombi) engine filter (separate known issue).
- [ ] Confirm `Main_Data` (historical drawn combos) is correct & separate from D.

---

## 6. CHANGELOG
- **(initial)** Captured all proven findings; probe confirmed no detail
  endpoint; committed to Camoufox path. Next: implement Steps A–D.
- **(update — data trust)** User flagged `Direct_D_NSW.csv` as possibly mock.
  Inspection CONFIRMED it: identical `36,42,45` tail on every row, only 6 rows,
  schema does not match Camoufox output. Retracted earlier claim that it proved
  the Camoufox scraper. STATUS RESET: no verified real scrape exists. New
  prerequisite (Step 0 below): make ONE clean Camoufox capture and verify it by
  eye against the live thelott site BEFORE building anything on top of it.
  Treat all existing CSVs as untrusted until verified.

## 7r. ★★ COLLATION REWRITTEN to correct model (D transposed, WIDE output) ★★
User corrected the whole collation orientation. CONFIRMED MODEL:
  • Every variable = a block of vertical w-columns. A formula lays the blocks SIDE
    BY SIDE (left→right) and renumbers w1..wN across the whole result → WIDE matrix.
  • B, R, Ep, Sp, So are ALREADY w-columns → used AS-IS (no transpose).
  • D (Direct) is raw syndicate ROWS → TRANSPOSED: each syndicate → one vertical
    w-column (15,547 syndicates → 15,547 columns). depth = pick length (7 for pb).
  • Numbered/pure formula Xn..Xn = "all of that variable joined" = ONE combined
    block. Strip trailing digits + de-dup, so D1D2D3 == one D block (NOT 3 copies),
    B1B2B3 == one B, etc. (User: numbers are just notation; use the ALL/combined.)
EXAMPLES (NSW pb):
  D1D2D3 = transpose(D_ALL_pb) = 15,547 w-cols × 7 rows (pure direct).
  BRD    = B cols + R cols + 15,547 D cols, renumbered w1..wN (≈15,562 cols), as
           tall as the deepest block.
FIX DETAILS (masterapp.execute_collation): for each component, base=strip digits,
de-dup; block = d_to_w_only(S[base]) (TRANSPOSES raw D, leaves wide vars as-is);
concat axis=1; renumber w1..wN; 1-based Row. PB intentionally NOT included in the
matrix (formula is the main-number picks; can add later if wanted).
Also fixed the Container-Formula "Missing/empty" pre-check to resolve numbered
comps the same way (D1D2D3 → checks for D, not D1/D2/D3).
VERIFIED on synthetic data: D1D2D3 → 4 syndicates=4 cols depth 7; BRD → 11 cols
(5B+2R+4D) wide. The earlier "depth 4 rows" was STALE data; correct depth = pick
length (7 for pb).
NOTE: BRD/D1D2D3 are now very WIDE (thousands of cols). CSVs are wide; previews
show head. This is the intended design.

## 7ae. ROOT CAUSE of circling found + tab consolidation started
DISCOVERY: each Variable-Inputs tab (R/Sp/So/Ep) already had its OWN older INLINE
generator from prior turns — and with WRONG inputs. Worst: the Ep tab built objects
from B's w-columns and all_wt from D's top-8 cols, NOT "D's 8 longest rows + R's
to_keep". R tab used a manual 1–8 slider (no safe-max). This duplication + wrong inputs
is the real reason the variables/collation never came out right. FIX = point every tab
at the single tested generate_* function with the CORRECT inputs.
Ep DEFAULT set to mode='pairs' (8 longest D rows, paired a=#1&#2…; R supplies wt) per
user confirmation ("8 rows of D … to_keep rainbow produced it").
DONE: R tab spliced to call generate_rainbow(auto safe-max; manual override optional);
stores S["R"] + S["_R_wt"] (R's wt → Ep input2).
REMAINING (next turn, same move): splice Sp tab → generate_splits(prepare_d_input_sets
(D,4)); So tab → generate_splits_combi(...); Ep tab → generate_excelpro(prepare_ep_
objects(D,'pairs'), S["_R_wt"]'s wt_abcd) — REPLACING the wrong from-B logic. Then
collation has correct B/R/D/Sp/So/Ep. Timer decision: clicking Generate runs the AUTO
choice immediately (decisive) with an Adjust override — robust; literal countdown is
fragile in Streamlit and deferred unless user insists.

## 7ad. Ep BUILT (both input modes) + duplicate generator block removed
generate_excelpro (Ep) ported from Java Main.java — only the substantive 'All' output
(POI cosmetics/colour/merge dropped). Ep: for each pair header (ab,ac,ad,bc,bd,cd),
4 cols = R's wt numbers landing in {x.half1,x.half2,y.half1,y.half2} → 24 cols.
prepare_ep_objects(D, mode): mode='halves' (4 longest split in half → 8 half-cols,
matches Sp/So) OR mode='pairs' (8 longest entries paired a=#1&#2,…). ★ AWAITING user
A/B confirmation (halves vs pairs) — both tested, only input-fill differs.
CLEANUP: an EARLIER duplicate generator block (the _gen_* helpers + d4/splits-signature
generate_rainbow/splits/splits_combi, no Ep) was sitting before the new one — REMOVED
(deleted old lines; kept the complete inlined set). Now ONE 'VARIABLE GENERATORS'
section, one def each, compiles, all four tested (R/Sp/So/Ep). masterapp.py = 5089 lines.
REMAINING TO FINISH: wire the four into the app's variable tabs with the TIMED
intervention gate (pre-fill auto choice, countdown, commit auto on timeout) + buttons
that run them from CURRENT D / Since-Last (DYNAMIC — re-run on input change) and store
into S[] for collation. Confirm Ep A/B, then only the UI wiring is left.

## 7ac. GENERATORS R/Sp/So BUILT & INLINED + auto-params + decisions
User decisions: (1) put EVERYTHING in masterapp.py (no separate module — inlined,
lottery_generators.py removed); (2) auto-pick highest SAFE ceiling (no manual); (3) a
TIMED intervention window for Sp/So/Ep/R params — pre-fill the auto choice, give a
countdown to override, else commit auto on timeout.
BUILT THIS TURN (inlined in masterapp.py, tested on synthetic data):
  • generate_rainbow (R) ← Since-Last table. Safe-max guard auto-lowers max_comb until
    combo-count ≤ guard (200k) — RESOLVES the "don't go too high" malfunction (no 2**K
    tail; bounded generation). Returns (result_df, wt_df w/ wt_abcd for Ep, info).
  • generate_splits (Sp) ← D's 4 longest rows (cols a,b,c,d); auto half-splits
    ((len+1)//2: 20→10, 17→9). Faithful port of task1b.sets_sampling. 112 set-cols.
  • generate_splits_combi (So) ← D's 4 longest rows; auto half-splits. Ports
    automation_vba.sets_sampling (len==4 set algebra), SKIPS the 300-line fragile
    column-relabeling (cosmetic only; collation needs just the sets). 181 set-cols.
  • auto_half_splits(), prepare_d_input_sets(D,n), sort_d_longest_first() — D feeds.
All return COLUMN-oriented sets → collation transposes to w-rows.
NEXT: (a) Ep — port Java ExcelPro → Python (input: D's 8 longest rows + R's wt_abcd);
(b) WIRE all four into the app's variable tabs with the TIMED intervention gate +
buttons that run them and store into S[]; (c) confirm which generator OUTPUT becomes
each variable (R likely the 'rainbow'/combo sets). Build order remaining: Ep, then UI.

## 7ab. GENERATOR PIPELINE (corrected mapping) + D-prep foundation built
User clarified the variable-generation pipeline (row-oriented):
  • Sp ← task1b.py (reads data_1b.xlsx / "Hoja 1") ← D's first 4 LONGEST w-ROWS.
    ★ task1b.py NOT YET UPLOADED — needed to build Sp.
  • So ← automation_vba.py ← D's first 4 LONGEST w-ROWS; auto-split IN HALVES
    (len 20→10, 17→9 = round up = (len+1)//2). (Earlier "8 cols" reading was WRONG —
    it's 4 longest ROWS now, row-oriented.)
  • Ep ← Java ExcelPro → CONVERT TO PYTHON ← D's first 8 LONGEST rows (input.xlsx)
    + input2.xlsx from processing R.
  • R ← task2.py (max combinations; author warned high values malfunction = the
    powerset 2^K explosion — fix by generating bounded combinations directly, not
    materializing full powerset). task2.py is OLDER than pipeline; has an unrelated
    RSA snippet at the bottom to IGNORE.
  • All generator outputs are TRANSPOSED, then fed as row-oriented variables; collation
    stacks B+R+D (+Sp/So/Ep). "We get R from our code"; Ep's input2 comes from R.
BUILT THIS TURN (verified): sort_d_longest_first(D) + prepare_d_input_sets(D, n) —
sorts D longest-entry→shortest and peels the N longest entries into labelled columns
a,b,c,d(…h). Foundation for every generator. B-rows + collation row-stack confirmed.
OPEN: (a) upload task1b.py (Sp); (b) confirm R's INPUT is the Since-Last data (numbers
+ since-last + to_keep), NOT D; (c) per generator, which OUTPUT sheet/cols become the
variable after transpose. Build order (easy→hard): R → So → Ep → Sp, then wire to S[].

## 7aa. ★★★ HEADLINE: syndicate coverage is POISSON-RANDOM ★★★
Crowding distribution (draw 4687): covered 1×=1,439,688 · 2×=161,423 · 3×=12,681 ·
4×=882 · 5×=53 · 6×=2 · 0×(untouched)=6,530,331. This is a near-PERFECT Poisson
distribution (λ = gross/total = 1,804,382/8,145,060 ≈ 0.2215). Observed vs Poisson-
expected: 0→80.2% vs 80.1%; 1→1.44M vs 1.45M; 2→161k vs 160k; 3→12.7k vs 11.8k
(excellent fit on big buckets). CONCLUSION: syndicate coverage of the combination
field is statistically indistinguishable from RANDOM scattering → entries are
randomly generated (QuickPick-style); there are NO "popular" combinations in
syndicate play; the overlaps are pure chance, not popularity (the two ×6 combos are
Poisson noise, predicted ~1). The "avoid crowded combos" idea has no target in
syndicate data. NUANCE: the tail (k=4,5,6) runs slightly ABOVE Poisson (882 vs 655,
53 vs 29) — the faint footprint of large SYSTEM entries with consecutive-number
blocks (the only non-random structure, a whisper). FULL PICTURE: ~99% pure random
spread + faint system-block tail. This is the project's headline research finding.

## 7z. CROWDING analysis (draw 4687) — field is THIN, not clustered
Ran per-combo crowding for draw 4687 (1,614,729 unique = 19.8% covered, 80.2%
untouched). FINDING (corrected the hypothesis): crowding is SHALLOW. Max coverage of
any single combo = ×6 (only 2 combos); then a wave of ×5. covered ONCE = 1,439,688
(89%); covered 2+ = 175,041 (11%). Top combos are NOT birthday/date clusters — they're
consecutive runs (41-42-43-44-45, 22-23-24-25, 13-14-15), the fingerprint of large
SYSTEM entries overlapping, not human picks. WHY: this is SYNDICATE (operator system-
generated) data designed to SPREAD coverage — the "greedy pile onto popular numbers"
effect lives in INDIVIDUAL manual/QuickPick entries, which the API doesn't expose
(cf. 15/23 Div-1 winners were QuickPicks). So syndicate sharing risk is LOW: a winning
covered combo most likely held by ONE syndicate entry.
NEXT PROBES (optional, user's research): (a) crowding distribution per draw to confirm
flatness; (b) megadraw vs ordinary Saturday — does operator flood MORE syndicates
(higher coverage %) while per-combo crowding stays flat = the "$20M effect" in the
measurable layer.

## 7y. ★ PER-DRAW COVERAGE (real result) + QLD sat fixed + regen confirmed
Regen (split+combine with Draw_Number-preserving code) SUCCEEDED. QLD sat now present
(87,839) — the "QLD = pb only" issue resolved by current re-tag/draw logic. National:
sat 355,190 · oz 62,812 · pb 44,749 · mwf 5,149 · sfl 0 (no SFL syndicates captured).
D_ALL_sat now carries Draw_Number (True). draw-aware dedup → dropped_dups 0.
PER-DRAW SAT COVERAGE (39 draws, of 8,145,060 possible):
  draw 4687 = 19.82% (1,614,729 combos) ← peak / best-captured (open draw 20 Jun 2026)
  draw 4683 = 8.5% · 4685 = 2.89% · rest taper to ~0% (future draws still filling;
  gap 4702–4711 = already-run/delisted). avg 1.07% (misleading — sparse future draws).
HEADLINE for research: a FULLY-SUBSCRIBED Saturday draw → syndicates cover ~8–20% of
the whole field; 4687 (~20%) is the cleanest single-draw measurement. The 33.2% union
was inflated by stacking many draws. Per-draw is the meaningful instrument now.
MAINT NOTE: Streamlit warns use_container_width removed after 2025-12-31 → eventually
swap to width='stretch' app-wide (still works for now, warnings only).

## 7x. UNIQUE coverage = 33.2% + Draw_Number now preserved through split
UNIQUE sat coverage: 2,707,514 distinct 6-combos = 33.2% of 8,145,060 (vs 3,624,765
gross / 44.5%). Overlap = 917,251 combos played by >1 syndicate (~25% of gross).
CAVEAT (user agrees): this is the UNION across all captured draws — the file has no
draw number, so per-draw coverage (the meaningful unit) can't be computed. Per-draw
will be far smaller than 33.2%.
FIX: scraper ALREADY captures Draw_Number (thelott_picks_scraper.py line 268, in the
row + header). It was being DROPPED by masterapp split_d_by_game's _clean_for_pipeline
(kept only Syndicate_ID/Name/Game/Games/PB/w). Now KEEPS Draw_Number + Draw_Date —
safe because the row-based collation reads only w-columns for D (no leak). combine_
states_for_game carries it through (just concats); bonus: drop_duplicates now treats
the same combo in different draws as distinct (was wrongly merging). NO RE-SCRAPE
needed IF raw Global_Scraper/D_<STATE>.csv already have Draw_Number — re-run
Promote+Split → new D_ALL_<game> carries the draw. THEN per-draw coverage = groupby
Draw_Number → unique combos & % per draw.

## 7w. Coverage finding (44.5%) + numbers-only D hardening
COMBINATION COVERAGE (sat): D_ALL_sat = ~354,681 entries. System entries expand by
C(n,6): 6→1, 7→7, 8→28, 9→84, 10→210, … 20→38,760. GROSS 6-number combinations =
3,624,765 = 44.5% of all C(45,6)=8,145,060 Saturday combinations. (User's research is
NOT prediction — this is field-coverage analysis.) Unique (deduped) count = run the
expand+set one-liner; gap vs 3.62M = overlap (how crowded popular picks are).
DISCOVERY: the glob'd D_ALL_sat.csv has ONLY w1..w20 columns — NO Syndicate_ID, NO
draw_number. Implications: (a) can't split coverage per-draw from this file (the
44.5% is aggregate over all captured draws); the scraper computes draw_number but
it's being dropped before save — keep it if per-draw matters. (b) ★ FIX: _to_w_rows
keyed D-detection on metadata, so a numbers-only D would be wrongly TRANSPOSED back
into the column wall. Added is_direct flag; execute_collation now calls
_to_w_rows(df, is_direct=(var=="D")) so D is recognized BY NAME and kept as rows
regardless of metadata. VERIFIED: numbers-only D (1000 rows) stays 1000 rows; B
still transposes. Shipped.

## 7v. ★★★ ORIENTATION FLIPPED TO ROW-STACKING (spreadsheet column ceiling) ★★★
FUNDAMENTAL REVERSAL of 7r (wide model). Why: Excel = 16,384 cols / ~1,048,576 rows;
Google Sheets ~18k cols. D_ALL_sat has 354,682 syndicates → transposing to w-COLUMNS
(w1..w354682) is impossible in any spreadsheet. User realized this and chose to
arrange w in ROWS instead. NEW CONFIRMED MODEL:
  • Each w-set is a ROW. D is already row-oriented (one syndicate per row) → KEPT as
    rows, no transpose. B, R, Ep, Sp, So are stored column-wise → TRANSPOSED so each
    becomes a row.
  • Collation STACKS vertically (axis=0): BRD = B rows + R rows + D rows → TALL
    (~355k rows × longest-combination columns w1..wK). Adds a "Source" col (B/R/D).
  • Matching = row-vs-row: each Main_Data combination row vs each CVI w-set row.
    "pretty much the same" as before per user.
IMPLEMENTED (masterapp.py, verified): new _to_w_rows() (keeps raw-D rows via D-meta
detection; transposes B/R/Ep/Sp/So via .T); execute_collation() now stacks rows +
Source col + Row index. TEST: B(720)+R(5)+D(1000) → 1725 rows × (Row,Source,w1..w24).
GUARDS: CVI-Matrix "Build W-Matrix" now SKIPS the transpose when D > 16,384 rows
(keeps rows, tells user to collate directly) — prevents a 354k-column freeze.
Collation display caps to 50 rows shown + true shape; full file saved/downloadable.
NOTE: build_w_matrix (transpose) now only used for SMALL D (<16k rows); the row model
is the default path. d_to_w_only (old wide helper) retained but no longer used by
collation. SUPERSEDES the "wide / D→columns" guidance in 7r/7t/7u.

## 7u. WRAP-UP fixes + answers + remaining work (from wrapup.docx)
FIXED & SHIPPED (compiled, B-fix verified on data):
  1. ★ B-COLLAPSE (the "one long column") — d_to_w_only now transposes ONLY genuine
     raw D (detected by SYNDICATE METADATA: Syndicate_ID/Game/Games/PB/Draw_Number/
     Outlet/…). B, R, Ep, Sp, So (already-wide) keep ALL their w-columns as-is; a
     stray label column no longer triggers a flatten. Verified: B 720 cols stays
     720; raw D transposes; BRD = 24 rows × (720+R+D) side by side.
  2. SC loader now also reads SC_<formula>*.xlsx (was .csv-only → couldn't see the
     user's .xlsx in Selected_Counts).
  3. FREEZE fix: never render huge frames. Collation result + CVI-matrix inspect now
     show only a corner (≤60 cols × ≤30 rows) + TRUE shape; full matrix still saved
     to disk + downloadable. (A 192k-column BRD sent to the browser was the freeze.)
  4. "depth: 4 rows" wording REMOVED everywhere → now "N w-columns (w1…wN) · longest
     column = M numbers" / "longest pick = M numbers". Matches the user's model
     (columns = syndicates; a column's length = its pick count).
ANSWERS GIVEN:
  • QLD only produced Powerball because the QLD file was scraped with the OLD
    (pre-re-tag) scraper whose company-2 product→game map was incomplete, so non-pb
    QLD lines got unknown tags and didn't split into sat. FIX = re-scrape QLD with
    the new re-tag scraper (resolve_game infers sat/oz from draw range). Then QLD sat
    appears and the user's sat total (191,449) completes.
  • 92,071 vs expected 192,169 BRD cols = B collapsing (fixed here) + QLD sat missing
    (fixed by re-scrape). Both now addressed.
  • Coverage: NSW/VIC/QLD/SA/TAS (ACT folds into NSW data · NT = 0 syndicates ·
    WA = Lotterywest, no open API). All syndicate-bearing states covered.
  • File clutter — KEEP: masterapp.py, thelott_picks_scraper.py,
    SYNDICATE_PROGRESS_SUMMARY.md, data folders (Global_Scraper, Games, Main_Data,
    Formulas), migrate_structure.py (until cleanup done). SAFE TO DELETE (one-time
    diagnostics): dump_one_syndicate.py, find_detail_endpoint.py, recon_capture.py,
    record_all.py, diagnose_403.py + recon JSON dumps.
REMAINING (bigger, deliberate — NOT yet done):
  A. NAMING with lotto type + draw so Saturday≠MWF≠Oz and draw1≠draw2 scrapes are
     distinct. Proposed: CVI_<game>_<formula>_<draw>.csv ; Main_<cluster>_<game>_
     D<draw>.csv ; outputs carry <game>_<draw>. Requires touching every save/scan
     (scan_main_data_files, parse_cvi_filename, collation save, dashboard outputs).
  B. DASHBOARD REDESIGN: collapse the long Selected/Unselected/breakdown trail behind
     expanders; per-row U/S DROPDOWN sized to the SC length, edited inline; pull
     detail on demand. UI rework of Container Dashboards page.
  C. Re-scrape ALL states with the re-tag scraper for corrected, complete national
     data (esp. QLD sat). Then Promote+Split → D_ALL_<game> per game.
  D. Real Ep/Sp/So generation (ExcelPro/task1b/auto_vba) — still placeholders;
     awaiting the user's algorithms.

## 7t. Since Last AUTO-FETCH + SC upload + Ep/Sp/So labeled as INPUT + rows/cols
Confirmed local masterapp.py IS current (grep "SIDE BY SIDE" = 1), so the 729-col
BRD was NOT old code — it was D NOT LOADED for Saturday (CVI shown = B 720 + small
R, no D). To get the wide BRD, load/build D (Build W-Matrix on the Saturday D file)
BEFORE collating. depth:4 = a STALE matrix file being inspected (delete it).
ROWS vs COLS (user's exact model — restate this way): final CVI is WIDE. COLUMNS =
syndicates (w1..wN, N huge). Each column's LENGTH = that syndicate's pick count
(7 for standard pb, MORE for System entries). NUMBER OF ROWS = the LONGEST column =
the longest pick; shorter columns padded with blanks below. Depth is NOT fixed at 7
and is NEVER truncated. B/R/Ep/Sp/So NEVER transposed; only D.
EDITS (shipped, compiled):
  • fetch_since_last(url,pool) + save_since_last(): best-effort lottolyzer scrape
    (urllib + pd.read_html, finds Number + "since"-type cols, 1..pool). R tab now
    AUTO-FETCHES when cache missing; Since Last tab got a "⤓ Fetch now" button.
    Manual CSV upload remains the fallback. NOTE: runs on user's Mac (needs lxml/bs4);
    can't verify network here — if lottolyzer layout differs, fetch returns None and
    UI shows manual fallback.
  • Dashboard SC: added active uploader (cols w + Selected Count → SC_<formula>.csv)
    where it used to just say "SC not loaded".
  • Ep/Sp/So RELABELED as INPUT placeholders everywhere ("feeds ExcelPro/Splits/
    SplitsCombi; not generated yet") — per user, the top-8/top-4 cols are INPUTS to
    generation code that ISN'T wired; the app currently shows the input, not output.
    TODO (pending user): real ExcelPro / task1b / auto_vba generation algorithms.

## 7s. ★ SCRAPER: RE-TAG mislabeled lines (keep data) + per-state drop count ★
SWEEP STATUS (sweep ALL, hardened scraper): TAS 15,876 → Global_Scraper/D_TAS.csv;
QLD 118,459 → D_QLD.csv; SA 61,873 → D_SA.csv. All landing correctly. NSW/VIC
still to finish (user chose to let full sweep complete).
TWO FIXES:
1) Per-state drop count: fetch_details._dropped never reset → printed a RUNNING
   TOTAL (why TAS/QLD/SA all showed identical 2467). Now reset at start of each
   sweep_state + scrape_postcode; increment is thread-safe (under _throttle_lock).
2) RE-TAG instead of DROP (user choice — keep the data): added resolve_game(
   company, product, draw, selections). If the mapped game's pool can't hold the
   picks, infer the TRUE game from DRAW RANGE + max pick:
     draw 4400–4900 → sat (mwf only if already mwf); draw 1400–1900 → pb if max≤35
     else oz; max≥46 → oz; max==45 → sat-family; max≤44 & sfl → sfl; else tightest
     pool that fits. fetch_details now calls resolve_game PER LINE and keeps it;
     only a pick >47 (beyond every pool) is unkeepable/dropped.
   VERIFIED: Sat-as-pb (picks 40/44, draw 4683) → retagged sat; real pb (max 35) →
   pb; oz (max 47) → oz; unmapped product + Sat draw → sat; pick 99 → dropped.
IMPLICATION: the 3 saved states (TAS/QLD/SA) + the in-flight NSW/VIC used the OLD
DROP scraper, so they're missing the re-taggable lines. To get the corrected,
more-complete national data, RE-RUN `sweep ALL` with this updated scraper once the
current run finishes (or replace now and re-run). Small fraction (~2467 cumulative
vs hundreds of thousands), so fine to test NSW first, re-scrape later.

## 7r. ★★ COLLATION MODEL CONFIRMED + VERIFIED WIDE (the formula rewrite) ★★
User clarified (and confirmed via Q&A) the TRUE model — execute_collation already
implements it; verified this turn:
  • Each variable = a block of vertical w-columns.
    - B, R, Ep, Sp, So: ALREADY w-columns → used as-is (NO transpose).
    - D (Direct): raw syndicate ROWS → TRANSPOSED (each syndicate → one w-column)
      via d_to_w_only. 15,547 pb syndicates → 15,547 columns. Depth = pick length
      (7 for pb), NOT the bogus "4" seen earlier (that was stale/old-local data).
  • A formula lays blocks SIDE BY SIDE (left→right), pads to deepest, renumbers
    w1…wN. BRD (NSW pb) = B cols + R cols + 15,547 D cols ≈ 15,562 cols, WIDE.
  • Pure numbered formulas COLLAPSE to one block: tokens have trailing digits
    stripped + de-duped, so D1D2D3 → single D block ("all direct joined" =
    transpose(D_ALL)), NOT three copies. B1B2B3→B, R1R2R3→R, S1S2S3→Sp, So…→So.
  • Missing-var check uses the SAME base-variable resolve (line ~3464), so D1D2D3
    checks for D — fixes the old "Missing: D1/D2/D3" message.
VERIFIED on realistic data: BRD = 22 rows × (3+2+5)=10 w-cols + Row; D1D2D3 = one
5-col D block (not 15); depth = 7. All in shipped masterapp.py.
KEY: user's screenshots (36 cols / depth 4 / "Missing D1D2D3") were an OLD LOCAL
masterapp.py. ACTION: replace local masterapp.py with current shipped one, restart,
rebuild → BRD wide, D1D2D3 = pure direct (15,547 cols for NSW pb).
FORMULA FAMILIES: D1D2D3=all direct joined (count irrelevant, = D_ALL). B1B2B3/
R1R2R3 = per-state/per-source of that var joined (single source now → just B/R).

## 7q. FIX: scraper save() crash — `_columns` was undefined (NameError) → restored
The scrape itself worked (postcode 2000 → 6,803 real Saturday rows) but save()
raised `NameError: name '_columns' is not defined` — the helper had been dropped
in an earlier edit. Restored `_columns(rows)`: builds a stable CSV header (known
metadata cols present → PB → w1..wN sorted numerically → any leftovers). No `re`
dependency. VERIFIED: save() writes header with Games + w1..w7 ordered correctly.
=> Scraper now runs clean end-to-end; re-run `sweep NSW` / `sweep ALL`.

## 7p. ★ 403 DIAGNOSED = temporary rate-limit (endpoint fine); scraper hardened ★
diagnose_403.py result: outlets + BOTH details calls returned 200 with REAL data.
=> The 403 storm was a TEMPORARY IP rate-limit from hitting details too fast, and
it cleared on its own. NOT a bot-wall, NOT a contract change, NO headers needed.
Endpoint api.thelott.com/syndicates/api/details is open to plain Python as before.
(Diagnostic's "0 outlets" was a typo in the DIAGNOSTIC only — wrong field
`outletId`; the real scraper correctly uses `outlet_id`. No scraper bug.)
">35 for Powerball" SOLVED: syndicate 22176509 is actually SATURDAY (product 1,
drawNumber 4683 = Sat-family range, selections [7,8,25,35,40,43,44] incl. 40/44).
It was mis-tagged toward pb; the POOL_MAX guard (drop pb selections >35) catches
exactly this. Confirms game = f(company, product, DRAW RANGE), not product alone.
SCRAPER HARDENED vs rate-limit (so sweep ALL won't stall):
  • MAX_WORKERS 8→6, PER_REQ_PAUSE 0.05→0.12 (gentler defaults).
  • fetch_details_retry now treats HTTP 403 as THROTTLING: waits THROTTLE_COOLDOWN
    (20s × attempt = 20/40/60s) and retries, instead of burning quick retries and
    dropping the syndicate. Other errors keep the short backoff. RETRY_TIMES 3→4.
  VERIFIED: 403→cooldown→retry→success (no premature drop).
NOTE: the no-arg run scrapes default postcode 2000 via scrape_postcode (sequential,
0.15s) — fine for a quick test; use `sweep NSW`/`sweep ALL` for real runs.

## 7o. ★ STRUCTURE REFACTOR: Main_Data≠D, Global_Scraper, Games_Breakdown, national D_ALL ★
USER CORRECTION (said repeatedly): Main_Data is ONLY the user's own draw data —
never the scraper's D. Fixed:
  • Scraper now writes RAW scrapes to Global_Scraper/D_<STATE>.csv (was
    Main_Data/D_<state>_<state>.csv). Clean single-state name.
  • masterapp DIRS gains "Global_Scraper": ROOT/Global_Scraper. All D-scrape reads
    (data status, promote candidates, split source, cached browser, CVI fallback)
    redirected Main_Data → Global_Scraper. (User-data scanner scan_main_data_files()
    left on Main_Data — that's the n-data.)
  • Per-game split folder renamed Direct → Games_Breakdown (findable, matches tab).
    game_dirs keeps "Direct" as an ALIAS to the same Games_Breakdown path so all
    existing ["Direct"] references keep working (no breakage).
  • Variables/Variable_Elements hierarchy kept (user accepted); B/R/Ep/Sp/So there.
NATIONAL COMBINE (user choice: combine ALL states into one D per game):
  • Added combine_states_for_game(game_key): concatenates all D_<STATE>_<game>.csv
    in the game's Games_Breakdown → D_ALL_<game>.csv (drops exact dup rows only;
    states' syndicates are distinct so kept). VERIFIED: NSW+VIC pb → 4-row D_ALL.
  • Promote All + Split now auto-builds D_ALL_<game>.csv per game and reports it.
  • CVI Matrix source list puts D_ALL_<game>.csv FIRST (the default national source).
USER PLAN: re-scrape all states with fixed scraper, then this combine gives the
national CVI. Migration: old Main_Data/D_*_*.csv become stale (move/delete);
new scrapes land in Global_Scraper/.

## 7n. ★ NAMING SCHEME + B sheet collision fix + orientation clarified ★
W-MATRIX ORIENTATION (confirmed correct & what user wants): each syndicate row →
ONE w-column (transpose). 13,924 NSW PB syndicates → 13,924 w-columns × (longest
pick-set) rows. build_w_matrix already does this. The "35 w-cols × 13924 rows"
seen was a STALE CVI_Matrix file from before the fix → REBUILD to fix.
DASHBOARD/CVI LEAK = STALE FILES too: dashboard just reads CVI_*.csv from disk;
the leaking CVI_BRD was collated before the execute_collation fix. RE-COLLATE to
overwrite clean. (No live code leak remains after 7m.)

B SHEET COLLISION (real bug): sat AND mwf both used sheet "Ta (2)". Fixed:
GAMES_CFG now has clean b_sheet per game (PB/OZ/SAT/SFL/MWF) + b_sheet_legacy
(old cryptic name) as fallback. B loader now prefers Base.xlsx then legacy
f_rules_Gclaude.xlsx, and clean sheet then legacy sheet — non-breaking migration.

UNIFIED NAMING SCHEME (target):
  Game keys: pb / oz / sat / sfl / mwf   (folders & sheets use UPPERCASE)
  B (Base):  ONE workbook Base.xlsx, one sheet per game → PB, OZ, SAT, SFL, MWF
  D full:    Main_Data/D_<STATE>.csv            e.g. D_NSW.csv
  D split:   Games/<G>/.../Direct/D_<STATE>_<key>.csv   e.g. D_NSW_pb.csv
  CVI matrix: Games/<G>/.../CVI/CVI_<STATE>_<key>.csv   e.g. CVI_NSW_pb.csv
  Ep/Sp/So:  Ep_<STATE>_<key>.csv / Sp_… / So_…         e.g. Ep_NSW_pb.csv
  Collated:  CVI_<FORMULA>_<key>.csv                     e.g. CVI_BRD_pb.csv
USER ACTION: create Base.xlsx with sheets PB/OZ/SAT/SFL/MWF (each: row0 = w-col
headers w1..wN, rows below = the base numbers). Old file still works meanwhile.

1-INDEXING: data-level numbering already 1-based (w1.., and collation "Row"
col = 1..N). The grey left-margin index in previews is Streamlit's 0-based
default — pending a focused display sweep (set previews to 1-based) if wanted.

OPEN ITEMS AFTER THIS:
  - Rebuild stale files: re-run Promote+Split, rebuild W-matrix, re-collate BRD.
  - Optional: 1-based display index sweep across previews.
  - User cleaned base-data structure; re-verify B parses from Base.xlsx.

## 7m. ★★ DEFINITIVE FIX: D metadata leak solved at the SOURCE (execute_collation) ★★
The leak persisted after 7l because the real cause was in `execute_collation`
(line ~1362): `data_cols = list(df.columns[1:])` = "drop col-0, keep EVERYTHING
else". For clean B/Ep/Sp/So (col-0 = index) that's fine, but for D it kept all
metadata after col-0 (Syndicate_Name, Draw_Number, Outlet_ID, Postcode,
Share_Cost, CompanyId, Product, System_Number, Total/Available_Shares) and
to_numeric'd them into the BRD → the 1400151 / 2000 / 1571 / 1.19 leak seen in
CVI + Container Dashboards.
FIX: execute_collation now selects ONLY w1…wN (+ PB) from each component; falls
back to old behaviour only when a component has no w-columns. Hardens EVERY path
(Container Formula, dashboards, all CVIs), not one button.
ALSO (defence in depth): split_d_by_game now writes CLEAN per-game D files —
keeps only Syndicate_ID/Syndicate_Name/Game/Games + PB + w1…wN, dropping metadata
at write time. So re-running Promote+Split makes the on-disk D files clean too.
VERIFIED on real-shaped data (B clean + R clean + D w/ metadata): BRD contains
only real numbers + PB; 1400151/2000/1571/1.19 all GONE; real D picks present.

WHERE RAW D IS SAVED (user asked):
  1. Main_Data/D_<LABEL>_<STATE>.csv  — the full scrape (e.g. Main_Data/D_NSW_NSW.csv).
  2. Games/<GAME>/Variables/Variable_Elements/Direct/D_<...>_<game>.csv — per-game
     split files that the pipeline reads (e.g. Games/PB/.../Direct/D_NSW_NSW_pb.csv).
  After this fix, re-running Promote+Split rewrites (2) in clean form.

ACTION: replace masterapp.py, restart Streamlit, re-run Promote+Split (to clean
on-disk D files), then CVI build + Collate BRD → BRD now clean. No re-scrape.

## 7l. ★ FIX: BRD metadata leak (D now collates as w-only) + tab styling ★
SYMPTOM: BRD collated successfully (86,812 rows, real numbers in w1..w17) BUT
trailing columns held metadata: 4687 (Draw_Number), 1400286 (Outlet_ID), 2000
(Postcode), 7, 5, 48, 134… leaking into the w-columns.
CAUSE: the D variable used by collation was the RAW D_*.csv (39 cols: real
w-columns PLUS Syndicate_ID/Draw_Number/Outlet_ID/Postcode/Share_Cost…). Those
metadata columns were treated as numbers during collation. (Build path set
Ep/Sp/So but never set S["D"], so D stayed the raw file.)
FIX (masterapp.py):
  • Added d_to_w_only(df): reduces any D frame to clean w-columns only (returns
    as-is if already a built matrix; else rebuilds via build_w_matrix). Metadata
    can no longer reach collation.
  • CVI build now sets S["D"] = w_mat (the clean matrix).
  • Promote-to-Direct now wraps load in d_to_w_only().
  VERIFIED on real-shaped data: Outlet_ID/Postcode/Draw values gone; only w-cols
  remain.
ALSO: main nav tabs (st.radio) were hard to see — added CSS: bordered pills,
brighter bold labels, SELECTED tab highlighted amber. (User request.)
NO RE-SCRAPE NEEDED — the NSW data is real and fine; this was a load/collation
bug, not a data bug.
ACTION: replace masterapp.py, restart Streamlit, re-run CVI build + collate BRD →
BRD should now be clean real numbers with NO metadata columns.

## 7k. ★ FIX: build_w_matrix now reads D's w-columns (was n-only) ★
SYMPTOM: CVI Matrix → Build W-Matrix on Saturday D file failed with "No
n-columns found. Ensure D file has n1…nN columns." — even though Promote+Split
worked (66,144-row D_NSW_NSW_sat.csv loaded fine).
CAUSE: build_w_matrix() only detected n1…nN columns, but D (syndicate) files
correctly use w1…wN. Prefix mismatch → empty matrix → that error.
FIX (masterapp.py): build_w_matrix now detects source number columns by EITHER
prefix (^[wn]\d+$), so D's w-columns load; output is still w-columns. Error
message updated to say w1…wN (n1…nN also accepted). VERIFIED on real w-column
data: builds proper matrix; n-column files still work.
=> Re-run in app: CVI Matrix → BUILD W-MATRIX & SLICE — should now succeed and
produce real w-columns (1–45 for Saturday), then Ep/Sp/So slices, then CVI/BRD.

## 7j. ★ NSW REAL DATA FILE COMPLETE — READY FOR APP ★
Main_Data/D_NSW_NSW.csv = 86,812 unique real syndicate game-lines (deduped from
1,621,593 raw — ~18x redundancy across outlets, exactly why dedup matters).
Game spread: sat 66,144 / pb 13,924 / oz 6,744. Real picks in w1..wN (e.g.
13,29,33,36,42,43,45). Games column added (was made by older run; patched in
place via key→name map — Powerball/Oz Lotto/Saturday Lotto). has Games col: True.
NOTE: file was the OLD SEQUENTIAL run; some syndicates near pc 2630 may have been
skipped due to a transient network/WiFi dropout (errors: "nodename nor servname"
/ handshake timeout). Optional re-run on stable WiFi later; file is usable now.
NEXT (the payoff): App → Main Data → Promote All + Split by Game → CVI Matrix →
Build W-Matrix (start with Saturday, most rows) → confirm CVI_BRD shows REAL
numbers (1–45), not Syndicate_IDs/costs.
FUTURE SWEEPS: current parallel scraper already writes Games column — this manual
patch was only for the pre-existing file.

## 7i. ★ SPEED: DEDUP-FIRST + BOUNDED-PARALLEL SWEEP ADDED ★
sweep_state rewritten in two phases:
  Phase 1 (sequential, cheap): collect_syndicate_ids() = the UNIQUE set of
    syndicate IDs across all postcodes (each syndicate fetched ONCE, not per
    postcode — was the biggest waste).
  Phase 2 (parallel, bounded): ThreadPoolExecutor, MAX_WORKERS=8 default, with
    fetch_details_retry (3 tries + backoff) + small per-request pause.
Knobs at top of file: MAX_WORKERS, PER_REQ_PAUSE, RETRY_TIMES, RETRY_BACKOFF.
Usage: python3 thelott_picks_scraper.py sweep NSW       (8 workers)
       python3 thelott_picks_scraper.py sweep NSW 10    (10 workers)
VERIFIED: parallel path returns identical results to sequential on real data
(244 rows, sat/pb/oz tags, all picks in 1..47). Safe/polite by design to avoid
rate-limit/blocks (api.thelott.com is the data host; the WEBSITE is the walled one).
OPERATING MODEL (user plan, endorsed): full sweep at night (slow, thorough),
light refresh during day. cron line can automate the nightly sweep later.
NOTE (WiFi): user's Mac may be on 2.4GHz band ("WiFi-6BF0") vs 5GHz
("WiFi-6BF0-5G"). 5GHz is faster if close to router. But bandwidth is NOT the
main bottleneck — latency + per-request pacing is; dedup-first+parallel is the
real fix.

## 7h. ★ INTEGRATION VERIFIED — scraper output feeds split_d_by_game UNCHANGED ★
Live run confirmed clean game tags: Counter({'sat':5598,'pb':644,'oz':270}),
0 unknowns, dedup active ("deduped from 6513").
Scraper now also emits a **Games** column with canonical names the app's
GAME_NAME_MAP already understands (pb→"Powerball", oz→"Oz Lotto",
sat→"Saturday Lotto", mwf→"Monday & Wednesday Lotto", sfl→"Set for Life").
END-TO-END TEST against real data + the REAL split_d_by_game (unmodified):
  scraper CSV → split_d_by_game → pb:210 / oz:11 / sat:23 rows written to each
  game's Direct/ folder, each file carrying real w1..wN picks.
=> NO masterapp changes needed. Chain works:
   scrape → w-columns → split_d_by_game → Games/{GAME}/.../Direct/ →
   build_w_matrix → CVI → matching.
HOW TO USE IN APP:
  1. Run scraper to make D files:  python3 thelott_picks_scraper.py sweep NSW
     (writes Main_Data/D_NSW_NSW.csv with Games + w-columns)
  2. In app: Main Data page → Promote All + Split by Game (uses split_d_by_game)
  3. Proceed: CVI Matrix → Build W-Matrix → Container Formula → Dashboards.
REMAINING (optional polish): confirm mwf/sfl tagging when such syndicates appear;
the So-engine filter question (separate, pre-existing) still open if you want it.

## 7g. ★ LIVE RUN SUCCESS — SCRAPER NOW FEATURE-COMPLETE ★
`python3 thelott_picks_scraper.py 2000` → thousands of real game-line rows with
w1..wN. Pipeline works on live data, no browser.
ALL OPEN ITEMS RESOLVED:
  - MAPPING GAP: FIXED — NSW (company 3) also reuses low product IDs 1=sat,2=oz,
    3=pb,4=mwf,5=sfl. Added to GAME_BY_COMPANY_PRODUCT.
  - PB COLUMN: NOT a bug. powerball=0 with powerHit=true means a POWERHIT entry
    (system guarantees the PB, so no chosen number). Standard entries give PB 1-20.
    Scraper now labels Powerhit PB as "PH" for clarity; standard PBs show the number;
    non-PB games (sat/oz/etc) correctly blank/0. Verified on real data: PH + 1..20
    both present.
  - DEDUP: ADDED — _dedup() collapses identical lines by (Syndicate_ID, Draw_Number,
    Game, selections, PB). Needed because syndicates repeat across outlets/postcodes.
SCRAPER IS READY. Next: re-run a postcode to confirm NSW now tags pb/oz (no more
unknown_c3_p*), then WIRE OUTPUT IN AS D SOURCE (it emits `Game` for
split_d_by_game and w1..wN for build_w_matrix).

## 7f. ★ SCRAPER BUILT & VERIFIED (thelott_picks_scraper.py) ★
Built the fast pure-Python scraper: outlets → search → details → rows with
w1…wN + PB, game-tagged via (companyId, product) + draw-range cross-check.
VALIDATED against the real record_all_dump.json (5 captured syndicates):
  - produced 244 game-line rows; picks land in w1..wN correctly
  - game tags: 210 pb, 23 sat, 11 oz (all via company+product, 0 range conflicts)
  - 0 selections outside 1..47; Entry_Type/System/PB captured
USAGE: python3 thelott_picks_scraper.py 2000   (test one postcode)
       python3 thelott_picks_scraper.py sweep NSW / sweep ALL
WATCH on live run: PB column showed 0 on some Powerball rows — confirm PB fills
for Powerball games on a fresh fetch; adjust field if needed.
NEXT after live run verifies: wire this output in as the D source (it already
emits a `Game` column for split_d_by_game and w-columns for build_w_matrix).

## 7e. ★ CONFIRMED details RESPONSE STRUCTURE (from real capture) ★
Top-level: syndicateId, shareCost, company, syndicateName, totalShares,
availableShares, outlets, syndicateBets[], syndicatePrizes, syndicateStatus.

Each syndicateBets[] item:
  - product      : int — game ID, **only meaningful WITH companyId** (see rule below)
  - draws[]      : [{drawNumber, drawDate}]  ← the draw this bet covers
  - entries[]    : [{entryType e.g. "50 Game Standard", systemNumber, powerHit, games}]
  - games[]      : the actual lines — EACH has:
        * gameNumber
        * selections : [int,...]  ← THE PICKED NUMBERS (→ becomes w1…wN)
        * powerball  : int        ← PB number where applicable (→ PB column)
        * systemNumber, powerHit

RULE (critical): game = f(companyId, product), NOT product alone. Same product ID
is a different game in different states. Evidence from dump:
  - companyId 2 (QLD), product 3 → draws ~1568, "Powerhit/Standard"  → POWERBALL
  - companyId 1 (VIC), product 2 → draws ~1686                       → OZ LOTTO
  - companyId 6 (SA),  product 22 → draws ~4711-4713, "Weekday 3 Play", 6 sel → SAT-family
  - companyId 3 (NSW), product 1 → draws ~4687, "System" entries     → (NSW Sat-family)
Cross-check via DRAW-NUMBER RANGES (game-specific): Powerball ~1568, Oz ~1686,
Saturday-family ~4687-4713. And selection length: 6=Sat/MWF, 7=Oz/SfL/PB-main.
Use thelott_syndicate_scraper.py's PRODUCT_NAMES (already per-company) as the base map.

## 7d. ★ BREAKTHROUGH — DETAIL ENDPOINT FOUND (numbers captured) ★
`record_all.py` (visible browser) captured the real request. CONFIRMED:
```
GET https://api.thelott.com/syndicates/api/details?syndicateId={ID}&companyId={N}
  → status 200, plain api.thelott.com (NO bot wall, simple GET)
  → numbers at: syndicateBets[].games[].selections  e.g. [4,9,12,19,25,30,34,39,43,44]
```
- Works with just syndicateId (from search) + companyId (NSW/ACT=3, VIC/TAS=1, QLD=2, SA=6).
- This means a FAST PURE-PYTHON scraper is possible (search → details per syndicate
  → real picks). No browser needed for production runs.
- Output columns MUST be w1…wN (+PB) per the naming convention above.
- TODO: confirm from one full details body which field gives game/product + draw
  number per bet, so rows map to pb/oz/sat/sfl/mwf correctly.

## 7c. CHANGELOG (cont.)
- **(update — headless blocked)** Ran `recon_capture.py` (Playwright, headless,
  postcode 2000). Captured 26–28 JSON responses but ALL were analytics/tracking
  (Adobe demdex, Genesys mypurecloud, Google/YouTube, New Relic) plus Akamai-style
  bot-defense beacons at `thelott.com/zFp4fO/...`. **Zero `api.thelott.com/syndicates`
  calls** → the headless browser never loaded the syndicate list (bot challenge).
- **(update — wall is website-only; CONFIRMED from recon files)** recon_page.html
  = real page TITLE + "syndicate" x69, but "Add 1 share"/"shares available"/
  "Numbers picked" = 0 → app shell loaded, cards never rendered. Akamai Bot
  Manager present. KEY INSIGHT: the bot wall is on `www.thelott.com` (the SPA),
  NOT on `api.thelott.com` (the data host) — proven because `dump_one_syndicate.py`
  calls api.thelott.com from plain Python and works. So once we know the detail
  endpoint, a plain Python call should fetch numbers with NO browser.
  NEXT: capture the detail request from the USER'S real (unblocked) browser via
  DevTools → Network → open a syndicate → "Copy as cURL" the response that
  contains the numbers array. Then build a direct Python scraper around it.

## 7b. NEXT REQUIRED STEP (Step 0 — verification before all else)
1. Run Camoufox on ONE postcode (e.g. 2000) → save raw output.
2. Pick 2–3 rows; note their syndicate IDs.
3. Open those same syndicates on thelott.com and compare the numbers by eye.
4. If they MATCH the site → Camoufox is trustworthy → proceed to §3 Steps A–D.
   If they show a shared-tail / garbage pattern → the parser is buggy → fix the
   number-extraction in `thelott_camoufox_scraper.py` first.
