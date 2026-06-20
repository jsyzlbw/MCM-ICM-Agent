from mcm_agent.tui.runner import run_with_spinner


def test_run_with_spinner_returns_result() -> None:
    assert run_with_spinner(lambda: 6 * 7, "Computing") == 42


def test_run_with_spinner_propagates_exception() -> None:
    import pytest

    with pytest.raises(ValueError):
        run_with_spinner(lambda: (_ for _ in ()).throw(ValueError("boom")), "X")
