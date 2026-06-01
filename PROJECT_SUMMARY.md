# Syndicate System — Project Summary
**Last updated:** 2026-06-01  
**Project location:** `~/Desktop/Sika/o_Automation_Suite/`

---

## WHAT THIS PROJECT IS
A research system for tracking Australian lottery syndicate trends across draws.  
**NOT** a prediction system — a pattern documentation and analysis tool.  
End goal: follow number/syndicate lifecycle from first appearance to expiry.

---

## GAME COVERAGE
| Key | Game | Pool | Pick | Draw | Notes |
|-----|------|------|------|------|-------|
| pb  | Powerball | 1–35 (+PB 1–20) | 7+1 | Thursday | |
| oz  | Oz Lotto | 1–47 | 7 | Tuesday | |
| sat | Saturday Lotto | 1–45 | 6 | Saturday | TattsLotto/Gold Lotto/X Lotto all = sat |
| sfl | Set for Life | 1–44 | 7 | Daily | |
| mwf | Mon/Wed/Fri | 1–45 | 6 | Mon,Wed,Fri | Shares B sheet with sat |

**Game name mapping (critical):**
- `TattsLotto`, `Saturday Lotto`, `Gold Lotto`, `X Lotto`, `Lotto` → `sat`
- `Powerball` → `pb`
- `Oz Lotto` → `oz`
- `Monday & Wednesday Lotto` (actual API name), `Monday Lotto`, `Wednesday Lotto`, `Friday Lotto` → `mwf`
- `Set for Life` → `sfl`
- `Super 66`, `Lucky Lotteries` → skipped (not pipeline games)

---

## FOLDER STRUCTURE
```
o_Automation_Suite/
├── masterapp.py                    ← main Streamlit app (4252 lines)
├── thelott_syndicate_scraper.py    ← thelott.com API scraper
├── lottolyzer_scraper.py           ← lottolyzer.com Since Last scraper
├── excelpro.py                     ← Java ExcelPro → Python conversion
├── task2.py                        ← Rainbow (R) engine (original)
├── task1b.py                       ← Splits (Sp) engine (original)
├── automation_vba.py               ← SplitsCombi (So) engine (original)
├── f_rules_Gclaude.xlsx           ← NOT here; should be in Base/ (see below)
│
├── .streamlit/
│   └── config.toml                ← maxUploadSize=10000 (10GB)
│
├── Main_Data/                     ← RAW scraper output (all games mixed)
│   ├── D_NSW_NSW.csv              ← 41,430 rows
│   ├── D_VIC_VIC.csv              ← 52,503 rows
│   ├── D_QLD_QLD.csv              ← 39,650 rows
│   ├── D_SA_SA.csv                ← 20,687 rows
│   ├── D_TAS_TAS.csv              ← 3,836 rows
│   └── 1n/Main_Data.xlsx          ← cluster 1n main data
│
├── Variables/
│   └── Variable_Elements/
│       ├── Base/
│       │   └── f_rules_Gclaude.xlsx  ← B variable (all games, multi-sheet)
│       └── Direct/
│           ├── D_QLD_QLD.csv
│           └── D.xlsx
│
├── Containers/                    ← Container Formula.xlsx
├── Formulas/                      ← Selected_Counts/
├── Outputs/                       ← BRD_selected.csv
│
└── Games/
    ├── PB/
    ├── OZ/
    ├── SAT/
    ├── SFL/
    └── MWF/
        Each contains:
        ├── Main_Data/             ← game-specific combination datasets (1n etc.)
        ├── Outputs/
        ├── Formulas/Selected_Counts/
        ├── Containers/
        ├── SinceLast/since_last.json    ← from lottolyzer
        └── Variables/Variable_Elements/
            ├── Direct/            ← D_*_{game}.csv (after split)
            ├── Base/              ← B per game (read from f_rules_Gclaude.xlsx)
            ├── Splits/            ← Sp output
            ├── Splits_Combi/      ← So output
            ├── Rainbow/           ← R output
            ├── ExcelPro/          ← Ep output
            └── Container_Variable_Inputs/  ← CVI matrix
```

---

## THE 4 VARIABLE ENGINES
| Engine | File | Input | Output | Feeds |
|--------|------|-------|--------|-------|
| Ep (ExcelPro) | excelpro.py | Top 8 w-cols of D + B objects | wt_ab..wt_cd (new w-sets) | Container Formula rows 1–10, 12–17 |
| Sp (Splits) | task1b.py | Top 4 w-cols of D + 4 split points | split sets a0,a1..d0,d1 + combos | Container Formula |
| So (SplitsCombi) | automation_vba.py | Same top 4 w-cols | union combinations | Container Formula |
| R (Rainbow) | task2.py | Since Last (lottolyzer) + to_keep | powerset combos filtered by Since Last | Container Formula row 11 also standalone |

**Key relationship:**
- D ≠ Main Data. D is a variable element (scraped syndicates). Main Data is historical drawn combinations.
- D is standalone AND feeds into formula row 11.
- Main Data and D are NOT matched/joined — they INTERSECT in the matching engine.

---

## DATA FLOW
```
thelott.com API
    ↓ thelott_syndicate_scraper.py
Main_Data/D_{STATE}_{STATE}.csv  (all games mixed, ~158K rows total)
    ↓ split_d_by_game() in masterapp.py
Games/{GAME}/Variables/Variable_Elements/Direct/D_{STATE}_{game}.csv

lottolyzer.com
    ↓ lottolyzer_scraper.py (Playwright) OR manual CSV upload
Games/{GAME}/SinceLast/since_last.json
    → all_wt = numbers sorted by Since Last ascending (0=last draw first)
    → to_keep = all_wt re-indexed to sequential number order

Variables/Variable_Elements/Base/f_rules_Gclaude.xlsx
    → B variable per game (sheet per game: "w values Pb A (2)", "Ta (2)", "oz (2)", "sfl")
    → w-columns = pre-defined number sets / system entries

CVI Matrix page:
    D → build_w_matrix() → w1..wx columns (longest→shortest)
    → Ep slice: top 8 w-cols → excelpro.py → new w-sets
    → Sp slice: top 4 w-cols → task1b.py → split sets
    → So slice: top 4 w-cols → automation_vba.py → union combis

Container Formula (17 rows):
    Rows 1–10, 12–17: use Ep, Sp, So, B, D
    Row 11: uses R (Rainbow/Since Last) + D
    → Each formula row = one matching run against Main Data

Matching Engine:
    Main Data rows ∩ Variable Element sets = matched combinations
    Results → Container Dashboards → Master Outputs
```

---

## THE 17 CONTAINER FORMULA ROWS
```
1  BRD        8  BRDSSo      15 RVI 1
2  BSD        9  B1B2B3…     16 RVI 2
3  BSoD      10  R1R2R3…     17 Xnn…
4  SD        11  D1D2D3…
5  SoD       12  S1S2S3…
6  BD        13  So1So2So3…
7  BSSoD     14  Xn…
```

---

## THELOTT SCRAPER — CONFIRMED API
```
Step 1: GET https://api.thelott.com/outlet/outlets?state={STATE}&postcode_or_locality={POSTCODE}
Step 2: GET https://api.thelott.com/syndicates/api/search?company={INT}&outlets=ID1,ID2,ID3&limit=100

Company IDs: NSW/ACT=3, VIC/TAS=1, QLD=2, SA=6
CRITICAL: outlets = COMMA-SEPARATED (not repeated params)
SSL bypass required: ctx.verify_mode = ssl.CERT_NONE

Sweeps work from terminal. Streamlit has SSL restrictions — use terminal commands.
```

**Terminal sweep commands:**
```bash
cd ~/Desktop/Sika/o_Automation_Suite
python3 thelott_syndicate_scraper.py sweep NSW
python3 thelott_syndicate_scraper.py sweep ALL
```

---

## B VARIABLE
- File: `f_rules_Gclaude.xlsx` in `Variables/Variable_Elements/Base/`
- Sheets: `w values Pb A (2)` (Pb), `Ta (2)` (Sat+MWF), `oz (2)` (Oz), `sfl` (SfL)
- Each sheet: Row 0 = w-column headers, rows 1+ = number data
- Each w-column = a pre-defined system entry / filter-based number set
- Uploaded ONCE, rarely changes

---

## MAIN DATA NAMING
- `1n`   = standard 6-number combinations
- `1n+1` = 7-number combos (system entry)
- `1n-1` = 5-number combos
- `1n-2` = 4-number combos
- These are the historical drawn combinations matched against variable elements

---

## PERFORMANCE REALITY
| Game | Main Data rows | × 17 formulas | RAM estimate |
|------|---------------|--------------|-------------|
| Oz   | 63M           | 1.07B ops    | ~15GB       |
| SFL  | 44M           | 748M ops     | ~10GB       |
| Pb   | 7M            | 119M ops     | ~2GB        |
| Sat  | 8.3M          | 141M ops     | ~2GB        |
| MWF  | 8.3M          | 141M ops     | ~2GB        |

**Recommendation:** Use DuckDB for Oz/SFL large datasets. Chunked processing for others.
Run ONE game at a time. Test with 100K rows first.

---

## PENDING WORK (as of 2026-06-01)
1. **Scraper page restructure**: Global scraper collapsible at top, per-game breakdown collapsible, remove scraper from game pipeline pages
2. **DuckDB integration** for large dataset matching (63M rows Oz Lotto)
3. **lottolyzer scraper** — Playwright required; manual CSV upload works now
4. **Container Formula page** — wire Ep/Sp/So/R/B/D into 17 formula rows
5. **Container Dashboards** — 17 dashboards per game
6. **Master Outputs** — export and cluster management
7. **Since Last upload** for each game (manual CSV from lottolyzer)
8. **Test run** with small dataset to verify full pipeline
9. **MWF** — no dedicated B sheet yet (shares Ta/Sat sheet)
10. **SFL syndicates** — likely zero or very few syndicates sold

---

## KEY FILES TO HAVE IN o_Automation_Suite
```
masterapp.py                  ← main app
thelott_syndicate_scraper.py  ← D variable scraper
lottolyzer_scraper.py         ← Since Last scraper
excelpro.py                   ← Ep engine (Python)
task2.py                      ← R engine
task1b.py                     ← Sp engine
automation_vba.py             ← So engine
.streamlit/config.toml        ← upload size config
Variables/Variable_Elements/Base/f_rules_Gclaude.xlsx  ← B variable
```

---

## INPUT CHECKLIST PER GAME (for test run)
```
□ D variable     Place D_{STATE}_{game}.csv in Games/{GAME}/Variables/Variable_Elements/Direct/
                 (via Scraper → Promote All + Split)
□ B variable     f_rules_Gclaude.xlsx in Variables/Variable_Elements/Base/ ✓
□ Since Last     Upload CSV from lottolyzer → Variable Inputs → Since Last tab
□ Main Data      Place 1n.csv/xlsx in Games/{GAME}/Main_Data/
□ CVI Matrix     CVI Matrix page → Build W-Matrix button (auto-generates Ep/Sp/So)
□ Ep             Variable Inputs → Ep tab → Run ExcelPro
□ Sp             Variable Inputs → Sp tab → set 4 split points → Run Splits
□ So             Variable Inputs → So tab → Run SplitsCombi
□ R              Variable Inputs → R tab → Generate Rainbow (needs Since Last)
□ Container Formula → run 17 rows
```

---

## SHORTCUTS
```bash
# Run app
sika                        # if alias set up
# OR
streamlit run ~/Desktop/Sika/o_Automation_Suite/masterapp.py

# Open in browser
http://localhost:8501

# Sweep all states
cd ~/Desktop/Sika/o_Automation_Suite
python3 thelott_syndicate_scraper.py sweep ALL
```
