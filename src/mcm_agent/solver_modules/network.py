from __future__ import annotations

import heapq
from collections import defaultdict

import pandas as pd


def shortest_path_table(
    edges: pd.DataFrame,
    *,
    source: str,
    target: str,
    source_column: str = "source",
    target_column: str = "target",
    cost_column: str = "cost",
) -> pd.DataFrame:
    for column in [source_column, target_column, cost_column]:
        if column not in edges.columns:
            raise ValueError(f"missing edge column: {column}")
    graph: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in edges.itertuples(index=False):
        row_dict = row._asdict()
        start = str(row_dict[source_column])
        end = str(row_dict[target_column])
        cost = float(row_dict[cost_column])
        graph[start].append((end, cost))

    path, cost = _dijkstra(graph, source, target)
    return pd.DataFrame(
        [
            {
                "source": source,
                "target": target,
                "path": " -> ".join(path),
                "path_cost": cost,
                "edge_count": max(len(path) - 1, 0),
            }
        ]
    )


def _dijkstra(
    graph: dict[str, list[tuple[str, float]]],
    source: str,
    target: str,
) -> tuple[list[str], float]:
    queue: list[tuple[float, str, list[str]]] = [(0.0, source, [source])]
    visited: set[str] = set()
    while queue:
        cost, node, path = heapq.heappop(queue)
        if node == target:
            return path, cost
        if node in visited:
            continue
        visited.add(node)
        for next_node, edge_cost in graph.get(node, []):
            if next_node not in visited:
                heapq.heappush(queue, (cost + edge_cost, next_node, [*path, next_node]))
    return [source], float("inf")
