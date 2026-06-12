"""Validate materialized patterns against StatsBomb's own signals.

P1 vs the vendor-computed `counterpress` flag (pressing within 5s of an
open-play turnover) and P2 vs `play_pattern = 'From Counter'`. The signals have
different anchor semantics, so we expect strong -- not perfect -- agreement
(docs/patterns.md, validation hooks).

Usage:  python -m src.patterns.validate
"""

from ..ingest import common


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "n/a"


def main():
    driver = common.get_driver()
    with driver.session() as s:
        counts = {r["p"]: r["n"] for r in s.run(
            "MATCH (pi:PatternInstance) RETURN pi.pattern AS p, count(*) AS n")}
        print(f"Instances: {counts}\n")

        # --- P1 vs counterpress -------------------------------------------
        row = s.run("""
            MATCH (pi:PatternInstance {pattern:'P1'})-[:MATCHES]->(p:Pressure)
            RETURN count(p) AS total,
                   count(CASE WHEN p.counterpress THEN 1 END) AS flagged
        """).single()
        print(f"P1 anchors that StatsBomb flags as counterpress: "
              f"{row['flagged']}/{row['total']} ({pct(row['flagged'], row['total'])})")

        row = s.run("""
            MATCH (p:Pressure) WHERE p.counterpress AND p.x >= 60
            OPTIONAL MATCH (pi:PatternInstance {pattern:'P1'})-[:MATCHES]->(p)
            RETURN count(DISTINCT p) AS total, count(DISTINCT pi) AS covered
        """).single()
        print(f"High counterpress pressures captured by P1:        "
              f"{row['covered']}/{row['total']} ({pct(row['covered'], row['total'])})")

        # baseline: how common is the flag among *all* high pressures?
        row = s.run("""
            MATCH (p:Pressure) WHERE p.x >= 60
            RETURN count(p) AS total,
                   count(CASE WHEN p.counterpress THEN 1 END) AS flagged
        """).single()
        print(f"Baseline counterpress rate among high pressures:   "
              f"{row['flagged']}/{row['total']} ({pct(row['flagged'], row['total'])})\n")

        # --- P2 vs From Counter -------------------------------------------
        row = s.run("""
            MATCH (pi:PatternInstance {pattern:'P2'})-[:MATCHES]->(po:Possession)
            RETURN count(DISTINCT po) AS total,
                   count(DISTINCT CASE WHEN po.play_pattern = 'From Counter'
                                       THEN po END) AS counter
        """).single()
        print(f"P2 possessions labelled 'From Counter' by StatsBomb: "
              f"{row['counter']}/{row['total']} ({pct(row['counter'], row['total'])})")

        row = s.run("""
            MATCH (po:Possession {play_pattern:'From Counter'})
            WHERE EXISTS { MATCH (sh:Shot)-[:PART_OF]->(po) }
            OPTIONAL MATCH (pi:PatternInstance {pattern:'P2'})-[:MATCHES]->(po)
            RETURN count(DISTINCT po) AS total, count(DISTINCT pi) AS covered
        """).single()
        print(f"'From Counter' possessions with a shot captured by P2: "
              f"{row['covered']}/{row['total']} ({pct(row['covered'], row['total'])})")

        # baseline: P2 hit rate over all open-play own-half possessions
        row = s.run("""
            MATCH (po:Possession)
            RETURN count(po) AS total,
                   count(CASE WHEN po.play_pattern = 'From Counter' THEN 1 END)
                     AS counter
        """).single()
        print(f"Baseline 'From Counter' share of all possessions:     "
              f"{row['counter']}/{row['total']} ({pct(row['counter'], row['total'])})\n")

        # --- P3 sanity ------------------------------------------------------
        row = s.run("""
            MATCH (pi:PatternInstance {pattern:'P3'})-[:MATCHES]->(po:Possession)
            WITH DISTINCT po
            MATCH (e:Event)-[:PART_OF]->(po)
            WITH po, count(e) AS len
            RETURN count(po) AS n, avg(len) AS avg_len
        """).single()
        if row["n"]:
            print(f"P3: {row['n']} possessions, avg length {row['avg_len']:.1f} events "
                  f"(expected: long, constructed build-ups)")

        # per-team instance counts as a first style glimpse
        print("\nInstances per team (per 38 games):")
        for r in s.run("""
            MATCH (pi:PatternInstance)-[:EXHIBITED_BY]->(t:Team)
            WITH t.name AS team, pi.pattern AS p, count(*) AS n
            RETURN team,
                   sum(CASE WHEN p = 'P1' THEN n END) AS P1,
                   sum(CASE WHEN p = 'P2' THEN n END) AS P2,
                   sum(CASE WHEN p = 'P3' THEN n END) AS P3
            ORDER BY P1 DESC
        """):
            print(f"  {r['team']:<25} P1={r['P1'] or 0:>5}  P2={r['P2'] or 0:>4}  "
                  f"P3={r['P3'] or 0:>4}")
    driver.close()


if __name__ == "__main__":
    main()
