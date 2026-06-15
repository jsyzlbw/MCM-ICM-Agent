from __future__ import annotations

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


def kmeans_segmentation(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    n_clusters: int = 3,
) -> tuple[pd.DataFrame, dict[str, float]]:
    features = [column for column in feature_columns if column in frame.columns]
    if not features:
        raise ValueError("clustering requires feature columns")
    data = frame[features].fillna(0).astype(float)
    if data.empty:
        raise ValueError("clustering requires non-empty rows")
    cluster_count = max(1, min(int(n_clusters), len(data)))
    scaled = StandardScaler().fit_transform(data)
    if cluster_count == 1:
        labels = [0 for _ in range(len(data))]
        inertia = 0.0
        silhouette = 0.0
        distances = [0.0 for _ in range(len(data))]
    else:
        model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
        labels = model.fit_predict(scaled)
        inertia = float(model.inertia_)
        silhouette = (
            float(silhouette_score(scaled, labels))
            if len(set(labels)) > 1 and len(data) > cluster_count
            else 0.0
        )
        distances = model.transform(scaled).min(axis=1)
    result = frame.copy()
    result["cluster_id"] = labels
    result["cluster_distance"] = distances
    return result, {
        "cluster_count": float(cluster_count),
        "cluster_inertia": float(inertia),
        "cluster_silhouette": float(silhouette),
    }
