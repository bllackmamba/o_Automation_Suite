# Consolidated UI + Bugfix Spec — Matching Engine, SC Panel, Container Dashboards
# Sika Automation Suite

## Purpose
This consolidates several decisions made across a design discussion (not yet
built). Covers: chevron-based detail disclosure across three panels, removal
of redundant panels, splitting run-Mode from SC-availability, two real bugs,
an investigation task (Active checkbox), and a terminology correction
(w_row, not w-column/w-position, in all NEW UI text — do not touch existing
code identifiers like `_parse_cvi_row`, `w1`/`w2` column names, or docstrings
that already use correct internal language).

Read this whole spec before starting — several items touch the same files
and should land in one coherent pass, not six separate half-finished edits.

---

## STEP 0 — Baseline check

```bash
cd /Users/mamba/Desktop/Sika/o_Automation_Suite
git status
git log --oneline -5
```

Confirm tree is clean before starting. If not, report what's uncommitted
before touching anything.

---

## PART A — Two bugs (fix first, before UI changes — they affect what the
## chevron UI will even be showing)

### A1. Main Data false-negative banner

**Symptom:** Container Dashboards page shows "No Main Data files found in
Main_Data/. Expected pattern: {cluster}_Sat_D{draw_no}.csv" at the top of
the page, while the "Preview — Loaded Data" panel further down the SAME
page simultaneously shows "✅ Main Data — 8,145,059 rows × 6 cols" as
successfully loaded.

**Task:** Find both code paths — the one producing the warning banner and
the one producing the green confirmation — in `masterapp.py`. They are
almost certainly two different file-scan/glob calls with different
filename-pattern assumptions. Root-cause it:
- Read what pattern the warning-banner scanner expects
  (`{cluster}_Sat_D{draw_no}.csv` per the banner text).
- Read what pattern the "Preview — Loaded Data" scanner actually matched
  to find 8,145,059 rows.
- Fix the WARNING scanner to match reality (or unify both to call the
  same underlying scan function) so the banner only appears when Main
  Data genuinely isn't found — it must still work correctly the next time
  a game truly has no Main Data loaded. Do not just delete the banner.

### A2. CVI table Formula/Date columns blank

**Symptom:** "CVI files found for Sat: 6" table shows real filenames
(`CVI_BRD.csv`, `CVI_BRDEpSoSp.csv`, etc.) in the File column, but Formula
and Date columns are blank for every row.

**Task:** Find the function that scans CVI files and populates this table
(likely `scan_cvi_files()` — check masterapp.py). It almost certainly
parses Formula/Date out of the filename with a regex that no longer
matches the actual naming convention CVI files are saved under. Compare
the regex against real filenames (`CVI_BRD.csv` has no embedded date —
check whether Date is expected to come from file mtime instead, or from a
different naming scheme that was changed at some point without updating
this parser). Fix the parser to populate both columns correctly. Report
what the actual bug was (wrong regex / wrong field source / filename
convention drift) before committing.

Run both fixes past `tests/` — add a regression test for each so they
don't silently regress.

---

## PART B — Split run-Mode from SC-availability

**Current state:** One toggle — `SC: YES (Auto)` / `SC: NO (Manual)` —
conflates two independent things: how the engine paces through stages
(Auto = runs straight through; Manual = pauses at each stage for input),
and whether an SC file is actually loaded for this formula.

**New state:** Two independent controls.

1. **Pace:** `Auto` / `Manual` (radio or toggle, same visual style as
   current)
2. **SC source:** `Loaded from file` / `None (counts only)` — this should
   auto-detect (does `SC_{formula}_{game}.csv` exist? show "Loaded from
   file" and disable manual override) but allow explicit override to
   `None` even if a file exists, for cases like the one that prompted
   this fix — user deliberately wants counts-only output regardless of
   whether an SC file exists.

**Combination behavior:**
- **Auto + SC loaded:** current Auto behavior, using SC file thresholds.
- **Auto + None:** run straight through, every stage. Output = Main Count
  / Main Breakdown only, at every w_row. No Selected/Unselected columns
  populate (or they populate as "—" / not-applicable) since no selection
  criterion exists. This was confirmed as the intended behavior for this
  case — do not fabricate a fallback SC.
- **Manual + SC loaded:** pause at each stage; SC file's threshold for
  that stage pre-fills as a suggested selection the user can accept or
  override before Continue.
- **Manual + None:** pause at each stage; show Main Count/Breakdown for
  that stage; user picks SC values live (current Manual behavior when no
  file exists — this already works, just needs to be reachable
  independent of Auto/Manual as separate axes).

Locate where the current single toggle drives engine behavior (likely
in the Container Dashboard's matching-engine section of masterapp.py,
feeding into `run_matching` / `run_matching_step` in `matching.py`) and
refactor to two independent state variables. Confirm `run_matching_step`
in matching.py already supports "no SC provided" per-stage (check
existing `sc_for_stage=None` handling) before assuming new engine logic
is needed — this may be purely a UI/wiring change with no engine changes
required.

---

## PART C — Chevron-based detail disclosure

Apply the same interaction pattern across three panels: a chevron/expand
icon next to any condensed or truncated value; clicking it reveals full
detail inline (expander or popover — match whatever pattern
`st.expander` or similar already used elsewhere in the codebase for
consistency). No permanent always-visible detail panels for these
values.

### C1. Matching Table (the core engine table)

Columns get chevrons (condensed → full detail on click):

| Column | Chevron reveals |
|---|---|
| CVI | Full number list at that w_row (replaces old Inspect-a-Row "w_row numbers" display) |
| Dir | Current direction (U/S) + what pool carries forward under each option + inline toggle control (this IS the toggle, not just a display) |
| Main Count | Full count distribution (replaces old Inspect-a-Row "Count distribution" table) |
| Main Breakdown | Full untruncated breakdown string |
| Present Data | Which main-data rows are still present at this stage |
| Present Count | Distribution of present-count values |
| SC | Full detail on selected count-values for this stage |
| Selected | Full list/breakdown of selected rows |
| Sel Breakdown | Full untruncated breakdown string |
| Unsel Count | Distribution |
| Unselected | Full list |
| Unsel Breakdown | Full untruncated breakdown string |

`Row` and `Main Data` columns stay plain — nothing condensed to reveal.

**Remove entirely** (superseded by inline chevrons above):
- "Row-by-Row Summary" table
- "Inspect a Row" panel (row selector + separate w_row-numbers/count-
  distribution display)

These were added without being requested; the chevron pattern replaces
their function inline, in the same table, without a second panel or
selector.

### C2. Selected Count (SC) input panel

Keep visible, unchanged:
- "✅ Selected Counts loaded from SC_*.csv" status line
- "📂 Upload / Replace Selected Count file" section (upload control +
  "File must have columns: w, Selected Count" hint)
- Method selector: Custom / Same for all / Range

Move behind chevron (remove as permanent display):
- The large per-column SC grid (`w1=nan | w2=nan | ...`)
- The "Carry-forward direction" panel's row-by-row override table AND
  the "Apply to all" button — **except** keep a single "Default
  direction: U — Unselected" dropdown visible, used only as the
  pre-run default for **Auto mode** (Manual mode sets direction live via
  the Dir chevron in Part C1, so needs no separate panel).
- "Fallback Count (used if no SC file loaded)" — reconsider given Part B:
  if Auto + None now means "counts only, no fallback," this field may
  become unnecessary. Confirm against Part B behavior before deciding
  whether to keep, move behind chevron, or remove. Flag your decision in
  the report rather than silently picking one.

### C3. Container Dashboards page — CVI file list

"CVI files found for Sat: 6" table (Formula / Date / File columns) —
move behind a chevron, no permanent display. Fix the blank Formula/Date
columns first (Part A2) so what's behind the chevron is actually correct
when revealed.

**Remove:** the "Individual dashboard (open one at a time)" button list
(the ~20 buttons like "1n & ALL... Container Dashboard"). This
duplicates the "Open Dashboard:" dropdown + button immediately below it.
Keep only the dropdown + single open button.

---

## PART D — Active checkbox investigation (Container Formula screen)

**Symptom reported by user:** every formula row's "Active" checkbox
shows checked; unchecking one causes it to revert to checked; no visible
effect on anything when toggled either way.

**Task — investigate before designing anything on top of it:**
1. Find where "Active" is rendered (the Container Formula / formulas
   table in masterapp.py) and what session-state key or dataframe column
   backs it.
2. Determine: is it wired to anything downstream (e.g. filtering which
   formulas appear as quick-pick buttons, or which are eligible for
   collation), or is it currently a dead/inert control?
3. Determine why unchecking reverts — likely the widget is being
   re-instantiated from a source-of-truth that always says True on every
   rerun (common Streamlit bug: checkbox `value=` pulled fresh from a
   DataFrame each render instead of from `st.session_state`).
4. **Report findings. Do not fix or repurpose it yet** — this needs a
   design decision (is Active meant to gate "collate this formula" for
   the future multi-select-and-collate feature, or something else
   entirely) before further work. This step is diagnostic only.

---

## PART E — Terminology pass

In any NEW code/UI text touched by Parts A–D, use "w_row" (not
"w-column", "w-position") when referring to a CVI stage/position in
user-facing labels, docstrings you're newly writing, or comments you're
newly writing. Do NOT rename existing correct internal identifiers
(`_parse_cvi_row`, `w1`/`w2`/... column names, existing docstrings that
already reflect the July 2 CVI-language fix) — this is additive
consistency for new work, not a renaming pass over old code.

---

## Sequencing

Do Part A (bugs) first — Part C's chevrons will display whatever Part A
fixes, so fixing the data before rebuilding the display avoids showing
correct-looking chevrons over still-broken data.

Then Part B (mode/SC split) — Part C's Dir chevron and SC column chevron
both depend on knowing which mode is active.

Then Part C (chevron rollout + panel removals).

Then Part D (investigate only, no build).

Part E is not a separate step — apply it inline as you touch each file.

---

## Tests + validation

- Add regression tests for A1 and A2 (assert the scanner functions
  return correct Formula/Date for real filenames; assert banner logic
  agrees with the Preview panel's data source).
- For Part B, add a test matrix covering all 4 mode×SC combinations
  against `run_matching_step`, confirming Auto+None produces
  Main Count/Breakdown with no Selected/Unselected population.
- Run full suite: `pytest tests/ -q` — report pass count before and
  after.
- `python3 -m py_compile syndicate_core/matching.py masterapp.py
  syndicate_core/collation.py`

## Commit strategy

Separate commits per part (A1, A2, B, C, D-investigation-only, if D
produces no code change it doesn't need a commit — just report
findings). Do not squash into one giant commit — these are logically
distinct changes and you (Tai) will want to review/revert independently
if any one part needs rework.

---

## Report format

```
STEP 0 — baseline: clean / <uncommitted items>

PART A1 — Main Data banner
  Root cause: <finding>
  Fix: <what changed>
  Regression test: added, passing

PART A2 — Formula/Date blank columns
  Root cause: <finding>
  Fix: <what changed>
  Regression test: added, passing

PART B — Mode/SC split
  New state variables: <names>
  4-combination test matrix: <pass/fail per combo>
  Fallback Count field decision: kept / chevron / removed — <reasoning>

PART C — Chevron rollout
  C1 (Matching Table): <N> columns converted, Inspect-a-Row + Row-by-Row
    Summary removed
  C2 (SC panel): grid + direction table behind chevron, default-direction
    dropdown kept
  C3 (Container Dashboards): CVI table behind chevron, individual
    dashboard button list removed

PART D — Active checkbox
  Backing source: <finding>
  Currently wired to: <finding or "nothing">
  Revert-on-uncheck cause: <finding>
  Recommendation: <if any> — NO CODE CHANGE MADE, awaiting design decision

Tests: <N>/<N> passing (was <N>/<N> before)
py_compile: OK
Commits: <hash A1>, <hash A2>, <hash B>, <hash C>
```
