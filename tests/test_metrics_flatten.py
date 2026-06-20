from mcm_agent.core.metrics_flatten import flatten_metrics


def test_flatten_nested_per_subproblem() -> None:
    metrics = {
        "problem1": {"elimination_consistency_rate": 0.85, "auc": 0.75},
        "problem2": {"spearman_rho": 0.11},
        "n": 421,
    }
    flat = flatten_metrics(metrics)
    assert flat["problem1_elimination_consistency_rate"] == 0.85
    assert flat["problem1_auc"] == 0.75
    assert flat["problem2_spearman_rho"] == 0.11
    assert flat["n"] == 421


def test_flatten_skips_list_values() -> None:
    flat = flatten_metrics({"p_values": [0.1, 0.2], "marginal_r2": 0.28})
    assert flat == {"marginal_r2": 0.28}


def test_flatten_passthrough_flat() -> None:
    assert flatten_metrics({"a": 1, "b": 2.0, "c": "x"}) == {"a": 1, "b": 2.0, "c": "x"}


def test_flatten_non_dict() -> None:
    assert flatten_metrics([1, 2, 3]) == {}
