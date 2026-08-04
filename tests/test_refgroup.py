"""
tests/test_refgroup.py — Reference Group (RefGroup_w1) breakdown.

Covers syndicate_core/refgroup.py: the closed-form S0..S_pick breakdown, the
Selected/Unselected split, newest-draw extraction (auto-update), and the
collation-block shape + sequential Row_ID integration.

masterapp.py cannot be imported (it runs Streamlit at import), so the
execute_collation integration is verified by replicating its exact stacking
mechanism — ``pd.concat(pieces, ignore_index=True)`` then
``Row_ID = range(1, len+1)`` — with the real ``build_ref_group_piece``. This is
the same positional assignment the pipeline uses, so it proves RefGroup_w1 gets
the next sequential ID by construction, never a hand-picked one.
"""
from math import comb

import pandas as pd
import pytest

from syndicate_core.refgroup import (
    SET_LABEL,
    SOURCE,
    build_ref_group_piece,
    classify_shared,
    empirical_stream_counts,
    hypergeometric_breakdown,
    load_newest_reference,
    locked_sc_dict,
    main_data_stream,
    newest_reference_numbers,
    parse_draw_numbers,
    selected_bands_for_pick,
    selected_unselected,
    total_space,
)

# The Lott's published fixed distribution for Saturday Lotto (pool 45, pick 6).
SAT_EXPECTED = {0: 3_262_623, 1: 3_454_542, 2: 1_233_765,
                3: 182_780, 4: 11_115, 5: 234, 6: 1}
SAT_TOTAL = 8_145_060  # C(45, 6)


# ── Closed-form breakdown ─────────────────────────────────────────────────────

def test_sat_breakdown_matches_published_constants():
    # Arrange / Act
    bd = hypergeometric_breakdown(45, 6)
    # Assert
    assert bd == SAT_EXPECTED


def test_sat_breakdown_sums_to_full_space():
    bd = hypergeometric_breakdown(45, 6)
    assert sum(bd.values()) == SAT_TOTAL == total_space(45, 6)


def test_s6_is_division_one_odds():
    # Exactly one combination shares all 6 numbers — the 8,145,060:1 jackpot.
    assert hypergeometric_breakdown(45, 6)[6] == 1


@pytest.mark.parametrize("pool,pick", [(35, 7), (47, 7), (44, 7), (45, 6)])
def test_breakdown_always_partitions_the_space(pool, pick):
    bd = hypergeometric_breakdown(pool, pick)
    assert set(bd) == set(range(pick + 1))
    assert sum(bd.values()) == comb(pool, pick)
    assert all(v >= 0 for v in bd.values())


def test_breakdown_is_identity_independent():
    # The whole premise of the panel: the distribution depends only on
    # (pool, pick), never on which numbers the reference set holds.
    assert hypergeometric_breakdown(45, 6) == hypergeometric_breakdown(45, 6)


# ── Selected / Unselected split ───────────────────────────────────────────────

def test_selected_unselected_totals():
    bd = hypergeometric_breakdown(45, 6)
    selected, unselected = selected_unselected(bd)
    assert selected == 4_871_087            # S1 + S2 + S3
    assert unselected == 3_273_973          # S0 + S4 + S5 + S6
    assert selected + unselected == SAT_TOTAL


def test_selected_is_s1_s2_s3():
    bd = hypergeometric_breakdown(45, 6)
    selected, _ = selected_unselected(bd)
    assert selected == bd[1] + bd[2] + bd[3]


def test_s0_dominates_unselected():
    # S0 alone is ~99.65% of the Unselected total (documented property).
    bd = hypergeometric_breakdown(45, 6)
    _, unselected = selected_unselected(bd)
    assert bd[0] / unselected > 0.996


# ── Newest-draw extraction (auto-update) ──────────────────────────────────────

def _history(*rows):
    """Build a newest-first draw_history-style frame from '1,2,3,…' strings."""
    return pd.DataFrame(
        [{"draw": str(4900 - i), "numbers": r} for i, r in enumerate(rows)],
        dtype=str)


def test_newest_reference_reads_row_zero_sorted():
    hist = _history("[7, 3, 22, 45, 11, 30]", "[1, 2, 3, 4, 5, 6]")
    assert newest_reference_numbers(hist, 6) == [3, 7, 11, 22, 30, 45]


def test_newest_reference_auto_updates_when_new_draw_prepended():
    hist = _history("[1, 2, 3, 4, 5, 6]")
    assert newest_reference_numbers(hist, 6) == [1, 2, 3, 4, 5, 6]
    # A new draw arrives at the top (newest-first) → picked up automatically.
    hist_new = _history("[10, 20, 30, 40, 44, 45]", "[1, 2, 3, 4, 5, 6]")
    assert newest_reference_numbers(hist_new, 6) == [10, 20, 30, 40, 44, 45]


def test_newest_reference_none_on_empty_history():
    assert newest_reference_numbers(pd.DataFrame(), 6) is None


def test_newest_reference_none_on_wrong_count():
    # A malformed newest row must not silently produce a wrong reference set.
    assert newest_reference_numbers(_history("[1, 2, 3]"), 6) is None


def test_parse_draw_numbers_handles_string_and_list():
    assert parse_draw_numbers("[1, 5, 12]") == [1, 5, 12]
    assert parse_draw_numbers([1, 5, 12]) == [1, 5, 12]


# ── load_newest_reference (read-only CSV wrapper shared by panel + CVI export) ─

def test_load_newest_reference_reads_file_row_zero_sorted(tmp_path):
    path = tmp_path / "draw_history.csv"
    _history("[7, 3, 22, 45, 11, 30]", "[1, 2, 3, 4, 5, 6]").to_csv(path, index=False)
    assert load_newest_reference(path, 6) == [3, 7, 11, 22, 30, 45]


def test_load_newest_reference_none_when_file_missing(tmp_path):
    assert load_newest_reference(tmp_path / "does_not_exist.csv", 6) is None


def test_load_newest_reference_none_on_wrong_count(tmp_path):
    path = tmp_path / "draw_history.csv"
    _history("[1, 2, 3]").to_csv(path, index=False)
    assert load_newest_reference(path, 6) is None


def test_load_newest_reference_is_read_only(tmp_path):
    # The export path must never mutate draw_history.csv.
    path = tmp_path / "draw_history.csv"
    _history("[10, 20, 30, 40, 44, 45]").to_csv(path, index=False)
    before = path.read_bytes()
    load_newest_reference(path, 6)
    assert path.read_bytes() == before


# ── Collation block shape + no w1 collision ───────────────────────────────────

def test_ref_group_piece_shape_and_labels():
    piece = build_ref_group_piece([3, 7, 11, 22, 30, 45])
    assert list(piece.columns) == ["Source", "Set_Label",
                                    "w1", "w2", "w3", "w4", "w5", "w6"]
    assert piece.loc[0, "Source"] == SOURCE == "RefGroup"
    # Distinct label — never the bare "w1" that R and B each already use.
    assert piece.loc[0, "Set_Label"] == SET_LABEL == "RefGroup_w1"
    assert piece.loc[0, "Set_Label"] != "w1"
    assert list(piece.iloc[0, 2:]) == [3, 7, 11, 22, 30, 45]


# ── Sequential Row_ID integration (mirrors execute_collation's mechanism) ─────

def _collate_like_execute(var_pieces, ref_numbers):
    """Replica of execute_collation's stack: append RefGroup last, concat, then
    assign Row_ID positionally via range(1, len+1). Same code path the app runs.
    """
    pieces = list(var_pieces) + [build_ref_group_piece(ref_numbers)]
    combined = pd.concat(pieces, axis=0, ignore_index=True)
    wcols = sorted([c for c in combined.columns if str(c).startswith("w")],
                   key=lambda x: int(x[1:]))
    combined = combined[["Source", "Set_Label"] + wcols]
    combined.insert(0, "Row_ID", range(1, len(combined) + 1))
    return combined


def _var_block(source, n_rows, width=6):
    rows = [{"Source": source, "Set_Label": f"{source}_{i}",
             **{f"w{j+1}": (i + j + 1) for j in range(width)}}
            for i in range(n_rows)]
    return pd.DataFrame(rows)


def test_ref_group_gets_last_sequential_row_id():
    combined = _collate_like_execute(
        [_var_block("B", 3), _var_block("R", 5)], [1, 2, 3, 4, 5, 6])
    ref = combined[combined["Set_Label"] == SET_LABEL]
    assert len(ref) == 1
    # Last row, Row_ID == total length (next after every variable block).
    assert int(ref.iloc[0]["Row_ID"]) == len(combined) == 9
    assert int(ref.iloc[0]["Row_ID"]) == combined["Row_ID"].max()


def test_ref_group_row_id_shifts_with_variable_counts():
    small = _collate_like_execute([_var_block("B", 2)], [1, 2, 3, 4, 5, 6])
    large = _collate_like_execute(
        [_var_block("B", 40), _var_block("D", 100)], [1, 2, 3, 4, 5, 6])
    id_small = int(small[small["Set_Label"] == SET_LABEL].iloc[0]["Row_ID"])
    id_large = int(large[large["Set_Label"] == SET_LABEL].iloc[0]["Row_ID"])
    assert id_small == 3      # 2 var rows + RefGroup
    assert id_large == 141    # 140 var rows + RefGroup
    assert id_small != id_large


def test_ref_group_never_matched_against_r_or_b_rows():
    # RefGroup's Source/Set_Label are unique in the stack → it is only ever
    # addressed as itself, never folded into R's or B's own row sets.
    combined = _collate_like_execute(
        [_var_block("B", 3), _var_block("R", 3)], [1, 2, 3, 4, 5, 6])
    labels = combined["Set_Label"].tolist()
    assert labels.count(SET_LABEL) == 1
    assert (combined["Source"] == SOURCE).sum() == 1


# ── LOCKED Repeat/No_repeat split (confirmed 2026-07-15) ──────────────────────

def test_locked_split_pick6_games():
    # sat, mwf: Selected = {1,2,3}
    assert selected_bands_for_pick(6) == (1, 2, 3)


def test_locked_split_pick7_games():
    # pb, oz, sfl: Selected = {1,2,3,4}
    assert selected_bands_for_pick(7) == (1, 2, 3, 4)


def test_locked_split_general_rule():
    # Selected = {1 .. K-3} for every K; equivalently range(1, K-2).
    for pick in range(4, 12):
        assert selected_bands_for_pick(pick) == tuple(range(1, pick - 2))


def test_zero_is_never_selected():
    # The rejected inversion: 0 (no shared numbers) must never be Selected.
    for pick in range(4, 12):
        assert 0 not in selected_bands_for_pick(pick)
        assert classify_shared(0, pick) == "No_repeat"


def test_extreme_tail_is_no_repeat():
    # Sharing K-2 / K-1 / K numbers is No_repeat, not Repeat, under the split.
    for pick in (6, 7):
        for k in (pick - 2, pick - 1, pick):
            assert classify_shared(k, pick) == "No_repeat"


def test_classify_shared_mid_range_is_repeat():
    assert classify_shared(3, 6) == "Repeat"      # sat: 3 in {1,2,3}
    assert classify_shared(4, 6) == "No_repeat"   # sat: 4 in tail
    assert classify_shared(4, 7) == "Repeat"      # pb: 4 in {1,2,3,4}
    assert classify_shared(5, 7) == "No_repeat"   # pb: 5 in tail


def test_locked_sc_dict_applies_selected_bands_to_every_position():
    scd = locked_sc_dict(["w1", "w2", "w3", "w4", "w5", "w6"], 6)
    assert set(scd) == {"w1", "w2", "w3", "w4", "w5", "w6"}
    assert all(v == [1, 2, 3] for v in scd.values())
    scd7 = locked_sc_dict(["w1", "w2"], 7)
    assert all(v == [1, 2, 3, 4] for v in scd7.values())


# ── empirical_stream_counts: real-data bucketing == closed form on full space ─

def test_empirical_stream_counts_matches_closed_form_full_space():
    from itertools import combinations
    # Full C(8,4) space as synthetic main data with n1..n4 columns.
    rows = list(combinations(range(1, 9), 4))
    main = pd.DataFrame(rows, columns=["n1", "n2", "n3", "n4"])
    res = empirical_stream_counts(main, ["n1", "n2", "n3", "n4"], [1, 2, 3, 4], 4)
    # Closed form: S_k = C(4,k)·C(4,4-k) → {0:1, 1:16, 2:36, 3:16, 4:1}
    assert res["bands"] == {0: 1, 1: 16, 2: 36, 3: 16, 4: 1}
    assert res["M"] == 70
    # Locked split for pick 4: Selected = {1}; Unselected = {0,2,3,4}
    assert res["selected"] == 16
    assert res["unselected"] == 70 - 16


def test_empirical_stream_counts_is_read_only_on_input():
    main = pd.DataFrame([[1, 2, 3, 4]], columns=["n1", "n2", "n3", "n4"])
    before = main.copy()
    empirical_stream_counts(main, ["n1", "n2", "n3", "n4"], [1, 2], 4)
    pd.testing.assert_frame_equal(main, before)


# ── Rule 1 Main-Data split (main_data_stream) ─────────────────────────────────
# LOCKED doc Rule Set 1: the Main Data pool splits on the nonzero/zero boundary,
# NOT the Rule 2 candidate {1..pick-3} bands. Repeat = shares >= 1 number with
# the reference draw; No_Repeat = shares 0. Reference-invariant (depends only on
# set sizes). These tests lock that boundary and its divergence from Rule 2.

def test_main_data_stream_zero_is_no_repeat():
    assert main_data_stream(0) == "No_Repeat"


@pytest.mark.parametrize("shared", [1, 2, 3, 4, 5, 6, 7])
def test_main_data_stream_any_nonzero_is_repeat(shared):
    assert main_data_stream(shared) == "Repeat"


def test_main_data_stream_diverges_from_rule2_on_tail():
    # The exact Rule 1 vs Rule 2 divergence: a share of 4,5,6 is Repeat under
    # Rule 1 (Main Data) but No_repeat under Rule 2 (candidate {1,2,3} bands).
    for shared in (4, 5, 6):
        assert main_data_stream(shared) == "Repeat"
        assert classify_shared(shared, 6) == "No_repeat"


def test_main_data_stream_partitions_full_sat_space_to_rule1_counts():
    # Aggregate the published S0..S6 constants by the Rule 1 boundary and confirm
    # the LOCKED-doc Main Data figures: Repeat 4,882,437 / No_Repeat 3,262,623.
    repeat = sum(c for k, c in SAT_EXPECTED.items() if main_data_stream(k) == "Repeat")
    no_repeat = sum(c for k, c in SAT_EXPECTED.items()
                    if main_data_stream(k) == "No_Repeat")
    assert no_repeat == 3_262_623
    assert repeat == 4_882_437
    assert repeat + no_repeat == SAT_TOTAL
