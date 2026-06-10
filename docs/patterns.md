# Tactical Patterns — Formal Definitions (LO2/LO6/LO11)

Patterns are defined over the KG of docs/schema.md and implemented twice:
as **Cypher path queries** (Phase 3, `src/patterns/`) and — for patterns 1–2 — as
**recursive Datalog rules** (`src/datalog/`), cross-validated against each other.
Every match of a pattern is **materialized as a `(:PatternInstance)` node** with
`[:MATCHES]` provenance edges — derived knowledge that grows the KG (LO2 object
creation, LO8 evolution) and feeds the dashboard without re-running the queries.

Coordinates: all `x` values are from the *acting team's* attacking perspective
(x → 120 = opponent goal), so "opponent half" is simply `x ≥ 60` regardless of team.

---

## P1 — Pressing Regain

> Team T presses high and wins the ball back within seconds.

**Definition.** A `Pressure` event `p` by team T with `p.x ≥ minX` (default **60**,
opponent half), such that within `Δt` seconds (default **5**, same period) along the
`NEXT` chain there is a *regain event* `r` by T:
`r ∈ {BallRecovery (not failed), Interception (outcome Won/Success*), Duel (outcome Won/Success*)}`,
or the possession following `p`'s possession belongs to T.

**KG semantics.** `(p:Pressure)-[:BY_TEAM]->(T)`, variable-length `(p)-[:NEXT*1..k]->(r)`
bounded by `r.timestamp_s - p.timestamp_s ≤ Δt ∧ r.period = p.period`, `(r)-[:BY_TEAM]->(T)`.

**Validation hook.** StatsBomb's `counterpress` flag marks pressing actions within 5s of
an open-play turnover — instance sets should correlate strongly (not exactly: different
anchor semantics).

**Parameters.** `minX = 60`, `Δt = 5 s`, `k = 10` (NEXT hop bound).

---

## P2 — Fast Transition (Counter-Attack)

> Win the ball deep, shoot fast.

**Definition.** A possession `P` of team T such that:
1. its first event `f` lies in T's own half (`f.x ≤ 60`) and `P.play_pattern` is open play
   (not From Corner / Free Kick / Throw In / Kick Off / Penalty),
2. `P` contains a `Shot` event `s` with `s.timestamp_s − f.timestamp_s ≤ T_max`
   (default **15 s**, same period),
3. net forward progress `s.x − f.x ≥ minProgress` (default **30** pitch units).

**KG semantics.** `(f)-[:PART_OF]->(P)<-[:PART_OF]-(s:Shot)`, `f` = event with minimal
`idx` in `P`, `(P)-[:POSSESSION_BY]->(T)`.

**Validation hook.** Overlap with StatsBomb `play_pattern = "From Counter"` possessions.

**Parameters.** `T_max = 15 s`, `minProgress = 30`, own-half threshold `60`.

---

## P3 — Wide Build-Up

> Constructed progression through the wide channels into the final third.

**Definition.** A possession `P` of team T such that:
1. `P` contains ≥ `N` events (default **3**) in *middle-third wide zones*
   (`middle-left` ∪ `middle-right`),
2. a later event of `P` (higher `idx`) enters the *final third through a wide channel*
   (`final-left` ∪ `final-right`),
3. `P.play_pattern = "Regular Play"` (constructed build-up, not transitions/set pieces).

**KG semantics.** Zone membership via `(:Event)-[:IN_ZONE]->(:Zone)`; ordering via `idx`.

**Parameters.** `N = 3`, zone grid as in docs/schema.md (wide = y<18 ∪ y>62).

---

## PatternInstance materialization

```
(:PatternInstance {pattern: 'P1'|'P2'|'P3', match_id, team_id, params, t_start, t_end})
  -[:MATCHES]-> (:Event ...)      // anchor events (pressure+regain / first+shot / wide events)
  -[:MATCHES]-> (:Possession)     // P2, P3
  -[:FOUND_IN]-> (:Match)
  -[:EXHIBITED_BY]-> (:Team)
```

Re-running a pattern with the same params is idempotent (instances are MERGEd on
`(pattern, match_id, anchor event ids)`).

## Team-style metrics (Phase 4)

- **Pressing intensity**: P1 instances per opponent possession (and per 90).
- **Directness**: P2 instances per own open-play possession won in own half.
- **Wide orientation**: P3 share of own Regular-Play possessions reaching the final third.
- Complementary descriptors for context: possession share, mean possession length.

Style profile = normalized vector of these per team → similarity/clustering in Phase 4.

## Datalog formulation sketch (P1, `src/datalog/`)

```
reach(P, E, DT) :- next(P, E), dt(P, E, DT), DT <= 5.
reach(P, E, DT) :- reach(P, M, _), next(M, E), dt(P, E, DT), DT <= 5.
regain(P, R)    :- pressure(P, T), reach(P, R), wins_ball(R, T).
p1(P, R, T)     :- pressure(P, T), high(P), regain(P, R).
```

`reach` is the recursive transitive closure of `NEXT` bounded by the time window —
the LO2 recursion story; `p1` derives new facts (object creation analogy when
materialized back as PatternInstance nodes).
