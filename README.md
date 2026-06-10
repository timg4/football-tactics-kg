# A Temporal Football Knowledge Graph for Tactical Pattern Discovery and Team Style Comparison

Portfolio project for the TU Wien course **Knowledge Graphs** (VU 192.116, 2026S).
Tim Greß (12412672), Jan Tölken (12432831).

We build a temporal Knowledge Graph from [StatsBomb Open Data](https://github.com/statsbomb/open-data)
(Premier League 2015/16), formulate tactical patterns (pressing regains, fast transitions,
wide build-up) as graph queries and recursive rules, and compare team styles through an
analytics dashboard backed by the KG.

## Setup

```bash
# 1. Data: clone StatsBomb open data into ./open-data (gitignored, ~12 GB)
git clone https://github.com/statsbomb/open-data.git

# 2. Neo4j (browser at http://localhost:7474, auth neo4j/kgfootball)
docker compose up -d

# 3. Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Layout

| Path | Purpose |
|---|---|
| `src/ingest/` | JSON → Neo4j mapping pipeline (schema constraints, loaders) |
| `src/patterns/` | Tactical pattern Cypher queries + style analytics |
| `src/datalog/` | Datalog (Soufflé) re-formulation of patterns, cross-validation |
| `src/embeddings/` | Triple export + PyKEEN link-prediction experiment |
| `src/dashboard/` | Streamlit team-style comparison app |
| `docs/` | Schema & pattern documentation |
| `notebooks/` | Exploration and analysis notebooks |
| `Inhalt/` | Course materials (lectures, assignment) |
| `open-data/` | StatsBomb data (gitignored — clone yourself, see Setup) |

Project context for AI-assisted sessions: see `CLAUDE.md`.

## Data attribution

Data: [StatsBomb Open Data](https://github.com/statsbomb/open-data), used under their
non-commercial license — analyses based on this data credit StatsBomb as source.
