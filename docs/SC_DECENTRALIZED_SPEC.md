# Decentralized Selected Counts (SC) — Spec

**Session:** 23 June 2026  
**Status:** Ready to build  
**Start in Claude Code:** implement `_compute_sc_block` in `collation.py`, then wire into masterapp.py

---

## Problem with current SC

SC is loaded from `Selected_Counts/SC_{formula}.csv` — one file covering ALL w-columns of the stacked CVI matrix for a specific formula string. This has two problems:

1. **Formula-bound**: if the formula changes (add/drop a variable), the SC file is stale and must be re-uploaded
2. **Opaque**: SC is an external upload with no automatic computation — user must figure out thresholds without seeing the count distributions

---

## Design Goals

| Property | What it means |
|----------|---------------|
| Formula-agnostic | SC files are named by variable (B, R, D, Ep, So, Sp), not by formula |
| One SC per collation block | Each variable generates and owns one SC file covering its positions w1..wK |
| Dynamic iteration | UI shows count distribution per position — user sees "SC=5 → 400 selected, SC=6 → 22 selected" |
| Sequential in AUTO mode | SC runs B → R → D → Ep → So → Sp one at a time, not all at once |
| Skip + log on error | If variable empty or main_data missing, log warning and continue to next |
| Per-variable display | Each variable's SC section is shown independently in the UI |

---

## Data Model

### Storage format (unchanged from existing SC files)

`formulas_{gk}/Selected_Counts/SC_{VAR}_{gk}.csv`

```
w,Selected Count
w1,"5,6"
w2,"5,6"
w3,"5,6"
w4,"5"
w5,"5"
w6,"5"
w7,"4,5"
```

- `w` = variable-RELATIVE position (w1 = first slot across ALL rows of this variable)
- `Selected Count` = comma-separated list of matching threshold integers
- One file per variable, NOT per formula
- Naming: `SC_B_sat.csv`, `SC_R_sat.csv`, `SC_D_sat.csv`, `SC_Ep_sat.csv`, `SC_So_sat.csv`, `SC_Sp_sat.csv`

Existing formula-level files (`SC_{formula}.csv`) continue to work as a fallback.

---

## New Functions

### 1. `_compute_sc_block` — in `collation.py`

```python
def _compute_sc_block(
    var_name: str,
    var_df: pd.DataFrame,
    main_df: pd.DataFrame,
    n_cols: list[str],
    is_direct: bool = False,
    force_column_oriented: bool = False,
) -> dict:
    """
    Compute per-position count distributions for one variable block.

    1. Calls _to_w_rows() on var_df to get row-oriented representation.
    2. Renames value columns to w1, w2, ... (variable-relative positions).
    3. For each w-position: extracts all non-null values → runs _count_matches
       against main_df → returns distribution array.

    Returns:
        {
          "w1": np.ndarray,   # counts per main_df row for position 1
          "w2": np.ndarray,   # ...
          ...
          "_meta": {
              "var_name": str,
              "n_cvi_rows": int,       # rows in var_df
              "n_positions": int,      # number of w-columns
              "n_main_rows": int,      # len(main_df)
          }
        }

    Returns {} on any error (empty var_df, empty main_df, _to_w_rows failure).
    Logs warnings for skipped variables.
    """
```

**Requires import of `_count_matches` from `matching.py`.** To avoid circular import, put the import inside the function body:
```python
from syndicate_core.matching import _count_matches
```

**Note on is_direct / force_column_oriented:** pass the same flags used in `execute_collation` for each variable:
- D: `is_direct=True`
- Sp: `force_column_oriented=True`
- B, R, Ep, So: defaults

---

### 2. `_sc_distribution_table` — in `collation.py`

```python
def _sc_distribution_table(counts_dict: dict) -> pd.DataFrame:
    """
    Convert _compute_sc_block output to a human-readable table.

    For each position (w1, w2, ...), shows one row per possible count value:
        position | count_value | n_main_rows | pct_main
    
    count_value = integer match count (0, 1, 2, ... pool_size)
    n_main_rows = how many main_df rows had that match count at this position
    pct_main = percentage of main_df rows

    Caller uses this to show the distribution and pick SC thresholds.
    """
```

---

### 3. `_save_sc_block` — in `collation.py`

```python
def _save_sc_block(
    var_name: str,
    game_key: str,
    sc_thresholds: dict,   # {w1: [5,6], w2: [5], ...}
    gdirs: dict,
) -> Path:
    """
    Write SC_{VAR}_{gk}.csv to gdirs["Selected_Counts"].
    sc_thresholds keys are variable-relative (w1, w2, ...).
    Returns path written.
    Raises on write failure (caller should catch).
    """
```

---

### 4. `_load_sc_blocks` — in `collation.py`

```python
def _load_sc_blocks(
    variables: list[str],   # e.g. ["B", "R", "D"]
    game_key: str,
    gdirs: dict,
) -> dict:
    """
    Load per-variable SC files and merge into a single sc_dict.

    For each variable, loads SC_{VAR}_{gk}.csv if it exists.
    Merges per-variable SCs into global sc_dict using LAST-WRITE-WINS
    per relative position (i.e., if B sets w1=[5,6] and D sets w1=[4,5,6],
    D's value wins because D is listed after B).

    Returns merged sc_dict {w1: [5,6], w2: [5], ...}.
    Missing file → skip + log.
    Empty file or bad format → skip + log.
    Returns {} if no SC files found (caller falls back to existing logic).
    """
```

---

### 5. `_run_sc_auto` — in `collation.py` (AUTO mode entry point)

```python
def _run_sc_auto(
    var_order: list[str],   # ["B", "R", "D", "Ep", "So", "Sp"]
    var_map: dict,          # {var_name: var_df} — only non-empty vars
    main_df: pd.DataFrame,
    n_cols: list[str],
    game_key: str,
    gdirs: dict,
    is_direct_map: dict = None,   # {var: bool}
    force_col_map: dict = None,   # {var: bool}
) -> dict:
    """
    Run SC computation for all variables sequentially.
    Saves each variable's SC file immediately on success.

    Returns:
        {
          "B":  {"status": "ok", "distributions": {...}, "path": Path},
          "R":  {"status": "ok", ...},
          "D":  {"status": "skipped", "reason": "var_df empty"},
          "Ep": {"status": "error",   "reason": "..."},
          ...
        }
    """
```

---

## Changes to `execute_collation`

**Current signature:** `execute_collation(components: list[str]) -> pd.DataFrame`

**New behaviour (no signature change):** after building the stacked CVI, also attempt to auto-build sc_dict from per-variable SC files. This is a side-effect attached to the game-key context via session state. Return value stays `pd.DataFrame` to avoid breaking call sites.

Instead, add a **separate helper**:

```python
def collation_with_sc(
    components: list[str],
    game_key: str,
    gdirs: dict,
) -> tuple[pd.DataFrame, dict]:
    """
    Run execute_collation and auto-build sc_dict from per-variable SC files.
    Returns (cvi_df, sc_dict).
    sc_dict = {} if no per-variable SC files found.
    """
    cvi_df   = execute_collation(components)
    base_vars = list({re.sub(r"\d+$", "", c) for c in components if c})
    sc_dict  = _load_sc_blocks(base_vars, game_key, gdirs)
    return cvi_df, sc_dict
```

Container Dashboards can call `collation_with_sc` instead of `execute_collation` and use the returned `sc_dict` as the default (still overridable via the SC upload widget).

---

## Changes to `run_matching` / sc_dict build in Container Dashboards

**File:** `masterapp.py`, around line 5145 (sc_dict build section)

Current priority:
1. sc_auto (formula-level SC file from Selected_Counts)
2. fallback text input
3. same-for-all text input

New priority:
1. Per-variable SC files (via `_load_sc_blocks`) — loaded at page boot alongside cvi_df
2. Formula-level SC file `SC_{formula}.csv` (existing fallback — keep for backward compat)
3. Manual upload (existing)
4. Fallback text input
5. Same-for-all text input

Minimal code change at line ~4926 (sc_auto load block):
```python
sc_auto = {}

# 1. Try per-variable SC files (decentralized — formula-agnostic)
_base_vars = list({re.sub(r"\d+$","",c) for c in (cf_formula or "").split() if c})
if _base_vars:
    sc_auto = _load_sc_blocks(_base_vars, gk, _gdirs)

# 2. Fall back to formula-level SC file (existing logic)
if not sc_auto:
    sc_folder = _gdirs["Selected_Counts"]
    for sc_file in ...:   # existing code unchanged
        ...
```

---

## UI Changes (masterapp.py)

### Per-variable SC section

Add to each variable's section in `🧩 Variable Inputs` page (or to the Collation page — TBD). One collapsible expander per variable:

```
📊 B — Selected Counts
  [Compute SC]  (button — triggers _compute_sc_block)
  
  Loaded from: SC_B_sat.csv  ✅  (or ⚠️ not found)
  
  Position | CVI values | Distribution (count: n_draws) | SC threshold
  w1       | 1006       | 0:2k  1:4k  2:8k  3:10k ...   | [5,6  ▼]
  w2       | 1006       | 0:3k  1:5k  2:7k  3:9k  ...   | [5,6  ▼]
  ...
  
  [Save SC_B_sat.csv]
```

**Distribution display**: for each position, show a mini count table (count_value → n_draws). This is "dynamic iteration" — user sees all thresholds simultaneously and picks.

### AUTO SC button

In the Collation page or Variable Inputs page:
```
[🔄 Compute SC — All Variables]
```
Runs `_run_sc_auto` for all loaded variables sequentially. Shows status per variable on completion. If main_data not loaded: shows warning per variable (skip, not error).

---

## Parallel worker (`matching.py` — `_parallel_worker`)

Current SC load at line 964:
```python
if sc_path and Path(sc_path).exists():
    sc_df = pd.read_csv(sc_path)
    ...
```

New logic (after formula-level SC check):
```python
# 1. Try per-variable SC files
_formula_parts = formula_name.replace("+","").replace(",","").replace("/"," ").split()
_base_vars = list({re.sub(r"\d+$","",p) for p in _formula_parts if p})
if _base_vars:
    _sc_dir = Path(sc_path).parent if sc_path else None
    if _sc_dir and _sc_dir.exists():
        from syndicate_core.collation import _load_sc_blocks
        _gk = formula_name.rsplit("_", 1)[-1] if "_" in formula_name else "sat"
        _gdirs_tmp = {"Selected_Counts": _sc_dir}
        sc_dict = _load_sc_blocks(_base_vars, _gk, _gdirs_tmp)

# 2. Fall back to formula-level SC file (existing code)
if not sc_dict and sc_path and Path(sc_path).exists():
    ...   # unchanged
```

---

## Carry-Forward Defaults

`is_direct_map` and `force_col_map` constants for `_run_sc_auto`:

```python
_IS_DIRECT = {"D": True}
_FORCE_COL = {"Sp": True}
# All others: defaults (is_direct=False, force_column_oriented=False)
```

---

## Test Cases to Add

In `tests/test_collation.py`:

```python
def test_compute_sc_block_basic():
    """_compute_sc_block returns per-position count arrays."""

def test_compute_sc_block_empty_var():
    """Empty var_df → returns {}."""

def test_compute_sc_block_empty_main():
    """Empty main_df → returns {}."""

def test_save_load_sc_block_roundtrip():
    """Save then load SC file, verify thresholds survive round-trip."""

def test_load_sc_blocks_merge():
    """Two variables with overlapping positions: last-write-wins."""

def test_load_sc_blocks_missing_file():
    """Missing file is skipped gracefully, other files still loaded."""

def test_sc_distribution_table_shape():
    """Distribution table has correct columns and no NaN in count_value."""
```

---

## Build Order

1. `collation.py`: add `_compute_sc_block`, `_sc_distribution_table`, `_save_sc_block`, `_load_sc_blocks`, `_run_sc_auto`, `collation_with_sc`
2. `tests/test_collation.py`: add 6 test cases above — all green before touching masterapp
3. `masterapp.py`, sc_auto load block (~line 4926): insert per-variable SC load BEFORE formula-level fallback
4. `masterapp.py`, Variable Inputs page: add SC expander per variable with Compute + Save buttons
5. `masterapp.py`, Collation page: add AUTO SC button
6. `matching.py`, `_parallel_worker`: insert per-variable SC fallback before formula-level SC load
7. `py_compile` + `pytest` + commit

---

## What Stays Unchanged

- `run_matching` signature — sc_dict is still `{w1: [...], w2: [...], ...}`
- Existing `SC_{formula}.csv` files continue to work (fallback)
- Manual SC upload in Container Dashboards — still works, takes highest priority
- `carry_fwd` logic — no change
- `execute_collation` signature — no change

---

## Open Questions (not blocking build)

| Q | Notes |
|---|-------|
| Merge conflict strategy | Spec says last-write-wins. Could be made configurable later (min / max / mode) |
| SC for Sp | Sp uses `force_column_oriented=True` which may produce 100+ w-columns. Cap at widest syndicate? |
| SC hint auto-select | AUTO mode currently just computes distributions and saves them. Should it auto-pick a threshold based on heuristic (e.g., top-2 count buckets)? Defer. |
| SC display in Matching Table | Currently shows "SC" column per w-row. With per-variable SC, this is unchanged — sc_dict is still flat by w-column. |
