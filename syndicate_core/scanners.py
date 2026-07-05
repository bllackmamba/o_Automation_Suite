"""
Pure filename-scanner helpers shared with the Streamlit UI (masterapp.py).

These live in syndicate_core — not masterapp — so they are import-safe and unit
testable. masterapp.py executes Streamlit page code (`st.set_page_config`,
`st.title`, …) at import time and therefore cannot be imported by the test
suite; the pure decision/parse logic is factored out here instead.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# Legacy CVI names embedded a trailing draw date:
#   CVI_{lotto}_{formula}_{YYYY_MM_DD}.csv
_CVI_TRAILING_DATE = re.compile(r"_(\d{4}_\d{2}_\d{2})$")


def parse_cvi_filename(fname: str) -> dict:
    """
    Parse a CVI filename into ``{lotto, formula, date, raw}``.

    Current convention is ``CVI_{formula}.csv`` — the formula is the whole stem
    after the ``CVI_`` prefix (e.g. ``CVI_BRD.csv`` -> ``"BRD"``,
    ``CVI_Matrix_ALL_sat.csv`` -> ``"Matrix_ALL_sat"``). These names carry no
    date; ``scan_cvi_files`` fills the Date column from file mtime.

    The older ``CVI_{lotto}_{formula}_{YYYY_MM_DD}.csv`` form is still
    recognised: a trailing date is pulled into ``date``. ``lotto`` is left blank
    (the UI's file filter treats a blank lotto as "matches any game", which is
    the intended behaviour under the current no-lotto-in-name convention).
    """
    stem = Path(fname).stem
    result = {"lotto": "", "formula": "", "date": "", "raw": fname}
    if not stem.startswith("CVI_"):
        return result
    body = stem[len("CVI_"):]
    m = _CVI_TRAILING_DATE.search(body)
    if m:
        result["date"] = m.group(1)
        body = body[:m.start()]
    result["formula"] = body
    return result


def cvi_date_from_mtime(mtime: float) -> str:
    """Format a file mtime (epoch seconds) as ``YYYY-MM-DD`` for the Date column."""
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def resolve_main_data_choices(scanned: list[dict],
                              session_path: str,
                              session_rows: int) -> list[dict]:
    """
    Decide which Main Data files the parallel runner should offer.

    ``scan_main_data_files`` only recognises the strict
    ``{cluster}_{lotto}_D{draw}.csv`` convention. Main Data loaded through the
    permissive uploader/scan (any ``*.csv`` saved to Main_Data/) lives in
    session state and is invisible to that strict scan — which produced a false
    "No Main Data files found" banner even while the Preview panel showed the
    file loaded (e.g. 8,145,059 rows).

    When the strict scan finds nothing but session state holds loaded rows with
    a real on-disk path, surface that file so the banner only fires when Main
    Data is genuinely absent (empty scan AND nothing loaded). An in-memory
    upload with no path can't feed the file-based parallel runner, so it is
    treated as absent.
    """
    if scanned:
        return list(scanned)
    if session_rows > 0 and session_path:
        p = Path(session_path)
        return [{"raw": p.name, "path": str(p), "rows": session_rows,
                 "lotto": "", "draw": "D?"}]
    return []
