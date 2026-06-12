"""Train TransE/ComplEx on the exported triples and evaluate link prediction
(LO1); compare embedding-space team neighbours with the symbolic Phase-4 style
clusters (LO12) and read the held-out evaluation as KG completion (LO8).

Runs in the dedicated embeddings venv (.venv-emb, see requirements-embeddings.txt)
and deliberately has no Neo4j dependency — input is generated/embeddings/triples.tsv
from export_triples.py.

Usage:  .venv-emb/Scripts/python -m src.embeddings.train
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster import hierarchy

REPO_ROOT = Path(__file__).resolve().parents[2]
TRIPLES = REPO_ROOT / "generated" / "embeddings" / "triples.tsv"
METRICS = REPO_ROOT / "generated" / "style" / "metrics.csv"
OUT_DIR = REPO_ROOT / "generated" / "embeddings"

STYLE_DIMS = ["pressing", "directness", "wide", "possession_share", "avg_poss_len"]
SEED = 42
N_CLUSTERS = 4


def train(model_name, training, validation, testing):
    from pykeen.pipeline import pipeline

    res = pipeline(
        model=model_name,
        training=training, validation=validation, testing=testing,
        model_kwargs=dict(embedding_dim=64),
        training_kwargs=dict(num_epochs=150, batch_size=256),
        optimizer_kwargs=dict(lr=0.01),
        random_seed=SEED, device="cpu",
    )
    metrics = {m: res.metric_results.get_metric(m)
               for m in ("mrr", "hits@1", "hits@3", "hits@10")}
    return res, metrics


def team_neighbours(res, tf, teams):
    """Cosine nearest neighbours among team entities (TransE vectors)."""
    emb = res.model.entity_representations[0](indices=None).detach().cpu().numpy()
    if np.iscomplexobj(emb):
        emb = np.concatenate([emb.real, emb.imag], axis=1)
    idx = [tf.entity_to_id[t] for t in teams]
    vecs = emb[idx]
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    sim = vecs @ vecs.T
    np.fill_diagonal(sim, -np.inf)
    return {teams[i]: [teams[j] for j in np.argsort(-sim[i])[:3]]
            for i in range(len(teams))}


def style_clusters():
    df = pd.read_csv(METRICS).sort_values("team").reset_index(drop=True)
    z = (df[STYLE_DIMS] - df[STYLE_DIMS].mean()) / df[STYLE_DIMS].std()
    labels = hierarchy.fcluster(hierarchy.linkage(z, method="ward"),
                                N_CLUSTERS, criterion="maxclust")
    return dict(zip(df["team"], labels))


def main():
    from pykeen.triples import TriplesFactory

    tf = TriplesFactory.from_path(str(TRIPLES))
    training, testing, validation = tf.split([0.8, 0.1, 0.1], random_state=SEED)
    print(f"{tf.num_triples} triples, {tf.num_entities} entities, "
          f"{tf.num_relations} relations")

    clusters = style_clusters()
    teams = [t for t in clusters if t in tf.entity_to_id]
    all_metrics = {}

    for model_name in ("TransE", "ComplEx"):
        print(f"\n=== {model_name} ===")
        res, metrics = train(model_name, training, validation, testing)
        all_metrics[model_name] = metrics
        print("  " + "  ".join(f"{k}={v:.3f}" for k, v in metrics.items()))

        nn = team_neighbours(res, tf, teams)
        agree = sum(clusters[t] == clusters[nn[t][0]] for t in teams)
        print(f"  nearest team neighbour in same style cluster: "
              f"{agree}/{len(teams)}")

        lines = [f"{t} (cluster {clusters[t]}): "
                 + ", ".join(f"{n} (c{clusters[n]})" for n in nn[t])
                 for t in teams]
        (OUT_DIR / f"team_neighbours_{model_name.lower()}.txt").write_text(
            "\n".join(lines), encoding="utf-8")
        res.metric_results.to_df().to_csv(
            OUT_DIR / f"metrics_{model_name.lower()}.csv", index=False)

    (OUT_DIR / "summary.json").write_text(
        json.dumps(all_metrics, indent=2), encoding="utf-8")
    print(f"\n-> {OUT_DIR}")


if __name__ == "__main__":
    main()
