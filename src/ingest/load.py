"""Ingest StatsBomb PL 2015/16 JSON into the Neo4j KG (schema: docs/schema.md).

Usage:
    python -m src.ingest.load --limit 2     # first N matches (iteration/testing)
    python -m src.ingest.load               # full season (resumable, skips loaded matches)
"""

import argparse
import json
import time

from . import common
from .common import DATA_DIR, SUBTYPE_LABELS, ZONES, timestamp_seconds, zone_id

CONSTRAINTS = [
    "CREATE CONSTRAINT match_id IF NOT EXISTS FOR (m:Match) REQUIRE m.match_id IS UNIQUE",
    "CREATE CONSTRAINT team_id IF NOT EXISTS FOR (t:Team) REQUIRE t.team_id IS UNIQUE",
    "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player) REQUIRE p.player_id IS UNIQUE",
    "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
    "CREATE CONSTRAINT zone_id IF NOT EXISTS FOR (z:Zone) REQUIRE z.zone_id IS UNIQUE",
    # composite uniqueness needs Enterprise; a composite index makes the MERGE fast instead
    "CREATE INDEX possession_key IF NOT EXISTS FOR (p:Possession) ON (p.match_id, p.possession)",
    "CREATE INDEX event_match IF NOT EXISTS FOR (e:Event) ON (e.match_id, e.idx)",
    "CREATE INDEX event_type IF NOT EXISTS FOR (e:Event) ON (e.type)",
]


def setup_schema(session):
    for stmt in CONSTRAINTS:
        session.run(stmt)
    session.run("UNWIND $zones AS z MERGE (:Zone {zone_id: z.zone_id, third: z.third, channel: z.channel})",
                zones=ZONES)


def load_matches(session):
    matches = json.loads((DATA_DIR / "matches" / str(common.COMPETITION_ID) / f"{common.SEASON_ID}.json").read_text())
    rows = [{
        "match_id": m["match_id"],
        "date": m["match_date"],
        "kickoff": m.get("kick_off"),
        "week": m.get("match_week"),
        "home_score": m["home_score"],
        "away_score": m["away_score"],
        "stadium": (m.get("stadium") or {}).get("name", "").strip() or None,
        "referee": (m.get("referee") or {}).get("name"),
        "home_id": m["home_team"]["home_team_id"],
        "home_name": m["home_team"]["home_team_name"],
        "away_id": m["away_team"]["away_team_id"],
        "away_name": m["away_team"]["away_team_name"],
    } for m in matches]
    session.run("""
        UNWIND $rows AS r
        MERGE (m:Match {match_id: r.match_id})
          SET m.date = r.date, m.kickoff = r.kickoff, m.week = r.week,
              m.home_score = r.home_score, m.away_score = r.away_score,
              m.stadium = r.stadium, m.referee = r.referee
        MERGE (h:Team {team_id: r.home_id}) SET h.name = r.home_name
        MERGE (a:Team {team_id: r.away_id}) SET a.name = r.away_name
        MERGE (h)-[:HOME_IN]->(m)
        MERGE (a)-[:AWAY_IN]->(m)
    """, rows=rows)
    return [m["match_id"] for m in matches]


def load_lineups(session, match_id):
    lineups = json.loads((DATA_DIR / "lineups" / f"{match_id}.json").read_text())
    rows = []
    for side in lineups:
        for p in side["lineup"]:
            pos = p.get("positions") or []
            rows.append({
                "player_id": p["player_id"],
                "name": p["player_name"],
                "country": (p.get("country") or {}).get("name"),
                "team_id": side["team_id"],
                "jersey": p.get("jersey_number"),
                "position": pos[0]["position"] if pos else None,
                "from_minute": pos[0]["from"] if pos else None,
                "to_minute": pos[-1]["to"] if pos else None,
                "played": bool(pos),
            })
    session.run("""
        UNWIND $rows AS r
        MERGE (p:Player {player_id: r.player_id})
          SET p.name = r.name, p.country = r.country
        WITH p, r WHERE r.played
        MATCH (m:Match {match_id: $match_id})
        MERGE (p)-[pi:PLAYED_IN]->(m)
          SET pi.team_id = r.team_id, pi.jersey = r.jersey, pi.position = r.position,
              pi.from_minute = r.from_minute, pi.to_minute = r.to_minute
    """, rows=rows, match_id=match_id)


def event_rows(events, match_id):
    """Flatten raw events into per-label node rows + relationship rows."""
    nodes = {}          # label -> [props]
    rels = {"next": [], "part_of": [], "by_team": [], "by_player": [],
            "received_by": [], "in_zone": [], "related": []}
    possessions = {}    # possession number -> {play_pattern, team_id}

    ordered = sorted(events, key=lambda e: e["index"])
    for e in ordered:
        loc = e.get("location") or [None, None]
        row = {
            "event_id": e["id"], "match_id": match_id, "idx": e["index"],
            "period": e["period"], "minute": e["minute"], "second": e["second"],
            "timestamp_s": timestamp_seconds(e["timestamp"]),
            "type": e["type"]["name"], "play_pattern": e["play_pattern"]["name"],
            "x": loc[0], "y": loc[1], "duration": e.get("duration"),
            "under_pressure": e.get("under_pressure", False),
            "counterpress": e.get("counterpress", False),
            "off_camera": e.get("off_camera", False),
        }
        name = e["type"]["name"]
        label = SUBTYPE_LABELS.get(name)
        if name == "Pass":
            p = e.get("pass", {})
            end = p.get("end_location") or [None, None]
            row.update(length=p.get("length"), height=(p.get("height") or {}).get("name"),
                       body_part=(p.get("body_part") or {}).get("name"),
                       pass_type=(p.get("type") or {}).get("name"),
                       outcome=(p.get("outcome") or {}).get("name", "Complete"),
                       end_x=end[0], end_y=end[1],
                       cross=p.get("cross", False), switch=p.get("switch", False),
                       through_ball=p.get("through_ball", False))
            if p.get("recipient"):
                rels["received_by"].append({"event_id": e["id"], "player_id": p["recipient"]["id"]})
        elif name == "Shot":
            s = e.get("shot", {})
            end = (s.get("end_location") or [None, None])[:2]
            row.update(xg=s.get("statsbomb_xg"), outcome=(s.get("outcome") or {}).get("name"),
                       technique=(s.get("technique") or {}).get("name"),
                       body_part=(s.get("body_part") or {}).get("name"),
                       end_x=end[0], end_y=end[1])
        elif name == "Carry":
            end = e.get("carry", {}).get("end_location") or [None, None]
            row.update(end_x=end[0], end_y=end[1])
        elif name == "Ball Recovery":
            row.update(recovery_failure=e.get("ball_recovery", {}).get("recovery_failure", False))
        elif label:  # remaining subtypes: keep outcome where the payload has one
            key = "goalkeeper" if name == "Goal Keeper" else name.lower().replace(" ", "_").rstrip("*")
            payload = e.get(key, {})
            if isinstance(payload, dict) and payload.get("outcome"):
                row.update(outcome=payload["outcome"]["name"])

        nodes.setdefault(label or "", []).append(row)

        poss = e["possession"]
        possessions.setdefault(poss, {"play_pattern": e["play_pattern"]["name"],
                                      "team_id": e["possession_team"]["id"]})
        rels["part_of"].append({"event_id": e["id"], "possession": poss})
        rels["by_team"].append({"event_id": e["id"], "team_id": e["team"]["id"]})
        if e.get("player"):
            rels["by_player"].append({"event_id": e["id"], "player_id": e["player"]["id"]})
        z = zone_id(loc[0], loc[1])
        if z:
            rels["in_zone"].append({"event_id": e["id"], "zone_id": z})
        for rid in e.get("related_events", []):
            if e["id"] < rid:  # dedupe: one edge per unordered pair
                rels["related"].append({"a": e["id"], "b": rid})

    rels["next"] = [{"a": ordered[i]["id"], "b": ordered[i + 1]["id"]}
                    for i in range(len(ordered) - 1)]
    poss_rows = [{"possession": k, "match_id": match_id, **v} for k, v in possessions.items()]
    return nodes, rels, poss_rows


def load_events(session, match_id):
    events = json.loads((DATA_DIR / "events" / f"{match_id}.json").read_text())
    nodes, rels, poss_rows = event_rows(events, match_id)

    def run(tx):
        for label, rows in nodes.items():
            labels = f":Event:{label}" if label else ":Event"
            tx.run(f"UNWIND $rows AS r CREATE (e{labels}) SET e = r", rows=rows)
        tx.run("""UNWIND $rows AS r
                  MERGE (p:Possession {match_id: r.match_id, possession: r.possession})
                    SET p.play_pattern = r.play_pattern
                  WITH p, r
                  MATCH (m:Match {match_id: r.match_id}) MERGE (p)-[:IN_MATCH]->(m)
                  WITH p, r
                  MATCH (t:Team {team_id: r.team_id}) MERGE (p)-[:POSSESSION_BY]->(t)""",
               rows=poss_rows)
        tx.run("""UNWIND $rows AS r
                  MATCH (a:Event {event_id: r.a}), (b:Event {event_id: r.b})
                  CREATE (a)-[:NEXT]->(b)""", rows=rels["next"])
        tx.run("""UNWIND $rows AS r
                  MATCH (e:Event {event_id: r.event_id}),
                        (p:Possession {match_id: $mid, possession: r.possession})
                  CREATE (e)-[:PART_OF]->(p)""", rows=rels["part_of"], mid=match_id)
        tx.run("""UNWIND $rows AS r
                  MATCH (e:Event {event_id: r.event_id}), (t:Team {team_id: r.team_id})
                  CREATE (e)-[:BY_TEAM]->(t)""", rows=rels["by_team"])
        tx.run("""UNWIND $rows AS r
                  MATCH (e:Event {event_id: r.event_id}), (p:Player {player_id: r.player_id})
                  CREATE (e)-[:BY_PLAYER]->(p)""", rows=rels["by_player"])
        tx.run("""UNWIND $rows AS r
                  MATCH (e:Pass {event_id: r.event_id}), (p:Player {player_id: r.player_id})
                  CREATE (e)-[:RECEIVED_BY]->(p)""", rows=rels["received_by"])
        tx.run("""UNWIND $rows AS r
                  MATCH (e:Event {event_id: r.event_id}), (z:Zone {zone_id: r.zone_id})
                  CREATE (e)-[:IN_ZONE]->(z)""", rows=rels["in_zone"])
        tx.run("""UNWIND $rows AS r
                  MATCH (a:Event {event_id: r.a}), (b:Event {event_id: r.b})
                  CREATE (a)-[:RELATED_TO]->(b)""", rows=rels["related"])
        # starting formations from the two Starting XI events
        tx.run("""MATCH (e:Event {match_id: $mid, type: 'Starting XI'})-[:BY_TEAM]->(t:Team)
                  MATCH (t)-[r:HOME_IN|AWAY_IN]->(m:Match {match_id: $mid})
                  SET r.formation = e.formation""", mid=match_id)

    # formation lives in the raw tactics object; attach it to the row before writing
    for e in events:
        if e["type"]["name"] == "Starting XI":
            for row in nodes.get("", []):
                if row["event_id"] == e["id"]:
                    row["formation"] = e["tactics"]["formation"]
    session.execute_write(run)
    return len(events)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="ingest only the first N matches")
    args = ap.parse_args()

    driver = common.get_driver()
    with driver.session() as session:
        setup_schema(session)
        match_ids = load_matches(session)
        if args.limit:
            match_ids = match_ids[: args.limit]
        already = {r["mid"] for r in session.run(
            "MATCH (e:Event) RETURN DISTINCT e.match_id AS mid")}
        todo = [m for m in match_ids if m not in already]
        print(f"{len(match_ids)} matches requested, {len(already)} already loaded, {len(todo)} to do")

        t0 = time.time()
        for i, mid in enumerate(todo, 1):
            load_lineups(session, mid)
            n = load_events(session, mid)
            if i % 10 == 0 or i == len(todo):
                rate = i / (time.time() - t0)
                print(f"[{i}/{len(todo)}] match {mid}: {n} events "
                      f"({rate:.1f} matches/s, ETA {((len(todo) - i) / rate):.0f}s)")
    driver.close()


if __name__ == "__main__":
    main()
