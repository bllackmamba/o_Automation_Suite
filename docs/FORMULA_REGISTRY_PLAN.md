# Container Formula Registry — 4-Group Restructure (PLAN)

**Status:** Plan approved for build — no implementation code written yet.
**Scope this pass:** `sat` only. `oz`/`sfl` (DuckDB) deferred.
**Start in Claude Code:** `refgroup.main_data_stream` → `main_split.py` → `escalation.py` stubs → `config.FORMULA_GROUPS` → `collation._run_formula_groups` → masterapp UI.
**Models on:** the Decentralized SC feature (`docs/SC_DECENTRALIZED_SPEC.md`) — same formula-agnostic, skip-and-log, no-hardcoded-names discipline.

---

## Problem being restructured

Today 17 hardcoded container formulas (`CF_ROWS` in `config.py`) each match candidate rows
against **one undivided** ~8.1M-row Main Data pool via `execute_collation` → `_match_cvi_rows`.

This restructures that into **4 formula groups**, each matched against a Main Data pool that is
itself **split into Repeat / No_Repeat streams** (Rule 1, per RefGroup). The split is recomputed
every time RefGroup rolls to a new draw — it is NOT a one-time split.

---

## Confirmed decisions (locked with Tai)

1. **Main Data split = `rule1_nonzero_zero`** (LOCKED doc Rule Set 1): Repeat = shared ∈ {1–6}
   (= 4,882,437 for sat), No_Repeat = shared = 0 (= 3,262,623). This is the **Main Data** split.
   It is NOT the Rule 2 `{1,2,3}` candidate-row split (`refgroup.classify_shared`), which is unrelated here.
2. **Rule 9 does not exist** — G2/G4 escalation is net-new (pass-through stub this pass).
3. **G3 shallow anchor**: reuse `stacked_blocks.block_layout` / `since_last_map` for the shallow-list
   math; the Rule 4 exclude-and-hold **filter** is net-new pipeline code (pass-through stub this pass).
4. **G1 escalation = `spread3_borderline`** (spec §4; LOCKED doc Rule Set 3 spread categories) — net-new
   (pass-through stub this pass). NOT unassigned.
5. **`target_range` = per-group** (all four are `[10,20]` today, but stored per group, not a global constant).
6. **Escalation control:** escalate only when survivor count is **above** the window. Below the window →
   **log-only** (escalation cannot manufacture rows). Still out of range **after** escalation → flag
   `out_of_range_after_escalation` and **let it through unblocked** — never hold the pipeline.
7. **`default_narrow` is a runner step, not registry data** — same for every group. **Decided
   2026-08-05: pass-through seam** this pass (returns candidates untouched, injected like the
   escalation stubs). The real survivor rule is an OPEN question in the LOCKED rules (Rule 2 w2+
   undefined; Rule 6 Selected/Unselected boundary undecided), so the runner control flow is real
   and tested while the narrowing criterion drops in later without signature churn. Only `escalate`
   varies per group.

---

## The four groups

| G  | Components            | `escalate` name              | Escalation status (this pass) |
|----|-----------------------|------------------------------|-------------------------------|
| G1 | `R`                   | `spread3_borderline`         | net-new stub (reuses persisted `Constituent_Groups` spread math) |
| G2 | `D`                   | `rule9_boundary_aggressive`  | net-new stub (Rule 9 does not exist) |
| G3 | `B1`                  | `shallow_anchor_exclude_hold`| net-new stub (reuses `block_layout`/`since_last_map`; filter net-new) |
| G4 | `Ep`, `So`, `Sp`, `B2`| `rule9_boundary_aggressive`  | net-new stub |

Shallow Anchor stays "B1/R only" (G3 = B1). Rule 9 covers the two multi/direct groups (G2, G4).
G1 (R) uses the spread-3 borderline mechanism from its own construction (Rule 3), not a match rule.

---

## 1. Registry — `syndicate_core/config.py` (beside `CF_ROWS`)

Frozen dataclass (typed + immutable per `python/coding-style.md`). Escalation referenced **by string
name** — `config.py` imports no callables, keeping the runner formula-agnostic (same trick as the SC
pattern's no-hardcoded-names rule).

```python
@dataclass(frozen=True)
class FormulaGroup:
    key: str                     # "G1".."G4"
    label: str
    components: tuple[str, ...]  # tokens fed straight to execute_collation
    escalate: str                # resolved via ESCALATIONS registry
    target_range: tuple[int, int]   # per-group survivor window; no global default

FORMULA_GROUPS = [
    FormulaGroup("G1", "R",            ("R",),                    "spread3_borderline",          (10, 20)),
    FormulaGroup("G2", "D",            ("D",),                    "rule9_boundary_aggressive",   (10, 20)),
    FormulaGroup("G3", "B1",           ("B1",),                   "shallow_anchor_exclude_hold", (10, 20)),
    FormulaGroup("G4", "Ep+So+Sp+B2",  ("Ep", "So", "Sp", "B2"),  "rule9_boundary_aggressive",   (10, 20)),
]
```

- `components` tuples flow into the **existing** `execute_collation(components)` unchanged — it already
  strips trailing digits + dedups (`B2`→`B`), so no change to that function.
- `target_range` carries an explicit value per group (no class-level default) so a future per-group
  retune is a one-line data edit, never a code change.

---

## 2. RefGroup-keyed Main-Data split cache — new `syndicate_core/main_split.py`

Import-safe, Streamlit-free, unit-testable (same discipline as `refgroup.py`).

**Rule-1 boundary defined once, in `refgroup.py`** (additive — avoids the second, drifting definition
seen at `analysis/sl_group_regime.py:92`):

```python
# refgroup.py (additive)
def main_data_stream(shared: int) -> str:
    """Rule 1 (Main Data): 'Repeat' iff shared > 0, else 'No_Repeat'. Nonzero/zero — NOT Rule 2."""
```

**Pure split fn** in `main_split.py` (vectorized, mirrors `refgroup.empirical_stream_counts`):

```python
def split_streams(main_df, n_cols, ref_numbers) -> dict[str, pd.DataFrame]:
    # shared = np.isin(main_arr, sorted(set(ref_numbers))).sum(axis=1)
    # Repeat    = rows where shared > 0
    # No_Repeat = rows where shared == 0
    # returns {"Repeat": df, "No_Repeat": df}
```

**RefGroup-keyed cache + rollover invalidation** (net-new — no persisted RefGroup marker exists today):

- **Key** `ref_key = "-".join(map(str, sorted(ref_numbers)))` — the newest-draw tuple; changes ⇔ rollover.
- **Disk** `Games/{GAME}/Main_Data/_split_cache/{Repeat|No_Repeat}__{ref_key}.parquet`
  plus `_split_marker.json` (`ref_key`, `n_main`, per-stream counts).
- **Boot flow** (called before the group run):
  1. `ref = load_newest_reference(hist_path, pick)` — existing fn, reads `draw_history.csv` row 0.
  2. Compute `ref_key`. If `== marker.ref_key` and both parquets exist → load them.
  3. Else **rebuild**: `split_streams(...)`, write both parquets, rewrite marker, drop stale
     `*__{old_ref_key}.*`. This is what makes it per-RefGroup, not one-time.
- **In-session** layer: `@st.cache_data` keyed on `(game_key, ref_key)`, wired into the existing
  **Active Draw** invalidation cycle (CLAUDE.md) so a draw change clears it alongside Sp/So/Ep.
- **Scale:** `sat` only this pass — pandas is fine. `oz`/`sfl` DuckDB split deferred (noted, not built).

---

## 3. Runner — new `_run_formula_groups(...)` in `syndicate_core/collation.py`

Mirrors `_run_sc_auto`: ordered iteration, per-item **status dict**, **skip-and-log**, nothing switched
on specific variable names (all from `group.components`).

**Control flow — per group, per stream:**

```
split = load_or_build_split(...)              # §2, RefGroup-keyed
for group in FORMULA_GROUPS:                   # registry-driven
  candidates = execute_collation(group.components)   # REUSE, unchanged
  for stream_name, stream_df in split.items():        # "Repeat", "No_Repeat"
    try:
      narrowed = narrow_fn(candidates, stream_df, n_cols, ctx=ctx)     # pass-through seam (step 5)
      n = len(narrowed); lo, hi = group.target_range
      escalated = False; flag = None
      if n > hi:                                        # too many → tighten
        narrowed = ESCALATIONS[group.escalate](narrowed, stream_df, n_cols, ctx=ctx)
        n = len(narrowed); escalated = True
        if not (lo <= n <= hi):
          flag = "out_of_range_after_escalation"        # let through unblocked
      elif n < lo:                                       # too few
        flag = "below_target"                            # log-only, no escalation
      results[group.key][stream_name] = {
        "status": "ok", "n": n, "escalated": escalated, "flag": flag}
    except Exception as e:
      results[group.key][stream_name] = {"status": "error", "reason": str(e)}   # never blocks others
```

- **`default_narrow`** is a **pass-through seam** this pass (decided 2026-08-05) — returns candidates
  untouched, injected via `narrow_fn` (default `_default_narrow`). When the survivor rule is decided,
  it will reuse `matching._match_cvi_rows` + `refgroup.selected_bands_for_pick`, imported **inside**
  the function (circular-import dodge, as `_compute_sc_block` does).
- **Missing inputs** (empty group, absent B1, missing stream) → `status:"skipped"` + log
  (precedent: `pipeline.b1_path` returns `None` gracefully).
- **`ctx`** is a small immutable bundle (`ref_numbers`, `history_df`, `pool`, `pick`, `game_key`)
  passed to every escalation so no signature churn when real filters land.

---

## 4. Escalation stubs — new `syndicate_core/escalation.py`

All three are **pure pass-through** this pass: log "not yet tuned", return the candidate set untouched.
The registry can call any of them whether or not tuned — the interface is the deliverable.

```python
ESCALATIONS: dict[str, Callable] = {
    "spread3_borderline":          spread3_borderline,
    "rule9_boundary_aggressive":   rule9_boundary_aggressive,
    "shallow_anchor_exclude_hold": shallow_anchor_exclude_hold,
}

def rule9_boundary_aggressive(narrowed_df, stream_df, n_cols, *, ctx):
    logging.info("escalation rule9_boundary_aggressive not yet tuned — pass-through")
    return narrowed_df                      # Rule 9 does not exist yet

def shallow_anchor_exclude_hold(narrowed_df, stream_df, n_cols, *, ctx):
    logging.info("escalation shallow_anchor_exclude_hold not yet tuned — pass-through")
    # LATER: build rolling own-era shallow list via stacked_blocks.block_layout / since_last_map
    #        from ctx.history_df + ctx.ref_numbers; exclude rows with zero overlap → holding.
    return narrowed_df                      # filter is net-new; identity for now

def spread3_borderline(narrowed_df, stream_df, n_cols, *, ctx):
    logging.info("escalation spread3_borderline not yet tuned — pass-through")
    # LATER: spread = len(Constituent_Groups) for R rows (already persisted by execute_collation);
    #        act on Spread-3 (Borderline) per LOCKED Rule Set 3. Filter is net-new.
    return narrowed_df                      # identity for now
```

Each stub's `LATER` note records the **existing** math it will reuse (nothing to reuse for Rule 9;
`block_layout`/`since_last_map` for shallow anchor; persisted `Constituent_Groups` for spread-3) so the
tuning pass is wiring, not rediscovery.

---

## 5. masterapp.py integration — additive, minimal

- Container Dashboards page: **new** section "▶ Run Formula Groups (4-group / RefGroup-split)" calling
  `_run_formula_groups`, rendering the per-group × per-stream status table + survivor CSVs. Reuse the
  existing result-rendering block (same reuse pattern as SC=NO reusing SC=YES's renderer).
- The **17-formula path stays untouched** — parallel surface, not a replacement.

---

## 6. What stays unchanged

`execute_collation` signature · `_match_cvi_rows` / `run_matching` · `refgroup.py` (only the additive
`main_data_stream` helper) · `CF_ROWS` and the 17-formula UI · `stacked_blocks.py` (read-only reuse).

---

## 7. Test plan — new `tests/test_main_split.py` + `tests/test_formula_groups.py`

- `split_streams`: Repeat == **4,882,437**, No_Repeat == **3,262,623** on a full C(45,6) sat fixture
  (locks Rule 1; guards against Rule 2 drift).
- Cache: same `ref_key` → no rebuild; changed `ref_key` → both parquets rewritten, stale dropped, marker updated.
- Runner: one group's error leaves the others running; status-dict shape; no-B1 → `skipped` not `error`.
- Escalation control: `n > hi` triggers escalation call; `n < lo` → `flag == "below_target"`, no call;
  still-out-after-escalation → `flag == "out_of_range_after_escalation"`, row set returned unblocked.
- Stub identity: each escalation output `.equals()` its input (pass-through proof).
- Registry: every `escalate` name resolves in `ESCALATIONS`; every `components` tuple resolves through `execute_collation`.

---

## 8. Build order (each step green before the next; commit per working step, only when asked)

1. `refgroup.main_data_stream` + test
2. `main_split.py` (split + cache + invalidation) + `tests/test_main_split.py`
3. `escalation.py` (3 stubs + `ESCALATIONS`) + identity tests
4. `config.FORMULA_GROUPS`
5. `collation._run_formula_groups` + `tests/test_formula_groups.py`
6. `masterapp.py` UI section
7. `py_compile` + full `pytest` + CLAUDE.md changelog entry

---

## 9. Deferred / not in this pass

- `oz` / `sfl` DuckDB split path.
- Real tuning of all three escalations (Rule 9 logic; shallow anchor exclude-and-hold filter;
  spread-3 borderline filter) — interfaces exist and pass through until designed.
- No_Repeat-stream iteration rule (LOCKED doc open question 3) — out of scope here.
