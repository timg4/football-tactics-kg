# Knowledge Graphs — Semester Project (TU Wien, VU 192.116, 2026S)

Persistent context for all sessions. Course: "Knowledge Graphs" (Prof. Emanuel Sallinger, DBAI/TU Wien).
Team: Tim Greß (12412672), Jan Tölken (12432831). Mode: **6 ECTS**.

## Project overview

**"A Temporal Football Knowledge Graph for Tactical Pattern Discovery and Team Style Comparison"** (see [One-Pager](One-Pager_Greß_Tölken.pdf)).
We build a temporal KG from StatsBomb open football event data. Entities: matches, teams, players, events, possessions, formations, pitch zones; relations capture participation, spatial context, and temporal order. On top of this we formulate tactical patterns (e.g. pressing regains, fast transitions, wide build-up) as KG queries/rules and use them to compare how teams realize these patterns ("team style"). Plan: (1) select dataset subset → (2) design KG schema + JSON→KG mappings → (3) formulate tactical pattern queries, iteratively increasing complexity.

## Decisions (2026-06-10)

- **Tech stack: Neo4j property graph (Cypher) as the main KG** — JSON→KG mapping pipeline targets Neo4j; tactical patterns as Cypher path queries; Neo4j visualization feeds the LO11 service story. Plus two small side components: (a) **Datalog** (e.g. Soufflé) re-expressing 1–2 patterns as recursive rules → LO2/LO6 + LO4 comparison material; (b) **PyKEEN** embeddings on exported triples → LO1, framed also as KG completion for LO8.
- **Proposal feedback (lecturer, verbatim):** *"Great project! Please go ahead! You have a very interesting choice of LOs you want to focus on - very good, and it should allow you to explore exactly what you want to explore! When you do the data ingestion / integration (i.e. building the data part of the Knowledge Graph) - be careful that you do not use that much time for this part. We are looking forward to your final submission!"* → Implications: (a) **time-box ingestion** — keep the pipeline simple; LO7 depth = schema design + mapping rationale, not ingestion engineering; (b) main effort goes to pattern queries + team comparison (as the one-pager promised).
- **Exceed-LO flexibility (team decision):** aim to exceed in LO7 + LO11 as proposed, but build the LO2 work (recursive pattern rules) deep enough to serve as a third "exceed" candidate — the cover pages tick whatever we actually achieved at submission, so we can switch late if the depth lands elsewhere.
- **LO11 service = Streamlit dashboard** (committed, not a stretch goal); report written in **LaTeX/Overleaf**; code lives in this GitHub repo (`timg4/KnowledgeGraphs`); full phase roadmap in `docs/plan.md`.
- **Data subset: one full league season, primary = Premier League 2015/16** (`matches/2/27.json`, 380 matches, all event files present, 1.13 GB, no 360 data). Rationale: club teams are more comparable in skill and have settled tactics vs. national tournaments; profiling showed the *only* complete, balanced league seasons in the open data are the 2015/16 big-five (PL/La Liga/Serie A: 380 matches & 38/team; Ligue 1: 377; Bundesliga: 306) — every other league season is single-club-centric (e.g. Barcelona's La Liga). Expansion option if time allows: a second 2015/16 league for cross-league style comparison.

## Status

**Phases 0–2 complete (2026-06-10):** KG fully loaded & verified — 380 matches, 1.31M events,
72k possessions, 644 players; all integrity checks green (`python -m src.ingest.verify`).
**Next: Phase 3** — implement P1–P3 from `docs/patterns.md` as Cypher + Datalog.
Current state & onboarding: **`docs/handover.md`**.

## Data

StatsBomb Open Data, vendored at `open-data/` (~12 GB JSON total):

| Path | Content | Size |
|---|---|---|
| `data/competitions.json` | 75 competition-season entries (World Cup, Euros, La Liga, Premier League, Bundesliga, …) | 32 KB |
| `data/matches/<comp_id>/<season_id>.json` | Match metadata per competition/season (21 competition folders) | 6 MB |
| `data/events/<match_id>.json` | **Core data.** Full event stream per match (~3–4k events/match, 3464 matches) | 9.8 GB |
| `data/lineups/<match_id>.json` | Lineups per match (3464 files) | 70 MB |
| `data/three-sixty/<match_id>.json` | 360° freeze-frames, only 326 matches | 2.2 GB |
| `doc/*.pdf` | Format specs: Events v4.0.0, Matches v3.0.0, Lineups v2.0.0, Competitions v2.0.0, 360 Frames v1.0.0 | — |

Event JSON structure: each event has `id, index, period, timestamp, minute, second, type, possession, possession_team, play_pattern, team, player, position, location [x,y], duration, under_pressure, related_events` + type-specific objects (`pass`, `shot`, …). Dominant types: Pass, Ball Receipt, Carry, Pressure, Ball Recovery, Duel, Shot. `possession` ids group events into possession chains; `related_events` links events — both are natural graph edges.
**We work on a subset** (proposal commitment): core event types (passes, shots, …) for a chosen set of competitions/matches; expand as time allows. Attribution required: cite StatsBomb as source + logo (see `open-data/README.md`, `LICENSE.pdf`).

## Course context (what the lectures teach — project should visibly use this)

Three blocks (lecture decks in `Inhalt/Vorlesungen/`, numbered KG-01…KG-08):

- **Representations**
  - *KG Embeddings* (KG-03): TransE, ComplEx, ConvE; training (negative sampling, SGD); link prediction; tool: **PyKEEN**.
  - *Logical knowledge* (KG-04): rules, **recursion** (SQL & Datalog), existential quantification / object creation (Datalog±), **Warded Datalog / Vadalog**; unified framework across DB/SemWeb/KR communities.
  - *GNNs* (KG-05): message passing, GCN, GraphSAGE, R-GCN for link prediction; tools: PyTorch Geometric, DGL. *(Excluded from our project per proposal.)*
  - *Data models* (KG-06-02): graph models, RDF / RDF-star, property graphs, **temporal KG models**, comparison across communities. (Deck even uses a football match→graph example.)
- **Systems** (KG-06): KGMS architectures, scalable reasoning, Vadalog system, graph databases (db-engines landscape).
- **KG lifecycle** (KG-07): **creation** (schema design, schema mapping, record linkage), **evolution** (completion/link prediction, rule learning, cleaning, schema evolution, view/truth maintenance).
- **Applications** (KG-08): industrial showcases, company/financial KGs, ownership & control, hostile takeovers, enterprise AI architectures. *(Financial = LO10, excluded per proposal.)*

## Requirements & grading

**Assessment = one item: the portfolio** (mini-project report). Grading by learning outcomes (defined in `Inhalt/assignment/courseaims.txt`):

- Grade 4: basic proficiency in ≥ 6 LOs · Grade 3: ≥ 10 LOs · Grade 2: ≥10 + **exceed** threshold in ≥ 1 LO · **Grade 1: ≥10 + exceed in ≥ 2 LOs**.

**Calibration (lecturer's own words, `transcript.txt`):** the LO list is "something to guide your thinking and writing, not a checklist". Many LOs are deliberately easy at basic level — a paragraph suffices for data-model choice (LO4), architecture description (LO5, "you get it for free, just describe it"), scalable reasoning (LO6, "your graph database gives it to you for free; even SQL failing to scale shows proficiency"), evolution (LO8, "just a note on what happens if something changes"), application framing (LO9/LO10), connections (LO12). The service (LO11) at basic level *is* the application itself. Scoping the project to the hour budget is itself part of what's assessed. "Understand and **apply**" LOs (LO1–LO3) are the ones needing an actual, possibly small, applied component.

Our one-pager claims **exactly 10 LOs** (no slack!) — focus (must exceed): LO7, LO11; basic: LO1, LO2, LO4, LO5, LO6, LO8, LO9, LO12; excluded: LO3, LO10.

| LO | What it is | How our project covers it | Status |
|---|---|---|---|
| LO1 | KG embeddings (TransE/ComplEx/ConvE) | Small applied component (LO says "apply", and a KG itself is symbolic — embeddings don't come for free): export KG triples → PyKEEN TransE/ComplEx → mini link-prediction experiment. ~Few hours | Only remaining LO needing a dedicated work item |
| LO2 | Logical knowledge, recursion, object creation | Tactical patterns as *rules*; possession chains are naturally recursive. Only counts if we deliberately use a logic/rule formalism (Datalog/Vadalog or recursive queries), not just plain pattern matching | At risk — depends on stack |
| LO3 | GNNs | Excluded (allowed) | — |
| LO4 | Compare KG data models, incl. temporal | Justify our choice (RDF vs property graph vs temporal model) in a written comparison; temporal focus aligns well | Plan exists, must be written explicitly |
| LO5 | Design KG architecture | Describe pipeline architecture: storage, mapping layer, query/service layer, what's in-KG vs application code | Implicit — make explicit in report |
| LO6 | Scalable reasoning/querying | 9.8 GB events → subsetting/scaling strategy + recursive pattern queries | Plausible, must be framed as reasoning |
| **LO7** | **Apply a system to create a KG** (schema design, schema mapping, record linkage) | **Focus LO.** JSON→KG schema design + mappings is exactly schema mapping. Record linkage is weak (StatsBomb IDs are consistent) — optional boost: link players/teams to Wikidata | Strong, needs depth to *exceed* |
| LO8 | Evolve a KG (completion, cleaning) | Paragraph-level (per lecturer): how new matches/seasons/event types get added, what changes; optionally tie LO1's link prediction in as KG completion | Paragraph in report |
| LO9 | Describe/design real-world KG applications | Football analytics use case framing (intro/motivation) | Easy, must be written |
| LO10 | Financial KGs | Excluded (allowed) | — |
| **LO11** | **Provide services through a KG** (query interfaces, analytics, visualization, NL interfaces, recommenders) | **Focus LO.** Basic level = the tactical-pattern analytics *is* the service (per lecturer). To **exceed**: make the team-style comparison a worked-out analytics deliverable (systematic cross-team results + visualization), beyond raw queries | Basic covered; define what "exceed" looks like |
| LO12 | Connections KG ↔ ML ↔ AI | Reflection/discussion section (symbolic queries vs embeddings on same KG) | Easy, must be written |

**Report mechanics (matter for grading):** mark LO coverage inline in the report text as "(LO7)" etc., especially where cover pages point; cover pages = per-LO table (basic/exceeded checkbox + 1–2 sentences + page refs).

## Deliverables & constraints

- **One PDF**: filled cover pages (template in `Inhalt/assignment/KG-S2-03…pdf`) + report. Structure free; suggested: Intro / Background / Method / Results / Conclusion.
- **One ZIP**: code + data, via TUWEL (or link if too large — our data subset will exceed TUWEL limits, so likely link).
- Cover pages also ask hours spent (6 ECTS; suggested baseline in template is 40h project + 15h portfolio — stated to have *no* effect on marking) and reuse declarations.
- **Deadlines**: one-pager 31 Mar (✅ submitted); portfolio **30 June 2026 (standard track)**; extended track 30 Sep (early track 16 June is effectively now). No presentation mentioned anywhere — assessment is by document only.
- FAQ slide: bad empirical results don't hurt if LOs are demonstrated.

## Folder guide

- `CLAUDE.md` — this file.
- `transcript.txt` — lecturer's video walkthrough of the one-pager/LO expectations (source of the calibration note above).
- `One-Pager_Greß_Tölken.pdf` — our accepted project proposal (defines scope + LO claims).
- `Inhalt/Vorlesungen/` — ~50 lecture decks, KG-01…KG-08 (see Course context above for the map).
- `Inhalt/assignment/` — `courseaims.txt` (authoritative LO definitions), portfolio slides: grading & tracks (`KG-12-02-v2`), cover-pages template (`KG-S2-03`), report/submission format (`KG-S2-04`), reflection (`KG-S2-05`, title slide only).
- `open-data/` — StatsBomb dataset (see Data above), **gitignored**. Do **not** load `data/events/` wholesale — 9.8 GB.
- `docs/plan.md` — the full phase plan (Phase 0–6 with dates, hours, LO mapping, risks). `docs/` also gets `schema.md` (Phase 1) and `patterns.md` (Phase 3).
- `src/{ingest,patterns,datalog,embeddings,dashboard}/` — implementation modules per phase (see README.md table).
- `notebooks/` — exploration/analysis notebooks.
- Dev environment: `docker compose up -d` → Neo4j 5.26 + APOC at `bolt://localhost:7687` / browser `:7474`, auth `neo4j/kgfootball`, container state in gitignored `neo4j/`. Python: `.venv/` (pyenv 3.12.2), `pip install -r requirements.txt`; PyKEEN/torch only via `requirements-embeddings.txt` in Phase 5.
- A stub `CLAUDE.md` one level above the repo points here (for sessions started in the parent folder).

## Open questions / risks

All pre-start questions settled 2026-06-10 (tech stack, subset, feedback, exceed-LO policy — see Decisions). Remaining working items:

1. **Event-type scope** beyond the core set (Pass, Shot, Carry, Pressure, Ball Recovery, …) — decide during schema design with the Events v4.0.0 spec open.
2. **"Exceed" bar** (working assumption): LO7 = complete, documented schema design + mapping with justified choices; LO11 = systematic style comparison across all 20 teams with visualized results; LO2 kept deep as insurance candidate.
3. **LO1 PyKEEN mini-experiment** (~few hours) — schedule after KG is built (needs exported triples); frame as KG completion to also feed LO8.
4. **No slack in LO count** (10 claimed / 10 required): every claimed LO gets an explicit (LOx)-tagged paragraph in the report — final checklist pass against cover pages before submission.
5. **Hour budget**: assume ~80h project + ~30h portfolio doc for 6 ECTS (double the 3-ECTS baseline; unconfirmed). Per lecturer feedback: ingestion time-boxed, main effort on patterns + comparison.
6. **Timeline to 30 June deadline** (as of 2026-06-10): schema + time-boxed ingest by ~17 June → patterns + team comparison by ~24 June → PyKEEN/Datalog side components + report finalization by 30 June. Report sections written alongside, not at the end.
