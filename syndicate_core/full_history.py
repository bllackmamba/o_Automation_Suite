"""syndicate_core/full_history.py — full-range draw history via B1 + splice.

The Stacked Draws "Blocked flat (all_wt)" view (and its Flat-rank / Cascading
siblings) compute Since-Last purely from a chronological, newest-first list of
draws — see ``stacked_blocks.since_last_map`` — never from the lottolyzer R
snapshot (``since_last.json``). Their only data feed is ``draw_history.csv``,
which is itself lottolyzer-sourced (``scraping.fetch_draw_history`` → the
``/history/`` URL) and therefore shallow (~150 recent draws for sat, 4403→4701).

To reach the full research range (sat draws ~2761→4701) we splice the two
sources this module knows about:

* **B1** (``B1_{gk}_updated.csv``) — the authoritative full win history, 970
  draws, newest-first, winning numbers in ``pos_*`` / ``w*`` columns. It is the
  ONLY source that reaches the deep floor (~2761), but its ``update`` draw-number
  column is populated for only a handful of rows and it has no dates.
* **draw_history.csv** — shallow but carries EXPLICIT draw numbers and dates,
  and reaches one draw newer than B1 (4701 vs B1's 4699).

The splice therefore uses draw_history for the very top (the draws B1 lacks) and
B1 for everything else, assigning every B1 row a real draw number by
extrapolating draw_history's explicit numbering from a verified anchor. Crucially
it **validates the overlap**: the draws present in BOTH sources must agree on
their winning-number sets before the join is trusted (``overlap_agree``). This is
pure/import-safe (no Streamlit, no I/O beyond the DataFrames handed in) so it is
unit-testable; masterapp stays UI-only.

SCOPE NOTE (2026-08-11 decision): only the OVERLAP-validated window
(~4403->4701 for sat: the 149-draw B1 n draw_history overlap + the confirmed top
draw 4701) is trusted for pattern-finding today. The deeper B1-only tail
(2761->4403) is real winning-number data, but its per-draw NUMBER LABELS are
extrapolated here (anchor - step*i), NOT externally verified -- so that range is
built-but-PARKED infrastructure. **Deferred follow-up: externally verify the
deep draw-number labels** before relying on the 2761->4403 range. Until then the
UI defaults History source to "Lottolyzer (recent)" (= the validated window) and
the splice is opt-in only.
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

import pandas as pd

from syndicate_core.pipeline import b1_ball_columns
from syndicate_core.refgroup import parse_draw_numbers

# A draw record is the same shape masterapp's Stacked Draws builder uses:
#   {"draw": str, "date": str, "nums": set[int]}
DrawRecord = dict


def _is_int_str(s: str) -> bool:
    return str(s).strip().lstrip("-").isdigit()


def draw_history_records(dh_df: pd.DataFrame) -> list[DrawRecord]:
    """draw_history.csv → newest-first records (order preserved as in the file).

    Expects the fetched schema ``draw, date, numbers`` where ``numbers`` is a
    ``"[1, 5, 12, …]"`` string. Rows whose ``numbers`` parse to an empty set are
    dropped (defensive — a blank/malformed row must not become a phantom draw).
    """
    recs: list[DrawRecord] = []
    for _, r in dh_df.iterrows():
        nums = set(parse_draw_numbers(r.get("numbers", "")))
        if not nums:
            continue
        recs.append({
            "draw": str(r.get("draw", "")).strip(),
            "date": str(r.get("date", ""))[:10],
            "nums": nums,
        })
    return recs


def b1_records(b1_df: pd.DataFrame, pick: int) -> list[DrawRecord]:
    """B1 frame → newest-first records (file order = newest-first for B1).

    Ball columns are detected via :func:`b1_ball_columns` (rename-proof), so a
    future ``pos_`` → ``w_`` rename cannot break the reader. ``draw`` carries
    B1's own ``update`` value where present (mostly blank) — real draw numbers
    are assigned later by the splice; ``date`` is unknown from B1 alone.
    """
    cols = b1_ball_columns(b1_df, pick)
    if not cols:
        raise ValueError("B1 frame has no detectable ball columns")
    recs: list[DrawRecord] = []
    for _, r in b1_df.iterrows():
        nums: set[int] = set()
        for c in cols:
            v = pd.to_numeric(r[c], errors="coerce")
            if pd.notna(v):
                nums.add(int(v))
        if not nums:
            continue
        recs.append({"draw": str(r.get("update", "")).strip(), "date": "", "nums": nums})
    return recs


def infer_step(dh_records: Sequence[DrawRecord]) -> int:
    """Draw-number step from draw_history's explicit, newest-first numbering.

    Uses the most common positive consecutive difference (sat = 2). Raises if no
    positive difference is derivable (e.g. no numeric draw labels).
    """
    draws = [int(r["draw"]) for r in dh_records if _is_int_str(r["draw"])]
    diffs = [draws[i] - draws[i + 1] for i in range(len(draws) - 1)]
    pos = [d for d in diffs if d > 0]
    if not pos:
        raise ValueError("cannot infer draw step from draw history numbering")
    return Counter(pos).most_common(1)[0][0]


def best_offset(b1: Sequence[DrawRecord], dh: Sequence[DrawRecord],
                max_offset: int = 12) -> tuple[int, int, int]:
    """Find the offset aligning B1 to draw_history by winning-number sets.

    Both lists are newest-first. Returns ``(offset, mismatches, overlap_n)`` for
    the offset ``o`` (draw_history is newer at the top by ``o`` draws) that
    MINIMISES the mismatch rate over the full overlap ``b1[i] vs dh[i+o]``. The
    caller trusts the join only when ``mismatches == 0``. Content-based (not
    draw-number based) precisely because B1's own draw numbers are unreliable.
    """
    best: tuple[int, int, int] | None = None
    best_rate = 2.0
    for o in range(min(max_offset, len(dh))):
        n = min(len(b1), len(dh) - o)
        if n <= 0:
            continue
        mm = sum(1 for i in range(n) if b1[i]["nums"] != dh[i + o]["nums"])
        rate = mm / n
        if rate < best_rate:
            best_rate, best = rate, (o, mm, n)
    if best is None:
        raise ValueError("no overlap between B1 and draw history to align on")
    return best


def overlap_mismatches(b1: Sequence[DrawRecord], dh: Sequence[DrawRecord],
                       offset: int) -> list[dict]:
    """Enumerate the draws that DISAGREE between sources at ``offset``.

    Each entry: ``{b1_index, dh_draw, b1_nums, dh_nums}``. Empty ⇒ every
    overlapping draw agrees and the join is safe to trust.
    """
    n = min(len(b1), len(dh) - offset)
    out: list[dict] = []
    for i in range(n):
        if b1[i]["nums"] != dh[i + offset]["nums"]:
            out.append({
                "b1_index": i,
                "dh_draw": dh[i + offset]["draw"],
                "b1_nums": sorted(b1[i]["nums"]),
                "dh_nums": sorted(dh[i + offset]["nums"]),
            })
    return out


def build_full_history(b1_df: pd.DataFrame, dh_df: pd.DataFrame,
                       pick: int) -> tuple[list[DrawRecord], dict]:
    """Splice B1 (deep) + draw_history (top + numbering) into one full history.

    Returns ``(records, report)`` where ``records`` is newest-first
    ``{"draw", "date", "nums"}`` spanning the full range, and ``report`` carries
    the splice provenance and the overlap sanity-check result. The function does
    NOT raise on overlap disagreement — it records it in ``report["overlap_agree"]``
    / ``report["overlap_mismatches"]`` so the caller can refuse to trust an
    unverified join explicitly. It DOES raise when the sources are structurally
    unusable (empty, no ball columns, no numbering to anchor on).
    """
    b1 = b1_records(b1_df, pick)
    dh = draw_history_records(dh_df)
    if not b1:
        raise ValueError("B1 produced no draw records")
    if not dh:
        raise ValueError("draw_history produced no draw records")

    step = infer_step(dh)
    offset, mm, overlap_n = best_offset(b1, dh)
    mismatches = overlap_mismatches(b1, dh, offset)

    # Anchor: B1's newest row is the same draw as dh[offset]; take dh's explicit
    # number there and extrapolate backward by the verified step for every B1 row.
    if not _is_int_str(dh[offset]["draw"]):
        raise ValueError("anchor draw in draw_history is not numeric — cannot number B1")
    anchor = int(dh[offset]["draw"])
    dh_date_by_draw = {int(r["draw"]): r["date"] for r in dh if _is_int_str(r["draw"])}

    crosscheck: list[dict] = []
    full: list[DrawRecord] = []
    # Top: the draws only draw_history has (newer than B1), kept verbatim.
    for i in range(offset):
        full.append(dict(dh[i]))
    # Body: every B1 row, numbered from the anchor; borrow dh dates where they overlap.
    for i, rec in enumerate(b1):
        drawnum = anchor - step * i
        if _is_int_str(rec["draw"]) and int(rec["draw"]) != drawnum:
            crosscheck.append({"b1_index": i, "b1_update": int(rec["draw"]),
                               "derived": drawnum})
        full.append({"draw": str(drawnum),
                     "date": dh_date_by_draw.get(drawnum, ""),
                     "nums": rec["nums"]})

    draws_all = [int(r["draw"]) for r in full if _is_int_str(r["draw"])]
    report = {
        "n_b1": len(b1),
        "n_dh": len(dh),
        "pick": pick,
        "step": step,
        "offset": offset,
        "anchor_draw": anchor,
        "top_from_dh": [dh[i]["draw"] for i in range(offset)],
        "overlap_n": overlap_n,
        "overlap_agree": not mismatches,
        "overlap_mismatches": mismatches,
        "b1_update_crosscheck_mismatches": crosscheck,
        "n_full": len(full),
        "newest_draw": max(draws_all) if draws_all else None,
        "oldest_draw": min(draws_all) if draws_all else None,
    }
    return full, report


def records_to_df(records: Sequence[DrawRecord]) -> pd.DataFrame:
    """Records → a DataFrame in the ``draw, date, numbers`` schema of
    draw_history.csv, so the output is a drop-in feed for the existing view's
    reader (numbers rendered as a ``"[1, 5, 12]"`` string, sorted ascending).
    """
    return pd.DataFrame([
        {"draw": r["draw"], "date": r["date"],
         "numbers": "[" + ", ".join(str(n) for n in sorted(r["nums"])) + "]"}
        for r in records
    ])


def build_full_range_df(b1_df: pd.DataFrame, dh_df: pd.DataFrame,
                        pick: int) -> tuple[pd.DataFrame, dict]:
    """Convenience: :func:`build_full_history` → (draw_history-schema df, report)."""
    records, report = build_full_history(b1_df, dh_df, pick)
    return records_to_df(records), report
