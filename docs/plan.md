# Temporal Football KG — Full Project Plan (to 30 June 2026)

## Context

Portfolio project for TU Wien "Knowledge Graphs" (6 ECTS, team: Jan + Tim, deadline **30 June 2026**). Approved proposal: build a temporal KG from StatsBomb event data, formulate tactical patterns as queries, compare team styles. Lecturer feedback: *time-box the ingestion* — depth belongs in schema design, patterns, and the comparison service.

Grading target (grade 1): basic proficiency in the 10 claimed LOs + exceed threshold in 2 (planned: LO7 creation, LO11 services; LO2 logical knowledge kept deep as a third candidate). Full context: `CLAUDE.md`.

Settled decisions: **Neo4j/Cypher** main KG + **Datalog (Soufflé)** side component + **PyKEEN** mini-experiment; data = **Premier League 2015/16** (`open-data/data/matches/2/27.json`, 380 matches, 1.13 GB events, all files verified present); LO11 service = **Streamlit dashboard**; report in **LaTeX/Overleaf**; code in the existing GitHub repo `timg4/KnowledgeGraphs` (working dir `…/Knowledge Graphs/KnowledgeGraphs/`, `open-data/` gitignored).

Environment verified: Docker 28 ✅, Python 3.13 (pyenv) with torch/pandas/jupyter ✅; need `neo4j` driver, `pykeen` (3.13-compat risk → pyenv 3.12 venv fallback), `streamlit`; Soufflé via Homebrew (fallback: recursive SQL in DuckDB — both are course-taught formalisms).

## Phase 0 — Scaffolding (~3h, 10–11 Jun)

1. Move `CLAUDE.md` + `transcript.txt` into the repo (`KnowledgeGraphs/`) so they're versioned and shared with Tim; fix relative paths inside CLAUDE.md (drop the `KnowledgeGraphs/` prefix).
2. Repo layout:
   ```
   KnowledgeGraphs/
     docker-compose.yml        # neo4j:5-community, APOC, ports 7474/7687, data volume
     requirements.txt          # neo4j, pandas, streamlit, pykeen, ...
     src/ingest/  src/patterns/  src/datalog/  src/embeddings/  src/dashboard/
     docs/        notebooks/
   ```
3. Python venv (pyenv 3.12 to be safe for PyKEEN); install deps.
4. Smoke test: `docker compose up` → driver connects → write/read one node. Commit.

## Phase 1 — KG schema design (LO7 core + LO4) (~6h, 11–13 Jun)

1. Read specs in `open-data/doc/` (Events v4.0.0, Lineups v2.0.0, Matches v3.0.0).
2. Write `docs/schema.md` (+ Mermaid diagram):
   - **Nodes**: `Match`, `Team`, `Player`, `Event` (all events; extra label per core type, e.g. `:Event:Pass`), `Possession`, `Zone` (pitch grid over StatsBomb 120×80, coarse: thirds × lanes, ~9–18 zones), `PatternInstance` (created later by rules).
   - **Relationships**: `(:Event)-[:NEXT]->(:Event)` (temporal order within match — ingest **all** event types as nodes so chains never break; detailed properties only for core types), `[:PART_OF]->(:Possession)`, `[:IN_MATCH]`, `[:BY_PLAYER]`, `[:BY_TEAM]`, `(:Pass)-[:RECEIVED_BY]`, `[:IN_ZONE]`, `[:RELATED_TO]` (from `related_events`), `(:Player)-[:PLAYED_IN {team, position}]->(:Match)`, `(:Team)-[:HOME_IN|AWAY_IN]->(:Match)`.
   - **Temporal model**: NEXT edges + `(period, minute, second, timestamp, index)` properties + possession grouping; justify vs. alternatives (reification, RDF-star, temporal RDF) → this is the LO4 comparison material.
   - Core detail event types v1: Pass, Ball Receipt, Carry, Shot, Pressure, Ball Recovery, Interception, Duel, Dribble, Clearance, Block, Dispossessed, Foul Committed/Won.
3. Start the Overleaf project; draft LO4 (data-model choice) + schema-design narrative (LO7) while fresh.

## Phase 2 — Ingestion, time-boxed ≤12h (LO7 + LO5) (13–17 Jun)

1. Constraints/indexes first (unique ids for Event/Match/Player/Team; index `Event(match_id, idx)`).
2. `src/ingest/`: parse matches/lineups/events for comp 2 season 27 → batched `UNWIND` writes via the driver; iterate schema on 1–2 matches.
3. Scale to 380 matches (~1.3M events). If driver ingest > ~1h wall time → switch to CSV generation + `neo4j-admin database import full` (one-shot bulk load).
4. **Verification**: node/rel counts vs. source JSON per match; 20 teams / 380 matches / 38 per team; NEXT-chain integrity (one chain per match period, no orphans); spot-check one known match against real events.
5. Hard stop per lecturer feedback: if over budget, trim detail properties — never the NEXT chain or possession grouping.

## Phase 3 — Tactical patterns as queries & rules (LO2 + LO6 + basis for LO11) (~14h, 17–22 Jun)

1. `docs/patterns.md`: formal definitions, thresholds explicit (tunable params):
   - **Pressing regain**: Pressure by team T → within N events / Δt sec, Ball Recovery/Interception by T in opponent half.
   - **Fast transition**: possession won in own half → shot within ≤T sec / ≤K events with forward progress ≥ X.
   - **Wide build-up**: possession path through wide lanes in middle third → final-third/box entry.
2. Cypher implementations over NEXT/possession chains; **materialize results as `(:PatternInstance)` nodes** linked to events/team/match — derived knowledge added to the KG (clean LO2 "object creation" + LO8 "KG grows by reasoning" narrative, and makes the dashboard fast).
3. Datalog side component: export facts as TSV → Soufflé program for patterns 1–2 using recursion (possession chain = transitive closure of NEXT); **cross-validate counts vs. Cypher**. Fallback: DuckDB recursive CTEs (course covers recursion in SQL explicitly).
4. LO6 evidence: `PROFILE` plans, season-wide runtimes, index impact — short scalability writeup.

## Phase 4 — Team-style comparison + Streamlit dashboard (LO11 exceed) (~14h, 20–24 Jun)

1. Analytics (`src/patterns/` + notebook): per-team pattern frequencies normalized (per 90 / per possession) → style profile vectors → similarity (cosine, clustering/PCA); sanity-check vs. known narratives (Leicester's counter-press season, etc.).
2. `src/dashboard/` Streamlit app, live Neo4j backend (cached queries):
   - **League overview**: pattern league table, radar/scatter of styles, team clusters.
   - **Team detail**: style profile, trend over season, top pattern instances.
   - **Pattern explorer**: drill into a PatternInstance → event sequence + pitch plot (mplsoccer optional).
3. Fallback if time is short: cut to 2 pages; the notebook charts remain as backup deliverable.

## Phase 5 — Embeddings & completion mini-experiment (LO1 + LO8) (~6h, 24–26 Jun)

Note: triples alone are not embeddings — LO1 ("understand and **apply** KGEs") requires *training* an embedding model on the triples so entities/relations become learned vectors (TransE: head + relation ≈ tail). The "export" is just plumbing: one Cypher query flattening the Neo4j property graph into the `(h, r, t)` TSV that PyKEEN consumes. The flattening choices (which relations; literals can't embed) feed the LO4/LO12 discussion.

1. Export triples from the KG (e.g. `plays_for`, `plays_position`, aggregated `passes_to`, `exhibits_pattern`).
2. PyKEEN TransE (+ ComplEx if trivial): standard split, MRR/Hits@k; qualitative check — do embedding-space team neighbours match the symbolic style clusters from Phase 4? (Direct LO12 material: learned vs. symbolic representations of the same KG.)
3. Frame as KG completion (LO8): discuss plausible predicted links. If PyKEEN fights Python 3.13 → dedicated pyenv 3.12 venv.

## Phase 6 — Report & submission (~25h spread; polish 27–30 Jun)

Write sections in Overleaf as phases complete (parallelize with Tim), structure:
Intro & application (LO9) → Background → Data & schema design (LO7, LO4) → Architecture + diagram (LO5) → Patterns: rules & queries (LO2, LO6) → Style comparison service (LO11) → Embeddings & completion (LO1, LO8) → Discussion: KG–ML–AI connections (LO12) → Conclusion.

- Inline `(LOx)` tags wherever an LO is demonstrated (required by portfolio format).
- Cover pages: tick basic ×8 + exceeded ×2 (LO7+LO11, or swap in LO2 if depth landed there), 1–2 sentences + page refs each; hours page filled honestly.
- ZIP: code + docs + small data sample + README linking StatsBomb repo (not 1.13 GB); StatsBomb attribution + logo in the report (license requirement).
- Final checks: cover-page ↔ report cross-check for all 10 LOs; clean-clone reproducibility (`docker compose up` → ingest 1 match → run 1 pattern query).
- Submit PDF + ZIP/link on TUWEL **by 30 June**.

## Effort & risks

≈ 55h implementation + 25h report ≈ 80h two-person budget — fits, with the lecturer's "ingestion lean" warning enforced by the Phase 2 time-box.

| Risk | Fallback |
|---|---|
| PyKEEN × Python 3.13 | pyenv 3.12 venv for embeddings module |
| Soufflé install trouble | DuckDB recursive SQL (course-aligned) |
| Slow full-season ingest | `neo4j-admin` bulk import; then trim detail props, never NEXT chains |
| Dashboard overruns | reduce pages; notebook charts as LO11 backup |
| An LO fails to convince (no slack, 10/10 needed) | explicit (LOx)-tagged paragraph per LO + final cross-check pass |

## Verification (end-to-end)

1. After Phase 2: source-vs-KG count reconciliation + known-match spot check.
2. After Phase 3: Cypher vs. Datalog result cross-validation on same patterns.
3. After Phase 4: style results vs. known 2015/16 narratives; dashboard runs from clean start.
4. Before submission: clean-clone repro test + all-LO coverage cross-check against cover pages.
