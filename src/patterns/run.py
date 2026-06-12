"""Materialize tactical-pattern instances in the KG (definitions: docs/patterns.md).

Usage:
    python -m src.patterns.run                 # all patterns, all matches
    python -m src.patterns.run --pattern P1    # one pattern
    python -m src.patterns.run --limit 5       # first N matches (testing)

Idempotent: instances are MERGEd on (pattern, match_id, anchor); re-running adds
nothing new. Runs per match like the loader, keeping transactions small.
"""

import argparse
import json
import time

from ..ingest import common
from .cypher import P2_EXCLUDED_PATTERNS, PATTERNS, REGAIN_OUTCOMES

INDEXES = [
    "CREATE INDEX pattern_instance_key IF NOT EXISTS "
    "FOR (pi:PatternInstance) ON (pi.pattern, pi.match_id, pi.anchor)",
    # per-match entry points: the composite :Event(match_id, idx) index from the
    # loader is unusable without an idx predicate (composite indexes need
    # predicates on every property), so the pattern queries fell back to label
    # scans over the whole season (see generated/profiles/, LO6)
    "CREATE INDEX event_match_only IF NOT EXISTS FOR (e:Event) ON (e.match_id)",
    "CREATE INDEX possession_match IF NOT EXISTS "
    "FOR (po:Possession) ON (po.match_id)",
]


def run_pattern(session, name, match_ids, params):
    query, defaults = PATTERNS[name]
    p = {**defaults, **(params or {})}
    bind = {**p, "params": json.dumps(p, sort_keys=True),
            "regainOutcomes": REGAIN_OUTCOMES,
            "excludedPatterns": P2_EXCLUDED_PATTERNS}
    total, t0 = 0, time.time()
    for i, mid in enumerate(match_ids, 1):
        n = session.run(query, mid=mid, **bind).single()["n"]
        total += n
        if i % 50 == 0 or i == len(match_ids):
            print(f"  [{i}/{len(match_ids)}] {name}: {total} instances "
                  f"({i / (time.time() - t0):.1f} matches/s)")
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", choices=sorted(PATTERNS), default=None,
                    help="run a single pattern (default: all)")
    ap.add_argument("--limit", type=int, default=None,
                    help="only the first N matches")
    args = ap.parse_args()

    driver = common.get_driver()
    with driver.session() as session:
        for stmt in INDEXES:
            session.run(stmt)
        match_ids = [r["mid"] for r in session.run(
            "MATCH (m:Match) RETURN m.match_id AS mid ORDER BY m.match_id")]
        if args.limit:
            match_ids = match_ids[: args.limit]

        names = [args.pattern] if args.pattern else sorted(PATTERNS)
        for name in names:
            print(f"{name} over {len(match_ids)} matches ...")
            total = run_pattern(session, name, match_ids, params=None)
            print(f"{name}: {total} instances total")
    driver.close()


if __name__ == "__main__":
    main()
