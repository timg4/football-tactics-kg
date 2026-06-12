"""Export KG facts (EDB) for the Datalog re-expression of P1/P2.

Writes generated/datalog/facts.duckdb (tables: event, next, part_of, possession)
and, with --tsv, Soufflé-style .facts TSVs next to it.

Usage:  python -m src.datalog.export [--tsv]
"""

import argparse
from pathlib import Path

import duckdb
import pandas as pd

from ..ingest import common

OUT_DIR = common.REPO_ROOT / "generated" / "datalog"

EXPORTS = {
    "event": """
        MATCH (e:Event)-[:BY_TEAM]->(t:Team)
        RETURN e.event_id AS eid, e.match_id AS mid, e.idx AS idx,
               e.period AS period, e.timestamp_s AS ts, e.type AS type,
               e.x AS x, t.team_id AS team, e.outcome AS outcome,
               e.recovery_failure AS recovery_failure
    """,
    "next": """
        MATCH (a:Event)-[:NEXT]->(b:Event)
        RETURN a.event_id AS a, b.event_id AS b
    """,
    "part_of": """
        MATCH (e:Event)-[:PART_OF]->(po:Possession)
        RETURN e.event_id AS eid, po.match_id AS mid, po.possession AS poss
    """,
    "possession": """
        MATCH (po:Possession)-[:POSSESSION_BY]->(t:Team)
        RETURN po.match_id AS mid, po.possession AS poss,
               t.team_id AS team, po.play_pattern AS play_pattern
    """,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", action="store_true",
                    help="also write Soufflé .facts TSV files")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = OUT_DIR / "facts.duckdb"
    if db_path.exists():
        db_path.unlink()
    db = duckdb.connect(str(db_path))

    driver = common.get_driver()
    with driver.session() as s:
        for name, query in EXPORTS.items():
            print(f"exporting {name} ...", flush=True)
            df = pd.DataFrame([dict(r) for r in s.run(query)])
            db.execute(f"CREATE TABLE {name} AS SELECT * FROM df")
            print(f"  {len(df):,} rows")
            if args.tsv:
                # Soufflé reads tab-separated, no header; bools as 0/1 and
                # missing coordinates as -1.0 (matched by `X >= 0` guards)
                tsv = df.copy()
                for col in tsv.columns:
                    if tsv[col].dtype == bool:
                        tsv[col] = tsv[col].astype(int)
                if "x" in tsv.columns:
                    tsv["x"] = tsv["x"].fillna(-1.0)
                tsv.to_csv(OUT_DIR / f"{name}.facts", sep="\t", header=False,
                           index=False, na_rep="")
    driver.close()
    db.close()
    print(f"done -> {db_path}")


if __name__ == "__main__":
    main()
