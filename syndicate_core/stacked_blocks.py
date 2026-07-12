"""
Pure block/decoration logic for the Stacked Draws "Blocked flat (all_wt)" view.

Lives in syndicate_core — not masterapp — so it is import-safe and unit
testable (masterapp.py runs Streamlit page code at import time and cannot be
imported by the test suite). No Streamlit, no I/O, no colour hex here: this
module speaks in numbers and *band indices* only; the UI maps band/number to
the app's existing palette (`_num_colour`) so there is no parallel palette.

`history` everywhere is the newest-first list of draws the UI already builds:
each item is a mapping with a ``"nums"`` set of that draw's winning numbers.
SL is always computed against the FULL history passed in (never a slider
slice) — see the Blocked-flat spec §2.

RECURSIVE COLUMN ALIGNMENT (Addendum 1, supersedes spec §3): displayed draws
d_0 (newest, left) … d_k (oldest, right). col(d_k) is the clean all_wt seed
(block_layout). Each newer col(d_j) = W_j top block + spacer + the FULL grid of
col(d_{j+1}) with each W_j member holed. Older winner positions therefore
persist as gaps in newer columns, so every column's grid aligns cell-for-cell
(alignment invariant, asserted in tests).

Verified against hand fixtures in tests/test_stacked_blocks.py (spec §8 +
Addendum 1).
"""
from __future__ import annotations

from typing import Mapping, Sequence

# Band boundaries — value ranges that share one colour, mirroring
# masterapp._num_colour. Only the *grouping* lives here (needed for the
# catch-fill contrast rule); the hex values stay in the UI.
_BAND_MAX = (9, 19, 29, 39)  # >39 falls through to the last (pink) band


def band_of(n: int) -> int:
    """Return the band index (0..4) a number belongs to.

    0: 1–9 · 1: 10–19 · 2: 20–29 · 3: 30–39 · 4: 40+
    Two numbers "contrast" iff their band indices differ.
    """
    for i, hi in enumerate(_BAND_MAX):
        if n <= hi:
            return i
    return len(_BAND_MAX)


def since_last_map(draw_idx: int, history: Sequence[Mapping], pool: int) -> dict[int, int]:
    """SL(n) for every number 1..pool at ``history[draw_idx]`` (newest-first).

    SL(n) = draws since n last appeared, counted at this draw:
      0 if n is in this draw, j if n is in the draw j steps older.
    A number never seen from this draw backwards gets the sentinel
    ``len(history) - draw_idx`` (strictly larger than any real SL), which the
    unseen rule (see :func:`block_layout`) collapses into one trailing block.
    """
    sl: dict[int, int] = {}
    for num in range(1, pool + 1):
        for back in range(draw_idx, len(history)):
            if num in history[back]["nums"]:
                sl[num] = back - draw_idx
                break
        else:
            sl[num] = len(history) - draw_idx
    return sl


def block_layout(draw_idx: int, history: Sequence[Mapping], pool: int) -> list[list[int]]:
    """The all_wt block layout for ``history[draw_idx]``.

    Returns blocks ordered by SL ascending (SL0 on top); each block is the
    numbers sharing that SL, ascending. Every number 1..pool appears exactly
    once. Unseen numbers share the sentinel SL and therefore fall into a single
    trailing block at the bottom automatically (spec §2 unseen rule).
    """
    sl = since_last_map(draw_idx, history, pool)
    by_sl: dict[int, list[int]] = {}
    for num in range(1, pool + 1):
        by_sl.setdefault(sl[num], []).append(num)
    return [sorted(by_sl[s]) for s in sorted(by_sl)]


def deep_repeats(draw_idx: int, history: Sequence[Mapping]) -> set[int]:
    """Numbers that repeat at ``history[draw_idx]`` — in this draw AND the one
    immediately before it (spec §5). Empty for the oldest draw in history.
    Deep cells therefore always sit in this draw's SL0 / top block.
    """
    cur: set = set(history[draw_idx]["nums"])
    prev: set = set(history[draw_idx + 1]["nums"]) if draw_idx + 1 < len(history) else set()
    return cur & prev


# ── catch-fill contrast rule (spec §4) ──────────────────────────────────────
def _choose_catch(vband: int, up, down):
    """Pick the catch-fill number for a hole from its two candidates.

    ``up``/``down`` are ``(distance, number)`` or ``None`` — the nearest
    surviving number above / below in the same block run. Prefer a candidate
    whose band contrasts the vanished number's ``vband``; among contrasting
    candidates take the nearer, ties → above. No contrast (or no candidate) →
    ``None`` (white wall).
    """
    cands = []
    if up is not None:
        cands.append((up[0], 0, up[1]))    # 0 => above (wins ties)
    if down is not None:
        cands.append((down[0], 1, down[1]))  # 1 => below
    contrast = [c for c in cands if band_of(c[2]) != vband]
    if not contrast:
        return None
    contrast.sort(key=lambda c: (c[0], c[1]))
    return contrast[0][2]


def decorate_newest(skeleton: Sequence[Sequence[int]], winners) -> dict:
    """Single-level decoration of a skeleton (spec §4).

    ``skeleton`` = the previous draw's :func:`block_layout`. ``winners`` = the
    newest draw's winning numbers. Returns
    ``{"top": [w ascending], "fills": {w: fill_num_or_None}}`` (None => wall).

    This is the non-recursive form (one column against a clean skeleton). The
    recursive view (:func:`render_columns`) computes fills over composed cell
    structures instead, but both share :func:`_choose_catch` and agree on the
    §8.3 fixture.
    """
    wset = set(winners)
    fills: dict[int, int | None] = {}
    for block in skeleton:
        blk = list(block)
        for pos, num in enumerate(blk):
            if num not in wset:
                continue
            vband = band_of(num)
            up = None
            for j in range(pos - 1, -1, -1):
                if blk[j] not in wset:
                    up = (pos - j, blk[j])
                    break
            down = None
            for j in range(pos + 1, len(blk)):
                if blk[j] not in wset:
                    down = (j - pos, blk[j])
                    break
            fills[num] = _choose_catch(vband, up, down)
    return {"top": sorted(wset), "fills": fills}


# ── recursive column structures (Addendum 1) ────────────────────────────────
# Structural cell kinds (colour-free, used for recursion + alignment tests):
#   ("num", n) · ("empty",) · ("spacer",)
# Render cell kinds (what the UI draws):
#   ("num", n, deep_bool) · ("hole", fill_num_or_None) · ("gap",) · ("spacer",)

def _run_bounds(cells: Sequence, i: int) -> tuple[int, int]:
    """Inclusive bounds (start, end) of the non-spacer run containing index i.
    Spacer rows are walls the run never crosses."""
    start = i
    while start - 1 >= 0 and cells[start - 1][0] != "spacer":
        start -= 1
    end = i
    while end + 1 < len(cells) and cells[end + 1][0] != "spacer":
        end += 1
    return start, end


def _catch_over_cells(cells: Sequence, i: int, winners) -> int | None:
    """Catch fill for a fresh hole at structural-cell index ``i``.

    ``cells`` is the child column's structural cells; index ``i`` holds a
    ``("num", n)`` whose ``n`` is a winner (about to be holed). Candidates are
    the nearest surviving number above / below within the same run — surviving
    = a ``("num", m)`` with ``m`` NOT a winner; all empty cells (fresh or
    inherited holes) and other winner cells are skipped. Returns the fill
    number, or ``None`` for a white wall.
    """
    vnum = cells[i][1]
    vband = band_of(vnum)
    start, end = _run_bounds(cells, i)
    up = None
    j = i - 1
    while j >= start:
        c = cells[j]
        if c[0] == "num" and c[1] not in winners:
            up = (i - j, c[1])
            break
        j -= 1
    down = None
    j = i + 1
    while j <= end:
        c = cells[j]
        if c[0] == "num" and c[1] not in winners:
            down = (j - i, c[1])
            break
        j += 1
    return _choose_catch(vband, up, down)


def _seed_structure(draw_idx: int, history: Sequence[Mapping], pool: int) -> list[tuple]:
    """Structural cells for the oldest displayed (seed) column: its clean
    all_wt, blocks separated by one spacer."""
    cells: list[tuple] = []
    for bi, blk in enumerate(block_layout(draw_idx, history, pool)):
        if bi:
            cells.append(("spacer",))
        for n in blk:
            cells.append(("num", n))
    return cells


def column_structures(draw_indices: Sequence[int], history: Sequence[Mapping],
                      pool: int) -> list[list[tuple]]:
    """Structural cells for each displayed column.

    ``draw_indices`` are the displayed draws newest-first ([d_0 … d_k], indices
    into ``history``). Returns a newest-first list aligned to ``draw_indices``.
    col(d_k) is the seed; col(d_j<k) = W_j top block + spacer + col(d_{j+1})
    with each W_j member turned into a hole.

    Cell kinds: ``("num", n)``, ``("hole", "wall"|"caught")``, ``("spacer",)``.
    A hole's kind is decided once, in the column where its number exited (wall
    if no contrasting neighbour, else caught), and every newer column INHERITS
    that same kind unchanged — hole colour is a permanent record, not a
    one-column decoration (Addendum 1, Visual round 5). Deep shade is the only
    per-column decoration, applied later in :func:`render_columns`.
    """
    k = len(draw_indices) - 1
    structs: list[list[tuple]] = [[] for _ in draw_indices]
    structs[k] = _seed_structure(draw_indices[k], history, pool)
    for j in range(k - 1, -1, -1):
        winners = set(history[draw_indices[j]]["nums"])
        child = structs[j + 1]
        cells: list[tuple] = [("num", n) for n in sorted(winners)]
        cells.append(("spacer",))
        for idx, c in enumerate(child):
            if c[0] == "num":
                if c[1] in winners:                       # fresh exit → new hole
                    fill = _catch_over_cells(child, idx, winners)
                    cells.append(("hole", "caught" if fill is not None else "wall"))
                else:
                    cells.append(("num", c[1]))
            elif c[0] == "hole":
                cells.append(c)                            # inherited — colour persists
            else:
                cells.append(("spacer",))
        structs[j] = cells
    return structs


def render_columns(draw_indices: Sequence[int], history: Sequence[Mapping],
                   pool: int) -> list[list[tuple]]:
    """Render-ready cells for each displayed column (newest-first).

    Render cell kinds: ``("num", n, deep)``, ``("hole", "wall"|"caught")``,
    ``("spacer",)``. Hole kinds come straight from :func:`column_structures`
    (they persist across columns); the only thing added here is per-column deep
    shading, which lands only on the column's own top block (spec §5) because
    ``deep_repeats(d_j) ⊆ W_j`` and a winner's inherited occurrences are holes,
    not numbers.
    """
    if not draw_indices:
        return []
    structs = column_structures(draw_indices, history, pool)
    out: list[list[tuple]] = []
    for j, di in enumerate(draw_indices):
        deep = deep_repeats(di, history)
        col: list[tuple] = []
        for c in structs[j]:
            if c[0] == "num":
                col.append(("num", c[1], c[1] in deep))
            else:
                col.append(c)                              # hole (with kind) or spacer
        out.append(col)
    return out


def column_pads(draw_indices: Sequence[int], history: Sequence[Mapping]) -> list[int]:
    """Top-padding (blank rows) per displayed column so the recursive grids
    line up: pad(d_0)=0, pad(d_j)=pad(d_{j-1}) + |W_{d_{j-1}}| + 1 (Addendum 1).
    """
    pads = [0] * len(draw_indices)
    for j in range(1, len(draw_indices)):
        prev_w = len(history[draw_indices[j - 1]]["nums"])
        pads[j] = pads[j - 1] + prev_w + 1
    return pads


# ── group clarity: rail + visible group count (Addendum 1, Visual round 3) ───
# A "group" is an SL group: a spacer-bounded run that still holds a surviving
# NUMBER. Holes and white walls (numbers that emigrated to a newer top block)
# do NOT make a group — otherwise the count would exceed the distinct SL count
# and diverge from the 'max groups' grouping (decision 6 wins over decision 5's
# looser "non-gap" wording; confirmed with Tai 2026-07-11). The rail still
# spans holes/walls, but only inside a run that has a number.

def visible_group_count(cells: Sequence) -> int:
    """Number of SL groups visible in a column: spacer-bounded runs that hold
    at least one ``("num", …)`` cell. A run split only by inherited holes still
    counts as ONE group; an all-hole run counts as ZERO. Equals the number of
    distinct SL values for the column's draw (asserted in tests) — this is the
    count Tai reads to set 'max groups'."""
    count = 0
    run_has_num = False
    in_run = False
    for c in cells:
        if c[0] == "spacer":
            if in_run and run_has_num:
                count += 1
            in_run, run_has_num = False, False
        else:
            in_run = True
            if c[0] == "num":
                run_has_num = True
    if in_run and run_has_num:
        count += 1
    return count


def group_rail_flags(cells: Sequence) -> list[bool]:
    """Per-cell flag: does this cell carry the group rail? A run is railed only
    if it holds a surviving number; within such a run the rail spans from its
    first to its last visible cell — num or hole (wall/caught) — passing through
    any cells in between. Cells outside that span, spacers, and all-hole runs
    get no rail (Addendum 1, decisions 4 + num-only count)."""
    flags = [False] * len(cells)
    n = len(cells)
    i = 0
    while i < n:
        if cells[i][0] == "spacer":
            i += 1
            continue
        j = i
        while j < n and cells[j][0] != "spacer":
            j += 1
        if any(cells[k][0] == "num" for k in range(i, j)):
            visible = [k for k in range(i, j) if cells[k][0] in ("num", "hole")]
            for k in range(visible[0], visible[-1] + 1):
                flags[k] = True
        i = j
    return flags
