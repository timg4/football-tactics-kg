"""Per-team style metrics from the materialized PatternInstances (Phase 4, LO11).

Metric definitions follow docs/patterns.md §Team-style metrics:
  pressing   = P1 instances per opponent possession
  directness = P2 instances per own open-play possession starting in the own half
  wide       = P3 instances per own Regular-Play possession reaching the final third
plus context: possession share, mean possession length (events).

Writes generated/style/metrics.csv (the dashboard reads it; re-run after
re-materializing patterns).

Usage:  python -m src.dashboard.metrics
"""

import pandas as pd

from ..ingest import common
from ..patterns.cypher import P2_EXCLUDED_PATTERNS

OUT_DIR = common.REPO_ROOT / "generated" / "style"

INSTANCES = """
MATCH (pi:PatternInstance)-[:EXHIBITED_BY]->(t:Team)
RETURN t.team_id AS team_id, t.name AS team, pi.pattern AS pattern, count(*) AS n
"""

# opponent possessions in the team's 38 matches (pressing denominator)
OPP_POSS = """
MATCH (t:Team)-[:HOME_IN|AWAY_IN]->(m:Match)<-[:IN_MATCH]-(po:Possession)
WHERE NOT (po)-[:POSSESSION_BY]->(t)
RETURN t.team_id AS team_id, count(po) AS opp_poss
"""

# own possessions + mean length in events (context metrics)
OWN_POSS = """
MATCH (po:Possession)-[:POSSESSION_BY]->(t:Team)
MATCH (e:Event)-[:PART_OF]->(po)
WITH t, po, count(e) AS len
RETURN t.team_id AS team_id, count(po) AS own_poss, avg(len) AS avg_poss_len
"""

# own open-play possessions whose first located event lies in the own half
# (directness denominator; mirrors the P2 anchor without the shot condition)
OPENPLAY_OWNHALF = """
MATCH (po:Possession)-[:POSSESSION_BY]->(t:Team)
WHERE NOT po.play_pattern IN $excludedPatterns
MATCH (f:Event)-[:PART_OF]->(po)
WHERE f.x IS NOT NULL
WITH t, po, min(f.idx) AS fidx
MATCH (f:Event {match_id: po.match_id, idx: fidx})
WHERE f.x <= 60
RETURN t.team_id AS team_id, count(po) AS openplay_ownhalf
"""

# own Regular-Play possessions with at least one own event in the final third
# (wide-orientation denominator)
REGULAR_FINAL = """
MATCH (po:Possession {play_pattern: 'Regular Play'})-[:POSSESSION_BY]->(t:Team)
WHERE EXISTS {
    MATCH (e:Event)-[:PART_OF]->(po)
    WHERE (e)-[:BY_TEAM]->(t) AND (e)-[:IN_ZONE]->(:Zone {third: 'final'})
}
RETURN t.team_id AS team_id, count(po) AS regular_final
"""

GAMES = 38


def compute():
    driver = common.get_driver()
    with driver.session() as s:
        inst = pd.DataFrame([dict(r) for r in s.run(INSTANCES)])
        frames = [
            pd.DataFrame([dict(r) for r in s.run(OPP_POSS)]),
            pd.DataFrame([dict(r) for r in s.run(OWN_POSS)]),
            pd.DataFrame([dict(r) for r in s.run(
                OPENPLAY_OWNHALF, excludedPatterns=P2_EXCLUDED_PATTERNS)]),
            pd.DataFrame([dict(r) for r in s.run(REGULAR_FINAL)]),
        ]
    driver.close()

    df = inst.pivot_table(index=["team_id", "team"], columns="pattern",
                          values="n", fill_value=0).reset_index()
    for f in frames:
        df = df.merge(f, on="team_id")

    df["pressing"] = df["P1"] / df["opp_poss"]
    df["directness"] = df["P2"] / df["openplay_ownhalf"]
    df["wide"] = df["P3"] / df["regular_final"]
    df["possession_share"] = df["own_poss"] / (df["own_poss"] + df["opp_poss"])
    for p in ("P1", "P2", "P3"):
        df[f"{p.lower()}_per_match"] = df[p] / GAMES
    return df.sort_values("team").reset_index(drop=True)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = compute()
    df.to_csv(OUT_DIR / "metrics.csv", index=False)
    cols = ["team", "pressing", "directness", "wide",
            "possession_share", "avg_poss_len"]
    print(df[cols].round(3).to_string(index=False))
    print(f"\n-> {OUT_DIR / 'metrics.csv'}")


if __name__ == "__main__":
    main()
