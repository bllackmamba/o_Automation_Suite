"""
syndicate_core/main_split.py — RefGroup-keyed Main Data split (Rule 1).

Splits a Main Data pool into Repeat / No_Repeat streams on the LOCKED-doc
Rule 1 boundary (nonzero/zero vs the newest-draw reference numbers), then caches
the two streams keyed by that reference draw. The cache rebuilds ONLY when the
reference rolls over to a new draw — this is a per-RefGroup split, not a
one-time one.

No Streamlit dependency — safe to import in tests and CLI scripts. The Rule 1
boundary itself lives once in refgroup.main_data_stream; this module reuses it
so there is never a second, drifting definition (cf. analysis/sl_group_regime).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

__all__ = [
    "split_streams",
    "ref_key_of",
    "load_or_build_split",
]

REPEAT = "Repeat"
NO_REPEAT = "No_Repeat"
_MARKER_NAME = "_split_marker.json"


def split_streams(
    main_df: pd.DataFrame,
    n_cols: Sequence[str],
    ref_numbers: Sequence[int],
) -> dict[str, pd.DataFrame]:
    """Partition ``main_df`` into Repeat / No_Repeat on the Rule 1 boundary.

    A row is **Repeat** iff it shares >= 1 number with ``ref_numbers`` (across
    ``n_cols``), else **No_Repeat**. Read-only on the input; returned frames are
    row subsets of ``main_df`` with the index reset. Empty ``main_df`` yields two
    empty frames; empty ``ref_numbers`` yields all-No_Repeat (nothing shares).
    """
    if main_df is None or main_df.empty:
        empty = main_df.iloc[0:0].copy() if main_df is not None else pd.DataFrame()
        return {REPEAT: empty.copy(), NO_REPEAT: empty.copy()}

    ref = np.array(sorted({int(n) for n in ref_numbers}), dtype=np.int64)
    if ref.size == 0:
        return {REPEAT: main_df.iloc[0:0].copy(),
                NO_REPEAT: main_df.reset_index(drop=True).copy()}

    arr = main_df[list(n_cols)].to_numpy()
    shared = np.isin(arr, ref).sum(axis=1)
    repeat_mask = shared > 0
    return {
        REPEAT: main_df[repeat_mask].reset_index(drop=True).copy(),
        NO_REPEAT: main_df[~repeat_mask].reset_index(drop=True).copy(),
    }


def ref_key_of(ref_numbers: Sequence[int]) -> str:
    """Stable cache key for a reference draw: sorted, de-duped, dash-joined.

    Order-independent so the same draw always maps to the same key
    (``[3,1,2] -> "1-2-3"``). Changing the key ⇔ a RefGroup rollover.
    """
    return "-".join(str(n) for n in sorted({int(x) for x in ref_numbers}))


def _stream_path(cache_dir: Path, stream: str, ref_key: str) -> Path:
    return cache_dir / f"{stream}__{ref_key}.parquet"


def _read_marker(marker_path: Path) -> dict:
    if not marker_path.exists():
        return {}
    try:
        return json.loads(marker_path.read_text())
    except Exception as ex:  # corrupt marker → treat as absent, force rebuild
        logging.warning("main_split: unreadable marker %s: %s", marker_path, ex)
        return {}


def _drop_stale(cache_dir: Path) -> None:
    """Remove every cached split parquet (both streams, any ref_key)."""
    for p in list(cache_dir.glob(f"{REPEAT}__*.parquet")) + \
            list(cache_dir.glob(f"{NO_REPEAT}__*.parquet")):
        try:
            p.unlink()
        except OSError as ex:
            logging.warning("main_split: could not remove stale %s: %s", p, ex)


def load_or_build_split(
    main_df: pd.DataFrame,
    n_cols: Sequence[str],
    ref_numbers: Sequence[int],
    cache_dir,
) -> dict:
    """Return the Repeat / No_Repeat streams for ``ref_numbers``, cached on disk.

    Cache hit (marker's ref_key matches AND both parquets exist and load) returns
    the stored streams with ``_meta.rebuilt == False``. Otherwise the split is
    recomputed, stale parquets from any prior ref_key are dropped, the two new
    parquets + marker are written, and ``_meta.rebuilt == True``. This is the
    RefGroup rollover invalidation — a new reference draw forces a rebuild.

    Returns ``{"Repeat": df, "No_Repeat": df, "_meta": {...}}``.
    """
    cache_dir = Path(cache_dir)
    ref_key = ref_key_of(ref_numbers)
    rep_path = _stream_path(cache_dir, REPEAT, ref_key)
    nor_path = _stream_path(cache_dir, NO_REPEAT, ref_key)
    marker_path = cache_dir / _MARKER_NAME

    marker = _read_marker(marker_path)
    if (marker.get("ref_key") == ref_key
            and rep_path.exists() and nor_path.exists()):
        try:
            rep = pd.read_parquet(rep_path)
            nor = pd.read_parquet(nor_path)
            return {REPEAT: rep, NO_REPEAT: nor,
                    "_meta": {"ref_key": ref_key, "rebuilt": False,
                              "n_repeat": len(rep), "n_no_repeat": len(nor),
                              "n_main": len(rep) + len(nor)}}
        except Exception as ex:  # unreadable parquet → fall through to rebuild
            logging.warning("main_split: cache read failed (%s) — rebuilding", ex)

    streams = split_streams(main_df, n_cols, ref_numbers)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _drop_stale(cache_dir)
    streams[REPEAT].to_parquet(rep_path, index=False)
    streams[NO_REPEAT].to_parquet(nor_path, index=False)
    meta = {"ref_key": ref_key, "rebuilt": True,
            "n_repeat": len(streams[REPEAT]),
            "n_no_repeat": len(streams[NO_REPEAT]),
            "n_main": len(streams[REPEAT]) + len(streams[NO_REPEAT])}
    marker_path.write_text(json.dumps(meta))
    return {REPEAT: streams[REPEAT], NO_REPEAT: streams[NO_REPEAT], "_meta": meta}
