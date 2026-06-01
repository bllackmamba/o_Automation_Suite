# Syndicate System — Claude Code Instructions

## WHO YOU ARE WORKING WITH
This is a solo developer project. Be direct, efficient, and avoid over-explaining basics.
Always read this file fully before touching any code.

---

## WHAT THIS PROJECT IS
A research and analysis system for tracking Australian lottery syndicate trends.
- **NOT a prediction tool** — it documents and analyses patterns
- Built as a single Streamlit app (`masterapp.py`, ~4300 lines)
- Tracks syndicate lifecycle: first appearance → expiry
- Run with: `streamlit run ~/Desktop/Sika/o_Automation_Suite/masterapp.py`
- Local URL: `http://localhost:8501`

---

## PROJECT ROOT
```
~/Desktop/Sika/o_Automation_Suite/
```
All paths in code are relative to ROOT (auto-detected by `find_root()` in masterapp.py).

---

## GAME KEYS — ALWAYS USE THESE
| Key | Game | Pool | Pick | Draw |
|-----|------|------|------|------|
| `pb`  | Powerball | 1–35 (+PB 1–20) | 7+1 | Thursday |
| `oz`  | Oz Lotto | 1–47 | 7 | Tuesday |
| `sat` | Saturday Lotto | 1–45 | 6 | Saturday |
| `sfl` | Set for Life | 1–44 | 7 | Daily |
| `mwf` | Mon/Wed/Fri | 1–45 | 6 | Mon/Wed/Fri |

**Brand name → key mapping (critical — API returns brand names):**
- `TattsLotto`, `Saturday Lotto`, `Gold Lotto`, `X Lotto`, `Lotto` → `sat`
- `Monday & Wednesday Lotto`, `Monday Lotto`, `Wednesday Lotto`, `Friday Lotto` → `mwf`
- `Powerball` → `pb` | `Oz Lotto` → `oz` | `Set for Life` → `sfl`
- `Super 66`, `Lucky Lotteries` → **skip** (not pipeline games)

---

## THE 4 VARIABLE ENGINES
| Engine | File | Input | Output |
|--------|------|-------|--------|
| Ep (ExcelPro) | `excelpro.py` | Top 8 w-cols of D + B objects | `wt_ab..wt_cd` new w-sets |
| Sp (Splits) | `task1b.py` | Top 4 w-cols of D + 4 split points | split sets `a0,a1..d0,d1` |
| So (SplitsCombi) | `automation_vba.py` | Top 4 w-cols of D | union combinations |
| R (Rainbow) | `task2.py` | Since Last (lottolyzer) + `to_keep` | powerset combos filtered by Since Last |

**Key distinction:**
- **D** = Direct variable (scraped syndicates from thelott.com) — NOT Main Data
- **Main Data** = historical drawn combinations
- D and Main Data are **never joined** — they INTERSECT in the matching engine

---

## THE 17 CONTAINER FORMULA ROWS
```
1  BRD        6  BD         11 D1D2D3     16 RVI2
2  BSD        7  BSSoD      12 S1S2S3     17 Xnn
3  BSoD       8  BRDSSo     13 So1So2So3
4  SD         9  B1B2B3     14 Xn
5  SoD       10  R1R2R3     15 RVI1
```
- Rows 1–10, 12–17: use Ep, Sp, So, B, D
- Row 11: uses R (Rainbow/Since Last) + D
- Each row = one matching run against Main Data

---

## DATA FLOW (summary)
```
thelott.com API → thelott_syndicate_scraper.py → Main_Data/D_{STATE}_{STATE}.csv
    → split_d_by_game() → Games/{GAME}/Variables/Variable_Elements/Direct/D_{STATE}_{game}.csv

lottolyzer.com → lottolyzer_scraper.py (Playwright) or manual CSV
    → Games/{GAME}/SinceLast/since_last.json

Variables/Variable_Elements/Base/f_rules_Gclaude.xlsx → B variable per game

D → build_w_matrix() → w-columns → Ep/Sp/So engines
    → Container Formula (17 rows) → match against Main Data
    → Container Dashboards → Master Outputs
```

---

## FOLDER STRUCTURE
```
o_Automation_Suite/
├── masterapp.py                          ← main app (DO NOT split into multiple files)
├── thelott_syndicate_scraper.py
├── lottolyzer_scraper.py
├── excelpro.py                           ← Ep engine
├── task2.py                              ← R engine
├── task1b.py                             ← Sp engine
├── automation_vba.py                     ← So engine
├── .streamlit/config.toml               ← maxUploadSize=10000
├── Main_Data/                           ← raw scraper output (all games mixed)
├── Variables/Variable_Elements/
│   ├── Base/f_rules_Gclaude.xlsx        ← B variable (DO NOT auto-modify)
│   ├── Direct/                          ← D variable CSVs
│   ├── Splits/                          ← Sp output
│   ├── Splits_Combi/                    ← So output
│   ├── Rainbow/                         ← R output
│   └── ExcelPro/                        ← Ep output
└── Games/
    └── {GAME}/                          ← pb, oz, sat, sfl, mwf
        ├── Main_Data/
        ├── Outputs/
        ├── SinceLast/since_last.json
        └── Variables/Variable_Elements/
```

---

## B VARIABLE (f_rules_Gclaude.xlsx)
- Location: `Variables/Variable_Elements/Base/f_rules_Gclaude.xlsx`
- Sheets: `w values Pb A (2)` (pb), `Ta (2)` (sat+mwf), `oz (2)` (oz), `sfl` (sfl)
- Row 0 = w-column headers, rows 1+ = number data
- Uploaded ONCE, rarely changes — **never auto-overwrite this file**

---

## SCRAPER — CONFIRMED API
```
Step 1: GET https://api.thelott.com/outlet/outlets?state={STATE}&postcode_or_locality={POSTCODE}
Step 2: GET https://api.thelott.com/syndicates/api/search?company={INT}&outlets=ID1,ID2,ID3&limit=100
Company IDs: NSW/ACT=3, VIC/TAS=1, QLD=2, SA=6
CRITICAL: outlets = COMMA-SEPARATED (not repeated params)
SSL bypass required: ctx.verify_mode = ssl.CERT_NONE
Streamlit has SSL restrictions — always run sweeps from terminal, not Streamlit UI
```

**Terminal sweep:**
```bash
cd ~/Desktop/Sika/o_Automation_Suite
python3 thelott_syndicate_scraper.py sweep ALL
```

---

## PERFORMANCE RULES

| Game | Main Data rows | RAM estimate |
|------|---------------|-------------|
| oz   | 63M           | ~15GB        |
| sfl  | 44M           | ~10GB        |
| pb   | 7M            | ~2GB         |
| sat  | 8.3M          | ~2GB         |
| mwf  | 8.3M          | ~2GB         |

### pandas vs DuckDB — use the right tool, not one or the other

**Always use pandas for:**
- All variable engine work: building D, running Ep/Sp/So/R, CVI w-matrix construction
- B variable loading from f_rules_Gclaude.xlsx (small, column-oriented)
- Any logic that requires row-by-row Python operations or dynamic reshaping
- Streamlit display — DataFrames render directly without conversion
- pb, sat, mwf matching (8M rows fits comfortably in RAM)

**Always use DuckDB for:**
- The final matching/intersection step for oz (63M rows) and sfl (44M rows) only
- Any aggregation or filter across oz/sfl Main Data before loading into memory
- Querying oz/sfl CSVs directly off disk — never load them fully into pandas

**The boundary is the matching engine:**
- Everything before the intersection (variable preparation) → pandas
- The intersection itself for oz/sfl (Main Data ∩ Variable Element sets) → DuckDB
- Do NOT DuckDB-ify the engine files (excelpro.py, task1b.py, automation_vba.py, task2.py)

**Other rules:**
- Use chunked processing (CHUNK_SIZE = 500_000) for pb/sat/mwf if needed
- Run ONE game at a time
- Test with 100K rows before full runs

---

## CODING RULES — ALWAYS FOLLOW
1. **masterapp.py stays as one file** — do not split it or suggest refactoring into modules
2. **Preserve all existing section separators** (`# ═══...`) and comment style
3. **Never modify f_rules_Gclaude.xlsx** programmatically unless explicitly asked
4. **Game keys are always lowercase**: `pb`, `oz`, `sat`, `sfl`, `mwf`
5. **D ≠ Main Data** — never conflate these two datasets
6. **SSL bypass is intentional** in the scraper — do not remove or flag it
7. When adding new Streamlit pages, follow the existing page pattern in masterapp.py
8. Prefer `pathlib.Path` over `os.path` for all file operations
9. Always check `GAMES_CFG` dict for game config — do not hardcode game values inline
10. For any matching logic, preserve the intersection model (D ∩ Main Data)

---

## PENDING WORK (as of 2026-06-01)
1. Scraper page restructure — global scraper collapsible at top, per-game collapsible below
2. DuckDB integration for oz and sfl large dataset matching
3. Container Formula page — wire Ep/Sp/So/R/B/D into all 17 formula rows
4. Container Dashboards — 17 dashboards per game
5. Master Outputs — export and cluster management
6. lottolyzer scraper — Playwright required; manual CSV upload works now
7. Since Last upload UI per game (manual CSV from lottolyzer)
8. Test run with small dataset (100K rows) to verify full pipeline
9. MWF — no dedicated B sheet yet (shares Ta/Sat sheet)
10. SFL syndicates — likely zero or very few syndicates sold

---

## MAIN DATA NAMING CONVENTION
- `1n`   = standard 6-number combinations
- `1n+1` = 7-number combos (system entry)
- `1n-1` = 5-number combos
- `1n-2` = 4-number combos

---

## QUICK REFERENCE
```bash
# Run app
streamlit run ~/Desktop/Sika/o_Automation_Suite/masterapp.py

# Alias (if set)
sika

# Sweep scraper
cd ~/Desktop/Sika/o_Automation_Suite
python3 thelott_syndicate_scraper.py sweep ALL
python3 thelott_syndicate_scraper.py sweep NSW
```
