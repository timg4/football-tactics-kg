# A Temporal Football Knowledge Graph

### Tactical Pattern Discovery and Team-Style Comparison

Portfolio project for the TU Wien course **Knowledge Graphs** (VU 192.116, 2026S).
Tim Greß (12412672), Jan Tölken (12432831).

We turn a full season of raw football event data into a **temporal knowledge graph**, express
tactical concepts ("press high and win the ball back", "win it deep and shoot fast", "build up
through the wings") as **graph queries and recursive rules**, and use the patterns they find to
**compare how the 20 Premier League teams play**. On top of the graph sit a recursive-logic
cross-check, an analytics dashboard, and a knowledge-graph-embedding experiment.

**Data:** [StatsBomb Open Data](https://github.com/statsbomb/open-data), Premier League 2015/16 —
380 matches, ~1.3 million events.

---

## What the project does

The pipeline goes from JSON event files to tactical insight in five stages:

```
StatsBomb JSON          Neo4j property graph        Tactical patterns          Team style
(380 matches,    ──▶    1.3M events, possessions,  ──▶  P1/P2/P3 as Cypher  ──▶  metrics, clustering,
 1.3M events)           zones, NEXT/PART_OF edges        + recursive Datalog       dashboard, embeddings
```

1. **Build the graph** — every event becomes a node, ordered by explicit `NEXT` edges, grouped
   into possessions, located in pitch zones, attributed to teams and players. *(schema design + mapping)*
2. **Mine tactical patterns** — three patterns are defined formally and run as Cypher path queries,
   materializing their matches back into the graph as `PatternInstance` nodes (derived knowledge).
3. **Re-express the patterns as logic** — patterns P1/P2 are written as recursive Datalog rules
   (Soufflé) and as recursive SQL CTEs (DuckDB), and cross-validated against the Cypher counts
   *to the exact instance*.
4. **Compare team styles** — per-team style metrics are computed from the pattern instances,
   normalized into style vectors, and explored through PCA, clustering, and a Streamlit dashboard.
5. **Learn embeddings** — the graph is exported to triples and fed to PyKEEN (TransE, ComplEx) for
   a link-prediction experiment, whose learned team neighbourhoods are cross-checked against the
   symbolic style clusters.

---

## The knowledge graph

A **temporal property graph** in Neo4j: events are first-class nodes carrying time and location, so
*sequence* patterns become *path* patterns and recursion (variable-length sequences) maps naturally
to Cypher and Datalog. Full rationale and the data-model comparison are in [`docs/schema.md`](docs/schema.md).

**Nodes** — `Match`, `Team`, `Player`, `Event` (with subtype labels `Pass`, `Shot`, `Pressure`,
`Carry`, `Duel`, …), `Possession`, `Zone` (a static 3×3 pitch grid), and the derived `PatternInstance`.

**Key relationships** — `(:Event)-[:NEXT]->(:Event)` (total temporal order per match),
`-[:PART_OF]->(:Possession)`, `-[:BY_TEAM]->(:Team)`, `-[:BY_PLAYER]->(:Player)`,
`-[:IN_ZONE]->(:Zone)`, `-[:RECEIVED_BY]->(:Player)`, plus `PatternInstance` provenance edges.

After ingestion the graph holds **1,313,773 events, 71,884 possessions, 644 players, 380 matches,
20 teams**, verified 1:1 against the source JSON (`python -m src.ingest.verify`).

---

## The tactical patterns

Formal definitions (parameters, KG semantics, validation hooks) live in
[`docs/patterns.md`](docs/patterns.md). Each match is materialized as a `PatternInstance` node.

| Pattern | Idea | Definition (short) | Instances |
|---|---|---|---|
| **P1 — Pressing Regain** | Press high, win it back within seconds | A `Pressure` in the opponent half followed within 5 s (along the `NEXT` chain) by the same team regaining possession | **9,121** |
| **P2 — Fast Transition** | Win it deep, shoot fast | An open-play possession starting in the own half that produces a shot within 15 s and ≥ 30 m of forward progress | **979** |
| **P3 — Wide Build-Up** | Constructed progression through the wings | A Regular-Play possession with ≥ 3 events in the wide middle third, then entering the wide final third | **6,998** |

**Validation against StatsBomb's own signals** (`python -m src.patterns.validate`):
P2 is strongly enriched for StatsBomb's `From Counter` label (30.5 % vs a 1.8 % baseline ≈ 17×);
P1 overlaps the `counterpress` flag as expected for its different anchor semantics.
Face validity is strong: P1 is topped by the league's pressing sides (Spurs, Liverpool, City),
**P2 by Leicester — that season's counter-attacking champions** — and P3 by van Gaal's possession-based
Manchester United.

---

## Team-style comparison

From the pattern instances we derive per-team style metrics (`python -m src.dashboard.metrics`):

- **Pressing intensity** — P1 instances per opponent possession
- **Directness** — P2 instances per own-half open-play possession
- **Wide orientation** — P3 instances per Regular-Play possession reaching the final third
- plus **possession share** and **mean possession length** as context

These form normalized style vectors used for PCA, Ward clustering, and cosine similarity. The
**Streamlit dashboard** (`streamlit run src/dashboard/app.py`) presents:

- **League overview** — style table, PCA "style map", clustering dendrogram, similarity heatmap
- **Team profile** — ranked metrics, a z-score radar vs the league, and `mplsoccer` pitch maps per
  pattern (P1 pressure heatmap, P2 start→shot arrows, P3 final-third entry points)
- **Compare teams** — radar overlay and side-by-side pitch maps for any two teams

---

## Knowledge-graph embeddings

The graph is flattened to **9,300 triples over 596 entities and 4 relations** (`plays_for`,
`plays_position`, `passes_to`, `exhibits_pattern`) and trained with PyKEEN:

| Model | MRR | Hits@1 | Hits@3 | Hits@10 |
|---|---|---|---|---|
| TransE | 0.255 | 0.021 | 0.394 | 0.721 |
| ComplEx | 0.265 | 0.120 | 0.334 | 0.553 |

TransE's near-zero Hits@1 next to ComplEx illustrates the classic difficulty translational models
have with 1-to-N relations. As a symbolic-vs-learned cross-check, a team's nearest embedding
neighbour falls in the same style cluster for **9/20 teams (ComplEx)** versus a ~4/20 random
baseline — the learned representation rediscovers the hand-built style structure from passing,
positions, and pattern participation alone.

---

## Setup

```bash
# 1. Data — clone StatsBomb open data into ./open-data (gitignored, ~12 GB)
git clone https://github.com/statsbomb/open-data.git

# 2. Neo4j 5.26 + APOC (browser http://localhost:7474, bolt :7687, auth neo4j/kgfootball)
docker compose up -d

# 3. Python environment (3.13)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> **Windows note:** all JSON is read with explicit UTF-8; no extra configuration needed.

## Running the pipeline

```bash
# Build & verify the knowledge graph (resumable, idempotent per match; ~20 min)
python -m src.ingest.load
python -m src.ingest.verify

# Mine tactical patterns → PatternInstance nodes, then validate & profile
python -m src.patterns.run
python -m src.patterns.validate
python -m src.patterns.profile          # PROFILE plans for the scalability write-up

# Recursive-logic cross-check (Datalog ≡ Cypher)
python -m src.datalog.export --tsv      # facts → DuckDB + Soufflé .facts
python -m src.datalog.run_duckdb        # recursive CTEs vs Cypher counts (exact match)
#   Soufflé (macOS/Linux): souffle -F generated/datalog -D generated/datalog src/datalog/p1.dl

# Team-style metrics + dashboard
python -m src.dashboard.metrics
python -m src.dashboard.fetch_assets      # club crests + PL logo (optional; graceful fallback)
streamlit run src/dashboard/app.py

# Embeddings (separate venv — heavy torch dependency)
python -m venv .venv-emb && source .venv-emb/bin/activate
pip install -r requirements-embeddings.txt
python -m src.embeddings.export_triples
python -m src.embeddings.train
```

Generated artifacts (pattern profiles, Datalog facts, style metrics, triples, embedding results)
are written to `generated/` (gitignored).

## Repository layout

| Path | Purpose |
|---|---|
| `src/ingest/` | JSON → Neo4j mapping pipeline (schema constraints, loaders, verification) |
| `src/patterns/` | Tactical pattern Cypher queries, materialization, validation, profiling |
| `src/datalog/` | Soufflé `.dl` rules + DuckDB recursive-CTE runner and cross-validation |
| `src/dashboard/` | Team-style metrics and the Streamlit comparison app |
| `src/embeddings/` | Triple export + PyKEEN link-prediction experiment |
| `docs/` | `schema.md` (KG design), `patterns.md` (pattern definitions), `plan.md`, `handover.md` |
| `notebooks/` | Exploration and analysis notebooks |
| `open-data/` | StatsBomb data (gitignored — clone yourself, see Setup) |

## Tech stack

Neo4j 5.26 (Cypher) · Python 3.13 (pandas, scikit-learn, mplsoccer) · DuckDB & Soufflé (recursive
logic) · Streamlit (dashboard) · PyKEEN / PyTorch (embeddings) · Docker Compose.

## Data attribution

Data: [StatsBomb Open Data](https://github.com/statsbomb/open-data), used under their
non-commercial license. Any analysis derived from this data credits StatsBomb as the source.
