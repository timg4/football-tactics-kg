"""Flatten the property graph into (head, relation, tail) triples for PyKEEN.

Embedding models need a symbolic triple KG: literals and the 1.3M-event stream
cannot embed meaningfully, so we export the *aggregated* player/team layer
(docs/plan.md Phase 5). Relations:

  plays_for         (player, team)      from PLAYED_IN (team_id)
  plays_position    (player, position)  starting positions from PLAYED_IN
  passes_to         (player, player)    completed passes, aggregated, >= MIN_PASSES
  exhibits_pattern  (player, pattern)   anchor involvement in P1-P3 instances,
                                        >= MIN_INSTANCES

Output: generated/embeddings/triples.tsv (tab-separated h, r, t).
Usage:  python -m src.embeddings.export_triples   (main .venv)
"""

import pandas as pd

from ..ingest import common

OUT_DIR = common.REPO_ROOT / "generated" / "embeddings"
MIN_PASSES = 10      # pass-pair threshold: keeps the relation informative
MIN_INSTANCES = 10   # pattern involvement threshold

QUERIES = {
    "plays_for": """
        MATCH (p:Player)-[pi:PLAYED_IN]->(:Match)
        MATCH (t:Team {team_id: pi.team_id})
        RETURN DISTINCT p.name AS h, 'plays_for' AS r, t.name AS t
    """,
    "plays_position": """
        MATCH (p:Player)-[pi:PLAYED_IN]->(:Match)
        WHERE pi.position IS NOT NULL
        RETURN DISTINCT p.name AS h, 'plays_position' AS r, pi.position AS t
    """,
    "passes_to": f"""
        MATCH (a:Player)<-[:BY_PLAYER]-(e:Pass)-[:RECEIVED_BY]->(b:Player)
        WHERE e.outcome = 'Complete'
        WITH a, b, count(*) AS n
        WHERE n >= {MIN_PASSES}
        RETURN a.name AS h, 'passes_to' AS r, b.name AS t
    """,
    "exhibits_pattern": f"""
        MATCH (pi:PatternInstance)-[:MATCHES]->(:Event)-[:BY_PLAYER]->(p:Player)
        WITH p, pi.pattern AS pattern, count(DISTINCT pi) AS n
        WHERE n >= {MIN_INSTANCES}
        RETURN p.name AS h, 'exhibits_pattern' AS r, pattern AS t
    """,
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    driver = common.get_driver()
    frames = []
    with driver.session() as s:
        for name, q in QUERIES.items():
            df = pd.DataFrame([dict(r) for r in s.run(q)])
            print(f"{name}: {len(df):,} triples")
            frames.append(df)
    driver.close()

    triples = pd.concat(frames, ignore_index=True)
    # entity names may contain tabs/newlines in theory; normalize whitespace
    for col in ("h", "t"):
        triples[col] = triples[col].str.replace(r"\s+", " ", regex=True).str.strip()
    path = OUT_DIR / "triples.tsv"
    triples.to_csv(path, sep="\t", header=False, index=False)
    ents = pd.unique(triples[["h", "t"]].to_numpy().ravel())
    print(f"total: {len(triples):,} triples, {len(ents):,} entities -> {path}")


if __name__ == "__main__":
    main()
