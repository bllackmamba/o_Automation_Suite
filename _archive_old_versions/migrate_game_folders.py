#!/usr/bin/env python3
"""
migrate_game_folders.py

Migrates o_Automation_Suite folder structure to the agreed naming convention:

1. Removes duplicate top-level folders at the root of o_Automation_Suite
   (Containers, Formulas, Main_Data, Variables, Outputs)

2. For each game folder (SAT, OZ, PB, MWF, SFL):
   a. Renames top-level subfolders to use _<game> suffix
      e.g.  Main_Data      → main_data_sat
            Formulas       → formulas_sat
            Containers     → containers_sat
            Outputs        → outputs_sat
            SinceLast      → sincelast_sat
            Games_Breakdown → games_breakdown_sat

   b. Flattens the old Variables/ tree into two suffixed top-level folders:
        Variables/Scraper/             → variable_inputs_<game>/Scraper/
        Variables/Variable_Elements/*  → variable_inputs_<game>/   (one level flattened)
        Variables/Container_Variable_Inputs/ → container_variable_inputs_<game>/
      Then removes the now-empty Variables/ shell.

Usage:
    python migrate_game_folders.py --root /path/to/o_Automation_Suite [--dry-run]
"""

import os
import sys
import shutil
import argparse

GAMES = ["SAT", "OZ", "PB", "MWF", "SFL"]

TOP_LEVEL_TO_REMOVE = [
    "Containers",
    "Formulas",
    "Main_Data",
    "Variables",
    "Outputs",
]

# Maps normalised folder name → canonical base name (before _{game} suffix)
GAME_SUBFOLDER_MAP = {
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
    "cvi_matrix":                "container_variable_inputs",  # old alias
    "cvimatrix":                 "container_variable_inputs",
    "container_variable_inputs": "container_variable_inputs",
    "containervariableinputs":   "container_variable_inputs",
    "variable_inputs":           "variable_inputs",
    "variableinputs":            "variable_inputs",
}

# Subfolders inside the old Variables/ tree that should NOT be migrated here
# (they are handled by the Variables migration step)
VARIABLES_SKIP = {"variable_elements", "scraper", "container_variable_inputs"}


def normalize(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def get_canonical(folder_name: str, game_key: str) -> str | None:
    """Return the canonical base name, stripping any existing suffix first."""
    key = normalize(folder_name)
    suffix = f"_{game_key.lower()}"
    if key.endswith(suffix):
        key = key[: -len(suffix)]
    return GAME_SUBFOLDER_MAP.get(key)


def _move(src: str, dst: str, dry_run: bool):
    """Move src → dst, with dry-run support."""
    if dry_run:
        print(f"    [DRY RUN] move  {src}  →  {dst}")
    else:
        os.rename(src, dst)
        print(f"    Moved:  {os.path.basename(src)}  →  {dst}")


def migrate_variables_folder(game_path: str, gk: str, dry_run: bool):
    """
    Migrate the old Variables/ tree into the new flat suffixed structure.

    Old layout:
        Variables/
            Scraper/
            Variable_Elements/
                Base/ Splits/ Splits_Combi/ Rainbow/ ExcelPro/
            Container_Variable_Inputs/

    New layout:
        variable_inputs_{gk}/
            Scraper/  Base/  Splits/  Splits_Combi/  Rainbow/  ExcelPro/
        container_variable_inputs_{gk}/
    """
    variables_dir = os.path.join(game_path, "Variables")
    if not os.path.isdir(variables_dir):
        return  # nothing to migrate

    var_inputs_dst  = os.path.join(game_path, f"variable_inputs_{gk}")
    cvi_dst         = os.path.join(game_path, f"container_variable_inputs_{gk}")

    print(f"\n    Migrating Variables/ tree for {gk.upper()}:")

    # ── Scraper ───────────────────────────────────────────────────────────
    src_scraper = os.path.join(variables_dir, "Scraper")
    if os.path.isdir(src_scraper):
        dst_scraper = os.path.join(var_inputs_dst, "Scraper")
        if not os.path.exists(var_inputs_dst):
            if not dry_run:
                os.makedirs(var_inputs_dst, exist_ok=True)
            else:
                print(f"    [DRY RUN] makedirs {var_inputs_dst}")
        if os.path.exists(dst_scraper):
            print(f"    CONFLICT — {dst_scraper} already exists, skipping Scraper")
        else:
            _move(src_scraper, dst_scraper, dry_run)

    # ── Variable_Elements/* → variable_inputs_{gk}/ (flatten one level) ─
    var_elem_dir = os.path.join(variables_dir, "Variable_Elements")
    if os.path.isdir(var_elem_dir):
        if not os.path.exists(var_inputs_dst) and not dry_run:
            os.makedirs(var_inputs_dst, exist_ok=True)
        for entry in sorted(os.listdir(var_elem_dir)):
            src = os.path.join(var_elem_dir, entry)
            dst = os.path.join(var_inputs_dst, entry)
            if os.path.exists(dst):
                print(f"    CONFLICT — {entry} already in variable_inputs_{gk}/, skipping")
                continue
            _move(src, dst, dry_run)
        # Remove now-empty Variable_Elements shell
        if not dry_run and not os.listdir(var_elem_dir):
            os.rmdir(var_elem_dir)
            print(f"    Removed empty dir: Variable_Elements/")
        elif dry_run:
            print(f"    [DRY RUN] remove empty shell: Variable_Elements/")

    # ── Container_Variable_Inputs → container_variable_inputs_{gk} ───────
    src_cvi = os.path.join(variables_dir, "Container_Variable_Inputs")
    if os.path.isdir(src_cvi):
        if os.path.exists(cvi_dst):
            print(f"    CONFLICT — {cvi_dst} already exists, skipping CVI folder")
        else:
            _move(src_cvi, cvi_dst, dry_run)

    # ── Remove the empty Variables/ shell ─────────────────────────────────
    if not dry_run:
        remaining = [e for e in os.listdir(variables_dir)
                     if not e.startswith(".")]
        if not remaining:
            os.rmdir(variables_dir)
            print(f"    Removed empty dir: Variables/")
        else:
            print(f"    NOTE: Variables/ not empty after migration "
                  f"({remaining}) — left in place")
    else:
        print(f"    [DRY RUN] remove empty shell: Variables/")


def migrate(root: str, dry_run: bool):
    if not os.path.isdir(root):
        print(f"ERROR: Root path does not exist: {root}")
        sys.exit(1)

    print(f"Root: {root}")
    print(f"Dry run: {dry_run}\n")

    # ------------------------------------------------------------------ #
    # Step 1: Remove top-level duplicate folders
    # ------------------------------------------------------------------ #
    print("=== Step 1: Remove top-level duplicate folders ===")
    for folder_name in TOP_LEVEL_TO_REMOVE:
        folder_path = os.path.join(root, folder_name)
        if os.path.isdir(folder_path):
            if dry_run:
                print(f"  [DRY RUN] Would remove: {folder_path}")
            else:
                shutil.rmtree(folder_path)
                print(f"  Removed: {folder_path}")
        else:
            print(f"  Not found (skip): {folder_path}")

    print()

    # ------------------------------------------------------------------ #
    # Step 2: Rename top-level subfolders inside each game folder
    # ------------------------------------------------------------------ #
    games_dir = os.path.join(root, "Games")
    if not os.path.isdir(games_dir):
        print(f"WARNING: Games directory not found at {games_dir}")
        print("Skipping game subfolder renaming.")
        return

    print("=== Step 2: Rename game top-level subfolders ===")
    for game in GAMES:
        game_path = os.path.join(games_dir, game)
        if not os.path.isdir(game_path):
            print(f"\n  [{game}] folder not found — skipping")
            continue

        print(f"\n  [{game}]  {game_path}")
        gk     = game.lower()
        suffix = f"_{gk}"

        for entry in sorted(os.listdir(game_path)):
            entry_path = os.path.join(game_path, entry)
            if not os.path.isdir(entry_path):
                continue

            norm = normalize(entry)
            if norm == "variables":
                continue  # handled separately in Step 3

            canonical = get_canonical(entry, game)
            if canonical is None:
                print(f"    UNKNOWN folder (skipped): {entry}")
                continue

            desired_name = f"{canonical}{suffix}"
            desired_path = os.path.join(game_path, desired_name)

            if entry == desired_name:
                print(f"    OK (already correct): {entry}")
                continue

            if os.path.exists(desired_path):
                print(f"    CONFLICT — target exists, skipping: {entry} -> {desired_name}")
                continue

            if dry_run:
                print(f"    [DRY RUN] {entry}  →  {desired_name}")
            else:
                os.rename(entry_path, desired_path)
                print(f"    Renamed: {entry}  →  {desired_name}")

    # ------------------------------------------------------------------ #
    # Step 3: Migrate Variables/ tree for each game
    # ------------------------------------------------------------------ #
    print("\n=== Step 3: Migrate Variables/ tree ===")
    for game in GAMES:
        game_path = os.path.join(games_dir, game)
        if not os.path.isdir(game_path):
            continue
        migrate_variables_folder(game_path, game.lower(), dry_run)

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate o_Automation_Suite folder structure.")
    parser.add_argument(
        "--root", required=True,
        help="Absolute path to the o_Automation_Suite folder",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without applying them",
    )
    args = parser.parse_args()
    migrate(args.root, args.dry_run)


if __name__ == "__main__":
    main()
