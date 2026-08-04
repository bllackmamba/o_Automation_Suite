"""
tests/test_formula_groups.py — Formula Group registry (step 4) + runner (step 5).

Step 4 covers the FORMULA_GROUPS registry in config.py: the four groups, their
components and escalation names, and the first CROSS-MODULE check — every
group's escalate name must resolve in syndicate_core.escalation.ESCALATIONS.
"""
from dataclasses import FrozenInstanceError

import pytest

from syndicate_core.config import FORMULA_GROUPS, FormulaGroup
from syndicate_core.escalation import ESCALATIONS

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
