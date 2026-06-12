"""Tactical patterns P1-P3 as Cypher (formal definitions: docs/patterns.md).

Each query runs per match (parameter $mid) and MERGEs (:PatternInstance) nodes
keyed on (pattern, match_id, anchor) -- re-running is idempotent; re-running with
different $params overwrites the params property (params are not part of the key,
see docs/patterns.md).

Outcome vocabulary observed in the data (PL 2015/16): regains are
'Won' | 'Success In Play' | 'Success Out'; a NULL outcome counts as not won.
"""

REGAIN_OUTCOMES = ["Won", "Success In Play", "Success Out"]

# P2: "open play" excludes set-piece possessions (docs/patterns.md);
# 'From Penalty' does not occur in this season but is excluded for robustness.
P2_EXCLUDED_PATTERNS = ["From Corner", "From Free Kick", "From Throw In",
                        "From Kick Off", "From Penalty"]

P1_DEFAULTS = {"minX": 60.0, "dt": 5.0, "k": 10}
P2_DEFAULTS = {"tMax": 15.0, "minProgress": 30.0, "ownHalf": 60.0}
P3_DEFAULTS = {"n": 3}

# --- P1: Pressing Regain -----------------------------------------------------
# Branch a: a regain *event* by the pressing team within dt along the NEXT chain.
# Branch b: no explicit regain event, but the very next possession belongs to the
# pressing team and starts within dt (turnover forced by the press).
# Both branches anchor on the pressure event, so an instance is created once.

P1 = """
MATCH (p:Event:Pressure {match_id: $mid})-[:BY_TEAM]->(t:Team)
WHERE p.x >= $minX
CALL (p, t) {
    MATCH path = (p)-[:NEXT*1..10]->(r:Event)
    WHERE r.period = p.period
      AND r.timestamp_s - p.timestamp_s <= $dt
      AND (r)-[:BY_TEAM]->(t)
      AND (
        (r:BallRecovery AND NOT coalesce(r.recovery_failure, false)) OR
        (r:Interception AND r.outcome IN $regainOutcomes) OR
        (r:Duel AND r.outcome IN $regainOutcomes)
      )
    RETURN r ORDER BY r.idx LIMIT 1
  UNION
    MATCH (p)-[:PART_OF]->(po:Possession)
    MATCH (po2:Possession {match_id: $mid, possession: po.possession + 1})
          -[:POSSESSION_BY]->(t)
    USING INDEX po2:Possession(match_id, possession)
    MATCH (r:Event)-[:PART_OF]->(po2)
    WHERE r.period = p.period AND r.timestamp_s - p.timestamp_s <= $dt
    RETURN r ORDER BY r.idx LIMIT 1
}
WITH p, t, r ORDER BY r.idx
WITH p, t, collect(r)[0] AS r
MATCH (m:Match {match_id: $mid})
MERGE (pi:PatternInstance {pattern: 'P1', match_id: $mid, anchor: p.event_id})
SET pi.team_id = t.team_id, pi.params = $params,
    pi.t_start = p.timestamp_s, pi.t_end = r.timestamp_s, pi.period = p.period
MERGE (pi)-[:MATCHES]->(p)
MERGE (pi)-[:MATCHES]->(r)
MERGE (pi)-[:FOUND_IN]->(m)
MERGE (pi)-[:EXHIBITED_BY]->(t)
RETURN count(pi) AS n
"""

# --- P2: Fast Transition (counter-attack) ------------------------------------
# First located event of an open-play possession lies in the own half; a shot in
# the same possession follows within tMax with >= minProgress forward progress.
# Anchored on the shot (a possession with two qualifying shots yields two
# instances -- each shot is its own transition outcome).

P2 = """
MATCH (po:Possession {match_id: $mid})-[:POSSESSION_BY]->(t:Team)
WHERE NOT po.play_pattern IN $excludedPatterns
MATCH (f:Event)-[:PART_OF]->(po)
WHERE f.x IS NOT NULL
WITH po, t, f ORDER BY f.idx
WITH po, t, collect(f)[0] AS f
WHERE f.x <= $ownHalf
MATCH (s:Shot)-[:PART_OF]->(po)
WHERE (s)-[:BY_TEAM]->(t)
  AND s.period = f.period
  AND s.timestamp_s - f.timestamp_s <= $tMax
  AND s.x - f.x >= $minProgress
MATCH (m:Match {match_id: $mid})
MERGE (pi:PatternInstance {pattern: 'P2', match_id: $mid, anchor: s.event_id})
SET pi.team_id = t.team_id, pi.params = $params,
    pi.t_start = f.timestamp_s, pi.t_end = s.timestamp_s, pi.period = f.period
MERGE (pi)-[:MATCHES]->(f)
MERGE (pi)-[:MATCHES]->(s)
MERGE (pi)-[:MATCHES]->(po)
MERGE (pi)-[:FOUND_IN]->(m)
MERGE (pi)-[:EXHIBITED_BY]->(t)
RETURN count(pi) AS n
"""

# --- P3: Wide Build-Up --------------------------------------------------------
# A Regular-Play possession with >= n of the team's events in the wide middle
# third, entering the wide final third afterwards (idx after the n-th wide
# event). Wide events are restricted to the possession team: the pattern
# describes T's build-up, and possessions also contain opponent events
# (pressures, duels). Anchored on the possession.

P3 = """
MATCH (po:Possession {match_id: $mid, play_pattern: 'Regular Play'})
      -[:POSSESSION_BY]->(t:Team)
MATCH (w:Event)-[:PART_OF]->(po), (w)-[:BY_TEAM]->(t), (w)-[:IN_ZONE]->(z:Zone)
WHERE z.third = 'middle' AND z.channel IN ['left', 'right']
WITH po, t, w ORDER BY w.idx
WITH po, t, collect(w) AS wides
WHERE size(wides) >= $n
WITH po, t, wides, wides[$n - 1] AS nth
MATCH (e:Event)-[:PART_OF]->(po), (e)-[:BY_TEAM]->(t), (e)-[:IN_ZONE]->(zf:Zone)
WHERE zf.third = 'final' AND zf.channel IN ['left', 'right'] AND e.idx > nth.idx
WITH po, t, wides, e ORDER BY e.idx
WITH po, t, wides, collect(e)[0] AS entry
MATCH (m:Match {match_id: $mid})
MERGE (pi:PatternInstance {pattern: 'P3', match_id: $mid,
                           anchor: toString(po.possession)})
SET pi.team_id = t.team_id, pi.params = $params,
    pi.t_start = wides[0].timestamp_s, pi.t_end = entry.timestamp_s,
    pi.period = entry.period
MERGE (pi)-[:MATCHES]->(po)
MERGE (pi)-[:MATCHES]->(entry)
WITH pi, m, wides, entry
UNWIND wides AS w
MERGE (pi)-[:MATCHES]->(w)
WITH DISTINCT pi, m
MATCH (t:Team {team_id: pi.team_id})
MERGE (pi)-[:FOUND_IN]->(m)
MERGE (pi)-[:EXHIBITED_BY]->(t)
RETURN count(pi) AS n
"""

PATTERNS = {
    "P1": (P1, P1_DEFAULTS),
    "P2": (P2, P2_DEFAULTS),
    "P3": (P3, P3_DEFAULTS),
}
