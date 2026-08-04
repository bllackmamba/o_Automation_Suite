"""
tests/test_formula_groups.py — Formula Group registry (step 4) + runner (step 5).

Step 4 covers the FORMULA_GROUPS registry in config.py: the four groups, their
components and escalation names, and the first CROSS-MODULE check — every
group's escalate name must resolve in syndicate_core.escalation.ESCALATIONS.
"""
from dataclasses import FrozenInstanceError
from pathlib import Path

import pandas as pd
import pytest

from syndicate_core.collation import (
    _default_narrow,
    _refgroup_w1_pivot,
    _run_formula_groups,
)
from syndicate_core.config import FORMULA_GROUPS, FormulaGroup
from syndicate_core.escalation import ESCALATIONS, EscalationContext

# Full sat C(45,6) pool — same file the main_split real-data lock uses.
SAT_FULL_POOL = (Path(__file__).resolve().parents[1]
                 / "Games" / "SAT" / "Main_Data_sat" / "Main_Data_sat.csv")
N6 = ["n1", "n2", "n3", "n4", "n5", "n6"]

# (key, label, components, escalate) — the locked 4-group layout.
EXPECTED = [
    ("G1", "R",           ("R",),                    "spread3_borderline"),
    ("G2", "D",           ("D",),                    "rule9_boundary_aggressive"),
    ("G3", "B1",          ("B1",),                   "shallow_anchor_exclude_hold"),
    ("G4", "Ep+So+Sp+B2", ("Ep", "So", "Sp", "B2"),  "rule9_boundary_aggressive"),
]


def test_four_groups_in_order():
    assert [g.key for g in FORMULA_GROUPS] == ["G1", "G2", "G3", "G4"]


def test_keys_are_unique():
    keys = [g.key for g in FORMULA_GROUPS]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("idx,expected", list(enumerate(EXPECTED)))
def test_group_fields_match(idx, expected):
    g = FORMULA_GROUPS[idx]
    key, label, comps, esc = expected
    assert isinstance(g, FormulaGroup)
    assert (g.key, g.label, g.components, g.escalate) == (key, label, comps, esc)
    assert g.target_range == (10, 20)   # per-group value, not a global constant


def test_components_are_nonempty_tuples():
    for g in FORMULA_GROUPS:
        assert isinstance(g.components, tuple)
        assert len(g.components) >= 1


def test_groups_are_frozen():
    with pytest.raises(FrozenInstanceError):
        FORMULA_GROUPS[0].key = "X"  # type: ignore[misc]


def test_every_escalate_name_resolves_in_registry():
    # Cross-module contract: config names an escalation, escalation.py provides it.
    for g in FORMULA_GROUPS:
        assert g.escalate in ESCALATIONS, f"{g.key} escalate {g.escalate!r} not in ESCALATIONS"


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 — the runner (_run_formula_groups)
# ══════════════════════════════════════════════════════════════════════════════

def _ctx() -> EscalationContext:
    return EscalationContext(ref_numbers=(3, 6, 9, 14, 21, 22), history_df=None,
                             pool=45, pick=6, game_key="sat")


def _split(n_repeat: int = 2, n_no_repeat: int = 2) -> dict:
    """A split like main_split output, including a _meta key the runner must skip."""
    return {
        "Repeat": pd.DataFrame({"n1": range(n_repeat)}),
        "No_Repeat": pd.DataFrame({"n1": range(n_no_repeat)}),
        "_meta": {"rebuilt": True},
    }


def _cands(n: int) -> pd.DataFrame:
    return pd.DataFrame({"Row_ID": range(1, n + 1), "Source": ["X"] * n,
                         "w1": range(n)})


def _collate_const(n: int):
    """collate_fn returning an n-row candidate set for any group."""
    return lambda components: _cands(n)


def _grp(key, esc="noop", target=(10, 20)):
    return FormulaGroup(key, key, ("X",), esc, target)


# ── default_narrow seam ───────────────────────────────────────────────────────

def test_default_narrow_is_identity_passthrough():
    cands = _cands(7)
    out = _default_narrow(cands, pd.DataFrame({"n1": [1]}), ["n1"], ctx=_ctx())
    assert out is cands
    pd.testing.assert_frame_equal(out, _cands(7))


# ── control flow: within / above / below target_range ─────────────────────────

def test_within_window_no_escalation():
    groups = [_grp("G", target=(10, 20))]
    res = _run_formula_groups(groups, _collate_const(15), _split(), ["n1"], _ctx())
    assert res["G"]["status"] == "ok"
    for stream in ("Repeat", "No_Repeat"):
        s = res["G"]["streams"][stream]
        assert s == {"status": "ok", "n": 15, "escalated": False, "flag": None,
                     "unit": "candidates", "target_range_meaningful": True}


def test_above_window_calls_escalation_and_can_land_in_range():
    # Escalation trims to 15 → back inside (10,20).
    esc = {"shrink15": lambda df, s, n, *, ctx: df.head(15)}
    groups = [_grp("G", esc="shrink15", target=(10, 20))]
    res = _run_formula_groups(groups, _collate_const(30), _split(), ["n1"], _ctx(),
                              escalations=esc)
    s = res["G"]["streams"]["Repeat"]
    assert s["escalated"] is True and s["n"] == 15 and s["flag"] is None


def test_above_window_still_out_after_escalation_is_flagged_but_unblocked():
    esc = {"shrink25": lambda df, s, n, *, ctx: df.head(25)}   # still > 20
    groups = [_grp("G", esc="shrink25", target=(10, 20))]
    res = _run_formula_groups(groups, _collate_const(30), _split(), ["n1"], _ctx(),
                              escalations=esc)
    s = res["G"]["streams"]["Repeat"]
    assert s["status"] == "ok"          # never blocks
    assert s["escalated"] is True and s["n"] == 25
    assert s["flag"] == "out_of_range_after_escalation"


def test_below_window_logs_only_and_never_escalates():
    def boom(df, s, n, *, ctx):
        raise AssertionError("escalation must NOT run below the window")
    groups = [_grp("G", esc="boom", target=(10, 20))]
    res = _run_formula_groups(groups, _collate_const(3), _split(), ["n1"], _ctx(),
                              escalations={"boom": boom})
    s = res["G"]["streams"]["Repeat"]
    assert s["status"] == "ok" and s["n"] == 3
    assert s["escalated"] is False and s["flag"] == "below_target"


# ── skip-and-log isolation ────────────────────────────────────────────────────

def test_empty_candidates_group_skipped_others_still_run():
    def collate(components):
        return pd.DataFrame() if components == ("A",) else _cands(15)
    groups = [FormulaGroup("G1", "G1", ("A",), "noop", (10, 20)),
              FormulaGroup("G2", "G2", ("B",), "noop", (10, 20))]
    res = _run_formula_groups(groups, collate, _split(), ["n1"], _ctx(),
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert res["G1"]["status"] == "skipped" and res["G1"]["streams"] == {}
    assert res["G2"]["status"] == "ok"
    assert res["G2"]["streams"]["Repeat"]["n"] == 15


def test_collate_error_isolated_to_its_group():
    def collate(components):
        if components == ("A",):
            raise ValueError("collate boom")
        return _cands(15)
    groups = [FormulaGroup("G1", "G1", ("A",), "noop", (10, 20)),
              FormulaGroup("G2", "G2", ("B",), "noop", (10, 20))]
    res = _run_formula_groups(groups, collate, _split(), ["n1"], _ctx(),
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert res["G1"]["status"] == "error" and "collate boom" in res["G1"]["reason"]
    assert res["G2"]["status"] == "ok"


def test_narrow_error_isolated_to_its_stream():
    def narrow(cands, stream_df, n_cols, *, ctx):
        if len(stream_df) == 0:      # No_Repeat here is empty → blow up only there
            raise RuntimeError("narrow boom")
        return cands
    groups = [_grp("G", esc="noop")]
    split = {"Repeat": pd.DataFrame({"n1": [1, 2]}),
             "No_Repeat": pd.DataFrame({"n1": []})}
    res = _run_formula_groups(groups, _collate_const(15), split, ["n1"], _ctx(),
                              narrow_fn=narrow,
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert res["G"]["streams"]["Repeat"]["status"] == "ok"
    assert res["G"]["streams"]["No_Repeat"]["status"] == "error"
    assert "narrow boom" in res["G"]["streams"]["No_Repeat"]["reason"]


def test_unknown_escalation_name_errors_that_stream_only():
    groups = [_grp("G", esc="does_not_exist", target=(10, 20))]
    res = _run_formula_groups(groups, _collate_const(30), _split(), ["n1"], _ctx(),
                              escalations={})   # name unresolvable
    s = res["G"]["streams"]["Repeat"]
    assert s["status"] == "error" and "does_not_exist" in s["reason"]


def test_meta_key_in_split_is_not_treated_as_a_stream():
    groups = [_grp("G", esc="noop")]
    res = _run_formula_groups(groups, _collate_const(15), _split(), ["n1"], _ctx(),
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert set(res["G"]["streams"]) == {"Repeat", "No_Repeat"}   # no "_meta"


# ── integration: real registry + real (stub) escalations ──────────────────────

def test_real_registry_all_groups_run_with_stub_escalations():
    # ALL four groups now default to split. G1's Repeat stream runs the REAL
    # _refgroup_w1_pivot (routed via config); the synthetic Repeat rows here
    # (n1 ∈ {0,1}) share nothing with ctx.ref_numbers → 0 survivors (real
    # behaviour, not a workaround). G1's No_Repeat + G2/G3/G4 stay on the
    # pass-through stub. Candidate-count streams read below_target (n=3<lo).
    res = _run_formula_groups(FORMULA_GROUPS, _collate_const(3), _split(),
                              ["n1"], _ctx())
    assert set(res) == {"G1", "G2", "G3", "G4"}
    assert all(res[k]["mode"] == "split" for k in ("G1", "G2", "G3", "G4"))
    assert set(res["G1"]["streams"]) == {"Repeat", "No_Repeat"}
    # G1 Repeat — real pivot, unit = main_data_rows, 0 survivors here
    g1r = res["G1"]["streams"]["Repeat"]
    assert g1r["status"] == "ok" and g1r["unit"] == "main_data_rows"
    assert g1r["n"] == 0 and g1r["target_range_meaningful"] is False
    # G1 No_Repeat — pass-through, unit = candidates
    g1nr = res["G1"]["streams"]["No_Repeat"]
    assert g1nr["unit"] == "candidates" and g1nr["n"] == 3
    # G2/G3/G4 — pass-through both streams, candidate unit
    for key in ("G2", "G3", "G4"):
        assert res[key]["status"] == "ok"
        for stream in ("Repeat", "No_Repeat"):
            s = res[key]["streams"][stream]
            assert (s["n"] == 3 and s["flag"] == "below_target"
                    and s["escalated"] is False and s["unit"] == "candidates")


# ── split/no-split mode (uses_main_data_split + split_override) ────────────────

def _grp_ns(key, esc="noop", target=(10, 20)):
    """A group that defaults to NO split (uses_main_data_split=False)."""
    return FormulaGroup(key, key, ("X",), esc, target, False)


def test_uses_main_data_split_defaults():
    # Corrected 2026-08-05: G1 defaults to split (True), same as the others —
    # R's real narrowing structurally REQUIRES the Main Data split. The field
    # still supports False (used by _grp_ns) for a future no-split group.
    for g in FORMULA_GROUPS:
        assert g.uses_main_data_split is True
    assert _grp_ns("Z").uses_main_data_split is False


def test_no_split_group_produces_single_entry_and_mode():
    res = _run_formula_groups([_grp_ns("G")], _collate_const(15), _split(),
                              ["n1"], _ctx(),
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert res["G"]["mode"] == "no_split"
    assert set(res["G"]["streams"]) == {"no_split"}
    assert res["G"]["streams"]["no_split"] == {
        "status": "ok", "n": 15, "escalated": False, "flag": None,
        "unit": "candidates", "target_range_meaningful": True}


def test_no_split_passes_none_stream_df_to_narrow():
    seen = {}
    def narrow(cands, stream_df, n_cols, *, ctx):
        seen["stream_df"] = stream_df
        return cands
    _run_formula_groups([_grp_ns("G")], _collate_const(15), _split(), ["n1"],
                        _ctx(), narrow_fn=narrow,
                        escalations={"noop": lambda d, s, n, *, ctx: d})
    assert seen["stream_df"] is None   # no-split runs once, with no stream


def test_split_override_forces_no_split_group_into_split():
    res = _run_formula_groups([_grp_ns("G")], _collate_const(3), _split(),
                              ["n1"], _ctx(), split_override={"G": True},
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert res["G"]["mode"] == "split"
    assert set(res["G"]["streams"]) == {"Repeat", "No_Repeat"}


def test_split_override_can_force_a_split_group_off():
    # Symmetric: a normally-split group can be forced no-split for one run.
    res = _run_formula_groups([_grp("G", target=(10, 20))], _collate_const(15),
                              _split(), ["n1"], _ctx(),
                              split_override={"G": False},
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert res["G"]["mode"] == "no_split"
    assert set(res["G"]["streams"]) == {"no_split"}


def test_split_override_leaves_other_groups_on_their_default():
    groups = [_grp_ns("G1"), _grp("G2")]
    res = _run_formula_groups(groups, _collate_const(3), _split(), ["n1"], _ctx(),
                              split_override={"G1": True},
                              escalations={"noop": lambda d, s, n, *, ctx: d})
    assert res["G1"]["mode"] == "split"          # overridden on
    assert res["G2"]["mode"] == "split"          # its own default (unchanged)
    assert set(res["G2"]["streams"]) == {"Repeat", "No_Repeat"}


def test_no_split_still_applies_target_range_and_escalation():
    # Above window → escalation fires even in no-split mode.
    esc = {"shrink15": lambda d, s, n, *, ctx: d.head(15)}
    res = _run_formula_groups([_grp_ns("G", esc="shrink15")], _collate_const(30),
                              _split(), ["n1"], _ctx(), escalations=esc)
    s = res["G"]["streams"]["no_split"]
    assert s["escalated"] is True and s["n"] == 15 and s["flag"] is None


# ── _refgroup_w1_pivot — RefGroup_w1 pivot stage (G1 / Repeat only) ────────────
# Filters Main Data ROWS (not candidates): keep rows sharing {1..pick-3} numbers
# with the reference draw, drop {pick-2,pick-1,pick}. shared==0 cannot occur in a
# Repeat pool by construction (Rule 1 already excluded it).

def _pivot_ctx(ref):
    return EscalationContext(ref_numbers=tuple(ref), history_df=None,
                             pool=45, pick=6, game_key="sat")


def test_pivot_filters_stream_not_candidates_and_keeps_1_2_3():
    ref = (1, 2, 3, 4, 5, 6)
    # Six rows sharing exactly 1..6 numbers with ref, in order.
    stream = pd.DataFrame([
        [1, 40, 41, 42, 43, 44],   # shares 1  → keep
        [1, 2, 41, 42, 43, 44],    # shares 2  → keep
        [1, 2, 3, 42, 43, 44],     # shares 3  → keep
        [1, 2, 3, 4, 43, 44],      # shares 4  → drop
        [1, 2, 3, 4, 5, 44],       # shares 5  → drop
        [1, 2, 3, 4, 5, 6],        # shares 6  → drop
    ], columns=N6)
    dummy_candidates = pd.DataFrame({"ignored": [1, 2, 3]})
    out = _refgroup_w1_pivot(dummy_candidates, stream, N6, ctx=_pivot_ctx(ref))
    assert len(out) == 3                                   # kept {1,2,3}
    shared = out[N6].isin(ref).sum(axis=1).tolist()
    assert sorted(shared) == [1, 2, 3]                    # dropped {4,5,6}


def test_pivot_declares_main_data_rows_unit():
    assert getattr(_refgroup_w1_pivot, "unit", None) == "main_data_rows"
    assert getattr(_default_narrow, "unit", "candidates") == "candidates"


@pytest.mark.skipif(not SAT_FULL_POOL.exists(),
                    reason="full sat C(45,6) pool absent (gitignored 8.1M-row data file)")
def test_pivot_real_repeat_pool_locks_survivor_count():
    from syndicate_core.main_split import split_streams
    main = pd.read_csv(SAT_FULL_POOL)
    ref = [3, 6, 9, 14, 21, 22]                            # any valid 6-set (invariant)
    repeat = split_streams(main, N6, ref)["Repeat"]
    assert len(repeat) == 4_882_437                        # Rule 1 Repeat pool
    out = _refgroup_w1_pivot(pd.DataFrame(), repeat, N6, ctx=_pivot_ctx(ref))
    assert len(out) == 4_871_087                           # keeps {1,2,3}
    assert len(repeat) - len(out) == 11_350                # drops {4,5,6} sliver
