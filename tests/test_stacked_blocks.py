"""Ground-truth tests for the Blocked flat (all_wt) view logic (spec §8).

Fixtures 8.1/8.3/8.4 are Tai's hand-verified Saturday-Lotto data and must fall
out of the real draw_history.csv automatically. Fixture 8.2 is used in its
CORRECTED 17-block form: the spec sheet split 24 (SL14) from 35 (SL15), but
both 24 and 35 last appeared together at D4657 ([16,17,24,33,35,36]) so they
share one SL block. Confirmed with Tai 2026-07-11 — use the corrected fixture.
"""
import ast
import csv
from pathlib import Path

import pytest

from syndicate_core.stacked_blocks import (
    _catch_over_cells,
    band_of,
    block_layout,
    column_pads,
    column_structures,
    decorate_newest,
    deep_repeats,
    render_columns,
    since_last_map,
)

POOL = 45
_HIST_PATH = (
    Path(__file__).resolve().parent.parent
    / "Games" / "SAT" / "SinceLast_sat" / "draw_history.csv"
)


def _load_history() -> list[dict]:
    """Newest-first list of {"draw", "nums"} from the real sat history file."""
    rows: list[dict] = []
    with _HIST_PATH.open() as f:
        for r in csv.DictReader(f):
            rows.append({
                "draw": r["draw"].strip(),
                "nums": set(ast.literal_eval(r["numbers"])),
            })
    return rows


@pytest.fixture(scope="module")
def history() -> list[dict]:
    if not _HIST_PATH.exists():
        pytest.skip(f"sat draw_history.csv not found at {_HIST_PATH}")
    return _load_history()


@pytest.fixture(scope="module")
def idx(history) -> dict[str, int]:
    return {r["draw"]: i for i, r in enumerate(history)}


# ── §8.1 all_wt rel D4689 ───────────────────────────────────────────────────
FIX_8_1 = [
    [15, 17, 24, 28, 36, 37], [3, 6, 9, 14, 21, 22], [12, 16, 30, 31, 40, 43],
    [10, 25, 44], [8, 19], [11, 20], [23, 32, 33, 39], [2], [18, 29, 34, 45],
    [41], [4, 5, 13], [1], [27], [35], [7], [26, 42], [38],
]


def test_block_layout_matches_fixture_8_1(history, idx):
    assert block_layout(idx["4689"], history, POOL) == FIX_8_1


# ── §8.2 all_wt rel D4687 (CORRECTED: {24,35} share SL15) ───────────────────
FIX_8_2 = [
    [3, 6, 9, 14, 21, 22], [12, 16, 30, 31, 40, 43], [10, 25, 44],
    [8, 19, 28, 36], [11, 20], [23, 32, 33, 39], [2, 17, 37], [18, 29, 34, 45],
    [41], [15], [4, 5, 13], [1], [27], [24, 35], [7], [26, 42], [38],
]


def test_block_layout_matches_fixture_8_2_corrected(history, idx):
    assert block_layout(idx["4687"], history, POOL) == FIX_8_2


def test_24_and_35_share_sl_block_rel_4687(history, idx):
    """Regression for the spec-sheet slip: 24 & 35 co-occurred at D4657, so
    they must land in the same SL block relative to D4687."""
    sl = since_last_map(idx["4687"], history, POOL)
    assert sl[24] == sl[35]


# ── §8.3 newest-column decoration for D4691 ─────────────────────────────────
def test_decorate_newest_d4691(history, idx):
    skeleton = block_layout(idx["4689"], history, POOL)  # P's skeleton
    winners = history[idx["4691"]]["nums"]
    dec = decorate_newest(skeleton, winners)

    assert dec["top"] == [4, 8, 15, 32, 43, 44]

    fills = dec["fills"]
    # None => white wall; otherwise the fill candidate's number
    assert fills[15] is None          # below=17, both blue -> wall
    assert fills[43] is None          # only 40, both pink -> wall
    assert fills[4] is None           # only 5, both yellow -> wall
    assert fills[44] == 25            # 25 gray contrasts pink 44
    assert fills[8] == 19             # 19 blue contrasts yellow 8
    assert fills[32] == 23            # 23 gray beats 33 green (contrast + nearer/above)


def test_catch_fill_band_contrast_holds(history, idx):
    """Every non-wall fill must actually contrast the vanished number's band."""
    skeleton = block_layout(idx["4689"], history, POOL)
    winners = history[idx["4691"]]["nums"]
    fills = decorate_newest(skeleton, winners)["fills"]
    for hole, fill in fills.items():
        if fill is not None:
            assert band_of(fill) != band_of(hole)


# ── §8.4 deep shade ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("draw, expected", [
    ("4691", {15}), ("4689", set()), ("4687", set()),
    ("4685", {30, 31, 43}), ("4681", {19, 28}), ("4677", {33}), ("4673", {45}),
])
def test_deep_repeats(history, idx, draw, expected):
    assert deep_repeats(idx[draw], history) == expected


# ── §8.5 structural invariants ──────────────────────────────────────────────
@pytest.mark.parametrize("draw", ["4691", "4689", "4687", "4685", "4681"])
def test_block_invariants(history, idx, draw):
    blocks = block_layout(idx[draw], history, POOL)
    # every number 1..45 exactly once
    flat = [n for blk in blocks for n in blk]
    assert sorted(flat) == list(range(1, POOL + 1))
    # each block ascending
    for blk in blocks:
        assert blk == sorted(blk)
    # blocks ordered by strictly ascending SL
    sl = since_last_map(idx[draw], history, POOL)
    block_sls = [sl[blk[0]] for blk in blocks]
    assert block_sls == sorted(set(block_sls))


def test_band_of_boundaries():
    assert [band_of(n) for n in (1, 9)] == [0, 0]
    assert [band_of(n) for n in (10, 19)] == [1, 1]
    assert [band_of(n) for n in (20, 29)] == [2, 2]
    assert [band_of(n) for n in (30, 39)] == [3, 3]
    assert [band_of(n) for n in (40, 45)] == [4, 4]


# ── §8.5 unseen rule (synthetic short history) ──────────────────────────────
def test_unseen_numbers_collapse_to_single_trailing_block():
    # pool 5, history where 4 and 5 never appear
    hist = [
        {"nums": {1, 2}},   # newest (idx0)
        {"nums": {2, 3}},
        {"nums": {1, 3}},   # oldest
    ]
    blocks = block_layout(0, hist, pool=5)
    # 1 -> SL0, 2 -> SL0; 3 -> SL1; 4,5 -> unseen sentinel (single trailing block)
    assert blocks[0] == [1, 2]
    assert blocks[-1] == [4, 5]          # unseen collapsed together, ascending
    flat = [n for blk in blocks for n in blk]
    assert sorted(flat) == [1, 2, 3, 4, 5]


# ── Addendum 1: recursive column alignment ──────────────────────────────────
def _coarse(cells):
    """Collapse cell kind to alignment classes: spacer stays, everything else
    (num/empty) is a filled 'cell' row."""
    return ["spacer" if c[0] == "spacer" else "cell" for c in cells]


def test_recursion_identity_grid_equals_child_holed(history, idx):
    """Addendum test 1: col(D4689)'s grid below its top block == col(D4687)'s
    full grid with D4689's winners holed, cell-for-cell."""
    dis = [idx["4691"], idx["4689"], idx["4687"]]
    structs = column_structures(dis, history, POOL)
    w4689 = set(history[idx["4689"]]["nums"])
    offset = len(w4689) + 1  # top block + spacer
    child = structs[2]       # col(D4687) structure
    expected = [("empty",) if (c[0] == "num" and c[1] in w4689) else c for c in child]
    assert structs[1][offset:] == expected


def test_alignment_invariant_four_column_window(history, idx):
    """Addendum test 2: for every adjacent pair, col(d_j)'s grid region below
    its top block aligns row-for-row (coarse) with col(d_{j+1})'s full grid."""
    dis = [idx["4691"], idx["4689"], idx["4687"], idx["4685"]]
    structs = column_structures(dis, history, POOL)
    for j in range(len(dis) - 1):
        wj = len(history[dis[j]]["nums"])
        offset = wj + 1
        assert _coarse(structs[j][offset:]) == _coarse(structs[j + 1])


def test_render_fresh_vs_inherited_holes(history, idx):
    """Addendum test 3: fresh holes carry a catch fill (number) or None (wall);
    inherited empties render as plain gaps with no fill."""
    dis = [idx["4691"], idx["4689"], idx["4687"]]
    cols = render_columns(dis, history, POOL)
    newest = cols[0]
    kinds = {c[0] for c in newest}
    assert "hole" in kinds          # fresh W_0 holes exist
    assert "gap" in kinds           # inherited empties exist
    # holes hold either an int fill or None; gaps carry nothing extra
    for c in newest:
        if c[0] == "hole":
            assert c[1] is None or isinstance(c[1], int)
        if c[0] == "gap":
            assert len(c) == 1


def test_newest_column_recursive_fills_match_8_3(history, idx):
    """Addendum re-derivation: the newest column's fresh-hole fills, computed
    over the recursive structure, still match fixture 8.3."""
    dis = [idx["4691"], idx["4689"], idx["4687"]]
    structs = column_structures(dis, history, POOL)
    w0 = set(history[idx["4691"]]["nums"])
    fills = {}
    for i, c in enumerate(structs[1]):
        if c[0] == "num" and c[1] in w0:
            fills[c[1]] = _catch_over_cells(structs[1], i, w0)
    assert fills[15] is None
    assert fills[43] is None
    assert fills[4] is None
    assert fills[44] == 25
    assert fills[8] == 19
    assert fills[32] == 23


@pytest.mark.parametrize("ncols", [1, 2, 3, 5, 8])
def test_every_column_has_each_number_once(history, idx, ncols):
    """Addendum test 4: each column contains all 45 numbers exactly once
    (winners in the top block, the rest in the grid; holes/gaps are not nums)."""
    dis = list(range(ncols))  # newest-first indices into full history
    cols = render_columns(dis, history, POOL)
    for col in cols:
        nums = sorted(c[1] for c in col if c[0] == "num")
        assert nums == list(range(1, POOL + 1))


def test_deep_lives_in_one_column_only(history, idx):
    """Deep shade is per-column: a big window whose newest column embeds
    D4685's block still shows deep only for the newest draw's own repeats."""
    dis = list(range(6))  # D4691 … D4681
    cols = render_columns(dis, history, POOL)
    newest_deep = {c[1] for c in cols[0] if c[0] == "num" and c[2]}
    assert newest_deep == {15}                         # only D4691's repeat
    # the column whose seed/own draw is D4685 shows its own repeats
    d4685_col = cols[dis.index(idx["4685"])]
    d4685_deep = {c[1] for c in d4685_col if c[0] == "num" and c[2]}
    assert d4685_deep == {30, 31, 43}


def test_column_pads_formula(history, idx):
    dis = [idx["4691"], idx["4689"], idx["4687"], idx["4685"]]
    pads = column_pads(dis, history)
    # sat picks 6 -> +7 per column
    assert pads == [0, 7, 14, 21]
