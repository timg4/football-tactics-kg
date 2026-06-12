"""Execute the Datalog rules for P1/P2 as DuckDB recursive CTEs and
cross-validate the result against the Cypher PatternInstances in Neo4j.

The recursive `reach` CTE is the SQL spelling of the recursive Datalog rule in
src/datalog/p1.dl (lecture KG-04: recursion in SQL vs Datalog). Soufflé itself
is not available on Windows; the .dl files run unchanged on macOS/Linux.

Usage:  python -m src.datalog.run_duckdb   (after python -m src.datalog.export)
"""

import time

import duckdb

from ..ingest import common
from .export import OUT_DIR

P1_SQL = """
WITH RECURSIVE
pressure AS (
    SELECT eid, mid, team, ts, period FROM event
    WHERE type = 'Pressure' AND x >= 60
),
wins AS (
    SELECT eid, team FROM event
    WHERE (type = 'Ball Recovery' AND NOT coalesce(recovery_failure, false))
       OR (type IN ('Interception', 'Duel')
           AND outcome IN ('Won', 'Success In Play', 'Success Out'))
),
reach AS (
    SELECT p.eid AS p_eid, p.team, p.ts AS p_ts, p.period AS p_period,
           n.b AS e_eid, 1 AS depth
    FROM pressure p
    JOIN next n ON n.a = p.eid
    JOIN event e ON e.eid = n.b
    WHERE e.period = p.period AND e.ts - p.ts <= 5
  UNION ALL
    SELECT r.p_eid, r.team, r.p_ts, r.p_period, n.b, r.depth + 1
    FROM reach r
    JOIN next n ON n.a = r.e_eid
    JOIN event e ON e.eid = n.b
    WHERE e.period = r.p_period AND e.ts - r.p_ts <= 5 AND r.depth < 10
),
branch_a AS (
    SELECT DISTINCT r.p_eid
    FROM reach r JOIN wins w ON w.eid = r.e_eid AND w.team = r.team
),
branch_b AS (
    SELECT DISTINCT p.eid AS p_eid
    FROM pressure p
    JOIN part_of pm ON pm.eid = p.eid
    JOIN possession po2
      ON po2.mid = p.mid AND po2.poss = pm.poss + 1 AND po2.team = p.team
    JOIN part_of pm2 ON pm2.mid = po2.mid AND pm2.poss = po2.poss
    JOIN event f ON f.eid = pm2.eid
    WHERE f.period = p.period AND f.ts - p.ts <= 5
),
p1 AS (SELECT p_eid FROM branch_a UNION SELECT p_eid FROM branch_b)
SELECT p.mid, count(*) AS n
FROM p1 JOIN pressure p ON p.eid = p1.p_eid
GROUP BY p.mid
"""

P2_SQL = """
WITH f AS (
    SELECT po.mid, po.poss, arg_min(e.eid, e.idx) AS feid
    FROM part_of po JOIN event e ON e.eid = po.eid
    WHERE e.x IS NOT NULL
    GROUP BY po.mid, po.poss
),
p2 AS (
    SELECT DISTINCT s.mid, s.eid
    FROM possession ps
    JOIN f ON f.mid = ps.mid AND f.poss = ps.poss
    JOIN event fe ON fe.eid = f.feid
    JOIN part_of sp ON sp.mid = ps.mid AND sp.poss = ps.poss
    JOIN event s ON s.eid = sp.eid AND s.type = 'Shot' AND s.team = ps.team
    WHERE ps.play_pattern NOT IN ('From Corner', 'From Free Kick',
                                  'From Throw In', 'From Kick Off',
                                  'From Penalty')
      AND fe.x <= 60
      AND s.period = fe.period
      AND s.ts - fe.ts <= 15
      AND s.x - fe.x >= 30
)
SELECT mid, count(*) AS n FROM p2 GROUP BY mid
"""


def cypher_counts(pattern):
    driver = common.get_driver()
    with driver.session() as s:
        rows = s.run("MATCH (pi:PatternInstance {pattern: $p}) "
                     "RETURN pi.match_id AS mid, count(*) AS n", p=pattern)
        out = {r["mid"]: r["n"] for r in rows}
    driver.close()
    return out


def compare(name, sql, db):
    t0 = time.time()
    dd = {mid: n for mid, n in db.execute(sql).fetchall()}
    dt = time.time() - t0
    cy = cypher_counts(name.upper())
    total_dd, total_cy = sum(dd.values()), sum(cy.values())
    mids = set(dd) | set(cy)
    diff = {m: (dd.get(m, 0), cy.get(m, 0)) for m in mids
            if dd.get(m, 0) != cy.get(m, 0)}
    status = "MATCH" if not diff else f"MISMATCH in {len(diff)} matches"
    print(f"{name}: DuckDB {total_dd} vs Cypher {total_cy} "
          f"({len(mids)} matches, {dt:.1f}s) -> {status}")
    for m, (a, b) in sorted(diff.items())[:10]:
        print(f"  match {m}: duckdb={a} cypher={b}")
    return not diff


def main():
    db = duckdb.connect(str(OUT_DIR / "facts.duckdb"), read_only=True)
    ok = compare("P1", P1_SQL, db)
    ok &= compare("P2", P2_SQL, db)
    db.close()
    print("\nCross-validation " + ("PASSED" if ok else "FAILED"))


if __name__ == "__main__":
    main()
