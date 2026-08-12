# R Greedy Removal (Intersection Filter) — Order-Independence Test

**Date:** 2026-08-08 · **Game:** SAT (6/45) · **Status:** read-only analysis, gate passes
**Code:** [`analysis/greedy_removal.py`](../analysis/greedy_removal.py), invariant
[`analysis/pool_invariant.py`](../analysis/pool_invariant.py).
Distinct from [greedy_cover](R_GREEDY_COVER_ORDER_INDEPENDENCE.md) (union coverage, unique 4,368) —
this is **sequential intersection**, the mechanism proposed for a 661→211→20 plateau-then-cliff.

---

## Mechanism (locked with Tai, 2026-08-08)

- Start: full **4,882,437**-combo Repeat pool (`match(D4687) ≥ 1`, D4687 = `{3,6,9,14,21,22}`).
- Each step INTERSECT: `pool = pool ∩ covered(R)`. Objective **remove-most** (shrink furthest).
- `covered(R)` = **non-D4687 overlap ≥1**: combo shares ≥1 number with `set(R) minus D4687`.
- Same 4 deterministic + 3 random tie-breaks as the cover run. Invariant checked every step.
- No preset stop — run until nothing removes anything; record size after every step.

### Why not plain match≥1
Plain "share ≥1 with R" is a **structural no-op** on the Repeat pool: **all 6,885 Repeat_R rows
contain all six D4687 numbers** (verified — `|row ∩ D4687| == 6` for every row; LOCKED "0 or 6"),
and every pool combo already shares ≥1 with D4687, so it trivially matches every row. The
discriminating signal must come from the non-D4687 numbers — hence `set(R) minus D4687`. The one
pure-D4687 row (empty discriminating set) is excluded as a non-filter (6,884/6,885 used).

**Gate:** the full 6,885×969 match matrix recomputes cell-exact vs `Match_Matrix_969` (0 mismatches);
the non-D4687 relation is derived from it. Zero invariant violations across all 42 steps.

---

## Result — identical trajectory, pure cliff, NO plateau

**Size trajectory — identical for ALL 7 variants:**

| step | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| pool | 4,882,437 | 584,066 | 57,365 | 4,340 | 225 | 6 | 0 |
| ×removed | — | ÷8.4 | ÷10.2 | ÷13.2 | ÷19.3 | ÷37.5 | →0 |

- **Geometric collapse to empty in 6 steps.** Steepest drop is **step 1** (removes 4,298,371).
  This is a **cliff from the start** — the *opposite* of plateau-then-cliff. There is **no plateau
  anywhere** (longest <1%-change run = 0 steps).
- **661 → 211 → 20 does NOT appear.** The intermediate sizes are 584,066 / 57,365 / 4,340 / 225 / 6.

### Two different order-independence answers
- **Size/shape: fully order-independent.** All 7 tie-breaks (incl. 3 random) give the *identical*
  6-step trajectory. Structural reason: remove-most always takes the smallest-|non-D4687-set| row
  (fewest discriminating numbers → most combos avoid it → largest removal); the sequence of those
  sizes is fixed, so the trajectory is fixed.
- **Row identity: NOT order-independent.** The 6 rows actually applied differ by tie-break —
  pairwise applied-set Jaccard **0.500 – 1.000** (e.g. V2≡V3 identical; V1 vs V4 share only 4/6).
  Different rows achieve the same per-step removal sizes. (Contrast the cover run, where the
  selected set was a unique 4,368.)

---

## Verdict

**The remove-most intersection filter is order-independent in trajectory shape but not in which rows
it uses — and it does not exhibit a plateau.** It collapses the Repeat pool geometrically to 0 in 6
steps (4.88M → 584k → 57k → 4,340 → 225 → 6 → 0), cliff-first.

**On 661 → 211 → 20:** this mechanism does **not** produce it — neither the numbers nor the
plateau-then-cliff shape appear under any tie-break. remove-most *maximizes* each step's drop, so it
is structurally incapable of a plateau (slow-then-fast).

---

## Remove-LEAST (gentlest filter) — 2026-08-08

Same filter (`covered(R)` = non-D4687 overlap ≥1), objective flipped to **remove-least**: each step
apply the row removing the *fewest* combos while still shrinking (max survivors with removed>0; CELF
on survivors). Rows whose covered-set already contains the whole pool (removed==0) are permanent
no-ops and discarded. Diagnostic first (gated): step-1 `removed(R)` min/med/max = 116,032 / 968,164 /
4,298,371, **0 rows at removed==0** — no stall risk.

**Result — a real staircase plateau-then-cliff, identical across all 7 variants:**

- **252 steps → pool 0**, all 7 tie-breaks (4 deterministic + 3 random) give the **single identical
  size-trajectory** (distinct trajectories = 1). Plateau (19 steps from step 37) and biggest cliff
  (−192,487 at step 127) are byte-identical across every variant.
- **Shape:** a repeating staircase — plateaus of ~9 steps recur (steps 12–21, 27–36, 62–71, 82–91,
  102–111), a 19-step plateau (37–56), a 14-step plateau (112–126) leading into the main cliff at
  step 127 (2,727,382 → 2,534,895). Later cliffs of −137,130 recur (steps 142/162/197). Endgame:
  116,928 → 87,552 → … → 20,736 → 13,824 → 6,912 → 0.
- **Invariant:** `pool_invariant.py` raised **zero** times across 252 × 7 = 1,764 steps.
- **Row-level path is strongly order-dependent:** applied-row-set Jaccard **0.125–0.385** across
  variants (even lower than remove-most's 0.500–1.000) — same size-trajectory, very different rows.

### Note on 661 / 211 / 20 (framing correction)

These were **never one chained sequence** — that was a shorthand that crept into the session, not a
real finding. Correct provenance (from the original work): **661** = Method 1 (a fixed-rule chain in
native order, *not* a search) on the **Repeat** stream; **211** = Method 1 on the **No_Repeat**
stream; **20** = Method 2 (greedy search) on the Repeat stream, later shown to be a combinatorial
artifact. They belong to different methods/streams and were never meant to compose. This thread
(greedy best-removal search, order-independence) is a different question and does not — and was never
expected to — reproduce them. For the record, this run's Repeat-pool trajectory never drops below
6,912 before hitting 0.

---

## Conclusion of this thread

**Sequential intersection of R rows against the Repeat pool is order-independent in SHAPE but
order-dependent in WHICH ROWS achieve it**, under the validated non-D4687-overlap discriminator:

| objective | steps | shape | size-trajectory across 7 tie-breaks | applied-row Jaccard |
|---|---:|---|---|---|
| remove-most | 6 | geometric cliff (no plateau) | **identical** | 0.500–1.000 |
| remove-least | 252 | staircase plateau-then-cliff | **identical** | 0.125–0.385 |

Both objectives, all 7 tie-breaks (4 deterministic + 3 random), drive the pool to 0 along a single
tie-break-invariant size-trajectory, while the specific rows used diverge (more so for remove-least).
Every step of both runs (plus the 4,368-row coverage run) passed the standing Rule-1 invariant
(`analysis/pool_invariant.py`) with zero violations. Gate: the non-D4687 relation derives from the
full match matrix, recomputed cell-exact against `Match_Matrix_969` (0 mismatches on 969 real draws).

Companion result: the **union-coverage** greedy ([R_GREEDY_COVER](R_GREEDY_COVER_ORDER_INDEPENDENCE.md))
is order-independent in *both* shape and rows — a unique 4,368-row cover (= the containment-maximal
rows ±1). Intersection-removal is the weaker form: shape is forced, row-identity is not.

---

## Addendum (2026-08-09) — Open Thread #1 "final 6" RETRACTED (unstable + degenerate)

Spec `syndicate_core/spec_final6_content_stability_check.md` asked whether the remove-most
`225 → 6` step is a real non-zero-floor production candidate or a tie-break artifact like the old
"20". Instrumented `greedy_removal.py` to snapshot the **6 surviving combos by number-content**
(`frozenset` of the combo's numbers — content identity, not load-order index; note the pool being
shrunk is COMBOS, not Repeat_R rows, so the spec's `row_id`-on-a-row phrasing was a mis-description).
Gate re-passed (0 mismatches vs `Match_Matrix_969`).

**[2a] exact set equality = FALSE — 4 distinct 6-sets across the 7 tie-breaks.** Size-trajectory is
identical (`…4340 → 225 → 6 → 0`) but combo *identity* is not; pairwise Jaccard is 1.000 within
groups / 0.000 between:

| group | variants | the six combos |
|---|---|---|
| A | V1, V3, R1 | `{1,7,15,27,41}` + one of RefGroup `{3,6,9,14,21,22}` |
| B | V2, V4 | `{1,7,15,27,38}` + one of RefGroup |
| C | R7 | `{7,15,27,38,41}` + one of RefGroup |
| D | R42 | `{1,7,15,38,41}` + one of RefGroup |

**Doubly dead:** each of the 4 sets is itself the "20"-class degenerate shadow — a fixed 5-number
anchor core + **every `C(6,1)` of RefGroup D4687**, fully enumerated (same signature as the old "20":
`{1,2,19}` + every `C(6,3)` of RefGroup). The tie-break's only freedom is which anchor core it lands
on (swapping among `1/27/38/41`); the RefGroup slot is always the full closed-form sweep. Would have
failed the step-3 artifact check even had 2a passed — confirming the asymmetry the spec warned of:
size-stability was real, meaningfulness was not.

**Verdict: retracted.** Not a real narrowing result; no early-stop rule pursued. Reusable
degenerate-structure detector added (`artifact_check`/`report_final6` in `greedy_removal.py`) — none
existed before; the "20" conclusion had lived only as prose. Snapshot: `greedy_removal_final6_snapshot.csv`.
Next: Open Thread #3 (Direction A / B1 diagnostic).
