"""Verify the ingested KG against the source JSON (docs/plan.md Phase 2 checks).

Usage: python -m src.ingest.verify
"""

import json
import random

from . import common
from .common import DATA_DIR


def main():
    driver = common.get_driver()
    failures = []

    def check(name, cond, detail=""):
        print(f"{'OK  ' if cond else 'FAIL'} {name}{': ' + str(detail) if detail else ''}")
        if not cond:
            failures.append(name)

    with driver.session() as s:
        counts = {r["label"]: r["n"] for r in s.run(
            "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n")}
        print("Node counts:", dict(sorted(counts.items(), key=lambda kv: -kv[1])))

        loaded = [r["mid"] for r in s.run("MATCH (e:Event) RETURN DISTINCT e.match_id AS mid")]
        check("matches with events", len(loaded) > 0, len(loaded))
        check("teams", counts.get("Team", 0) == 20, counts.get("Team"))
        check("zones", counts.get("Zone", 0) == 9, counts.get("Zone"))

        # per-match: event counts match the source file, NEXT chain is a single path
        sample = random.sample(loaded, min(5, len(loaded)))
        for mid in sample:
            src_n = len(json.loads((DATA_DIR / "events" / f"{mid}.json").read_text()))
            row = s.run("""
                MATCH (e:Event {match_id: $mid})
                OPTIONAL MATCH (e)-[r:NEXT]->(:Event)
                RETURN count(DISTINCT e) AS nodes, count(r) AS next_edges
            """, mid=mid).single()
            check(f"match {mid} event count", row["nodes"] == src_n,
                  f"kg={row['nodes']} src={src_n}")
            check(f"match {mid} NEXT chain", row["next_edges"] == src_n - 1,
                  f"{row['next_edges']} edges for {src_n} events")

        # chain integrity globally: exactly one chain start (in-degree 0) per match
        row = s.run("""
            MATCH (e:Event) WHERE NOT (:Event)-[:NEXT]->(e)
            RETURN count(e) AS starts
        """).single()
        check("one NEXT-chain start per match", row["starts"] == len(loaded),
              f"{row['starts']} starts / {len(loaded)} matches")

        # every event is in exactly one possession, possessions belong to a team
        row = s.run("""
            MATCH (e:Event)
            OPTIONAL MATCH (e)-[:PART_OF]->(p:Possession)
            WITH e, count(p) AS np WHERE np <> 1
            RETURN count(e) AS bad
        """).single()
        check("events in exactly one possession", row["bad"] == 0, row["bad"])

        # full-season expectations (only meaningful after a complete load)
        if len(loaded) == 380:
            row = s.run("""
                MATCH (t:Team)-[r:HOME_IN|AWAY_IN]->(:Match)
                WITH t, count(r) AS games
                RETURN min(games) AS lo, max(games) AS hi
            """).single()
            check("38 games per team", row["lo"] == 38 and row["hi"] == 38,
                  f"min={row['lo']} max={row['hi']}")

    driver.close()
    print("\nAll checks passed." if not failures else f"\n{len(failures)} FAILURES: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
