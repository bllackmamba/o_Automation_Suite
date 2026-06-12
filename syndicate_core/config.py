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
    },
    "oz": {
        "label": "Oz Lotto", "emoji": "🟠", "pool": 47, "pick": 7,
        "draw_day": "Tuesday",
        "lottolyzer": "https://en.lottolyzer.com/number-frequencies/australia/oz-lotto",
        "b_file": "Base_oz.xlsx", "b_sheet": "B_oz",
        "b_sheet_legacy": "oz (2)", "thelott_key": "oz",
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
    },
    "sfl": {
        "label": "Set for Life", "emoji": "🟢", "pool": 44, "pick": 7,
        "draw_day": "Daily",
        "lottolyzer": "https://en.lottolyzer.com/number-frequencies/australia/set-for-life",
        "b_file": "Base_sfl.xlsx", "b_sheet": "B_sfl",
        "b_sheet_legacy": "sfl", "thelott_key": "sfl",
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
