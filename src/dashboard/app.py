"""Streamlit dashboard: team-style comparison on the football KG (LO11).

Insight-first design: plain-language labels, an auto-generated verdict per team,
and difference-vs-league pitch maps (a team's absolute maps look like every other
PL team's — the *style* is the deviation from the league average). Team crests and
the Premier League logo are loaded from src/dashboard/assets (fetch_assets.py).

Reads generated/style/metrics.csv (python -m src.dashboard.metrics) and the pattern
instances from Neo4j (docker compose up -d).

Run:  streamlit run src/dashboard/app.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from mplsoccer import Pitch
from scipy.cluster import hierarchy
from scipy.ndimage import gaussian_filter

from src.ingest import common

ASSETS = REPO_ROOT / "src" / "dashboard" / "assets"
CRESTS = ASSETS / "crests"

# Premier League brand palette
PL_PURPLE = "#37003C"
PL_PINK = "#E90052"
PL_GREEN = "#00FF85"

st.set_page_config(page_title="Premier League 2015/16 — Team Styles",
                   page_icon=str(ASSETS / "premier_league.png") if
                   (ASSETS / "premier_league.png").exists() else None,
                   layout="wide")

st.markdown(f"""
<style>
    #MainMenu, footer, [data-testid="stToolbar"] {{ visibility: hidden; }}
    .block-container {{ padding-top: 2.5rem; max-width: 1300px; }}
    h1, h2, h3 {{ color: {PL_PURPLE}; font-weight: 700; }}
    [data-testid="stMetricValue"] {{ font-size: 1.4rem; color: {PL_PURPLE}; }}
    [data-testid="stMetricLabel"] {{ font-weight: 600; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 32px; margin-top: 6px; }}
    .stTabs [data-baseweb="tab"] {{ font-weight: 600; font-size: 1.02rem;
                                    padding: 10px 4px; }}
    .stTabs [aria-selected="true"] {{ color: {PL_PINK} !important; }}
</style>
""", unsafe_allow_html=True)

# --- plain-language metadata for every metric --------------------------------
# key -> (short label, one-line football meaning, positive trait, negative trait)
METRICS = {
    "pressing": (
        "Pressing",
        "How often the team presses in the opponent half and wins the ball back "
        "within 5 s — per opponent possession.",
        "presses high and intensely",
        "presses little and sits back"),
    "directness": (
        "Directness",
        "How often a deep ball recovery becomes a shot within 15 s — fast, "
        "vertical transitions.",
        "plays fast and vertically",
        "plays patiently, with few transitions"),
    "wide": (
        "Wide play",
        "How often the team reaches the final third through the wings rather than "
        "centrally.",
        "builds up down the wings",
        "builds up centrally"),
    "possession_share": (
        "Possession",
        "Share of all possessions in a match that belong to the team.",
        "dominates possession",
        "cedes the ball to the opponent"),
    "avg_poss_len": (
        "Build-up patience",
        "Average length of a possession in actions — long means patient, "
        "controlled build-up.",
        "keeps the ball for long spells",
        "plays in short, quick spells"),
}
DIMS = list(METRICS)
LABEL = {k: v[0] for k, v in METRICS.items()}

PATTERN_INTRO = {
    "Pressing (P1)": "Press high and win the ball back within 5 seconds.",
    "Counter-attacks (P2)": "Win the ball deep and get a shot away within 15 seconds.",
    "Wide build-up (P3)": "Progress into the final third through the wings.",
}
PATTERN_METRIC = {"Pressing (P1)": "pressing",
                  "Counter-attacks (P2)": "directness",
                  "Wide build-up (P3)": "wide"}

N_CLUSTERS = 4

# Every pitch map answers ONE question with one annotated number, instead of an
# abstract heatmap. NB: EXHIBITED_BY and MATCHES both start at pi, so they must
# be *separate* MATCH clauses — chaining them through Team matches nothing.
ALL_PRESSURES = ("MATCH (p:Pressure)-[:BY_TEAM]->(:Team {name:$team}) "
                 "RETURN p.x AS x, p.y AS y")
P3_ENTRIES = ("MATCH (pi:PatternInstance {{pattern:'P3'}}){team} "
              "MATCH (pi)-[:MATCHES]->(e:Event)-[:IN_ZONE]->(:Zone {{third:'final'}}) "
              "RETURN e.x AS x, e.y AS y")
P2_RUNS = """
    MATCH (pi:PatternInstance {pattern:'P2'})-[:EXHIBITED_BY]->(:Team {name:$team})
    MATCH (pi)-[:MATCHES]->(e:Event)
    WITH pi, e ORDER BY e.idx
    WITH pi, collect(e) AS es
    RETURN es[0].x AS x1, es[0].y AS y1, es[-1].x AS x2, es[-1].y AS y2,
           pi.t_end - pi.t_start AS dur, es[-1].outcome AS outcome
"""
# signature moment: the team's fastest counter goal, plus the actual ball path
# reconstructed by walking the possession's event chain in the graph
SIGNATURE_COUNTER = """
    MATCH (pi:PatternInstance {pattern:'P2'})-[:EXHIBITED_BY]->(t:Team {name:$team})
    MATCH (pi)-[:MATCHES]->(s:Shot) WHERE s.outcome = 'Goal'
    MATCH (pi)-[:FOUND_IN]->(m:Match)
    MATCH (o:Team)-[:HOME_IN|AWAY_IN]->(m) WHERE o.team_id <> t.team_id
    OPTIONAL MATCH (s)-[:BY_PLAYER]->(pl:Player)
    RETURN pi.match_id AS mid, s.idx AS shot_idx, m.week AS week,
           o.name AS opponent, s.minute AS minute, s.xg AS xg,
           pl.name AS scorer, pi.t_end - pi.t_start AS dur
    ORDER BY dur LIMIT 1
"""
COUNTER_PATH = """
    MATCH (pi:PatternInstance {pattern:'P2', match_id:$mid})
    MATCH (pi)-[:MATCHES]->(:Shot {idx:$shot_idx})
    MATCH (pi)-[:MATCHES]->(po:Possession)
    MATCH (e:Event)-[:PART_OF]->(po)
    WHERE e.x IS NOT NULL AND e.idx <= $shot_idx
      AND e.type <> 'Pressure'  // presser location, not the ball
      AND (e)-[:BY_TEAM]->(:Team {name:$team})
    RETURN e.x AS x, e.y AS y
    ORDER BY e.idx
"""


@st.cache_data
def load_metrics():
    path = REPO_ROOT / "generated" / "style" / "metrics.csv"
    if not path.exists():
        st.error("metrics.csv missing — run `python -m src.dashboard.metrics` first.")
        st.stop()
    df = pd.read_csv(path).sort_values("team").reset_index(drop=True)
    z = (df[DIMS] - df[DIMS].mean()) / df[DIMS].std()
    return df, z


@st.cache_data
def fetch(query, **params):
    driver = common.get_driver()
    try:
        with driver.session() as s:
            rows = [dict(r) for r in s.run(query, **params)]
    except Exception as e:  # Neo4j down — maps degrade gracefully, metrics still work
        st.warning(f"Neo4j unreachable ({e}). Pitch maps hidden — run "
                   "`docker compose up -d`.")
        return pd.DataFrame()
    finally:
        driver.close()
    return pd.DataFrame(rows)


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


@st.cache_data
def standings():
    """Final league table computed from the match scores in the KG."""
    rows = fetch("MATCH (h:Team)-[:HOME_IN]->(m:Match)<-[:AWAY_IN]-(a:Team) "
                 "RETURN h.team_id AS home, a.team_id AS away, "
                 "m.home_score AS hs, m.away_score AS asc")
    if rows.empty:
        return None
    from collections import defaultdict
    t = defaultdict(lambda: dict(points=0, W=0, D=0, L=0, gf=0, ga=0))
    for _, r in rows.iterrows():
        h, a, hs, as_ = int(r.home), int(r.away), int(r.hs), int(r.asc)
        t[h]["gf"] += hs; t[h]["ga"] += as_
        t[a]["gf"] += as_; t[a]["ga"] += hs
        if hs > as_:
            t[h]["points"] += 3; t[h]["W"] += 1; t[a]["L"] += 1
        elif hs < as_:
            t[a]["points"] += 3; t[a]["W"] += 1; t[h]["L"] += 1
        else:
            t[h]["points"] += 1; t[a]["points"] += 1
            t[h]["D"] += 1; t[a]["D"] += 1
    tbl = pd.DataFrame([{"team_id": k, "points": v["points"], "W": v["W"],
                         "D": v["D"], "L": v["L"], "gd": v["gf"] - v["ga"]}
                        for k, v in t.items()])
    tbl = tbl.sort_values(["points", "gd"], ascending=False).reset_index(drop=True)
    tbl["position"] = tbl.index + 1
    return tbl


def crest_path(team_id):
    p = CRESTS / f"{team_id}.png"
    return str(p) if p.exists() else None


@st.cache_data
def crest_img(team_id):
    p = CRESTS / f"{team_id}.png"
    return mpimg.imread(str(p)) if p.exists() else None


def team_id_of(df, team):
    return int(df.loc[df.team == team, "team_id"].iloc[0])


def team_header(df, team, level="##"):
    c1, c2 = st.columns([1, 11])
    path = crest_path(team_id_of(df, team))
    if path:
        c1.image(path, width=52)
    c2.markdown(f"{level} {team}")


def p3_entries(team=None):
    clause = "-[:EXHIBITED_BY]->(:Team {name:$team})" if team else ""
    q = P3_ENTRIES.format(team=clause)
    return fetch(q, team=team) if team else fetch(q)


@st.cache_data
def league_high_press_count():
    d = fetch("MATCH (p:Pressure) WHERE p.x >= 60 RETURN count(p) AS n")
    return int(d.n.iloc[0]) if len(d) else None


@st.cache_data
def league_left_share():
    d = p3_entries()
    return float((d.y < 40).mean()) if len(d) else None


def rank_of(df, dim, value):
    """1 = highest in the league."""
    return int((df[dim] > value).sum()) + 1


def verdict(team, row, zrow, df):
    """Auto-generated plain-language style summary from the z-scores.

    All trait phrases are main-clause ("<team> presses high"), so they read
    correctly whether used as a headline or a bullet.
    """
    order = sorted(DIMS, key=lambda d: -abs(zrow[d]))
    lead = order[0]
    _, _, pos, neg = METRICS[lead]
    phrase = pos if zrow[lead] > 0 else neg
    r = rank_of(df, lead, row[lead])
    if r == 1:
        head = f"**League-leading:** {team} {phrase}."
    elif r == len(df):
        head = f"**League-trailing:** {team} {phrase}."
    else:
        head = f"{team} {phrase}."

    bullets = []
    for d in order:
        z = zrow[d]
        if abs(z) < 0.8 or d == lead:
            continue
        _, _, pos, neg = METRICS[d]
        bullets.append(f"{pos if z > 0 else neg} "
                       f"(rank {rank_of(df, d, row[d])}/{len(df)})")
    return head, bullets[:3]


def show(fig, **kwargs):
    """st.pyplot + close: streamlit reruns the whole script per interaction, so
    unclosed figures pile up in memory and slow everything down."""
    st.pyplot(fig, **kwargs)
    plt.close(fig)


def draw_pitch():
    pitch = Pitch(pitch_type="statsbomb", line_color="#999", line_zorder=2,
                  pitch_color="none")
    fig, ax = pitch.draw(figsize=(6, 4))
    return pitch, fig, ax


def pressing_map(team):
    """One question: where does the HIGH press happen, and does it work?

    Deliberately restricted to pressures in the opponent's half (x >= 60), the
    same threshold as the P1 pattern: pressure in one's own half is ordinary
    defending that every team does and says nothing about a pressing game plan.
    """
    d = fetch(ALL_PRESSURES, team=team)
    pitch, fig, ax = draw_pitch()
    high = d[d.x >= 60] if len(d) else d
    if len(high) < 10:
        return fig, "Not enough high-pressing actions to draw a map."
    # binned heatmap + gaussian smoothing: looks like a KDE, renders ~30x faster
    stat = pitch.bin_statistic(high.x, high.y, statistic="count", bins=(60, 40))
    stat["statistic"] = gaussian_filter(stat["statistic"], sigma=2.5)
    pitch.heatmap(stat, ax=ax, cmap="Purples", zorder=1, alpha=0.9)
    ax.axvline(60, color=PL_PINK, lw=1.5, ls=":", zorder=3)
    # success rate: P1 instances (regain within 5 s) over all high presses
    p1_count = int(df.loc[df.team == team, "P1"].iloc[0])
    succ = p1_count / len(high)
    lg_high = league_high_press_count()
    lg_succ = df["P1"].sum() / lg_high if lg_high else None
    lg_txt = f" (league: {lg_succ:.0%})" if lg_succ else ""
    ax.set_title(f"{len(high):,} presses in the opponent's half · "
                 f"{succ:.0%} win the ball back within 5 s{lg_txt}",
                 fontsize=9, color="#333")
    cap = ("Only pressures in the opponent's half are shown — pressing in one's "
           "own half is ordinary defending and says little about tactics. Darker "
           "purple = presses there more often (pressing traps often show up on "
           "the wings). The success rate counts the presses that won the ball "
           "back within 5 seconds, straight from the pattern instances in the "
           "knowledge graph.")
    return fig, cap


def counter_map(team):
    """One question: where do counters start, and how fast are they?"""
    d = fetch(P2_RUNS, team=team).dropna(subset=["x1", "x2"])
    pitch, fig, ax = draw_pitch()
    if not len(d):
        return fig, "No counter-attacks found for this team."
    goals = d[d.outcome == "Goal"]
    other = d[d.outcome != "Goal"]
    pitch.scatter(d.x1, d.y1, ax=ax, s=30, color=PL_GREEN,
                  edgecolors="#1a8a55", linewidth=0.8, alpha=0.85, zorder=3)
    pitch.scatter(other.x2, other.y2, ax=ax, s=30, color=PL_PINK,
                  edgecolors="#90003a", linewidth=0.8, alpha=0.85, zorder=3)
    if len(goals):
        pitch.scatter(goals.x2, goals.y2, ax=ax, s=150, marker="*",
                      color="#FFD700", edgecolors="#8a6d00", linewidth=0.8,
                      zorder=5)
    pitch.arrows(d.x1.mean(), d.y1.mean(), d.x2.mean(), d.y2.mean(), ax=ax,
                 width=3, headwidth=7, color=PL_PURPLE, zorder=4)
    dur = float(d.dur.mean())
    goal_word = "goal" if len(goals) == 1 else "goals"
    ax.set_title(f"{len(d)} counter-attacks · avg {dur:.0f}s from winning the "
                 f"ball to the shot · {len(goals)} {goal_word}", fontsize=9,
                 color="#333")
    cap = ("Green dots = where the ball was won, pink dots = where the resulting "
           "shot was taken, gold stars = counters that ended in a goal. The "
           "purple arrow joins the average recovery spot to the average shot "
           "spot — a longer arrow means counters covering more ground.")
    return fig, cap


def wide_map(team):
    """One question: which flank does the build-up favour?"""
    d = p3_entries(team)
    pitch, fig, ax = draw_pitch()
    if not len(d):
        return fig, "No wide build-ups found for this team."
    pitch.scatter(d.x, d.y, ax=ax, s=26, color=PL_PURPLE, alpha=0.45, zorder=3)
    left = float((d.y < 40).mean())
    lg_left = league_left_share() or 0.5
    # y axis is inverted on the drawn pitch: small y renders at the top
    ax.text(40, 6, f"left flank {left:.0%}  (league {lg_left:.0%})",
            fontsize=9, color=PL_PURPLE, ha="center", fontweight="bold", zorder=4)
    ax.text(40, 76, f"right flank {1 - left:.0%}  (league {1 - lg_left:.0%})",
            fontsize=9, color=PL_PURPLE, ha="center", fontweight="bold", zorder=4)
    ax.set_title(f"{len(d)} wide build-ups — where they enter the final third",
                 fontsize=9, color="#333")
    cap = ("Each dot = the moment a patient build-up enters the final third "
           "through a wing. The percentages show which flank the team favours, "
           "compared with the league split.")
    return fig, cap


def pattern_map(choice, team):
    if choice.startswith("Pressing"):
        return pressing_map(team)
    if choice.startswith("Counter"):
        return counter_map(team)
    return wide_map(team)


def signature_counter_fig(team, mid, shot_idx):
    ev = fetch(COUNTER_PATH, team=team, mid=mid, shot_idx=shot_idx)
    pitch, fig, ax = draw_pitch()
    if len(ev) < 2:
        return None
    pitch.lines(ev.x[:-1], ev.y[:-1], ev.x[1:].values, ev.y[1:].values, ax=ax,
                comet=True, color=PL_PURPLE, lw=4, alpha=0.7, zorder=3)
    pitch.scatter([ev.x.iloc[0]], [ev.y.iloc[0]], ax=ax, s=90, color=PL_GREEN,
                  edgecolors="#1a8a55", linewidth=1, zorder=4)
    pitch.scatter([ev.x.iloc[-1]], [ev.y.iloc[-1]], ax=ax, s=280, marker="*",
                  color="#FFD700", edgecolors="#8a6d00", linewidth=0.8, zorder=5)
    return fig


def radar(ax, zrow, label, color):
    ang = np.linspace(0, 2 * np.pi, len(DIMS), endpoint=False)
    val = np.clip(zrow.to_numpy(), -2.5, 2.5)
    ang = np.concatenate([ang, ang[:1]])
    val = np.concatenate([val, val[:1]])
    ax.plot(ang, val, color=color, label=label, linewidth=2)
    ax.fill(ang, val, color=color, alpha=0.15)
    ax.set_xticks(ang[:-1])
    ax.set_xticklabels([LABEL[d] for d in DIMS], fontsize=8)
    ax.tick_params(axis="x", pad=13)  # keep labels clear of the web
    ax.set_ylim(-2.5, 2.5)
    ax.set_yticks([-2, -1, 0, 1, 2])
    ax.set_yticklabels(["--", "-", "avg", "+", "++"], fontsize=7, color="#999")
    ax.axhline(0, color="#ccc", lw=0.5)


def style_families(df, z, teams):
    link = hierarchy.linkage(z, method="ward")
    labels = hierarchy.fcluster(link, N_CLUSTERS, criterion="maxclust")
    fams = []
    for c in sorted(set(labels)):
        idx = [i for i in range(len(teams)) if labels[i] == c]
        mean_z = z.iloc[idx].mean()
        traits = [f"{'high' if mean_z[d] > 0 else 'low'} {LABEL[d].lower()}"
                  for d in mean_z.abs().sort_values(ascending=False).index[:2]]
        fams.append((", ".join(traits), [teams[i] for i in idx],
                     [int(df.iloc[i].team_id) for i in idx]))
    return fams


def scatter_crests(df, xdim, ydim):
    fig, ax = plt.subplots(figsize=(9, 6))
    for _, r in df.iterrows():
        img = crest_img(int(r.team_id))
        if img is not None:
            ab = AnnotationBbox(OffsetImage(img, zoom=0.055), (r[xdim], r[ydim]),
                                frameon=False)
            ax.add_artist(ab)
        else:
            ax.scatter(r[xdim], r[ydim], s=40, color=PL_PURPLE)
        if HAS_TABLE and not pd.isna(r.get("position")):
            ax.annotate(ordinal(int(r["position"])), (r[xdim], r[ydim]),
                        fontsize=6, color="#999", ha="center",
                        xytext=(0, -12), textcoords="offset points")
    ax.update_datalim(df[[xdim, ydim]].to_numpy())
    ax.autoscale_view()
    ax.margins(0.08)
    ax.axvline(df[xdim].mean(), color="#ccc", lw=0.8, ls="--")
    ax.axhline(df[ydim].mean(), color="#ccc", lw=0.8, ls="--")
    ax.set_xlabel(LABEL[xdim])
    ax.set_ylabel(LABEL[ydim])
    ax.spines[["top", "right"]].set_visible(False)
    return fig


# =============================================================================
df, z = load_metrics()
_tbl = standings()
if _tbl is not None:
    df = df.merge(_tbl, on="team_id", how="left")  # preserves order → z stays aligned
HAS_TABLE = _tbl is not None
teams = df["team"].tolist()


def finish_line(row):
    if not HAS_TABLE or pd.isna(row.get("position")):
        return None
    return (f"Finished **{ordinal(int(row['position']))}** · {int(row['points'])} pts "
            f"· {int(row['W'])}W–{int(row['D'])}D–{int(row['L'])}L · GD {int(row['gd']):+d}")

_pl_logo = ASSETS / "premier_league.png"
_b1, _b2 = st.columns([1, 13], vertical_alignment="center")
if _pl_logo.exists():
    _b1.image(str(_pl_logo), width=72)
_b2.markdown(f"""
<div style="background: linear-gradient(100deg, {PL_PURPLE} 0%, #59095f 55%, {PL_PINK} 140%);
            border-radius: 14px; padding: 20px 28px;">
  <div style="color: #ffffff; font-size: 1.8rem; font-weight: 800; line-height: 1.15;">
    Premier League 2015/16 — Team Playing Styles</div>
  <div style="color: #ffffffbb; font-size: 0.95rem; margin-top: 6px;">
    Three tactical patterns, mined from a knowledge graph as rules and compared
    across all 20 teams &nbsp;·&nbsp; StatsBomb Open Data</div>
</div>
""", unsafe_allow_html=True)

tab_league, tab_team, tab_cmp = st.tabs(
    ["League overview", "Team profile", "Compare teams"])

# --- LEAGUE ------------------------------------------------------------------
with tab_league:
    st.subheader("The three playing patterns")
    st.write("Each team is described by how often it creates these three recurring "
             "situations — always **relative to its opportunities**, so possession "
             "differences do not distort the numbers.")
    cols = st.columns(3)
    for col, (name, desc) in zip(cols, PATTERN_INTRO.items()):
        leader = df.loc[df[PATTERN_METRIC[name]].idxmax(), "team"]
        with col:
            st.markdown(f"**{name}**")
            st.caption(desc)
            lc1, lc2 = st.columns([1, 4])
            path = crest_path(team_id_of(df, leader))
            if path:
                lc1.image(path, width=34)
            lc2.metric("League leader", leader)

    if HAS_TABLE:
        st.divider()
        st.subheader("The season at a glance")
        st.caption("Final table with each team's style profile. Style bars are "
                   "scaled between the league's lowest and highest value.")
        view = df.sort_values("position")[
            ["position", "team", "points", "W", "D", "L", "gd"] + DIMS]
        colcfg = {
            "position": st.column_config.NumberColumn("Pos", width="small"),
            "team": st.column_config.TextColumn("Team", width="medium"),
            "points": st.column_config.NumberColumn("Pts", width="small"),
            "W": st.column_config.NumberColumn("W", width="small"),
            "D": st.column_config.NumberColumn("D", width="small"),
            "L": st.column_config.NumberColumn("L", width="small"),
            "gd": st.column_config.NumberColumn("GD", width="small"),
        }
        for d in DIMS:
            colcfg[d] = st.column_config.ProgressColumn(
                LABEL[d], help=METRICS[d][1],
                format="%.1f" if d == "avg_poss_len" else "%.3f",
                min_value=float(df[d].min()), max_value=float(df[d].max()))
        st.dataframe(view, column_config=colcfg, hide_index=True, height=738)

    st.divider()
    st.subheader("Who stands out?")
    metric = st.selectbox("Metric", DIMS, format_func=lambda d: LABEL[d])
    st.markdown(f"*{METRICS[metric][1]}*")
    ranked = df.sort_values(metric)
    fig, ax = plt.subplots(figsize=(8, 7))
    if HAS_TABLE:
        norm = plt.Normalize(vmin=1, vmax=len(df))
        cmap = plt.cm.RdYlGn_r
        ax.barh(ranked["team"], ranked[metric],
                color=[cmap(norm(p)) for p in ranked["position"]])
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cb = fig.colorbar(sm, ax=ax, pad=0.02, fraction=0.046)
        cb.set_label("Final league position", fontsize=8)
        cb.set_ticks([1, len(df)])
        cb.set_ticklabels(["1st", f"{len(df)}th"])
    else:
        ax.barh(ranked["team"], ranked[metric], color=PL_PURPLE)
    for j, (tid, val) in enumerate(zip(ranked["team_id"], ranked[metric])):
        img = crest_img(int(tid))
        if img is not None:
            ab = AnnotationBbox(OffsetImage(img, zoom=0.026), (val, j),
                                frameon=False, box_alignment=(-0.3, 0.5))
            ax.add_artist(ab)
    ax.set_xlim(0, ranked[metric].max() * 1.12)
    ax.margins(y=0.02)
    ax.set_xlabel(LABEL[metric])
    ax.spines[["top", "right"]].set_visible(False)
    show(fig, width="stretch")
    if HAS_TABLE:
        with st.expander("How to read this chart"):
            st.write("Bar length shows how much of this the team does, always "
                     "normalized per opportunity rather than raw counts. The bar "
                     "colour is the team's final league position — green finished "
                     "top, red finished bottom — so you can see at a glance "
                     "whether the style paid off.")

    st.divider()
    st.subheader("Style map")
    st.markdown("*Each crest is one team; pick the two axes. Dashed lines mark the "
                "league average — teams in the same corner play similarly.*")
    c1, c2 = st.columns(2)
    xdim = c1.selectbox("X axis", DIMS, index=0, format_func=lambda d: LABEL[d])
    ydim = c2.selectbox("Y axis", DIMS, index=1, format_func=lambda d: LABEL[d])
    show(scatter_crests(df, xdim, ydim), width="content")

    st.divider()
    st.subheader("Style families")
    st.caption("Teams automatically grouped by their overall profile "
               "(hierarchical clustering over all five metrics).")
    fams = style_families(df, z, teams)
    fam_cols = st.columns(len(fams))
    for col, (traits, members, ids) in zip(fam_cols, fams):
        with col:
            st.markdown(f"**{traits.capitalize()}**")
            paths = [p for p in (crest_path(t) for t in ids) if p]
            if paths:
                st.image(paths, width=34)
            st.caption(", ".join(members))

# --- TEAM --------------------------------------------------------------------
with tab_team:
    team = st.selectbox("Team", teams, key="profile")
    i = df.index[df.team == team][0]
    row, zrow = df.iloc[i], z.iloc[i]

    team_header(df, team)
    fl = finish_line(row)
    if fl:
        st.markdown(fl)
    head, bullets = verdict(team, row, zrow, df)
    st.markdown(f"### {head}")
    for b in bullets:
        st.markdown(f"- {b}")
    st.caption(f"Season: {int(row.P1)} pressing · {int(row.P2)} counter · "
               f"{int(row.P3)} wide-build-up situations.")

    st.divider()
    cols = st.columns(len(DIMS))
    for c, d in zip(cols, DIMS):
        r = rank_of(df, d, row[d])
        # delta vs league average in percent: its sign drives the arrow direction
        diff = 100 * (row[d] - df[d].mean()) / df[d].mean()
        c.metric(LABEL[d], f"Rank {r}/{len(df)}", f"{diff:+.0f}% vs league",
                 delta_color="off", help=METRICS[d][1])

    st.divider()
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Style profile vs. league**")
        fig = plt.figure(figsize=(4.2, 4.2))
        ax = fig.add_subplot(polar=True)
        radar(ax, zrow, team, PL_PURPLE)
        show(fig, width="stretch")
        st.caption("avg = league average, ++ = well above, -- = well below.")

        # nearest neighbours in style space (cosine on z-scored vectors)
        zm = z.to_numpy()
        zn = zm / np.linalg.norm(zm, axis=1, keepdims=True)
        sims = zn @ zn[i]
        closest = [j for j in np.argsort(-sims) if j != i][:2]
        st.markdown("**Plays most like**")
        sim_cols = st.columns(2)
        for c, j in zip(sim_cols, closest):
            other_row = df.iloc[j]
            with c:
                s1, s2 = st.columns([1, 3])
                p = crest_path(int(other_row.team_id))
                if p:
                    s1.image(p, width=34)
                s2.markdown(f"{other_row.team}  \n"
                            f"<span style='color:#888; font-size:0.85rem;'>"
                            f"{sims[j]:.0%} style match</span>",
                            unsafe_allow_html=True)
    with right:
        st.markdown("**Where on the pitch?**")
        choice = st.radio("Pattern", list(PATTERN_INTRO), horizontal=True)
        fig, cap = pattern_map(choice, team)
        show(fig, width="stretch")
        with st.expander("How to read this map"):
            st.write(cap + " Attacking direction: left to right.")

    sig = fetch(SIGNATURE_COUNTER, team=team)
    if len(sig):
        b = sig.iloc[0]
        st.divider()
        st.markdown("**Signature counter-attack** — the fastest counter goal "
                    "of the season")
        sfig = signature_counter_fig(team, int(b.mid), int(b.shot_idx))
        if sfig is not None:
            s1, s2 = st.columns([2, 1], vertical_alignment="center")
            with s1:
                show(sfig, width="stretch")
            with s2:
                scorer = b.scorer if pd.notna(b.scorer) else "Unknown scorer"
                st.markdown(f"### {scorer}")
                st.markdown(f"vs **{b.opponent}** · matchweek {int(b.week)} · "
                            f"minute {int(b.minute)}")
                m1, m2 = st.columns(2)
                m1.metric("Recovery to goal", f"{b.dur:.1f}s")
                if pd.notna(b.xg):
                    m2.metric("Shot quality (xG)", f"{b.xg:.2f}")
                st.caption("The actual ball path, reconstructed by walking this "
                           "possession's event chain in the knowledge graph — "
                           "green dot: ball won, gold star: goal.")


# --- COMPARE -----------------------------------------------------------------
with tab_cmp:
    c1, c2 = st.columns(2)
    a = c1.selectbox("Team A", teams, index=0, key="a")
    b = c2.selectbox("Team B", teams, index=1, key="b")
    ia, ib = df.index[df.team == a][0], df.index[df.team == b][0]

    col_a, col_b = st.columns(2)
    for col, team_x, idx in [(col_a, a, ia), (col_b, b, ib)]:
        with col:
            team_header(df, team_x, level="###")
            fl = finish_line(df.iloc[idx])
            if fl:
                st.caption(fl)
            head, bullets = verdict(team_x, df.iloc[idx], z.iloc[idx], df)
            st.markdown(head)
            for bl in bullets:
                st.markdown(f"- {bl}")

    st.divider()
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Style profiles overlaid**")
        fig = plt.figure(figsize=(4.6, 4.6))
        ax = fig.add_subplot(polar=True)
        radar(ax, z.iloc[ia], a, PL_PURPLE)
        radar(ax, z.iloc[ib], b, PL_PINK)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)
        show(fig, width="stretch")
    with right:
        st.markdown("**Metrics side by side**")
        data = {}
        if HAS_TABLE:
            data["Final position"] = [ordinal(int(df.iloc[ia]["position"])),
                                      ordinal(int(df.iloc[ib]["position"]))]
            data["Points"] = [int(df.iloc[ia]["points"]), int(df.iloc[ib]["points"])]
        for d in DIMS:
            data[f"{LABEL[d]} (rank)"] = [f"{rank_of(df, d, df.iloc[ia][d])}.",
                                          f"{rank_of(df, d, df.iloc[ib][d])}."]
        cmp = pd.DataFrame(data, index=[a, b]).T
        cmp.columns = [a, b]
        st.table(cmp)
        st.caption("Final league position, points, and league rank per style metric "
                   "(1 = highest value in the league).")

    st.divider()
    pattern = st.radio("Pitch map", list(PATTERN_INTRO), horizontal=True, key="cmpp")
    st.markdown(f"*{PATTERN_INTRO[pattern]}*")
    m1, m2 = st.columns(2)
    cap = None
    for col, team_x in [(m1, a), (m2, b)]:
        with col:
            st.markdown(f"**{team_x}**")
            fig, cap = pattern_map(pattern, team_x)
            show(fig, width="stretch")
    if cap:
        with st.expander("How to read these maps"):
            st.write(cap + " Attacking direction: left to right.")

st.divider()
st.caption("Data: StatsBomb Open Data (github.com/statsbomb/open-data). Patterns "
           "P1–P3 materialized as PatternInstance nodes in the Neo4j graph. Club "
           "crests are trademarks of their respective clubs.")
