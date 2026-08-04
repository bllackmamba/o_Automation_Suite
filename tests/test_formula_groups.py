"""
tests/test_formula_groups.py — Formula Group registry (step 4) + runner (step 5).

Step 4 covers the FORMULA_GROUPS registry in config.py: the four groups, their
components and escalation names, and the first CROSS-MODULE check — every
group's escalate name must resolve in syndicate_core.escalation.ESCALATIONS.
"""
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from syndicate_core.collation import _default_narrow, _run_formula_groups
from syndicate_core.config import FORMULA_GROUPS, FormulaGroup
from syndicate_core.escalation import ESCALATIONS, EscalationContext

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
        assert s == {"status": "ok", "n": 15, "escalated": False, "flag": None}


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
    # Below-window candidates → every group logs below_target, nothing blocks,
    # real ESCALATIONS pass-through never fires (n < lo).
    res = _run_formula_groups(FORMULA_GROUPS, _collate_const(3), _split(),
                              ["n1"], _ctx())
    assert set(res) == {"G1", "G2", "G3", "G4"}
    for key in ("G1", "G2", "G3", "G4"):
        assert res[key]["status"] == "ok"
        for stream in ("Repeat", "No_Repeat"):
            s = res[key]["streams"][stream]
            assert s["n"] == 3 and s["flag"] == "below_target" and s["escalated"] is False
