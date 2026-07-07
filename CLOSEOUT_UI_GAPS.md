# Close-out: Remaining CONSOLIDATED_UI_SPEC.md gaps
# Found via direct review of the running app — these are confirmed still
# outstanding, not assumptions. Fix all of them in this pass, then stop —
# no more incremental check-ins on this spec after this.

## 1. Remove Row-by-Row Summary table entirely
Still present below the Matching Table (pagination, "Download Row Summary
CSV" / "Download Row Summary Excel" buttons and all). Delete the whole
section. The Matching Table's own column chevrons already supersede it.

## 2. Remove Inspect-a-Row panel entirely
Still present: the "Select row to inspect" dropdown, the "w1 numbers (32):
[...]" expandable list, the "Count distribution (present rows)" table, the
"Main Data Breakdown" sub-panel, the "Selected S:0" / "Unselected → fwd"
sub-panels, and the "Final Stage Output" tabs (Selected (final) /
Unselected (final) / Breakdown S0/S1/S2... (all stages)). Delete the whole
panel — every one of these is now reachable via the Matching Table's own
per-row chevrons instead.

## 3. Add chevron to the Dir column
Currently plain text (`U`), no dropdown, unlike every other column in the
Matching Table. Add the same chevron/expander pattern used elsewhere in
this table. Reveal: what pool carries forward under U vs S for this row,
plus the toggle control itself (this chevron IS the toggle, not just a
display — clicking U vs S here should change the row's direction).

## 4. SC panel: move the per-column grid behind a chevron
The raw grid (`w1=0,1,2,3,4,5 | w2=... `) is currently shown TWICE,
permanently — once directly under the "Selected Counts loaded from
SC_*.csv" banner, and again next to the Method buttons as "Per-column SC
(from file): ...". Move both instances behind a single chevron (or
consolidate into one chevron if they're duplicating the same data — check
whether they're actually redundant while you're in there).

## 5. SC panel: un-collapse the Upload/Replace SC file section
This currently sits behind a chevron ("› Upload / Replace Selected Count
file") — that's backwards. Per spec this section (the upload control +
"File must have columns: w, Selected Count" hint) must stay permanently
visible, same as the Method buttons beside it. Remove the chevron wrapping
it; leave the SC-grid chevron from item 4 as the only thing collapsed in
this area.

## 6. Remove "Apply to all" button and the Row/Direction override table
The full "Carry-forward direction" table (Row 1 · w1 ... through Row 27)
plus its "Apply to all" button are still present. Remove both. Keep ONLY
the "Default direction: U — Unselected" dropdown — this is the single
pre-run default used by Auto mode, per Part B. Manual mode direction is
handled entirely through the Dir chevron (item 3) now.

## 7. Fix: Excel export crash on "Breakdown (all stages)"
Reproducible now: selecting the "Breakdown S0/S1/S2... (all stages)" tab
(or downloading it) throws:
  ValueError: Row numbers must be between 1 and 1048576. Row number
  supplied was 1048577
Traceback: masterapp.py:6261 `to_styled_excel(unsel, final_cvi_set, n_u,
"Unselected")` → masterapp.py:784 `to_styled_excel` → openpyxl
worksheet.py `_get_cell`.
Root cause: `to_styled_excel` writes the full Unselected set (8,145,059
rows here) into an Excel sheet with no row-count guard, and openpyxl hard-
caps at 1,048,576 rows/sheet.
Fix: add a size guard BEFORE attempting the write, matching the pattern
already used elsewhere in this codebase (the "U:8145059 — not stored
(M>500,000)" tooltip shows this convention already exists) — if row count
exceeds Excel's limit (or your existing M>500,000 threshold, whichever is
the real established convention here — check the existing guard's exact
threshold and reuse it, don't invent a new one), show the same kind of
graceful message instead of attempting the write and crashing.
If this panel gets removed anyway as part of item 2 (Inspect-a-Row
removal), confirm whether this export lives ONLY inside that panel — if
so, item 2's removal fixes this by deletion, and this item becomes moot.
Check before doing both.

## 8. Check for a duplicate SC-preview mislabel
The "Preview — Loaded Data" panel shows "✅ SC — 20 w-columns" — same class
of bug fixed in Part A2 for a different label (that one was "181
w-columns" → should read "rows", not "w-columns"). Confirm whether this
instance was covered by the A2 fix already, or whether it's a second,
separate spot using the same wrong label — fix if separate.

---

## Report format
For each item 1–8: confirm done, or report what you found if it turned
out to be more involved than expected (e.g. item 4's grid being genuinely
duplicated data vs. two different things that look similar).

Run full suite + py_compile after all changes. Commit as one batch (or a
few logically-grouped commits, your call) — this is a close-out pass, not
exploratory work.
