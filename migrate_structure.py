#!/usr/bin/env python3
"""
migrate_structure.py — one-time tidy-up for the new folder layout.

Safe by default: it PRINTS what it will do (dry run). Re-run with --go to apply.

What it does:
  1. Moves raw scrape files out of Main_Data/ into Global_Scraper/ and renames
     the old doubled name D_<STATE>_<STATE>.csv → D_<STATE>.csv.
     (Main_Data is reserved for YOUR own draw data.)
  2. Lists stale trial files you can delete (old CVI_Matrix_* / CVI_BRD* and old
     per-game split files) — it does NOT delete them; you decide.

Usage:
  cd ~/Desktop/Sika/o_Automation_Suite
  python3 migrate_structure.py          # dry run (shows plan)
  python3 migrate_structure.py --go     # actually move files
"""
import sys, shutil, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GO = "--go" in sys.argv

def say(msg): print(("APPLY: " if GO else "PLAN : ") + msg)

def main():
    main_data = ROOT / "Main_Data"
    gscrape   = ROOT / "Global_Scraper"
    gscrape.mkdir(parents=True, exist_ok=True)

    # 1) Move raw D scrapes out of Main_Data → Global_Scraper, clean the name.
    moved = 0
    if main_data.exists():
        for fp in sorted(main_data.glob("D_*.csv")):
            # D_NSW_NSW.csv -> D_NSW.csv ; D_NSW.csv stays D_NSW.csv
            m = re.match(r"D_([A-Z]{2,3})(?:_\1)?\.csv$", fp.name)
            new_name = f"D_{m.group(1)}.csv" if m else fp.name
            dest = gscrape / new_name
            say(f"move {fp.relative_to(ROOT)}  ->  {dest.relative_to(ROOT)}")
            if GO:
                shutil.move(str(fp), str(dest))
            moved += 1
    if moved == 0:
        print("       (no raw D_*.csv found in Main_Data — nothing to move)")

    # 2) Flag stale trial files (NOT deleted — your call).
    print("\nStale files you can delete after re-running the pipeline "
          "(review first):")
    patterns = ["**/CVI_Matrix_*", "**/CVI_BRD*", "**/Container_Variable_Inputs/CVI_*"]
    seen = set()
    for pat in patterns:
        for fp in ROOT.glob(pat):
            if fp.is_file() and fp not in seen:
                seen.add(fp)
                print(f"   stale? {fp.relative_to(ROOT)}")
    if not seen:
        print("   (none found)")

    print("\nDone." + ("" if GO else "  (dry run — re-run with --go to apply moves)"))

if __name__ == "__main__":
    main()
