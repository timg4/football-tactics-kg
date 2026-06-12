# Handover / Status — 2026-06-12

## Where we are

| Phase (docs/plan.md) | Status |
|---|---|
| 0 — Scaffolding (Neo4j docker, venv, repo layout) | ✅ done |
| 1 — KG schema design → `docs/schema.md` | ✅ done |
| 2 — Ingestion PL 2015/16 → Neo4j | ✅ done & verified (re-runnable on any machine) |
| 3 — Pattern queries (Cypher + Datalog) | ✅ done — see below |
| 4 — Style analytics + Streamlit dashboard | ✅ v1 done (2026-06-12) — see below |
| 5 — PyKEEN embeddings (LO1/LO8) | pending |
| 6 — Report (Overleaf) + submission | pending — Overleaf project not yet created |

**KG contents (verified by `python -m src.ingest.verify`, all checks green):**
1,313,773 `:Event` (368k Pass, 277k Carry, 115k Pressure, 9.9k Shot, …), 71,884 `:Possession`,
644 `:Player`, 380 `:Match`, 20 `:Team`, 9 `:Zone`; per-match NEXT chains complete,
event counts reconcile 1:1 with the source JSON, every team has exactly 38 games.
(Counts differ by ~0.01% from the 2026-06-10 numbers — upstream open-data clone is newer.)

**Phase 3 results (2026-06-12):**

- `src/patterns/` — P1–P3 as Cypher, materialized as `(:PatternInstance)` (MERGE-idempotent
  on `(pattern, match_id, anchor)`): **9,121 P1 / 979 P2 / 6,998 P3** over 380 matches.
  Run: `python -m src.patterns.run` · validate: `python -m src.patterns.validate` ·
  profile: `python -m src.patterns.profile`.
- **Validation vs StatsBomb signals:** P2 strongly enriched (30.5% of P2 labelled
  'From Counter' vs 1.8% baseline = ~17×; 69.7% of From-Counter-with-shot possessions
  captured). P1 vs `counterpress` only weakly enriched (39.6% vs 36.9% baseline) —
  expected: different anchor semantics (counterpress = pressing after *own* loss;
  P1 = pressing that *succeeds*); discuss honestly in the report.
- **Face validity:** P1 top teams Spurs/Liverpool/City/Leicester (the league's pressing
  sides); P2 #1 Leicester (counter-attacking champions!); P3 #1 Man United (van Gaal
  possession football). Great report material.
- `src/datalog/` — P1/P2 re-expressed as recursive Datalog: Soufflé programs
  (`p1.dl`, `p2.dl`, run on macOS/Linux) + DuckDB recursive-CTE equivalent
  (`python -m src.datalog.export && python -m src.datalog.run_duckdb`).
  **Cross-validation: exact match with Cypher (9121/9121, 979/979, per match).** (LO2)
- **LO6 war story #2:** PROFILE showed all three pattern queries label-scanning the whole
  season per match — Neo4j composite indexes need predicates on *all* properties, so
  `:Event(match_id, idx)` never applied. Fix: single-property indexes on
  `:Event(match_id)` / `:Possession(match_id)` + `USING INDEX` hint in P1 branch b →
  P1 4×, P2 4×, P3 13× faster, identical counts. Before/after plans:
  `generated/profiles-before-index/` vs `generated/profiles/`.

## Getting started (fresh machine)

```bash
git clone https://github.com/timg4/KnowledgeGraphs && cd KnowledgeGraphs
git clone https://github.com/statsbomb/open-data.git   # 12 GB, gitignored
docker compose up -d            # Neo4j browser: http://localhost:7474 (neo4j/kgfootball)
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m src.ingest.load       # ~5k events/s, ~15 min; resumable — re-run anytime
python -m src.ingest.verify
```

The Neo4j data itself lives in the gitignored `neo4j/` folder — whoever continues just
re-runs the ingest locally (it is idempotent per match).

## Try it (Neo4j browser)

```cypher
// Leicester's high-pressure events in the opponent half, first 5
MATCH (t:Team {name:'Leicester City'})<-[:BY_TEAM]-(p:Pressure)
WHERE p.x >= 60 AND p.counterpress
RETURN p.match_id, p.minute, p.x, p.y LIMIT 5;

// a possession as an event path
MATCH (po:Possession {match_id: 3754058, possession: 23})<-[:PART_OF]-(e:Event)
RETURN e.idx, e.type, e.x, e.y ORDER BY e.idx;
```

**Phase 4 results (2026-06-12):**

- `src/dashboard/metrics.py` — per-team style metrics from the PatternInstances
  (docs/patterns.md §Team-style metrics): pressing (P1/opp. possession), directness
  (P2/own-half open-play possession), wide orientation (P3/final-third Regular-Play
  possession) + possession share & length → `generated/style/metrics.csv`.
  Results are face-valid: Spurs/Liverpool/City top pressing, **Leicester #1 directness
  by a wide margin (0.052 vs 0.038 next)**, Man United/Bournemouth top wide orientation.
- `src/dashboard/app.py` — Streamlit dashboard (`streamlit run src/dashboard/app.py`):
  *League overview* (style table, PCA style map, Ward dendrogram, cosine-similarity
  heatmap), *Team profile* (rank metrics, z-score radar, mplsoccer pitch maps per
  pattern: P1 pressure KDE, P2 start→shot arrows, P3 entry points), *Compare teams*
  (radar overlay + side-by-side pitch maps). All tabs smoke-tested headless.

## Next up

1. **Phase 5:** PyKEEN embeddings on exported triples (LO1, framed as KG completion for
   LO8) — install `requirements-embeddings.txt` in a separate venv if torch fights 3.13.
2. **Phase 6:** Report (Overleaf, still to be created) — LO6 material ready in
   `generated/profiles*/`, validation numbers in `python -m src.patterns.validate`.
3. Dashboard polish if time allows (match drill-down, P1→P2 chain views).

## Gotchas / lessons (also report material)

- **Windows: `read_text()` defaults to cp1252** — all JSON reads need explicit
  `encoding="utf-8"` (fixed 2026-06-12; UnicodeDecodeError on first lineup otherwise).
- **Soufflé has no native Windows build** — the .dl programs run on macOS/Linux;
  on Windows use the DuckDB recursive-CTE runner (same semantics, validated equal).
- **Laptop sleep kills running loaders** — harmless (per-match transactions roll back,
  loader resumes), just re-run.
- **Label/index mismatch bug (LO6 war story):** a relationship query matched
  `(e:Pass {event_id: …})` but the unique index is on `:Event(event_id)` — Neo4j indexes are
  label-specific, so this caused full label scans and a quadratic slowdown (stalled at ~0
  events/s by match 80). Fix: always look up events via `:Event`. After the fix: ~5,000 events/s.
- PyKEEN is deliberately **not** in `requirements.txt` (heavy torch dependency) — install
  `requirements-embeddings.txt` only for Phase 5; if it fights Python 3.12, use a 3.11 venv.
- Pass `outcome` defaults to `"Complete"` (StatsBomb omits the field for completed passes).
- All event coordinates are oriented per acting team (x→120 = opponent goal): "own half" is
  `x < 60` in every event, no flipping needed.

## Needs a human

- `git push` (Claude's permission setup blocks direct pushes to `main`).
- Create the **Overleaf project** and share it (report skeleton can be generated on request).
- Lecturer feedback + LO strategy are recorded in `CLAUDE.md` (read it before working with
  Claude in this repo — it is the persistent project context).
