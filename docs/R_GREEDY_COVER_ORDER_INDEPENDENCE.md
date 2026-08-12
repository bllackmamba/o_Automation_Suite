# R Greedy Set-Cover — Order-Independence Test

**Date:** 2026-08-08 · **Game:** SAT (6/45) · **Status:** read-only analysis, all gates pass
**Code:** [`analysis/greedy_cover.py`](../analysis/greedy_cover.py), invariant
[`analysis/pool_invariant.py`](../analysis/pool_invariant.py).
**RefGroup:** D4687 `{3,6,9,14,21,22}` (LOCKED reference draw).

---

## Definitions (locked with Tai, 2026-08-08)

- **Universe** = the **4,882,437** Main Data 6-combos with `match_count(combo, D4687) >= 1`
  (Rule Set 1 Repeat pool). NOT the 969 real draws — those are points *inside* this space.
- **Candidates** = the **6,885 Repeat_R** rows (each a 6–27-number set).
- **Coverage** = **containment**: R row `R` covers combo `e` iff `e ⊆ set(R)` (i.e. `match_count(R,e)==6`).
- **Greedy** = best-marginal-gain: each step, over ALL remaining rows, pick the row adding the most
  new coverage; break ties by a per-variant order.

## Validation gate (passed before any sweep)

Recomputed the full **6,885 × 969** Repeat match matrix from raw numbers and compared to the persisted
`Match_Matrix_969.xlsx`: **0 mismatches across 6,671,565 cells**; containment (`match==6`) agreed with
stored `==6` on every cell. Mapping: matrix `W1..W969` = B1 `w2..w970` (drops newest draw `w1`).
So the containment rule reproduces real match counts on all 969 real draws.

## Standing invariant (Step 1)

`analysis/pool_invariant.py` — LOCKED Rule Set 1, called after **every** selection step of **every**
variant (Repeat: every covered combo shares ≥1 with D4687; No_Repeat: exactly 0). Hard-raises on the
first offender naming step + row. **Zero violations** across all variants (4,368 steps × 8 runs).
Independently reconfirmed globally: the covered union equals U **exactly** (4,882,437, not more) — no
covered combo ever fell outside the Repeat pool.

---

## Result — the cover is UNIQUE and order-independent

| variant | survivors (full cover) | identical set? |
|---|---:|---|
| V1 generate_rainbow order | 4,368 | — |
| V2 generate_rainbow reversed | 4,368 | Jaccard 1.000 vs V1 |
| V3 Row_Length asc, then w | 4,368 | Jaccard 1.000 |
| V4 numbers-lexicographic | 4,368 | Jaccard 1.000 |
| random tie-break seeds 1 / 7 / 42 | 4,368 each | identical to V1 |

All 6 pairwise Jaccard overlaps = **1.000** (the selected sets are literally the same rows).
Rows-to-reach coverage milestones (nearly identical, ±≤4 at intermediate, identical at endpoints):

| milestone | 50% | 90% | 95% | 99% | 100% |
|---|---:|---:|---:|---:|---:|
| rows | 92 | ~1,433 | ~2,150 | ~3,404 | 4,368 |

### Why it is unique (proof, not coincidence)

- **1,770,228** universe combos are covered by **exactly one** Repeat_R row.
- The rows that are the *sole* coverer of ≥1 combo (**essential rows**) number **exactly 4,368**.
- Those 4,368 essential rows **alone cover 100%** of U.
- Therefore every exact cover must contain all 4,368, and they suffice → the minimal cover is **unique**.
  The greedy's selected set **== the essential set** (verified). Tie-break has no freedom to exercise;
  the remaining 2,517 rows are fully redundant (each contained within an essential row's coverage).

**Union of all Repeat_R 6-subsets = U exactly (100.0000%)** — Repeat_R tiles the entire Repeat pool.

---

## Verdict

**STABLE — "true wall" confirmed.** Full Repeat-pool coverage requires a **unique** set of **4,368**
Repeat_R rows, invariant to every tie-break tried (4 deterministic + 3 random). This is a hard
structural fact, not a tie-break artifact.

**On the 661 / 211 / 20-style numbers:** the best-marginal-gain *full cover* is **4,368**, so those small
counts were **not** full-Repeat-pool cover sizes. They came from a different computation — a partial
coverage threshold, a different universe (e.g. covering only the 969 real draws), or the retired
first-fit algorithm — not from this stable wall. Whatever they measured, it was not "minimal rows to
cover the 4.88M Repeat pool," which is single-valued at 4,368.
