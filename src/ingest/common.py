"""Shared helpers for the JSON -> Neo4j ingestion (see docs/schema.md)."""

from pathlib import Path

from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "open-data" / "data"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "kgfootball")

COMPETITION_ID = 2  # Premier League
SEASON_ID = 27      # 2015/16

# Event types that get a subtype label and detail properties (docs/schema.md).
SUBTYPE_LABELS = {
    "Pass": "Pass",
    "Shot": "Shot",
    "Carry": "Carry",
    "Pressure": "Pressure",
    "Ball Receipt*": "BallReceipt",
    "Ball Recovery": "BallRecovery",
    "Interception": "Interception",
    "Duel": "Duel",
    "Dribble": "Dribble",
    "Clearance": "Clearance",
    "Block": "Block",
    "Dispossessed": "Dispossessed",
    "Foul Committed": "FoulCommitted",
    "Foul Won": "FoulWon",
    "Goal Keeper": "Goalkeeper",
}

# 3x3 zone grid: thirds x channels (channel split 18/62 = penalty-box width).
ZONES = [
    {"zone_id": f"{third}-{channel}", "third": third, "channel": channel}
    for third in ("defensive", "middle", "final")
    for channel in ("left", "central", "right")
]


def zone_id(x, y):
    if x is None or y is None:
        return None
    third = "defensive" if x < 40 else "middle" if x < 80 else "final"
    channel = "left" if y < 18 else "central" if y <= 62 else "right"
    return f"{third}-{channel}"


def timestamp_seconds(ts):
    """'00:23:11.293' -> seconds since period start."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
