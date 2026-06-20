from mcm_agent.tui.runner import run_with_spinner


def test_run_with_spinner_returns_result() -> None:
    assert run_with_spinner(lambda: 6 * 7, "Computing") == 42


def test_run_with_spinner_propagates_exception() -> None:
    import pytest

    with pytest.raises(ValueError):
        run_with_spinner(lambda: (_ for _ in ()).throw(ValueError("boom")), "X")


def test_run_with_spinner_cancel_raises_interrupted() -> None:
    import time

    import pytest

    from mcm_agent.tui.runner import Interrupted, run_with_spinner

    with pytest.raises(Interrupted):
        run_with_spinner(lambda: time.sleep(1) or 1, "X", cancel_check=lambda: True)
