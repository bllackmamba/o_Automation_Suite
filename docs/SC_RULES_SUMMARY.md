# Selected Count (SC) — Rules, Do's and Don'ts
Sika Automation Suite — compiled from design discussion, 2026-07-02/03

---

## 1. Architecture — storage vs. application

**Rule (yours):** SC storage is decentralized — each variable (B, R, D, Ep, So,
Sp) has its own SC file (`SC_{VAR}_{gk}.csv`) using positions relative to that
variable's own w-rows.

**Rule (yours):** The CVI fed into the matching engine is a single, continuous,
absolute-position entity (w1...wN) — the engine has no concept of "this
position belongs to variable X." SC values must be correctly translated
("stitched") from each variable's relative positions into the CVI's absolute
positions before matching runs.

**Don't:** Treat per-variable SC and absolute-CVI SC as interchangeable
without stitching. If the mapping is wrong, "otherwise purpose will be
defeated" — SC will silently apply to the wrong w-row.

---

## 2. What determines SC for a given w-row

**Rule (yours — "hit the nail on the head"):** Three factors determine the
right SC for any w-row:
1. **Type of game** — pool size (45/47/44/35) sets the ceiling on possible
   match values.
2. **Nature of the numbers** in that w-row — spread vs. clustering shapes
   where the natural distribution breakpoints fall.
3. **Length of the w-row** — how many numbers are in it caps the maximum
   possible match count (min(row length, pick size)).

**Don't:** Pick an SC threshold (preset, top-N, or otherwise) without
grounding it in these three factors. A threshold that ignores row length or
game pool size is arbitrary.

---

## 3. Computation basis — Unselected, not Selected

**Rule (confirmed — "that is how I designed the system"):** When deciding
where to set SC at any stage, use the **Unselected** pool's distribution as
the basis, not the Selected pool.

**Why:** Unselected = the unconsidered population still awaiting
classification — the true signal for where the next threshold should sit.
Selected = already-claimed by a prior SC decision; using it as the basis for
a new SC is a deliberate recursive research act, not the default behavior.

**Don't:** Default to computing SC thresholds off the Selected pool. That's a
manual override case (like the w5→w6 switch test), not the standard path.

---

## 4. SC and carry-forward Direction (U/S) — stay decoupled

**Rule (yours — "stay completely manual and independent"):** SC threshold
selection and carry-forward direction (U/S) are two separate manual
decisions made by the researcher.

**Don't:** Auto-suggest or auto-enforce a direction switch based on SC
outcomes (e.g., auto-flipping to S when SC produces Unselected:0). Even
though that pattern is mechanically useful (as seen in the w5/w6 test), the
system must never make that call on its own.

---

## 5. No wild assumptions — follow the engine logic as written

**Rule (yours, stated twice, worth repeating verbatim):** "the code is not
supposed to make wild assumptions other than what is spelt out in the engine
matching logic" and "if there are things you do not understand, let me know
— no wild assumptions."

**Applied to saturation:** If a w-row's CVI is 95–100% match rate against
main data, that is the correct, intended behavior of the engine as designed
— not something to silently "fix" or route around. The engine does what the
matching logic says; it doesn't second-guess based on filtering
effectiveness.

**Don't (self-correction from this session):** Don't declare a wide/
saturated w-row "just real data, not a defect" without first checking which
variable(s) it actually traces back to. I did this once with w4 ("all 45
numbers") and you were right to push back — the honest move is to verify via
Source breakdown before concluding anything, not to assume.

---

## 6. Every variable, independently — not just whichever formula is handy

**Rule (yours — "I requested for all six not three"):** SC analysis and rule-
setting must cover all six variables (B, R, D, Ep, So, Sp) independently,
using each variable's own raw file. Analyzing only the variables that happen
to appear in one formula (e.g., BRD) is incomplete — Ep, So, Sp need the same
treatment from their own source files.

**Don't:** Infer a variable's nature from a combined formula's pooled output.
`execute_collation` stacks variables as rows under shared w-headers with no
positional exclusivity — a formula's w4 can contain values from every
variable that happened to have a row that wide. The only way to know which
variable is actually responsible for a given number is to check each
variable's own file directly, or split a combined CVI by its `Source` column.

---

## 7. Language — w-row, not w-column

**Rule (yours):** The conceptual unit is a "w-row" — a row of numbers. Pandas
stores CVI positions as DataFrame columns, but that's implementation detail,
not the vocabulary. "SC having the same number as CVI w's will be per row as
well" — SC entries correspond 1-to-1 with CVI w-rows.

**Applied:** `_parse_cvi_col` renamed to `_parse_cvi_row`; docstrings and
comments fixed throughout matching.py. Internal variable `w_cols` was left
unchanged (implementation detail, not user-facing language).

**Don't:** Refer to a w-position as a "column" in any explanation, docstring,
or discussion, even though pandas storage makes it one.

---

## 8. Data integrity — orientation must be verified, not assumed

**Rule (from your scaling concern):** As CVI files grow (23,357 rows today,
possibly 40,000+ later), a transposed CVI (w-positions as pandas rows instead
of columns) must never silently produce wrong matching output.

**Applied:** `_assert_cvi_orientation()` raises immediately if a CVI looks
transposed, called at the top of every engine entry point
(`_prepare_matching_state`, `run_matching`, `run_matching_step`).

**Don't:** Trust CVI shape without checking it, especially as file sizes
scale up and manual eyeballing becomes impractical.

---

## 9. Output granularity — match what's actually asked

**Rule (yours, stated twice — "not the breakdown you talking about" / "do
not need the 8.1 million details"):** When you ask for CVI numbers and match
counts, that means the qualitative distinct count values and the actual
numbers in that w-row — not a full S0:/S1:/S2: frequency breakdown with
percentages unless you specifically ask for that level of detail.

**Don't:** Default to the heaviest, most detailed output format. Build the
simple version first; only add frequency breakdowns and percentages when
explicitly requested.

---

## 10. Automation goal — must survive scale changes

**Rule (yours):** "the last time it was 23,357 row CVI, next time it might
be 40,000 row CVI — how do we automate the process so it can work with
little or no human intervention?"

**Implication:** Whatever SC-setting rule gets built from items 2–3 above
(game type + row length + number nature, evaluated against the Unselected
pool) must be expressed as a repeatable rule, not a one-time manual read of a
single CVI's distribution. The rule should hold regardless of whether the
CVI has 23,357 rows or 230,000.

**Status:** This is the one item on this list still genuinely open — the
exact functional form of the automated threshold rule (how items 2–3
translate into a specific SC value per w-row without a human looking at each
distribution) hasn't been designed yet. Everything else above is confirmed
and settled; this is the piece still to build.

---

## Quick-reference table

| # | Rule | Status |
|---|------|--------|
| 1 | CVI is flat/absolute; SC is per-variable and must be stitched to match | Confirmed design |
| 2 | Game type + number nature + row length determine SC | Confirmed design |
| 3 | Use Unselected pool as the basis for SC decisions, not Selected | Confirmed design |
| 4 | SC and Direction (U/S) stay manual and independent | Confirmed design |
| 5 | No wild assumptions — follow engine logic as written; verify before calling something "expected" | Confirmed principle |
| 6 | Analyze all six variables independently, not just one formula's subset | Confirmed requirement |
| 7 | Say "w-row," never "w-column" | Confirmed language |
| 8 | CVI orientation must be guarded, not assumed | Implemented (`_assert_cvi_orientation`) |
| 9 | Match output detail to what's asked — simple by default | Confirmed preference |
| 10 | SC threshold rule must scale automatically with CVI size | **Open — not yet designed** |
