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
    group_rail_flags,
    reclaim_window_dead_runs,
    render_columns,
    since_last_map,
    visible_group_count,
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
    full grid with D4689's winners holed (kind-aware), cell-for-cell."""
    dis = [idx["4691"], idx["4689"], idx["4687"]]
    structs = column_structures(dis, history, POOL)
    w4689 = set(history[idx["4689"]]["nums"])
    offset = len(w4689) + 1  # top block + spacer
    child = structs[2]       # col(D4687) structure (seed: nums + spacers only)
    expected = []
    for i, c in enumerate(child):
        if c[0] == "num" and c[1] in w4689:
            fill = _catch_over_cells(child, i, w4689)
            expected.append(("hole", "caught" if fill is not None else "wall"))
        else:
            expected.append(c)
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


def test_holes_carry_persistent_kind_no_gaps(history, idx):
    """Addendum test 3 (round 5): every empty cell is a coloured hole carrying
    "wall"/"caught" — there are no blank gap cells, and hole colour persists
    into newer columns."""
    dis = [idx["4691"], idx["4689"], idx["4687"]]
    cols = render_columns(dis, history, POOL)
    for col in cols:
        for c in col:
            assert c[0] in ("num", "hole", "spacer")   # no "gap"/"empty" kinds
            if c[0] == "hole":
                assert c[1] in ("wall", "caught")
    # newest column must contain fresh holes; both wall and caught occur today
    newest = cols[0]
    hole_kinds = {c[1] for c in newest if c[0] == "hole"}
    assert "wall" in hole_kinds and "caught" in hole_kinds


def test_wall_kind_persists_into_newer_column(history, idx):
    """15's wall (created when it left D4689's top block, below 17 same band)
    must still be a wall in the newer D4691 column — colour persists."""
    dis = [idx["4691"], idx["4689"], idx["4687"]]
    structs = column_structures(dis, history, POOL)
    # 15 exits at D4689 (col index 1): its old rel-4687 singleton position is a
    # wall there and stays a wall in col(D4691) (index 0).
    assert ("hole", "wall") in structs[1]
    assert ("hole", "wall") in structs[0]


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
    D4685's block still shows deep only for the newest draw's own repeats.
    Anchored by draw ID (not raw range) so it survives new draws landing in
    draw_history.csv."""
    dis = [idx[d] for d in ("4691", "4689", "4687", "4685", "4683", "4681")]
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


# ── Addendum 1, Visual round 3: group rail + visible group count ────────────
def test_visible_group_count_mid_hole_counts_as_one():
    cells = [("num", 8, False), ("hole", "caught"), ("num", 19, False)]  # one run
    assert visible_group_count(cells) == 1


def test_visible_group_count_all_hole_runs_count_zero():
    cells = [
        ("num", 8, False), ("spacer",),
        ("hole", "wall"), ("hole", "caught"), ("spacer",),  # all-hole block -> 0
        ("hole", "wall"),                                    # lone wall block -> 0
    ]
    # only the first run holds a surviving number
    assert visible_group_count(cells) == 1


def test_group_rail_spans_first_to_last_visible():
    cells = [("hole", "wall"), ("num", 5, False), ("hole", "caught"),
             ("num", 9, False), ("spacer",)]
    flags = group_rail_flags(cells)
    # run has a number, so the whole run (incl. its holes) is railed
    assert flags == [True, True, True, True, False]


def test_group_rail_all_hole_run_has_no_rail():
    cells = [("hole", "wall"), ("hole", "caught")]
    assert group_rail_flags(cells) == [False, False]


def test_group_rail_lone_wall_run_has_no_rail():
    # a run of only a white wall (winner emigrated) is not a group -> no rail
    cells = [("num", 8, False), ("spacer",), ("hole", "wall"), ("spacer",)]
    assert group_rail_flags(cells) == [True, False, False, False]
    assert visible_group_count(cells) == 1


@pytest.mark.parametrize("ncols", [1, 2, 3, 5, 10])
def test_group_count_identity_matches_distinct_sl(history, idx, ncols):
    """Addendum test 6: for every displayed column, visible_group_count equals
    the number of distinct SL values relative to that draw (the Since-Last
    grouping 'max groups' actually consumes)."""
    dis = list(range(ncols))
    cols = render_columns(dis, history, POOL)
    for j, col in enumerate(cols):
        distinct_sl = len(set(since_last_map(dis[j], history, POOL).values()))
        assert visible_group_count(col) == distinct_sl


# ── window-global reclamation (reclaim_window_dead_runs) ─────────────────────
# The redesign: an SL run's shared-grid space is reclaimed only if the run is
# dead (zero survivors) across the WHOLE displayed window — evaluated once, and
# removed UNIFORMLY from every column so no surviving number ever shifts row.
# For the full-range export (oldest column = clean seed) nothing is reclaimed;
# savings appear in a recent sub-window of the full skeleton.

def _num_rows(cols, pads):
    """{number: absolute_row} per column, for numbers shown as a num."""
    return [{c[1]: pads[j] + i for i, c in enumerate(col) if c[0] == "num"}
            for j, col in enumerate(cols)]


def _row_position_violations(cols, pads, dis, history):
    """A number that is a num in two adjacent displayed columns and did NOT win
    at the newer draw must sit at the same absolute row (the regression we fix)."""
    nr = _num_rows(cols, pads)
    v = 0
    for j in range(len(dis) - 1):
        winners_newer = set(history[dis[j]]["nums"])
        for x in set(nr[j]) & set(nr[j + 1]):
            if x not in winners_newer and nr[j][x] != nr[j + 1][x]:
                v += 1
    return v


def _is_subsequence(small, big):
    it = iter(big)
    return all(cell in it for cell in small)


def test_reclaim_full_window_is_noop(history, idx):
    """Displaying the whole history reclaims nothing — its oldest column is the
    clean all_wt seed (no dead run) — so the aligned view is returned unchanged."""
    dis = list(range(len(history)))
    cols = render_columns(dis, history, POOL)
    pads = column_pads(dis, history)
    rcols, rpads = reclaim_window_dead_runs(cols, pads, dis)
    assert rcols == cols
    assert rpads == pads


def test_reclaim_full_window_has_no_row_position_drift(history, idx):
    """The full-range export view (every column displayed): zero row-position
    violations — the alignment regression the window-global rule restores."""
    dis = list(range(len(history)))
    cols = render_columns(dis, history, POOL)
    pads = column_pads(dis, history)
    rcols, rpads = reclaim_window_dead_runs(cols, pads, dis)
    assert _row_position_violations(rcols, rpads, dis, history) == 0


def test_reclaim_recent_window_saves_space_without_drift(history, idx):
    """A recent sub-window of the full skeleton: dead-throughout runs are
    reclaimed (real space saving) yet no surviving number shifts row (0
    violations), N-grp is unchanged, and every number still appears once."""
    full = list(range(len(history)))
    cols = render_columns(full, history, POOL)
    pads = column_pads(full, history)
    dis = list(range(min(10, len(history))))            # newest ≤10 draws
    rcols, rpads = reclaim_window_dead_runs(cols, pads, dis)

    assert sum(len(c) for c in rcols) < sum(len(cols[j]) for j in dis)   # saved
    assert _row_position_violations(rcols, rpads, dis, history) == 0
    assert ([visible_group_count(cols[j]) for j in dis]
            == [visible_group_count(c) for c in rcols])                  # N-grp
    for col in rcols:
        assert sorted(c[1] for c in col if c[0] == "num") == list(range(1, POOL + 1))


def test_reclaim_removes_rows_uniformly(history, idx):
    """Reclamation only ever DROPS rows (never reorders/edits): each displayed
    column's result is a subsequence of its aligned column — the uniform removal
    that keeps every column mutually aligned."""
    full = list(range(len(history)))
    cols = render_columns(full, history, POOL)
    pads = column_pads(full, history)
    dis = list(range(min(10, len(history))))
    rcols, _ = reclaim_window_dead_runs(cols, pads, dis)
    for k, j in enumerate(dis):
        assert _is_subsequence(rcols[k], cols[j])


def test_reclaim_empty_window():
    assert reclaim_window_dead_runs([], [], []) == ([], [])
