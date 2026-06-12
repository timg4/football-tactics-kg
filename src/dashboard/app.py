"""Streamlit dashboard: team-style comparison on the football KG (LO11).

Reads generated/style/metrics.csv (python -m src.dashboard.metrics) and the
pattern instances from Neo4j (docker compose up -d).

Run:  streamlit run src/dashboard/app.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from mplsoccer import Pitch
from scipy.cluster import hierarchy
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity

from src.ingest import common

st.set_page_config(page_title="PL 2015/16 Team Style KG", layout="wide")

STYLE_DIMS = ["pressing", "directness", "wide", "possession_share", "avg_poss_len"]
DIM_LABELS = {
    "pressing": "Pressing intensity\n(P1 / opp. possession)",
    "directness": "Directness\n(P2 / own-half open play)",
    "wide": "Wide orientation\n(P3 / final-third entry)",
    "possession_share": "Possession share",
    "avg_poss_len": "Possession length\n(events)",
}

PITCH_QUERIES = {
    "P1": """
        MATCH (pi:PatternInstance {pattern:'P1'})-[:EXHIBITED_BY]->(:Team {name:$team})
        MATCH (pi)-[:MATCHES]->(p:Pressure)
        RETURN p.x AS x, p.y AS y
    """,
    "P2": """
        MATCH (pi:PatternInstance {pattern:'P2'})-[:EXHIBITED_BY]->(:Team {name:$team})
        MATCH (pi)-[:MATCHES]->(e:Event)
        WITH pi, e ORDER BY e.idx
        WITH pi, collect(e) AS es
        RETURN es[0].x AS x1, es[0].y AS y1,
               es[-1].x AS x2, es[-1].y AS y2, es[-1].xg AS xg
    """,
    "P3": """
        MATCH (pi:PatternInstance {pattern:'P3'})-[:EXHIBITED_BY]->(:Team {name:$team})
        MATCH (pi)-[:MATCHES]->(e:Event)-[:IN_ZONE]->(:Zone {third:'final'})
        RETURN e.x AS x, e.y AS y
    """,
}


@st.cache_data
def load_metrics():
    path = REPO_ROOT / "generated" / "style" / "metrics.csv"
    if not path.exists():
        st.error("metrics.csv missing — run `python -m src.dashboard.metrics` first")
        st.stop()
    df = pd.read_csv(path).sort_values("team").reset_index(drop=True)
    z = (df[STYLE_DIMS] - df[STYLE_DIMS].mean()) / df[STYLE_DIMS].std()
    return df, z


@st.cache_data
def fetch(query, **params):
    driver = common.get_driver()
    with driver.session() as s:
        rows = [dict(r) for r in s.run(query, **params)]
    driver.close()
    return pd.DataFrame(rows)


def radar(ax, zrow, label, color):
    angles = np.linspace(0, 2 * np.pi, len(STYLE_DIMS), endpoint=False)
    values = np.clip(zrow.to_numpy(), -2.5, 2.5)
    angles = np.concatenate([angles, angles[:1]])
    values = np.concatenate([values, values[:1]])
    ax.plot(angles, values, color=color, label=label)
    ax.fill(angles, values, color=color, alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([DIM_LABELS[d].split("\n")[0] for d in STYLE_DIMS],
                       fontsize=8)
    ax.set_ylim(-2.5, 2.5)
    ax.set_yticks([-2, -1, 0, 1, 2])
    ax.set_yticklabels([])


def pitch_figure(team, pattern):
    pitch = Pitch(pitch_type="statsbomb", line_color="#777", line_zorder=2)
    fig, ax = pitch.draw(figsize=(6, 4))
    if pattern == "P1":
        d = fetch(PITCH_QUERIES["P1"], team=team)
        if len(d):
            pitch.kdeplot(d.x, d.y, ax=ax, fill=True, cmap="Reds", levels=50, alpha=0.8)
            ax.set_title(f"P1 pressing regains — pressure locations ({len(d)})", fontsize=9)
    elif pattern == "P2":
        d = fetch(PITCH_QUERIES["P2"], team=team).dropna(subset=["x1", "x2"])
        if len(d):
            pitch.arrows(d.x1, d.y1, d.x2, d.y2, ax=ax, width=1.2,
                         headwidth=6, color="#1f77b4", alpha=0.5)
            ax.set_title(f"P2 fast transitions — start → shot ({len(d)})", fontsize=9)
    else:
        d = fetch(PITCH_QUERIES["P3"], team=team)
        if len(d):
            pitch.scatter(d.x, d.y, ax=ax, s=18, color="#2ca02c", alpha=0.4)
            ax.set_title(f"P3 wide build-ups — final-third entries ({len(d)})", fontsize=9)
    return fig


df, z = load_metrics()
teams = df["team"].tolist()

st.title("A Temporal Football KG — Team Style, PL 2015/16")
st.caption("Tactical patterns mined from the knowledge graph as Cypher/Datalog rules; "
           "data: StatsBomb Open Data.")

tab_league, tab_team, tab_compare = st.tabs(
    ["League overview", "Team profile", "Compare teams"])

with tab_league:
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Style metrics (per team, season totals normalized)")
        show = df[["team"] + STYLE_DIMS].set_index("team")
        st.dataframe(show.style.background_gradient(cmap="RdYlGn", axis=0)
                     .format("{:.3f}"), height=740)
    with right:
        st.subheader("Style map (PCA of z-scored style vectors)")
        pca = PCA(n_components=2)
        xy = pca.fit_transform(z)
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter(xy[:, 0], xy[:, 1], s=30, color="#1f77b4")
        for i, t in enumerate(teams):
            ax.annotate(t, (xy[i, 0], xy[i, 1]), fontsize=7,
                        xytext=(4, 2), textcoords="offset points")
        ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.0%})")
        ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.0%})")
        ax.spines[["top", "right"]].set_visible(False)
        st.pyplot(fig, use_container_width=True)

        st.subheader("Style clusters (Ward)")
        link = hierarchy.linkage(z, method="ward")
        fig, ax = plt.subplots(figsize=(6, 4))
        hierarchy.dendrogram(link, labels=teams, orientation="right",
                             leaf_font_size=8, ax=ax)
        ax.spines[["top", "right", "bottom"]].set_visible(False)
        st.pyplot(fig, use_container_width=True)

    st.subheader("Team similarity (cosine, z-scored style vectors)")
    order = hierarchy.leaves_list(hierarchy.linkage(z, method="ward"))
    sim = cosine_similarity(z.iloc[order])
    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(sim, cmap="RdBu_r", vmin=-1, vmax=1)
    labels = [teams[i] for i in order]
    ax.set_xticks(range(len(labels)), labels, rotation=90, fontsize=7)
    ax.set_yticks(range(len(labels)), labels, fontsize=7)
    fig.colorbar(im, shrink=0.8)
    st.pyplot(fig, use_container_width=False)

with tab_team:
    team = st.selectbox("Team", teams, key="profile_team")
    row = df[df.team == team].iloc[0]
    zrow = z.iloc[df.index[df.team == team][0]]

    cols = st.columns(5)
    for c, dim in zip(cols, STYLE_DIMS):
        rank = int((df[dim] > row[dim]).sum()) + 1
        c.metric(DIM_LABELS[dim].split("\n")[0], f"{row[dim]:.3f}",
                 f"rank {rank}/20", delta_color="off")

    left, right = st.columns([1, 2])
    with left:
        fig = plt.figure(figsize=(4, 4))
        ax = fig.add_subplot(polar=True)
        radar(ax, zrow, team, "#1f77b4")
        ax.set_title(f"{team} vs league (z-scores)", fontsize=9)
        st.pyplot(fig, use_container_width=True)
        st.caption(f"Season: {int(row.P1)} P1 / {int(row.P2)} P2 / {int(row.P3)} P3 "
                   f"pattern instances.")
    with right:
        pattern = st.radio("Pattern map", ["P1", "P2", "P3"], horizontal=True)
        st.pyplot(pitch_figure(team, pattern), use_container_width=True)
        st.caption("Attacking direction: left → right (StatsBomb coordinates).")

with tab_compare:
    c1, c2 = st.columns(2)
    a = c1.selectbox("Team A", teams, index=0, key="cmp_a")
    b = c2.selectbox("Team B", teams, index=1, key="cmp_b")
    za = z.iloc[df.index[df.team == a][0]]
    zb = z.iloc[df.index[df.team == b][0]]

    fig = plt.figure(figsize=(5, 5))
    ax = fig.add_subplot(polar=True)
    radar(ax, za, a, "#1f77b4")
    radar(ax, zb, b, "#d62728")
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), fontsize=8)
    st.pyplot(fig, use_container_width=False)

    pattern = st.radio("Pattern map", ["P1", "P2", "P3"], horizontal=True,
                       key="cmp_pattern")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{a}**")
        st.pyplot(pitch_figure(a, pattern), use_container_width=True)
    with c2:
        st.markdown(f"**{b}**")
        st.pyplot(pitch_figure(b, pattern), use_container_width=True)

st.divider()
st.caption("Data: StatsBomb Open Data (https://github.com/statsbomb/open-data). "
           "KG: Neo4j; patterns P1–P3 materialized as PatternInstance nodes.")
