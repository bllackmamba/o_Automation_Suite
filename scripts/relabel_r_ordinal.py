#!/usr/bin/env python3
"""Relabel R combo tuples from raw since-last distance → gap-compressed ordinal.

Backfills files written BEFORE syndicate_core.generators.generate_rainbow was
changed to emit gap-compressed group ordinals. This is a PURE RELABEL: only the
combo-tuple label columns are rewritten; every number/payload column is left
byte-identical (verified per file). Idempotent — re-running on an already-ordinal
file is a no-op.

Targets, under Games/ by default (archive/deprecated dirs excluded):
  • R_{game}.csv           → relabel the `combo` column
  • CVI_*.csv (R blocks)   → relabel `Set_Label` (and `Constituent_Groups` if
                             present) for rows where Source == "R" ONLY.

Mapping is SELF-CONTAINED per file: ordinal(k) = 1-based rank of k among the
distinct integers appearing in that file's own combo tuples. (Every group key
appears as an r=1 singleton, so the key set is complete.) When a game's
since_last.json is available it is used only as a NON-authoritative cross-check
and any divergence is reported — the file's own keys still drive the relabel,
because they are authoritative for that frozen file's content.

Usage:
    python3 scripts/relabel_r_ordinal.py                 # dry-run over Games/
    python3 scripts/relabel_r_ordinal.py --apply         # write changes
    python3 scripts/relabel_r_ordinal.py path1 path2 ... # explicit files
    python3 scripts/relabel_r_ordinal.py --apply p1      # write a single file

Apply mode writes ONE overwriting-safe backup per file (`<file>.rawbak`, never
clobbered if it already exists) before rewriting, and re-verifies that every
non-label column is byte-identical to the original afterwards.
"""
from __future__ import annotations

import argparse
import ast
import csv
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ── tuple parsing ────────────────────────────────────────────────────────────
def parse_combo(cell: str):
    """Return a tuple of ints if `cell` is a combo tuple string, else None.

    Guards against bare numbers (e.g. a D Syndicate_ID '22082278') and any
    non-tuple/non-int content — only genuine (a, b, ...) int tuples qualify.
    """
    if cell is None:
        return None
    s = cell.strip()
    if not s or not (s.startswith("(") and s.endswith(")")):
        return None
    try:
        val = ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(val, tuple) or not val:
        return None
    if not all(isinstance(x, int) for x in val):
        return None
    return val


# ── one file ─────────────────────────────────────────────────────────────────
class FileReport:
    def __init__(self, path):
        self.path = path
        self.kind = None            # "R" | "CVI" | "skip"
        self.reason = ""            # why skipped, if skipped
        self.n_rows = 0
        self.label_cols = []        # columns actually relabelled
        self.n_r_rows = 0           # CVI: rows with Source == R
        self.n_tuples = 0           # cells that parsed to a tuple
        self.n_no_tuple = 0         # target rows whose label was NOT a tuple
        self.keys = []              # sorted distinct raw keys found in-file
        self.mapping = {}           # raw key -> ordinal
        self.n_changed = 0          # cells whose label value changed
        self.n_identity = 0         # tuple cells already ordinal (no change)
        self.already_ordinal = False
        self.json_keys = None       # since_last.json cross-check keys
        self.json_status = ""       # match / mismatch / n/a
        self.new_rows = None        # transformed rows (kept for --apply)
        self.header = None


def classify(header):
    cols = list(header)
    if "combo" in cols:
        return "R", ["combo"], None
    if "Set_Label" in cols and "Source" in cols:
        labels = ["Set_Label"] + (["Constituent_Groups"] if "Constituent_Groups" in cols else [])
        return "CVI", labels, "Source"
    return "skip", [], None


def game_key_from_path(path: Path):
    for gk in ("sat", "mwf", "pb", "oz", "sfl"):
        if f"_{gk}" in path.name.lower() or f"/{gk.upper()}/" in str(path).upper():
            return gk
    return None


def load_json_keys(gk):
    """Authoritative keys = sorted distinct (since_last + 1), matching
    generate_rainbow's grouping. Returns sorted list or None."""
    if gk is None:
        return None
    hits = [h for h in glob.glob(str(REPO / "Games" / "**" / "since_last.json"), recursive=True)
            if f"_{gk}" in h.lower() or f"/{gk.upper()}/" in h.upper()]
    if not hits:
        return None
    try:
        d = json.loads(Path(hits[0]).read_text())
        vals = {int(v) + 1 for v in d.get("since_last_dict", {}).values()}
        return sorted(vals)
    except Exception:
        return None


def analyse(path: Path) -> FileReport:
    rep = FileReport(path)
    with path.open(newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        rep.kind, rep.reason = "skip", "empty file"
        return rep
    header, data = rows[0], rows[1:]
    rep.header = header
    rep.n_rows = len(data)
    kind, label_cols, source_col = classify(header)
    rep.kind = kind
    if kind == "skip":
        if path.name.startswith("R_"):
            rep.reason = ("R file lacks a `combo` column — legacy/column-oriented "
                          "format; REGENERATE via the pipeline, do not relabel")
        else:
            rep.reason = "no R data (no combo / Set_Label+Source columns)"
        return rep

    idx = {c: i for i, c in enumerate(header)}
    src_i = idx.get(source_col) if source_col else None
    lab_i = [idx[c] for c in label_cols]

    # Pass 1: collect distinct raw keys from parseable tuples (R-gated for CVI).
    keyset = set()
    for r in data:
        if src_i is not None:
            if src_i >= len(r) or r[src_i] != "R":
                continue
            rep.n_r_rows += 1
        for ci in lab_i:
            if ci >= len(r):
                continue
            t = parse_combo(r[ci])
            if t is not None:
                keyset |= set(t)
    rep.keys = sorted(keyset)
    rep.mapping = {k: i + 1 for i, k in enumerate(rep.keys)}
    rep.label_cols = label_cols
    rep.already_ordinal = bool(rep.keys) and rep.keys == list(range(1, len(rep.keys) + 1))

    # since_last.json cross-check (informational only).
    rep.json_keys = load_json_keys(game_key_from_path(path))
    if rep.json_keys is None:
        rep.json_status = "n/a (no since_last.json)"
    elif rep.json_keys == rep.keys:
        rep.json_status = "match"
    else:
        rep.json_status = (f"MISMATCH (json {len(rep.json_keys)} keys "
                           f"{rep.json_keys[:6]}… vs file {len(rep.keys)} keys "
                           f"{rep.keys[:6]}…) — using file keys")

    # Pass 2: build transformed rows; only label cells change.
    new_data = []
    for r in data:
        nr = list(r)
        gated = (src_i is None) or (src_i < len(r) and r[src_i] == "R")
        for ci in lab_i:
            if ci >= len(nr):
                continue
            if not gated:
                continue
            t = parse_combo(nr[ci])
            if t is None:
                if src_i is not None:            # a gated R row with no tuple
                    rep.n_no_tuple += 1
                continue
            rep.n_tuples += 1
            new_label = str(tuple(rep.mapping[k] for k in t))
            if new_label != nr[ci].strip():
                nr[ci] = new_label
                rep.n_changed += 1
            else:
                rep.n_identity += 1
        new_data.append(nr)
    rep.new_rows = new_data
    return rep


def write_file(path: Path, header, rows):
    with path.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def verify_payload_untouched(orig_path: Path, new_header, new_rows, label_cols):
    """Assert every NON-label column is byte-identical to the original file."""
    with orig_path.open(newline="") as f:
        orig = list(csv.reader(f))
    o_header, o_data = orig[0], orig[1:]
    if o_header != new_header or len(o_data) != len(new_rows):
        return False, "header/row-count drift"
    lab_i = {o_header.index(c) for c in label_cols}
    for oi, (orow, nrow) in enumerate(zip(o_data, new_rows)):
        if len(orow) != len(nrow):
            return False, f"row {oi} width drift"
        for ci in range(len(orow)):
            if ci in lab_i:
                continue
            if orow[ci] != nrow[ci]:
                return False, f"row {oi} col {ci} changed (non-label)"
    return True, "ok"


def discover_default():
    out = []
    for pat in ("Games/**/R_*.csv", "Games/**/CVI_*.csv"):
        for p in glob.glob(str(REPO / pat), recursive=True):
            if "_archive" in p or "_deprecated" in p:
                continue
            out.append(Path(p))
    return sorted(set(out))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="explicit files (default: Games/ tree)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args(argv)

    targets = [Path(p) for p in args.paths] if args.paths else discover_default()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== R ordinal relabel · {mode} · {len(targets)} candidate file(s) ===\n")

    total_changed = total_files_touched = 0
    for path in targets:
        rel = path.relative_to(REPO) if path.is_absolute() and str(path).startswith(str(REPO)) else path
        if not path.exists():
            print(f"[MISS] {rel} — not found"); continue
        rep = analyse(path)
        if rep.kind == "skip":
            print(f"[SKIP] {rel} — {rep.reason}"); continue

        head = f"[{rep.kind:>3}] {rel}"
        detail = f"rows={rep.n_rows}"
        if rep.kind == "CVI":
            detail += f" R-rows={rep.n_r_rows}"
        detail += f" groups={len(rep.keys)}"
        print(f"{head}\n       {detail} | labels={rep.label_cols}")
        if rep.keys:
            span = f"{rep.keys[0]}..{rep.keys[-1]}"
            print(f"       raw keys ({span}) -> ordinals 1..{len(rep.keys)}"
                  f"{'  [already ordinal]' if rep.already_ordinal else ''}")
            print(f"       since_last.json cross-check: {rep.json_status}")
        else:
            print(f"       no combo tuples found "
                  f"({'empty/lost R Set_Labels' if rep.kind=='CVI' else 'empty R file'})")
        if rep.n_no_tuple:
            print(f"       ⚠ {rep.n_no_tuple} R row(s) had no parseable tuple (left untouched)")
        print(f"       WOULD CHANGE {rep.n_changed} label cell(s); "
              f"{rep.n_identity} already correct; payload columns untouched")

        if rep.n_changed:
            total_files_touched += 1
            total_changed += rep.n_changed

        if args.apply and rep.n_changed:
            ok, why = verify_payload_untouched(path, rep.header, rep.new_rows, rep.label_cols)
            if not ok:
                print(f"       ✗ ABORT write — payload guard failed: {why}")
                continue
            bak = path.with_suffix(path.suffix + ".rawbak")
            if not bak.exists():
                bak.write_bytes(path.read_bytes())
                print(f"       backup → {bak.relative_to(REPO) if str(bak).startswith(str(REPO)) else bak}")
            else:
                print(f"       backup exists (kept): {bak.name}")
            write_file(path, rep.header, rep.new_rows)
            # post-write re-verify against the backup
            ok2, why2 = verify_payload_untouched(bak, rep.header, list(csv.reader(path.open(newline="")))[1:], rep.label_cols)
            print(f"       ✓ written; post-write payload check: {'OK' if ok2 else 'FAILED: '+why2}")
        print()

    verb = "changed" if args.apply else "would change"
    print(f"=== {mode} summary: {total_changed} label cell(s) {verb} "
          f"across {total_files_touched} file(s) ===")
    if not args.apply and total_changed:
        print("Re-run with --apply to write (one .rawbak backup per file).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
