# R Classification Verification — Spread Tiers + Shallow Anchor

**Date:** 2026-08-07 · **Game:** SAT (6/45) · **Status:** read-only analysis, gates pass
**Code:** [`analysis/r_spread_shallow.py`](../analysis/r_spread_shallow.py) (`python3 -m analysis.r_spread_shallow`)
**Rules under test:** LOCKED Rule Set 3 (Spread) and Rule Set 4 (Shallow Anchor) — `Sika_R_Rules_LOCKED.md`.

---

## Why this exists

Neither classifier existed on disk as runnable code that derives a result from a
draw's six numbers:

- **Spread / Constituent_Groups** — only ever *read* as a persisted column
  (`info/regenerate_r_sheet1.py:198`, `true_spread = len(groups)`); the producer
  `syndicate_core/generators.py:252` (`generate_rainbow`) defines it as the SL
  groups combined to *construct* an R powerset row, never as a lookup on six
  arbitrary numbers.
- **Shallow Anchor (Rule 4)** — only a pass-through **stub**
  (`syndicate_core/escalation.py:64`) and a **frozen-D4687-list** variant
  (`info/regenerate_r_sheet1.py:202`) that the LOCKED doc says produces
  out-of-era false failures on historical draws.

Both were therefore **reconstructed** here, using only the real primitives
`since_last_map` / `block_layout` in `syndicate_core/stacked_blocks.py`
(`:47`, `:67`). Reconstructed status is flagged throughout.

**Dataset (found on disk):** `Games/SAT/Variable_inputs_sat/Base_sat/B1_sat_updated.csv`
— 970 draws, newest-first `w1`..`w970` (**not** `draw_history.csv`, which has only 150).
**R rows (found):** `info/R_corrected_D4687_v2.xlsx` (persisted `True_Spread`).

---

## Validation gates (all must pass before any tabulation)

| Gate | Check | Result |
|---|---|---|
| **A** | Own-era shallow list as-of D4687 == the doc's 25-number list | ✅ exact |
| **B** | Own-era shallow anchor over 969 evaluable draws == 963 pass / 6 fail, and the 6 failures == `w115, w308, w362, w514, w733, w811` | ✅ exact |
| **C** | Spread-counting mechanism (fixed-D4687 mode) reproduces persisted `True_Spread` on all 20,292 R rows | ✅ 0 mismatch |
| **D** | Step-3 baseline DP brute-forced on synthetic eras + sums to C(45,6) on the real D4687 era | ✅ exact |

Gate C is a **mechanism check only** (fixed-D4687). It is expected — and correct —
that switching to own-era mode changes results for draws; that is not a failure.

---

## Step 2 — own-era spread tiers, full history

969 evaluable draws (oldest `w970` has no predecessor era, excluded).

| tier | wins | win share |
|---:|---:|---:|
| 1 | 1 | 0.10% |
| 2 | 0 | 0.00% |
| 3 | 22 | 2.27% |
| 4 | 158 | 16.31% |
| 5 | 436 | 44.99% |
| 6 | 352 | 36.33% |

**Tier-1/2 exceptions (reported explicitly):** one tier-1 draw, `w969` =
`[3,15,24,35,41,42]`; zero tier-2 draws.

### ⚠️ w969 caveat — thin-history artifact, not a real spread-1 draw

`w969` is the second-oldest draw, so its own-era reference is a **single**
predecessor (`w970`). With one predecessor the SL map has only two groups —
`w970`'s six numbers (SL0) and all 39 others collapsed into the "unseen"
sentinel. `w969` shares nothing with `w970`, so all six of its numbers fall in
the sentinel group → spread 1 **by construction**. This is a degenerate
edge-of-history artifact. With adequate own-era history, spread 1–2 does not
occur, which **confirms** Rule 3's "draws span 3–6, never 1–2" structural claim.

---

## Step 3 — enrichment ratio (win share ÷ combinatorial-space share)

Baseline per tier is computed per era from that era's SL-group sizes (exact DP,
gate D) and averaged over the same 969 eras the wins are scored against.

| tier | win share | combo-space share | **enrichment** |
|---:|---:|---:|---:|
| 1 | 0.10% | 0.07% | 1.51 *(n=1, the w969 artifact)* |
| 2 | 0.00% | 0.27% | **0.00** |
| 3 | 2.27% | 2.05% | 1.11 |
| 4 | 16.31% | 16.40% | **0.99** |
| 5 | 44.99% | 45.40% | **0.99** |
| 6 | 36.33% | 35.81% | **1.01** |

**Headline finding.** Tiers 4/5/6 sit at enrichment **0.99 / 0.99 / 1.01** —
dead neutral. Wins land in spread 4–6 ≈97% of the time **only because ≈97% of
the combinatorial space is spread 4–6** (size effect), not because spread 4–6 is
special. The **"Spread 4–6 = Solid" label is numerically hollow as a
discriminator.** The one genuine structural signal is the **depletion of
spread ≤2** (tier 2 enrichment 0.00: ≈2.6 wins expected if neutral, 0 observed) —
but spread ≤2 is only ≈0.34% of the space, so it removes very little.

---

## Step 4 — R-row cross-tab: spread tier × shallow-anchor status

From persisted `True_Spread` (found, not reconstructed) across the
`R_corrected_D4687_v2.xlsx` sheets.

| R rows | spread 1-2 | spread 3 | spread 4-6 |
|---|---:|---:|---:|
| Shallow-held (1,485) | 66 (4.44%) | 165 (11.11%) | 1,254 (84.44%) |
| Active Repeat (6,885) | 17 (0.25%) | 120 (1.74%) | 6,748 (98.01%) |
| Active No_Repeat (13,407) | 70 (0.52%) | 395 (2.95%) | 12,942 (96.53%) |

**Are "remove shallow anchor" and "remove spread 1-2" redundant? No.** Shallow-held
rows are ~10× more concentrated in spread 1-2 (4.44% vs ~0.4%) and ~4× in spread 3,
so the filters correlate — but **84% of what shallow anchor removes is spread
4-6**, which a spread-1-2 filter would never touch. A "remove spread 1-2" rule
catches only 66 of the 1,485 shallow-held rows (4.4% overlap). The two are
**complements, not substitutes** — you need both.

---

## Note on the Step-3 DP baseline ("ungated")

Unlike the spread mechanism and shallow anchor (gates A–C anchor them to known
ground-truth values), the combinatorial baseline has **no external ground truth
to validate against** — it is a derived quantity. It is therefore checked only
by (1) exact brute-force agreement on small synthetic eras and (2) summing to
C(45,6) on the real D4687 era (both in gate D). Treat the enrichment ratios as
resting on that internal validation, not on an external anchor.

## Reconstruction flags (summary)

| Number | Source | Status |
|---|---|---|
| History (970 draws) | `B1_sat_updated.csv` | found |
| `since_last_map`, `block_layout` | `stacked_blocks.py:47,67` | found (primitives) |
| Spread-from-6-numbers, own-era shallow list | built on those primitives | **reconstructed**, gated (A/B/C) |
| R-row spread tiers (Step 4) | persisted `True_Spread` in `R_corrected_D4687_v2.xlsx` | found |
| Combinatorial baseline (Step 3) | exact DP over per-era group sizes | **computed**, brute-force checked (D), no external anchor |
