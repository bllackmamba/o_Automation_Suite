"""
tests/test_escalation.py — escalation stub interface (Formula Registry step 3).

The three escalations are pass-through stubs this pass: they log "not yet tuned"
and return the candidate set untouched. These tests lock the *interface* — the
registry, the frozen context, and the identity/pass-through guarantee — so the
runner (step 5) can call any escalation whether or not it is tuned, and so a
future real implementation can't silently change the signature or mutate input.
"""
import logging
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from syndicate_core.escalation import (
    ESCALATIONS,
    EscalationContext,
    rule9_boundary_aggressive,
    shallow_anchor_exclude_hold,
    spread3_borderline,
)

EXPECTED_NAMES = {
    "spread3_borderline",
    "rule9_boundary_aggressive",
    "shallow_anchor_exclude_hold",
}


def _ctx() -> EscalationContext:
    return EscalationContext(ref_numbers=(3, 6, 9, 14, 21, 22), history_df=None,
                             pool=45, pick=6, game_key="sat")


def _candidates() -> pd.DataFrame:
    return pd.DataFrame({"Row_ID": [1, 2, 3], "Source": ["R", "R", "R"],
                         "w1": [10, 20, 30], "w2": [11, 21, 31]})


def _stream() -> pd.DataFrame:
    return pd.DataFrame({"n1": [1, 2], "n2": [3, 4]})


# ── registry ──────────────────────────────────────────────────────────────────

def test_registry_has_exactly_the_three_stubs():
    assert set(ESCALATIONS) == EXPECTED_NAMES
    assert all(callable(fn) for fn in ESCALATIONS.values())


def test_registry_maps_names_to_matching_callables():
    assert ESCALATIONS["spread3_borderline"] is spread3_borderline
    assert ESCALATIONS["rule9_boundary_aggressive"] is rule9_boundary_aggressive
    assert ESCALATIONS["shallow_anchor_exclude_hold"] is shallow_anchor_exclude_hold


# ── pass-through contract ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(EXPECTED_NAMES))
def test_stub_is_identity_passthrough(name):
    fn = ESCALATIONS[name]
    cands = _candidates()
    out = fn(cands, _stream(), ["n1", "n2"], ctx=_ctx())
    assert out is cands                                  # same object, no copy
    pd.testing.assert_frame_equal(out, _candidates())    # and unmutated


@pytest.mark.parametrize("name", sorted(EXPECTED_NAMES))
def test_stub_logs_not_yet_tuned(name, caplog):
    fn = ESCALATIONS[name]
    with caplog.at_level(logging.INFO):
        fn(_candidates(), _stream(), ["n1", "n2"], ctx=_ctx())
    assert "not yet tuned" in caplog.text
    assert name in caplog.text


# ── context ───────────────────────────────────────────────────────────────────

def test_context_is_frozen():
    ctx = _ctx()
    with pytest.raises(FrozenInstanceError):
        ctx.pick = 7  # type: ignore[misc]


def test_context_carries_expected_fields():
    ctx = _ctx()
    assert ctx.ref_numbers == (3, 6, 9, 14, 21, 22)
    assert ctx.pool == 45 and ctx.pick == 6 and ctx.game_key == "sat"
    assert ctx.history_df is None
