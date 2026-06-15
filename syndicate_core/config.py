from pathlib import Path
import shutil as _shutil

__all__ = [
    # path / dirs
    "find_root", "ROOT", "DIRS",
    # game config
    "GAMES_CFG", "GAME_KEYS", "GAME_LABELS", "GAME_NAME_MAP",
    # formula / dashboard config
    "CF_ROWS", "DASHBOARDS", "COMP_MAP",
    # lotto metadata
    "LOTTO_TYPES",
    # geography
    "TARGET_STATES", "STATE_POSTCODES",
    # processing tunables
    "CHUNK_SIZE", "DISPLAY_THRESHOLD",
]

# ═══════════════════════════════════════════════════════════════════════════════
# PATH AUTO-DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
def find_root() -> Path:
    for base in [Path.home()/"Desktop", Path.home()/"Documents",
                 Path.home(), Path.cwd()]:
        p = base / "o_Automation_Suite"
        if p.is_dir():
            return p
        if base.is_dir():
            for sub in base.iterdir():
                try:
                    q = sub / "o_Automation_Suite"
                    if q.is_dir():
                        return q
                except Exception:
                    pass
    # __file__ is syndicate_core/config.py — .parent.parent is the suite root
    fb = Path(__file__).parent.parent
    fb.mkdir(parents=True, exist_ok=True)
    return fb

ROOT = find_root()

# ── Global-only DIRS (shared across all games) ───────────────────────────────
# Game-specific paths (Main_Data, Formulas, Containers, Outputs, Variables, CVI,
# Selected_Counts, Base, Splits, etc.) are accessed via game_dirs() / active_game_dirs()
# so they are always scoped to the correct game and suffixed with _{game}.
# Only truly shared paths live here.
DIRS = {
    "Global_Scraper": ROOT / "Global_Scraper",  # raw scrapes: D_<STATE>.csv (all games)
    "debug_html":     ROOT / "debug_html",       # debug output
}
for _d in DIRS.values():
    _d.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP MIGRATION — runs once per session to enforce the folder convention.
#
# Problem: old code created root-level folders (Containers, Formulas, Main_Data,
# Variables, Outputs) and game subfolders without the _{game} suffix. Every time
# the app started those folders were re-created by the old DIRS mkdir loop.
#
# Fix embedded here so no separate script is needed:
#   1. Remove stale root-level duplicate folders (only if empty — no data lost).
#   2. Rename game subfolders to the _{game} suffix convention.
#   3. Flatten old Variables/ tree → variable_inputs_{game}/ and
#      container_variable_inputs_{game}/.
# ═══════════════════════════════════════════════════════════════════════════════
_ROOT_LEVEL_STALE = [
    "Containers", "Formulas", "Main_Data", "Variables", "Outputs",
]

_SUBFOLDER_CANON = {
    "containers":                "containers",
    "container":                 "containers",
    "formulas":                  "formulas",
    "formula":                   "formulas",
    "main_data":                 "main_data",
    "maindata":                  "main_data",
    "outputs":                   "outputs",
    "output":                    "outputs",
    "sincelast":                 "sincelast",
    "since_last":                "sincelast",
    "games_breakdown":           "games_breakdown",
    "gamesbreakdown":            "games_breakdown",
    "cvi_matrix":                "container_variable_inputs",
    "cvimatrix":                 "container_variable_inputs",
    "container_variable_inputs": "container_variable_inputs",
    "containervariableinputs":   "container_variable_inputs",
    "variable_inputs":           "variable_inputs",
    "variableinputs":            "variable_inputs",
}


def _norm(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def _startup_migrate(root: Path):
    """Idempotent startup migration — safe to run every launch."""

    # ── Step 1: remove stale empty root-level folders ──────────────────────
    for name in _ROOT_LEVEL_STALE:
        p = root / name
        if p.is_dir():
            contents = [x for x in p.iterdir() if not x.name.startswith(".")]
            if not contents:
                try:
                    _shutil.rmtree(str(p))
                except Exception:
                    pass
            # Non-empty root-level folders are handled in steps 4 & 5 below

    games_dir = root / "Games"
    if not games_dir.is_dir():
        return

    for game in ["SAT", "OZ", "PB", "MWF", "SFL"]:
        gp = games_dir / game
        if not gp.is_dir():
            continue
        gk = game.lower()
        suffix = f"_{gk}"

        # ── Step 2: rename top-level game subfolders ────────────────────────
        for entry in sorted(gp.iterdir()):
            if not entry.is_dir():
                continue
            key = _norm(entry.name)
            if key == "variables":
                continue  # handled in step 3
            # strip existing suffix before lookup
            if key.endswith(suffix):
                key = key[: -len(suffix)]
            canonical = _SUBFOLDER_CANON.get(key)
            if canonical is None:
                continue
            desired = gp / f"{canonical}{suffix}"
            if entry != desired and not desired.exists():
                try:
                    entry.rename(desired)
                except Exception:
                    pass

        # ── Step 3: flatten old Variables/ tree ────────────────────────────
        old_vars = gp / "Variables"
        if not old_vars.is_dir():
            continue

        var_inputs_dst = gp / f"variable_inputs_{gk}"
        cvi_dst        = gp / f"container_variable_inputs_{gk}"

        # Variables/Scraper → variable_inputs_{gk}/Scraper
        src = old_vars / "Scraper"
        dst = var_inputs_dst / "Scraper"
        if src.is_dir() and not dst.exists():
            var_inputs_dst.mkdir(parents=True, exist_ok=True)
            try:
                src.rename(dst)
            except Exception:
                pass

        # Variables/Variable_Elements/* → variable_inputs_{gk}/ (flatten)
        var_elem = old_vars / "Variable_Elements"
        if var_elem.is_dir():
            var_inputs_dst.mkdir(parents=True, exist_ok=True)
            for item in sorted(var_elem.iterdir()):
                dst_item = var_inputs_dst / item.name
                if not dst_item.exists():
                    try:
                        item.rename(dst_item)
                    except Exception:
                        pass
            # Remove shell if now empty
            remaining = [x for x in var_elem.iterdir()
                         if not x.name.startswith(".")]
            if not remaining:
                try:
                    var_elem.rmdir()
                except Exception:
                    pass

        # Variables/Container_Variable_Inputs → container_variable_inputs_{gk}
        src_cvi = old_vars / "Container_Variable_Inputs"
        if src_cvi.is_dir() and not cvi_dst.exists():
            try:
                src_cvi.rename(cvi_dst)
            except Exception:
                pass

        # Remove empty Variables/ shell
        remaining = [x for x in old_vars.iterdir()
                     if not x.name.startswith(".")]
        if not remaining:
            try:
                old_vars.rmdir()
            except Exception:
                pass

    # ── Step 4: flatten root-level Variables/ → Games/SAT/variable_inputs_sat/
    #    (old global Variables/ before game-specific structure was introduced)
    root_vars = root / "Variables"
    if root_vars.is_dir():
        sat_path = root / "Games" / "SAT"
        if sat_path.is_dir():
            vi_dst  = sat_path / "variable_inputs_sat"
            cvi_dst2 = sat_path / "container_variable_inputs_sat"

            src_sc = root_vars / "Scraper"
            dst_sc = vi_dst / "Scraper"
            if src_sc.is_dir() and not dst_sc.exists():
                vi_dst.mkdir(parents=True, exist_ok=True)
                try:
                    src_sc.rename(dst_sc)
                except Exception:
                    pass

            ve_dir = root_vars / "Variable_Elements"
            if ve_dir.is_dir():
                vi_dst.mkdir(parents=True, exist_ok=True)
                for item in sorted(ve_dir.iterdir()):
                    if item.name.startswith("."):
                        continue
                    dst_item = vi_dst / item.name
                    if not dst_item.exists():
                        try:
                            item.rename(dst_item)
                        except Exception:
                            pass
                rem = [x for x in ve_dir.iterdir() if not x.name.startswith(".")]
                if not rem:
                    try:
                        ve_dir.rmdir()
                    except Exception:
                        pass

            src_cvi2 = root_vars / "Container_Variable_Inputs"
            if src_cvi2.is_dir() and not cvi_dst2.exists():
                try:
                    src_cvi2.rename(cvi_dst2)
                except Exception:
                    pass

            rem_rv = [x for x in root_vars.iterdir() if not x.name.startswith(".")]
            if not rem_rv:
                try:
                    root_vars.rmdir()
                except Exception:
                    pass

    # ── Step 5: move root-level Formulas/ → Games/SAT/formulas_sat/
    #    (old global Formulas/ before game-specific structure)
    root_formulas = root / "Formulas"
    if root_formulas.is_dir():
        sat_path = root / "Games" / "SAT"
        if sat_path.is_dir():
            sat_formulas_dst = sat_path / "formulas_sat"
            sat_formulas_dst.mkdir(parents=True, exist_ok=True)
            for item in sorted(root_formulas.iterdir()):
                if item.name.startswith("."):
                    continue
                dst_item = sat_formulas_dst / item.name
                if not dst_item.exists():
                    try:
                        item.rename(dst_item)
                    except Exception:
                        pass
            rem_rf = [x for x in root_formulas.iterdir() if not x.name.startswith(".")]
            if not rem_rf:
                try:
                    root_formulas.rmdir()
                except Exception:
                    pass


_startup_migrate(ROOT)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
TARGET_STATES = ["NSW","VIC","QLD","WA","SA","TAS","ACT","NT"]

STATE_POSTCODES = {
    "NSW": list(range(2000,3000)),
    "VIC": list(range(3000,4000)),
    "QLD": list(range(4000,5000)),
    "WA":  list(range(6000,7000)),
    "SA":  list(range(5000,5600)),
    "TAS": list(range(7000,7800)),
    "ACT": list(range(2600,2619)),
    "NT":  list(range(800, 1000)),
}

CF_ROWS = [
    (1,  "BRD",       "Formed",    ["B","R","D"]),
    (2,  "BSD",       "Formed",    ["B","Sp","D"]),
    (3,  "BSoD",      "Formed",    ["B","So","D"]),
    (4,  "SD",        "Formed",    ["Sp","D"]),
    (5,  "SoD",       "Formed",    ["So","D"]),
    (6,  "BD",        "Formed",    ["B","D"]),
    (7,  "BSSoD",     "Formed",    ["B","Sp","So","D"]),
    (8,  "BRDSSo",    "Formed",    ["B","R","D","Sp","So"]),
    (9,  "B1B2B3",    "Formed",    ["B1","B2","B3"]),
    (10, "R1R2R3",    "Formed",    ["R1","R2","R3"]),
    (11, "D1D2D3",    "Formed",    ["D1","D2","D3"]),
    (12, "S1S2S3",    "Formed",    ["Sp1","Sp2","Sp3"]),
    (13, "So1So2So3", "Formed",    ["So1","So2","So3"]),
    (14, "Xn",        "Formed",    ["Xn"]),
    (15, "RVI1",      "Ready-made",["RVI1"]),
    (16, "RVI2",      "Ready-made",["RVI2"]),
    (17, "Xnn",       "Ready-made",["Xnn"]),
]
DASHBOARDS = [f"1n & {r[1]}" for r in CF_ROWS]
COMP_MAP   = {r[1]: r[3] for r in CF_ROWS}

CHUNK_SIZE = 500_000  # rows per processing chunk

# ── Lotto type codes (worldwide — extendable) ─────────────────────────────
LOTTO_TYPES = {
    "oz":  "Oz Lotto (AUS 7/47)",
    "pb":  "Powerball (AUS 7+1/35+20)",
    "sfl": "Set for Life (AUS)",
    "Mon": "Monday Lotto (AUS 6/45)",
    "Wed": "Wednesday Lotto (AUS 6/45)",
    "Fri": "Friday Lotto (AUS 6/45)",
    "Sat": "Saturday Lotto (AUS 6/45)",
    # Add more as needed — no cap
}

# ═══════════════════════════════════════════════════════════════════════════════
# GAME CONFIGURATION — one entry per game
# ═══════════════════════════════════════════════════════════════════════════════
GAMES_CFG = {
    "pb": {
        "label": "Powerball", "emoji": "🔵", "pool": 35, "pick": 7,
        "draw_day": "Thursday",
        "lottolyzer": "https://en.lottolyzer.com/number-frequencies/australia/powerball",
        "b_file": "Base_pb.xlsx", "b_sheet": "B_pb",
        "b_sheet_legacy": "w values Pb A (2)", "thelott_key": "pb",
        # Structural rows w1-w38; draw history starts at Excel row 39 = iloc[38].
        # Confirmed: iloc[38]=w39=[4,5,9,16,17,29,33]=draw#1283(2020-12-17).
        # File is stale by ~286 draws as of 2026-06-11. Only main 7 numbers stored; powerball excluded.
        "b_hist_start": 38,
    },
    "oz": {
        "label": "Oz Lotto", "emoji": "🟠", "pool": 47, "pick": 7,
        "draw_day": "Tuesday",
        "lottolyzer": "https://en.lottolyzer.com/number-frequencies/australia/oz-lotto",
        "b_file": "Base_oz.xlsx", "b_sheet": "B_oz",
        "b_sheet_legacy": "oz (2)", "thelott_key": "oz",
        # Structural rows w1-w42; draw history starts at Excel row 43 = iloc[42].
        # Confirmed: iloc[42]=w43=[2,9,14,19,28,29,44]=draw#1404(2021-01-12).
        # File is stale by ~282 draws as of 2026-06-09.
        "b_hist_start": 42,
    },
    "sat": {
        "label": "Saturday Lotto", "emoji": "🟡", "pool": 45, "pick": 6,
        "draw_day": "Saturday",
        # "tattslotto" is the correct slug for TattsLotto / Saturday Lotto (draws ~4683+).
        # "weekday-windfall" is Mon/Wed/Fri; "tatts-lotto" (hyphenated) served Set for Life data.
        # History URL is derived by replace() which gives /history/australia/tattslotto.
        "lottolyzer": "https://en.lottolyzer.com/number-frequencies/australia/tattslotto",
        "b_file": "Base_sat.xlsx", "b_sheet": "B_sat",
        "b_sheet_legacy": "Ta (2)", "thelott_key": "sat",
        # Structural rows w1-w42; draw history starts at Excel row 43 = iloc[42].
        # Confirmed: iloc[42]=w43=[12,16,30,31,40,43]=draw#4685(2026-06-13).
        # Corrected from 43→42: b_hist_start is 0-based (pandas iloc), not 1-based Excel row.
        "b_hist_start": 42,
    },
    "sfl": {
        "label": "Set for Life", "emoji": "🟢", "pool": 44, "pick": 7,
        "draw_day": "Daily",
        "lottolyzer": "https://en.lottolyzer.com/number-frequencies/australia/set-for-life",
        "b_file": "Base_sfl.xlsx", "b_sheet": "B_sfl",
        "b_sheet_legacy": "sfl", "thelott_key": "sfl",
        # Structural rows w1-w42; draw history section (w43+) is currently empty.
        # _sync_b returns gap_too_large ("b_hist_start=42 but B has only 42 rows")
        # until real draws are populated at w43 onwards.
        "b_hist_start": 42,
    },
    "mwf": {
        "label": "Mon/Wed/Fri", "emoji": "🟣", "pool": 45, "pick": 6,
        "draw_day": "Mon, Wed, Fri",
        # Lottolyzer uses "weekday-windfall" for Mon/Wed/Fri Lotto (draws ~4692+, 6 picks, pool 1-45).
        # "tatts-lotto" was previously used here but it serves Set for Life data — do NOT use it.
        # "tattslotto" (no hyphen) is Saturday Lotto — also distinct.
        "lottolyzer": "https://en.lottolyzer.com/number-frequencies/australia/weekday-windfall",
        "b_file": "Base_mwf.xlsx", "b_sheet": "B_mwf",      # own file+sheet; was colliding via "Ta (2)"
        "b_sheet_legacy": "Ta (2)", "thelott_key": "mwf",
        # Structural rows w1-w42; draw history section (w43+) is currently empty.
        # _sync_b returns gap_too_large ("b_hist_start=42 but B has only 42 rows")
        # until real draws are populated at w43 onwards.
        "b_hist_start": 42,
    },
}

GAME_KEYS   = list(GAMES_CFG.keys())
GAME_LABELS = {k: f"{v['emoji']} {v['label']}" for k, v in GAMES_CFG.items()}

# ── Game name → folder key mapping (handles brand name variations per state) ──
GAME_NAME_MAP = {
    # Saturday Lotto — multiple brand names across states
    "TattsLotto":               "sat",   # NSW, VIC, QLD brand
    "Saturday Lotto":           "sat",
    "Gold Lotto":               "sat",   # QLD brand
    "X Lotto":                  "sat",   # SA brand
    "Lotto":                    "sat",   # generic fallback

    # Powerball
    "Powerball":                "pb",

    # Oz Lotto
    "Oz Lotto":                 "oz",

    # Mon/Wed/Fri — THE KEY FIX: actual name in data is "Monday & Wednesday Lotto"
    "Monday & Wednesday Lotto": "mwf",   # ← actual name found in scraped data
    "Monday Lotto":             "mwf",   # alternate
    "Wednesday Lotto":          "mwf",   # alternate
    "Friday Lotto":             "mwf",   # alternate
    "Mon & Wed Lotto":          "mwf",   # safety variant

    # Set for Life — likely no syndicates sold, but map in case
    "Set for Life":             "sfl",

    # Skip these — supplementary games, not main pipelines
    "Super 66":                 None,
    "Lucky Lotteries":          None,
    "Lucky Lotteries Mega Jackpot": None,
    "Lucky Lotteries Super Jackpot": None,
}

DISPLAY_THRESHOLD = 500_000   # rows — above this, don't store per-row DataFrames
