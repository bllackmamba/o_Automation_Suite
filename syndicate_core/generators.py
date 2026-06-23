"""
syndicate_core/generators.py — Variable generators

Extracted from masterapp.py (Step 6).
Contains: R (Rainbow), Sp (Splits), So (SplitsCombi), Ep (ExcelPro) generators,
supporting helpers, and _auto_wire_generators which auto-runs them after D loads.
"""

import re
import warnings

import pandas as pd
import streamlit as st

__all__ = [
    "_sets_df_to_rows",
    "_rows_to_sets_df",
    "sort_d_longest_first",
    "prepare_d_input_sets",
    "auto_half_splits",
    "generate_rainbow",
    "generate_splits",
    "generate_splits_combi",
    "prepare_ep_objects",
    "generate_excelpro",
    "_auto_wire_generators",
    "_is_valid_sets_file",
]


# ── Output validation ─────────────────────────────────────────────────────────

def _is_valid_sets_file(df: pd.DataFrame, max_val: int) -> bool:
    """Return True if all numeric values in a sets DataFrame are <= max_val
    and the number of position columns does not exceed the pool size.
    Rejects degenerate output where row indices leaked in as values, and
    rejects pathologically wide files (e.g. 2175-col Sp from unfiltered D)."""
    if df is None or df.empty:
        return False
    val_cols = [c for c in df.columns if c not in ("Set_Label", "w")]
    if not val_cols:
        return False
    if len(val_cols) > max_val:
        return False
    numeric = df[val_cols].apply(pd.to_numeric, errors="coerce")
    mx = numeric.stack().max()
    return bool(mx <= max_val)


# ── Row / column transpose helpers ────────────────────────────────────────────

def _sets_df_to_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Transpose a column-oriented set DataFrame to row-oriented for display/export.

    Input:  columns = set names (e.g. 'ab', 'U', 'w10', 'a_ab'),
            rows    = values padded with NaN to equal length.
    Output: one row per set; columns = ['Set_Label', 'w', 0, 1, 2, …] where
            Set_Label is the original column name, w is a sequential label
            (w1, w2, …), and the integer columns hold the actual numbers.
    Empty/all-NaN rows are dropped.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    t = df.T.reset_index()
    n_val = t.shape[1] - 1
    t.columns = ["Set_Label"] + list(range(n_val))
    # Drop rows that are entirely NaN
    val_cols = list(range(n_val))
    t = t.dropna(subset=val_cols, how="all")
    # Drop trailing all-NaN position columns
    non_empty_val = [c for c in val_cols if t[c].notna().any()]
    t = t[["Set_Label"] + non_empty_val].reset_index(drop=True)
    t.insert(1, "w", [f"w{i+1}" for i in range(len(t))])
    return t


def _rows_to_sets_df(df: pd.DataFrame, set_col: str = "set") -> pd.DataFrame:
    """Inverse of _sets_df_to_rows: transpose row-oriented sets → column-oriented.

    Input:  one row per set; first column = set name (set_col);
            optional second column 'w' (sequential label — skipped);
            remaining columns hold the actual numbers.
    Output: columns = set names; rows = values padded with NaN.
    Used to read row-oriented input files back into the column-oriented format
    that Ep / Sp / So generators expect.
    If set_col is absent, row indices are used as column names.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    val_cols = [c for c in df.columns if c not in (set_col, "w")]
    if set_col in df.columns:
        labels = df[set_col].astype(str).tolist()
        data   = df[val_cols].values
    else:
        labels = [f"s{i}" for i in range(len(df))]
        data   = df.values
    result = {}
    for label, row in zip(labels, data):
        nums = [x for x in row if pd.notna(x)]
        result[label] = pd.Series(nums, dtype="Int64")
    return pd.DataFrame(result)


# ── D input helpers ────────────────────────────────────────────────────────────

def sort_d_longest_first(D: pd.DataFrame) -> pd.DataFrame:
    """Return D with rows ordered LONGEST entry (most numbers) → SHORTEST.

    'Length' = how many w-columns are filled in that row (a System 20 entry = 20,
    a standard game = 6). Stable sort, so equal-length rows keep their order.
    """
    if D is None or D.empty:
        return D
    wcols = [c for c in D.columns if re.match(r'^w\d+$', str(c), re.I)]
    if not wcols:
        return D
    lengths = D[wcols].notna().sum(axis=1)
    order = lengths.sort_values(ascending=False, kind="stable").index
    return D.loc[order].reset_index(drop=True)


def prepare_d_input_sets(D: pd.DataFrame, n: int) -> pd.DataFrame:
    """Peel off the N LONGEST entries of D as the generator input columns.

    Per the pipeline brief: the longest D rows become the w1, w2, w3, w4 (… w8) input
    SETS for the generators — Sp/So take the first 4 longest, Ep takes the first 8.
    Each chosen entry (a row of numbers in D) is laid DOWN one column, so the result
    is a DataFrame whose columns are w1, w2, w3, w4, … each holding one long entry's
    numbers.

    Handles two input orientations automatically:
      • Column-oriented D (legacy): columns are positional w1,w2,w3… (number slots),
        each ROW is one syndicate — peels n longest rows into output columns.
      • Row-oriented D (new):  each ROW is already a complete number set stored as
        pos_1, pos_2, … columns (or a leading 'set'/'label' column).  The function
        transposes these rows into columns before sorting by length and taking the top n.
        This matches the new convention where Sp/So/Ep input files are stored as rows.
    """
    if D is None or D.empty or n < 1:
        return pd.DataFrame()

    # ── Detect orientation ────────────────────────────────────────────────
    wcols   = [c for c in D.columns if re.match(r'^w\d+$',   str(c), re.I)]
    pos_cols = [c for c in D.columns if re.match(r'^pos_\d+$', str(c), re.I)]
    set_col  = next((c for c in D.columns
                     if str(c).strip().lower() in ("set", "label", "name")), None)

    if pos_cols or (set_col and not wcols):
        # ── Row-oriented input: transpose rows → columns first ────────────
        col_df = _rows_to_sets_df(D, set_col=set_col) if set_col else \
                 _rows_to_sets_df(D.rename(columns={D.columns[0]: "set"}), set_col="set")
        # Sort columns by their length (longest set first)
        lengths = {c: col_df[c].notna().sum() for c in col_df.columns}
        sorted_cols = sorted(lengths, key=lambda x: lengths[x], reverse=True)
        top_cols = sorted_cols[:n]
        labels = [f"w{i+1}" for i in range(len(top_cols))]
        result = {}
        for label, col in zip(labels, top_cols):
            nums = [int(x) for x in col_df[col].dropna()]
            result[label] = pd.Series(nums, dtype="Int64")
        return pd.DataFrame(result)

    # ── Column-oriented D: original behaviour (wN positional columns) ─────
    if not wcols:
        return pd.DataFrame()
    ordered = sort_d_longest_first(D)
    top = ordered[wcols].head(n)
    labels = [f"w{i+1}" for i in range(n)]  # w1, w2, w3, w4, …
    cols = {}
    for label, (_, row) in zip(labels, top.iterrows()):
        nums = [int(x) for x in row.dropna()]
        cols[label] = pd.Series(nums, dtype="Int64")
    return pd.DataFrame(cols)


def auto_half_splits(sets_dict: dict) -> list:
    """Split each set in halves, rounding UP: len 20→10, 17→9 (= (len+1)//2)."""
    return [(len(v) + 1) // 2 for v in sets_dict.values()]


def _d_input_to_sets(d_input_df: pd.DataFrame) -> dict:
    """Columns w1,w2,w3,w4… (each a long D entry down the rows) → {label: [numbers]}."""
    out = {}
    for col in d_input_df.columns:
        out[str(col)] = [int(x) for x in d_input_df[col].dropna().tolist()]
    return out


# ── R : Rainbow (ported from task2.py) ──────────────────────────────────────

def _bounded_combos(keys, max_comb):
    """Combinations of `keys` sized 1..max_comb, generated directly (no 2**K tail)."""
    from itertools import chain, combinations
    keys = list(keys)
    hi = min(max_comb, len(keys))
    return chain.from_iterable(combinations(keys, r) for r in range(1, hi + 1))


def _combo_count(n_keys, max_comb):
    from math import comb
    hi = min(max_comb, n_keys)
    return sum(comb(n_keys, r) for r in range(1, hi + 1))


def _normalise_sl(sl_df: pd.DataFrame) -> pd.DataFrame:
    df = sl_df.copy()
    lower = {str(c).strip().lower(): c for c in df.columns}
    def pick(*cands):
        for cand in cands:
            if cand in lower:
                return lower[cand]
        return None
    c_num = pick("numbers", "number", "n", "ball")
    c_sl = pick("since last", "since_last", "sincelast", "since", "sl")
    c_keep = pick("to_keep", "to keep", "tokeep", "keep")
    if c_num is None or c_sl is None:
        raise ValueError("Since-Last table needs a number column and a 'Since Last' "
                         "column (got: %s)" % list(df.columns))
    out = pd.DataFrame({
        "numbers": pd.to_numeric(df[c_num], errors="coerce"),
        "since_last": pd.to_numeric(df[c_sl], errors="coerce"),
    })
    out["to_keep"] = (pd.to_numeric(df[c_keep], errors="coerce")
                      if c_keep is not None else out["numbers"])
    out = out.dropna(subset=["since_last", "numbers"], how="any")
    out["since_last"] = out["since_last"].astype(int) + 1
    out["numbers"] = out["numbers"].astype(int)
    return out


def _wt_writer(df: pd.DataFrame) -> pd.DataFrame:
    """task2.py's 'wt' sheet (SL/wt/…/wt_abcd) — Ep reads this as input2 'All wt'."""
    listed = df.groupby("since_last")["numbers"].apply(list).to_dict()
    keep = set(df["to_keep"].dropna().tolist())
    i0, w0, i1, w1, iF, wF = [], [], [], [], [], []
    for i in sorted(listed.keys()):
        i0 += [i] + [None] * (len(listed[i]) - 1)
        i1 += [i] + [None] * len(listed[i])
        w0 += listed[i]
        w1 += listed[i] + [None]
        kref = [e for e in listed[i] if e in keep]
        iF += [i] + [None] * (len(kref) - 1)
        wF += kref
    gen = [i0, w0, i1, w1, iF, wF]
    out = pd.DataFrame({n: pd.Series(gen[n]) for n in range(len(gen))})
    out.columns = ["SL", "wt", "SL_", "wt_", "_SL_", "wt_abcd"]
    return out


def generate_rainbow(sl_df: pd.DataFrame, max_comb=None, combo_guard: int = 5_000):
    """R from the Since-Last table. Returns (result_df, wt_df, info).

    max_comb defaults to r_max_comb from GAMES_CFG, which equals the game's
    pick size (6, 7, or 8). Do not pass values larger than pick — there is no
    mathematical benefit to combining more SL groups than balls drawn.
    combo_guard emits a warning when the expected combo count exceeds it but
    never reduces max_comb — the caller is responsible for bounding output.
    result_df is row-oriented: columns = ["combo", "w", 0, 1, 2, …] where
    combo is the tuple string, w is the sequential label, and 0/1/2/… are
    the number positions (NaN for shorter combos).
    """
    import warnings as _warnings
    df = _normalise_sl(sl_df)
    grouped = df.groupby("since_last")["numbers"].apply(list).to_dict()
    to_keep = set(df["to_keep"].dropna().tolist())
    keys = sorted(grouped.keys())
    n = len(keys)
    requested = n if max_comb is None else max(1, min(int(max_comb), n))
    expected = _combo_count(n, requested)
    if expected > combo_guard:
        _warnings.warn(
            f"generate_rainbow: {expected:,} combos exceeds combo_guard={combo_guard:,}. "
            "Proceeding — pass max_comb to limit output.",
            stacklevel=2,
        )
    result = {}
    for comb in _bounded_combos(keys, requested):
        ref = []
        for g in comb:
            ref += grouped[g]
        result[str(comb)] = [e for e in ref if e in to_keep]
    # Build row-oriented DataFrame: one row per combo, integer position columns.
    if not result:
        result_df = pd.DataFrame(columns=["combo", "w"])
    else:
        rows = []
        for combo_str, nums in result.items():
            row: dict = {"combo": combo_str}
            row.update({j: v for j, v in enumerate(nums)})
            rows.append(row)
        result_df = pd.DataFrame(rows)
        int_cols = [c for c in result_df.columns if isinstance(c, int)]
        for col in int_cols:
            result_df[col] = pd.array(result_df[col], dtype="Int64")
        # Sort: more numbers first (mirrors previous fewest-NaN column sort).
        result_df["_n"] = result_df[int_cols].notna().sum(axis=1)
        result_df = (result_df
                     .sort_values("_n", ascending=False, kind="stable")
                     .drop(columns="_n")
                     .reset_index(drop=True))
        result_df.insert(1, "w", [f"w{i+1}" for i in range(len(result_df))])
    info = {"n_groups": n, "max_comb": requested,
            "n_combos": len(result_df), "capped": False, "combo_guard": combo_guard}
    return result_df, _wt_writer(df), info


# ── Sp : Splits (ported from task1b.py) ──────────────────────────────────────

def generate_splits(d_input_df: pd.DataFrame, splitter=None) -> pd.DataFrame:
    """Sp from D's 4 longest rows (columns w1,w2,w3,w4). Auto half-splits unless given."""
    from itertools import combinations
    sets_ready = _d_input_to_sets(d_input_df)
    keys = list(sets_ready.keys())
    if splitter is None:
        splitter = auto_half_splits(sets_ready)
    split_sets = {}
    for idx, k in enumerate(keys):
        split_sets[k + "0"] = sets_ready[k][:splitter[idx]]
        split_sets[k + "1"] = sets_ready[k][splitter[idx]:]
    comb3 = list(combinations(keys, 3))
    comb2 = list(combinations(keys, 2))
    let_3, fin_3 = ["e", "f", "g", "h"], ["o", "p", "q", "r"]
    let_2, fin_2 = ["i", "j", "k", "l", "m", "n"], ["s", "t", "u", "v", "z", "x"]
    comb3dict, comb2dict, result = {}, {}, {}
    universe = {e for k in keys for e in sets_ready[k]}
    for j, comb in enumerate(comb3):
        iter_set = {e for L in comb for e in sets_ready[L]}
        i = 0
        for suffix in ("0", "1"):
            for letter in comb:
                comb3dict[let_3[j] + str(i)] = iter_set - set(split_sets[letter + suffix]); i += 1
    for j, comb in enumerate(comb2):
        iter_set = {e for L in comb for e in sets_ready[L]}
        i = 0
        for suffix in ("0", "1"):
            for letter in comb:
                comb2dict[let_2[j] + str(i)] = iter_set - set(split_sets[letter + suffix]); i += 1
    for i in range(len(let_3)):
        for j in range(len(comb3dict) // len(let_3)):
            result[fin_3[i] + str(j)] = universe - comb3dict[let_3[i] + str(j)]
    for i in range(len(let_2)):
        for j in range(len(comb2dict) // len(let_2)):
            result[fin_2[i] + str(j)] = universe - comb2dict[let_2[i] + str(j)]
    skeys = sorted(split_sets.keys())
    for i, key in enumerate(split_sets):
        result[key] = split_sets[key]
        result["y" + str(i)] = universe - set(split_sets[skeys[i]])
    result.update(comb3dict)
    result.update(comb2dict)
    return pd.DataFrame({k: pd.Series(list(v), dtype="Int64") for k, v in result.items()})


# ── So : Splits-combi (ported from automation_vba.py, len==4 branch) ─────────

def generate_splits_combi(d_input_df: pd.DataFrame, splitter=None) -> pd.DataFrame:
    """So from D's 4 longest rows (columns w1,w2,w3,w4). Auto half-splits unless given.
    Ports the set algebra of automation_vba.sets_sampling; skips the cosmetic
    column-relabeling (not needed for the pipeline variable).

    Key naming: split keys are base_key + "0"/"1" (e.g. 'w10','w11' for base 'w1').
    Membership check strips the trailing suffix char to recover the base key.
    """
    from itertools import combinations
    sets_ready = _d_input_to_sets(d_input_df)
    keys = list(sets_ready.keys())
    if splitter is None:
        splitter = auto_half_splits(sets_ready)
    split_sets = {}
    for idx, k in enumerate(keys):
        split_sets[k + "0"] = sets_ready[k][:splitter[idx]]
        split_sets[k + "1"] = sets_ready[k][splitter[idx]:]
    universe = {e for s in sets_ready.values() for e in s}
    result = {"U": universe}
    comb_pairs = {p: set(split_sets[p[0]]) | set(split_sets[p[1]])
                  for p in combinations(split_sets.keys(), 2)}
    comb_three = {t: set().union(*[set(sets_ready[x]) for x in t])
                  for t in combinations(keys, 3)}
    for ti, tset in comb_three.items():
        for pj, pset in comb_pairs.items():
            # Strip trailing "0"/"1" suffix to get the base key, then check membership
            # in the triple. Works for any key length (w1, w2, ... or a, b, ...).
            base0 = pj[0][:-1]  # e.g. 'w10' → 'w1', 'a0' → 'a'
            base1 = pj[1][:-1]  # e.g. 'w21' → 'w2', 'b1' → 'b'
            if pset.issubset(tset) and base0 in ti and base1 in ti:
                result["U-" + str(ti) + "-" + str(pj)] = universe - (tset - pset)
                result[str(ti) + "-" + str(pj)] = tset - pset
        result[str(ti)] = tset
    for pj, pset in comb_pairs.items():
        result["U-" + str(pj)] = universe - pset
        result[str(pj)] = pset
    return pd.DataFrame({k: pd.Series(sorted(v), dtype="Int64") for k, v in result.items()})


# ── Ep : ExcelPro (ported from Java Main.java — the substantive 'All' output) ─

def prepare_ep_objects(D: pd.DataFrame, mode: str = "pairs") -> dict:
    """Build the 4 ExcelPro objects a, b, c, d — each = (arrayOne, arrayTwo) — from D.

    mode='pairs' (default): the 8 LONGEST D rows paired into 4 objects:
      a = (D-row#1, D-row#2)  →  i.e. the w1 and w2 longest rows
      b = (D-row#3, D-row#4)  →  w3, w4
      c = (D-row#5, D-row#6)  →  w5, w6
      d = (D-row#7, D-row#8)  →  w7, w8
    Each pair's first member becomes arrayOne, second becomes arrayTwo.
    Ep's wt filter list is supplied by R (rainbow).

    mode='halves': the 4 LONGEST D rows, each split in half (arrayOne=first half,
      arrayTwo=second half) — kept as an alternative.

    Accepts both column-oriented D (w1,w2,… positional columns) and
    row-oriented D (pos_1,pos_2,… columns — new convention).  Row-oriented input
    is transposed automatically via prepare_d_input_sets before pairing.
    """
    if mode == "pairs":
        inp = prepare_d_input_sets(D, 8)   # columns: w1, w2, … w8 (8 longest rows)
        cols = list(inp.columns)
        objects = {}
        for i, lab in enumerate(["a", "b", "c", "d"]):
            # pair i: cols[2i] = arrayOne (e.g. w1), cols[2i+1] = arrayTwo (e.g. w2)
            one = [int(x) for x in inp[cols[2 * i]].dropna()] if 2 * i < len(cols) else []
            two = [int(x) for x in inp[cols[2 * i + 1]].dropna()] if 2 * i + 1 < len(cols) else []
            objects[lab] = (one, two)
        return objects
    # mode='halves'
    inp = prepare_d_input_sets(D, 4)       # columns: w1, w2, w3, w4 (4 longest rows)
    objects = {}
    for lab, col in zip(["a", "b", "c", "d"], inp.columns):
        nums = [int(x) for x in inp[col].dropna()]
        half = (len(nums) + 1) // 2
        objects[lab] = (nums[:half], nums[half:])
    return objects


def generate_excelpro(objects: dict, wt_list) -> pd.DataFrame:
    """Ep — the ExcelPro 'All' result (faithful to Main.java comboList → 'All').

    For each pair (x, y) of the 4 objects a, b, c, d, emit 4 columns:
      a_<xy>  — wt numbers found in x.arrayOne
      b_<xy>  — wt numbers found in x.arrayTwo
      c_<xy>  — wt numbers found in y.arrayOne
      d_<xy>  — wt numbers found in y.arrayTwo

    Column naming uses the concatenated object labels (single chars), so pairs produce:
      a_ab, b_ab, c_ab, d_ab,
      a_ac, b_ac, c_ac, d_ac,
      a_ad, b_ad, c_ad, d_ad,
      a_bc, b_bc, c_bc, d_bc,
      a_bd, b_bd, c_bd, d_bd,
      a_cd, b_cd, c_cd, d_cd
    """
    from itertools import combinations as _ep_combos
    keys = list(objects.keys())   # ['a', 'b', 'c', 'd']
    wt = [int(w) for w in wt_list]
    result = {}
    for x, y in _ep_combos(keys, 2):
        h = x + y                 # e.g. 'ab', 'ac', 'ad', 'bc', 'bd', 'cd'
        xo, xt = set(objects[x][0]), set(objects[x][1])
        yo, yt = set(objects[y][0]), set(objects[y][1])
        result["a_" + h] = [w for w in wt if w in xo]
        result["b_" + h] = [w for w in wt if w in xt]
        result["c_" + h] = [w for w in wt if w in yo]
        result["d_" + h] = [w for w in wt if w in yt]
    ep_df = pd.DataFrame({k: pd.Series(v, dtype="Int64") for k, v in result.items()})
    if ep_df.empty:
        return ep_df
    # Transpose to row-oriented: each role_pair (a_ab, …) becomes one row.
    t = ep_df.T.reset_index()
    t = t.rename(columns={t.columns[0]: "sub_label"})
    t.insert(0, "pair", t["sub_label"].str.split("_", n=1).str[1])
    t.insert(1, "w", [f"w{i+1}" for i in range(len(t))])
    # Remaining columns are already named 0, 1, 2, … (original RangeIndex positions).
    return t


# ── Auto-wire: run generators immediately after D loads ───────────────────────

def _auto_wire_generators(gdirs: dict, gk: str):
    """Auto-run Sp, So (and Ep when B+R are available) immediately after D loads.

    Uses prepare_d_input_sets to peel the 4/8 longest D rows (w1,w2,w3,w4…) as
    column-oriented sets, then feeds them to the generators. Results are stored
    in st.session_state and written to disk so subsequent tabs show them instantly.
    """
    _d_all_path = gdirs["Games_Breakdown"] / f"D_ALL_{gk}.csv"
    active_draw = st.session_state.get(f"active_draw__{gk}")
    if _d_all_path.exists():
        _d_all = pd.read_csv(_d_all_path)
        if active_draw is not None and "Draw_Number" in _d_all.columns:
            _filtered = _d_all[_d_all["Draw_Number"] == active_draw]
        else:
            _filtered = _d_all
        if not _filtered.empty:
            d_df = _filtered.reset_index(drop=True)
        else:
            warnings.warn(
                f"_auto_wire_generators: D_ALL_{gk}.csv filtered to draw "
                f"{active_draw} is empty; falling back to D from session state.",
                stacklevel=2,
            )
            d_df = st.session_state.get(f"D__{gk}", pd.DataFrame())
    else:
        warnings.warn(
            f"_auto_wire_generators: {_d_all_path} not found; "
            "falling back to D from session state.",
            stacklevel=2,
        )
        d_df = st.session_state.get(f"D__{gk}", pd.DataFrame())
    if d_df is None or d_df.empty:
        return

    from syndicate_core.config import GAMES_CFG
    pool = GAMES_CFG.get(gk, {}).get("pool", 45)

    auto_status = st.empty()
    msgs = []

    # ── Sp (Splits / task1b) ────────────────────────────────────────────────
    try:
        sp_input = prepare_d_input_sets(d_df, 4)  # columns: w1,w2,w3,w4
        if not sp_input.empty:
            sp_df = generate_splits(sp_input)
            if not sp_df.empty:
                _sp_rows = _sets_df_to_rows(sp_df)
                if not _is_valid_sets_file(_sp_rows, pool):
                    warnings.warn(
                        f"_auto_wire_generators [{gk}]: Sp output invalid "
                        f"(max value > {pool}) — skipping write",
                        stacklevel=2,
                    )
                else:
                    st.session_state[f"Sp__{gk}"] = sp_df
                    _sp_rows.to_csv(gdirs["Splits"] / f"Sp_{gk}.csv", index=False)
                    msgs.append(f"Sp ({sp_df.shape[1]} cols)")
    except Exception as _sp_ex:
        msgs.append(f"Sp error: {_sp_ex}")

    # ── So (SplitsCombi / automation_vba) ──────────────────────────────────
    try:
        so_input = prepare_d_input_sets(d_df, 4)  # columns: w1,w2,w3,w4
        if not so_input.empty:
            so_df = generate_splits_combi(so_input)
            if not so_df.empty:
                _so_rows = _sets_df_to_rows(so_df)
                if not _is_valid_sets_file(_so_rows, pool):
                    warnings.warn(
                        f"_auto_wire_generators [{gk}]: So output invalid "
                        f"(max value > {pool}) — skipping write",
                        stacklevel=2,
                    )
                else:
                    st.session_state[f"So__{gk}"] = so_df
                    _so_rows.to_csv(gdirs["Splits_Combi"] / f"So_{gk}.csv", index=False)
                    msgs.append(f"So ({so_df.shape[1]} cols)")
    except Exception as _so_ex:
        msgs.append(f"So error: {_so_ex}")

    # ── Ep (ExcelPro) — requires R's wt list ───────────────────────────────
    b_df = st.session_state.get(f"B__{gk}", pd.DataFrame())
    r_wt_df = st.session_state.get(f"_R_wt__{gk}", pd.DataFrame())
    if not b_df.empty and not r_wt_df.empty:
        try:
            ep_objs = prepare_ep_objects(d_df, mode="pairs")  # 8 longest rows → 4 pairs
            wt_list = r_wt_df["wt"].dropna().tolist() if "wt" in r_wt_df.columns else []
            if not wt_list:
                # Fall back to all_wt column or any numeric column
                wt_list = r_wt_df.iloc[:, 0].dropna().tolist()
            if ep_objs and wt_list:
                ep_df = generate_excelpro(ep_objs, wt_list)
                if not ep_df.empty:
                    st.session_state[f"Ep__{gk}"] = ep_df
                    ep_path = gdirs["ExcelPro"] / f"Ep_{gk}.csv"
                    ep_df.to_csv(ep_path, index=False)
                    msgs.append(f"Ep ({len(ep_df)} rows)")
        except Exception as _ep_ex:
            msgs.append(f"Ep error: {_ep_ex}")

    if msgs:
        auto_status.markdown(
            f'<div class="ok">⚡ Auto-generated: {" · ".join(msgs)}</div>',
            unsafe_allow_html=True)
