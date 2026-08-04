"""
syndicate_core/escalation.py — Formula Registry escalation interface.

Each formula group names one escalation (by string, resolved via ESCALATIONS)
that the runner calls when a stream's survivor count is ABOVE its target_range,
to tighten the candidate set. This pass ships all three as PASS-THROUGH stubs:
they log "not yet tuned" and return the candidate set untouched, so the runner
can call any of them whether or not it is tuned. The real narrowing logic is
worked out separately over time.

  • rule9_boundary_aggressive   — G2 (D), G4 (Ep+So+Sp+B2). Rule 9 does not
    exist yet; nothing to reuse.
  • shallow_anchor_exclude_hold — G3 (B1). LATER reuses stacked_blocks
    (block_layout / since_last_map) for the rolling own-era shallow list.
  • spread3_borderline          — G1 (R). LATER reuses the persisted
    Constituent_Groups spread per LOCKED Rule Set 3.

No Streamlit dependency — safe to import in tests and CLI scripts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import pandas as pd

__all__ = [
    "EscalationContext",
    "spread3_borderline",
    "rule9_boundary_aggressive",
    "shallow_anchor_exclude_hold",
    "ESCALATIONS",
]


@dataclass(frozen=True)
class EscalationContext:
    """Immutable bundle passed to every escalation.

    Carries everything a tuned escalation needs (reference draw, draw history,
    game shape) so wiring real logic later never churns the call signature. The
    stubs ignore it.
    """
    ref_numbers: tuple[int, ...]
    history_df: Optional[pd.DataFrame]
    pool: int
    pick: int
    game_key: str


def rule9_boundary_aggressive(
    narrowed_df: pd.DataFrame,
    stream_df: pd.DataFrame,
    n_cols: Sequence[str],
    *,
    ctx: EscalationContext,
) -> pd.DataFrame:
    """G2/G4 escalation — STUB (Rule 9 does not exist yet). Pass-through."""
    logging.info("escalation rule9_boundary_aggressive not yet tuned — pass-through")
    return narrowed_df


def shallow_anchor_exclude_hold(
    narrowed_df: pd.DataFrame,
    stream_df: pd.DataFrame,
    n_cols: Sequence[str],
    *,
    ctx: EscalationContext,
) -> pd.DataFrame:
    """G3 escalation — STUB. Pass-through.

    LATER: build the rolling own-era shallow list via
    stacked_blocks.block_layout / since_last_map from ctx.history_df +
    ctx.ref_numbers, then exclude rows with zero overlap → holding (LOCKED
    Rule Set 4). The math is available; the exclude-and-hold filter is net-new.
    """
    logging.info("escalation shallow_anchor_exclude_hold not yet tuned — pass-through")
    return narrowed_df


def spread3_borderline(
    narrowed_df: pd.DataFrame,
    stream_df: pd.DataFrame,
    n_cols: Sequence[str],
    *,
    ctx: EscalationContext,
) -> pd.DataFrame:
    """G1 escalation — STUB. Pass-through.

    LATER: spread = len(Constituent_Groups) per R row (already persisted by
    execute_collation); act on Spread-3 (Borderline) per LOCKED Rule Set 3.
    The filter is net-new.
    """
    logging.info("escalation spread3_borderline not yet tuned — pass-through")
    return narrowed_df


ESCALATIONS: dict[str, Callable[..., pd.DataFrame]] = {
    "spread3_borderline": spread3_borderline,
    "rule9_boundary_aggressive": rule9_boundary_aggressive,
    "shallow_anchor_exclude_hold": shallow_anchor_exclude_hold,
}
