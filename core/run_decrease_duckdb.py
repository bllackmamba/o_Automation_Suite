# -*- coding: utf-8 -*-
"""
run_decrease_duckdb.py — PART 2 (DuckDB) contributing-parent extraction for the
large combination files (8_44, 8_47), with a validation pass on 8_35.

A parent is "contributing" iff it is the first (min file-order) claimer of at
least one of its 8 child 7-subsets, under first-claim exclusivity. That is
exactly ROW_NUMBER() OVER (PARTITION BY child ORDER BY rid) = 1, computed
efficiently as: first_rid = MIN(rid) GROUP BY child; contributing parents =
COUNT(DISTINCT first_rid). No 1.4B-row window sort.

Child key: rows are descending-sorted, so removing one element keeps canonical
order. Each child (7 numbers < 64) is packed into one BIGINT (6 bits each).

Usage:
  python run_decrease_duckdb.py <name> [--explain-only] [--out PATH]
  names: combinations_8_35 | combinations_8_44 | combinations_8_47
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

CORE = Path(__file__).resolve().parent

# name -> (file, header, expected_total, expected_contributing)
CONFIGS = {
    "combinations_8_35": ("combinations_8_35.csv", True, 23_535_820, 5_379_616),
    "combinations_8_44": ("combinations_8_44.csv", True, 177_232_627, 32_224_114),
    "combinations_8_47": ("combinations_8_47.csv", True, 314_457_495, 53_524_680),
}

P = [64 ** i for i in range(7)]  # P[0]=1 (c8) .. P[6]=64^6 (most significant)


def child_keys_sql() -> str:
    """8 BIGINT child-key expressions (remove c1..c8), descending order preserved."""
    cols = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]
    exprs = []
    for drop in range(8):
        remaining = [cols[i] for i in range(8) if i != drop]  # 7 cols, descending
        # most significant first: remaining[0] * 64^6 ... remaining[6] * 64^0
        terms = [f"{remaining[j]}*{P[6 - j]}" for j in range(7)]
        exprs.append("(" + " + ".join(terms) + ")")
    return "[\n      " + ",\n      ".join(exprs) + "\n    ]"


def run(name: str, explain_only: bool, out_path: Path | None) -> None:
    fname, header, exp_total, exp_contrib = CONFIGS[name]
    src = CORE / fname
    if out_path is None:
        out_path = CORE / f"{name}_contributing_input.csv"

    print(f"\n{'='*64}\n{name}: {fname}\n{'='*64}", flush=True)
    con = duckdb.connect(":memory:")
    con.execute("SET preserve_insertion_order=true")
    con.execute("PRAGMA temp_directory='/tmp/duckdb_spill'")
    try:
        con.execute("SET memory_limit='80GB'")
    except Exception:
        pass
    nthreads = con.execute("SELECT current_setting('threads')").fetchone()[0]
    print(f"  duckdb {duckdb.__version__} | threads={nthreads}", flush=True)

    cols_spec = "{" + ", ".join(f"'c{i}': 'BIGINT'" for i in range(1, 9)) + "}"
    read = (f"read_csv('{src}', header={'true' if header else 'false'}, "
            f"columns={cols_spec})")
    keys = child_keys_sql()

    # ── EXPLAIN the heavy aggregation (plan before running) ─────────────
    agg_sql = f"""
    SELECT MIN(rid) AS first_rid
    FROM (
      SELECT rid, UNNEST({keys}) AS child
      FROM (SELECT row_number() OVER () AS rid, * FROM {read})
    )
    GROUP BY child
    """
    print("\n  --- EXPLAIN (aggregation plan) ---", flush=True)
    plan = con.execute("EXPLAIN " + agg_sql).fetchall()
    print("\n".join("    " + r[1] for r in plan), flush=True)
    if explain_only:
        print("\n  (explain-only; not executing)", flush=True)
        return

    t0 = time.time()
    # 1) parents with file-order rid
    con.execute(f"CREATE TABLE parents AS SELECT row_number() OVER () AS rid, * FROM {read}")
    n_total = con.execute("SELECT count(*) FROM parents").fetchone()[0]
    t_load = time.time() - t0
    print(f"\n  loaded parents: {n_total:,} rows in {t_load:.1f}s "
          f"({'OK' if n_total == exp_total else 'MISMATCH vs '+format(exp_total,',')})",
          flush=True)

    # 2) first claimer per child, then distinct contributing rids
    t1 = time.time()
    con.execute(f"""
      CREATE TABLE firsts AS
      SELECT MIN(rid) AS first_rid
      FROM (SELECT rid, UNNEST({keys}) AS child FROM parents)
      GROUP BY child
    """)
    n_children = con.execute("SELECT count(*) FROM firsts").fetchone()[0]
    con.execute("CREATE TABLE contrib AS SELECT DISTINCT first_rid AS rid FROM firsts")
    contributing = con.execute("SELECT count(*) FROM contrib").fetchone()[0]
    t_agg = time.time() - t1
    print(f"  distinct children : {n_children:,}", flush=True)
    print(f"  contributing      : {contributing:,}  (expected {exp_contrib:,}  "
          f"{'OK' if contributing == exp_contrib else 'MISMATCH'})  in {t_agg:.1f}s",
          flush=True)

    ok = (n_total == exp_total and contributing == exp_contrib)
    if not ok:
        raise SystemExit(f"!!! STOP: {name} mismatch (total={n_total}, contributing={contributing})")

    # 3) export contributing parent rows in file order
    t2 = time.time()
    con.execute(f"""
      COPY (
        SELECT c1,c2,c3,c4,c5,c6,c7,c8
        FROM parents JOIN contrib USING (rid)
        ORDER BY rid
      ) TO '{out_path}' (HEADER, DELIMITER ',')
    """)
    t_exp = time.time() - t2
    size_mb = out_path.stat().st_size / 1_048_576
    dt = time.time() - t0
    print(f"  exported          : {out_path.name}  {size_mb:.2f} MB in {t_exp:.1f}s", flush=True)
    print(f"  PHASES            : load={t_load:.1f}s agg={t_agg:.1f}s export={t_exp:.1f}s "
          f"total={dt:.1f}s ({dt/60:.1f} min)", flush=True)
    print(f"  RESULT            : PASS", flush=True)


def main() -> None:
    args = sys.argv[1:]
    explain_only = "--explain-only" in args
    out_path = None
    if "--out" in args:
        out_path = Path(args[args.index("--out") + 1])
        args = [a for i, a in enumerate(args) if a not in ("--out", str(out_path))]
    names = [a for a in args if not a.startswith("--")]
    for nm in names:
        run(nm, explain_only, out_path)


if __name__ == "__main__":
    main()
