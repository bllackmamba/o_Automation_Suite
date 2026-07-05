"""Regression tests for the shared filename scanners (masterapp UI helpers)."""
from datetime import datetime

import pytest

from syndicate_core.scanners import (
    parse_cvi_filename,
    cvi_date_from_mtime,
    resolve_main_data_choices,
)


# ── A2: CVI filename parsing — Formula/Date columns were blank ───────────────

@pytest.mark.parametrize("fname, formula", [
    ("CVI_BRD.csv", "BRD"),
    ("CVI_BRDEpSoSp.csv", "BRDEpSoSp"),
    ("CVI_D1D2D3.csv", "D1D2D3"),
    ("CVI_R1R2R3.csv", "R1R2R3"),
    ("CVI_So1So2So3.csv", "So1So2So3"),
    ("CVI_RDEpSoSp.csv", "RDEpSoSp"),
    ("CVI_Matrix_ALL_sat.csv", "Matrix_ALL_sat"),
])
def test_parse_cvi_current_convention_populates_formula(fname, formula):
    # Regression: real CVI files are `CVI_{formula}.csv` with no embedded
    # lotto/date. The old parser expected `CVI_{lotto}_{formula}_{date}` and
    # required >=3 underscore parts, so it left Formula (and Date) blank for
    # every real filename.
    info = parse_cvi_filename(fname)
    assert info["formula"] == formula
    assert info["date"] == ""   # no embedded date -> scanner fills from mtime


def test_parse_cvi_legacy_dated_name_preserves_date():
    info = parse_cvi_filename("CVI_oz_BRD_2026_05_28.csv")
    assert info["date"] == "2026_05_28"
    assert info["formula"] == "oz_BRD"   # only the trailing date is stripped


def test_parse_cvi_non_cvi_name_is_blank():
    info = parse_cvi_filename("SC_BRD.csv")
    assert info == {"lotto": "", "formula": "", "date": "", "raw": "SC_BRD.csv"}


def test_cvi_date_from_mtime_formats_iso_date():
    ts = datetime(2026, 7, 1, 13, 30).timestamp()
    assert cvi_date_from_mtime(ts) == "2026-07-01"


# ── A1: Main Data banner must agree with the Preview panel's data source ─────

def test_resolve_prefers_strict_scan_when_present():
    scanned = [{"raw": "1n_oz_D1567.csv", "path": "/x/1n_oz_D1567.csv",
                "rows": 10, "lotto": "oz", "draw": "D1567"}]
    # When the strict scan finds files, they win; session state is not consulted.
    assert resolve_main_data_choices(scanned, "/other/loaded.csv", 8_145_059) == scanned


def test_resolve_falls_back_to_session_when_scan_empty():
    # The reported bug: strict scan finds nothing (off-convention filename) but
    # the Preview panel has 8.1M rows loaded -> banner must NOT show.
    out = resolve_main_data_choices([], "/games/SAT/Main_Data/maindata.csv", 8_145_059)
    assert len(out) == 1
    assert out[0]["raw"] == "maindata.csv"
    assert out[0]["path"] == "/games/SAT/Main_Data/maindata.csv"
    assert out[0]["rows"] == 8_145_059


def test_resolve_empty_when_genuinely_no_main_data():
    # Banner SHOULD still fire when nothing is scanned and nothing is loaded.
    assert resolve_main_data_choices([], "", 0) == []


def test_resolve_no_session_path_does_not_fabricate_choice():
    # In-memory upload (rows loaded but no on-disk path) can't feed the
    # file-based parallel runner -> treat as absent, banner shows.
    assert resolve_main_data_choices([], "", 8_145_059) == []


def test_resolve_always_yields_path_key_regardless_of_branch():
    # RUN ALL does Path(chosen_main_info["path"]); every dict resolve returns
    # must carry a populated "path" no matter which branch produced it, or the
    # ordinary strict-scan case would KeyError.
    #
    # Strict-scan branch: fixtures mirror scan_main_data_files() output, which
    # sets info["path"] = str(fp) (masterapp.py:325) alongside raw/rows/lotto/draw.
    scanned = [
        {"raw": "1n_oz_D1567.csv", "path": "/g/SAT/Main_Data/1n_oz_D1567.csv",
         "rows": 10, "lotto": "oz", "draw": "D1567"},
        {"raw": "2n_oz_D1568.csv", "path": "/g/SAT/Main_Data/2n_oz_D1568.csv",
         "rows": 20, "lotto": "oz", "draw": "D1568"},
    ]
    strict = resolve_main_data_choices(scanned, "", 0)
    assert strict, "strict-scan branch must return the scanned files"
    assert all(d.get("path") for d in strict)

    # Session-fallback branch must also populate path.
    fallback = resolve_main_data_choices([], "/g/SAT/Main_Data/maindata.csv", 8_145_059)
    assert fallback, "fallback branch must surface the loaded file"
    assert all(d.get("path") for d in fallback)
