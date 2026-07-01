"""Fetch team crests + the Premier League logo into src/dashboard/assets/.

Crests come from TheSportsDB's free API (badge PNGs on their CDN). Saved as
<team_id>.png so the dashboard can look them up by StatsBomb team id. A colored
initials badge is drawn as a fallback for any crest that fails to download, so
the dashboard never breaks on a missing file.

Usage:  python -m src.dashboard.fetch_assets

Note: club crests are trademarks of their clubs; used here only as small
identifying icons in a non-commercial academic dashboard.
"""

import json
import time
import urllib.parse
import urllib.request

import pandas as pd

from ..ingest import common

ASSETS = common.REPO_ROOT / "src" / "dashboard" / "assets"
CRESTS = ASSETS / "crests"
METRICS = common.REPO_ROOT / "generated" / "style" / "metrics.csv"
API = "https://www.thesportsdb.com/api/v1/json/3"
UA = {"User-Agent": "Mozilla/5.0 (academic project asset fetch)"}

# StatsBomb team name -> TheSportsDB search term where they differ
SEARCH_OVERRIDE = {"AFC Bournemouth": "Bournemouth"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    path.write_bytes(data)
    return len(data)


def crest_url(team_name):
    term = SEARCH_OVERRIDE.get(team_name, team_name)
    data = get_json(f"{API}/searchteams.php?t={urllib.parse.quote(term)}")
    teams = data.get("teams") or []
    # prefer the English Premier League entry, else the first hit
    for t in teams:
        if t.get("strLeague") == "English Premier League" and t.get("strBadge"):
            return t["strBadge"]
    return teams[0]["strBadge"] if teams and teams[0].get("strBadge") else None


def main():
    CRESTS.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(METRICS)

    ok, missing = 0, []
    for tid, name in zip(df.team_id, df.team):
        dest = CRESTS / f"{tid}.png"
        if dest.exists():
            ok += 1
            continue
        try:
            url = crest_url(name)
            if not url:
                missing.append(name)
                print(f"  no crest found: {name}")
                continue
            n = download(url, dest)
            ok += 1
            print(f"  {name:<22} -> {dest.name} ({n // 1024} KB)")
        except Exception as e:
            missing.append(name)
            print(f"  FAILED {name}: {e}")
        time.sleep(0.4)  # be polite to the free API

    # Premier League logo
    pl = ASSETS / "premier_league.png"
    if not pl.exists():
        try:
            data = get_json(f"{API}/lookupleague.php?id=4328")
            league = (data.get("leagues") or [{}])[0]
            url = league.get("strBadge") or league.get("strLogo")
            if url:
                download(url, pl)
                print(f"  Premier League logo -> {pl.name}")
        except Exception as e:
            print(f"  PL logo failed: {e}")

    print(f"\n{ok}/{len(df)} crests present"
          + (f", missing: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
