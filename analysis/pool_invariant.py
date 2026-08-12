"""
Repeat / No_Repeat pool invariant — standing checker (LOCKED Rule Set 1).

Call this after EVERY narrowing step of ANY chain that touches a Repeat or
No_Repeat pool, present or future. It is a hard gate, not a warning: a single
violating row raises ``PoolInvariantViolation`` immediately, naming the step and
the offending row.

Rule Set 1 (Sika_R_Rules_LOCKED.md:22-23), with RefGroup = D4687 {3,6,9,14,21,22}:
  - Repeat pool    : every surviving row shares >= 1 number with RefGroup.
  - No_Repeat pool : every surviving row shares exactly 0 with RefGroup.

Read-only: touches no tracked code/CSV. Pure functions + numpy fast path.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np

REFGROUP_D4687: frozenset[int] = frozenset({3, 6, 9, 14, 21, 22})
_STREAMS = ("Repeat", "No_Repeat")


class PoolInvariantViolation(AssertionError):
    """Raised the instant a surviving row breaks its stream's Rule-1 invariant."""


def match_count(row: Iterable[int], ref: Iterable[int] = REFGROUP_D4687) -> int:
    """Shared-number count between a row and RefGroup (the Rule-1 'match' value)."""
    return len(set(int(n) for n in row) & set(int(n) for n in ref))


def _bad_predicate(stream: str):
    """Return f(mc)->bool marking a match count as a violation for this stream."""
    if stream == "Repeat":
        return lambda mc: mc < 1          # Repeat must be nonzero
    if stream == "No_Repeat":
        return lambda mc: mc != 0         # No_Repeat must be exactly zero
    raise ValueError(f"stream must be one of {_STREAMS}, got {stream!r}")


def assert_pool_invariant(
    rows: Sequence[Iterable[int]],
    stream: str,
    *,
    step_label: str,
    ref: Iterable[int] = REFGROUP_D4687,
) -> int:
    """Assert every row in ``rows`` satisfies ``stream``'s Rule-1 invariant.

    ``rows`` is an iterable of number-collections (the CURRENT survivors after a
    narrowing step). Returns the number of rows checked; raises
    :class:`PoolInvariantViolation` on the first offender, naming ``step_label``,
    the row index, its numbers, and its match count.
    """
    bad = _bad_predicate(stream)
    ref_set = set(int(n) for n in ref)
    checked = 0
    for i, row in enumerate(rows):
        nums = [int(n) for n in row]
        mc = len(set(nums) & ref_set)
        if bad(mc):
            raise PoolInvariantViolation(
                f"[{step_label}] {stream} invariant broken at row {i}: "
                f"nums={sorted(nums)} match_count(RefGroup)={mc} "
                f"(Repeat needs >=1, No_Repeat needs ==0)")
        checked += 1
    return checked


def assert_pool_invariant_array(
    arr: np.ndarray,
    stream: str,
    *,
    step_label: str,
    ref: Iterable[int] = REFGROUP_D4687,
) -> int:
    """Vectorized form for large pools: ``arr`` is (N, k) ints (0 = empty slot).

    Same contract as :func:`assert_pool_invariant` but numpy-fast for millions of
    rows. Raises on the first offending row (lowest index) so the message is
    deterministic.
    """
    bad = _bad_predicate(stream)
    ref_arr = np.array(sorted(set(int(n) for n in ref)), dtype=arr.dtype)
    shared = np.isin(arr, ref_arr).sum(axis=1)
    # a row is bad iff its match count violates the stream rule
    if stream == "Repeat":
        offenders = np.flatnonzero(shared < 1)
    else:
        offenders = np.flatnonzero(shared != 0)
    if offenders.size:
        i = int(offenders[0])
        raise PoolInvariantViolation(
            f"[{step_label}] {stream} invariant broken at row {i}: "
            f"nums={sorted(int(x) for x in arr[i] if x)} "
            f"match_count(RefGroup)={int(shared[i])} "
            f"({offenders.size} offending rows total)")
    return int(arr.shape[0])
