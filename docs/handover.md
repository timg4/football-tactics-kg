# Handover / Status — 2026-06-10

## Where we are

| Phase (docs/plan.md) | Status |
|---|---|
| 0 — Scaffolding (Neo4j docker, venv, repo layout) | ✅ done |
| 1 — KG schema design → `docs/schema.md` | ✅ done |
| 2 — Ingestion PL 2015/16 → Neo4j | ✅ done & verified |
| 3 — Pattern queries (Cypher + Datalog) | 🔜 next — definitions ready in `docs/patterns.md` |
| 4 — Style analytics + Streamlit dashboard | pending |
| 5 — PyKEEN embeddings (LO1/LO8) | pending |
| 6 — Report (Overleaf) + submission | pending — Overleaf project not yet created |

**KG contents (verified by `python -m src.ingest.verify`, all checks green):**
1,313,783 `:Event` (368k Pass, 277k Carry, 115k Pressure, 9.9k Shot, …), 71,976 `:Possession`,
644 `:Player`, 380 `:Match`, 20 `:Team`, 9 `:Zone`; per-match NEXT chains complete,
event counts reconcile 1:1 with the source JSON, every team has exactly 38 games.

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

## Next up (Phase 3 — see docs/patterns.md for the formal definitions)

1. `src/patterns/`: Cypher for P1 (pressing regain), P2 (fast transition), P3 (wide build-up);
   materialize `(:PatternInstance)` nodes (MERGE for idempotency).
2. Validate: P1 vs StatsBomb `counterpress`, P2 vs `play_pattern='From Counter'`.
3. `src/datalog/`: export facts → Soufflé recursive rules for P1/P2, cross-validate counts
   (`brew install souffle`; fallback: DuckDB recursive CTEs).
4. Record PROFILE plans + runtimes for the LO6 writeup.

## Gotchas / lessons (also report material)

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
