"""Regression tests for the shared filename scanners (masterapp UI helpers)."""
from datetime import datetime

import pytest

from syndicate_core.scanners import (
    parse_cvi_filename,
    cvi_date_from_mtime,
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
