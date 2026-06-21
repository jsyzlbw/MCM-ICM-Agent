import pytest

jupyter_client = pytest.importorskip("jupyter_client")


def _make_interp(tmp_path, cell_timeout: float = 30.0):
    from mcm_agent.tools.code_interpreter import JupyterCodeInterpreter
    try:
        return JupyterCodeInterpreter(tmp_path, cell_timeout=cell_timeout)
    except Exception as exc:  # no kernel available in this env
        pytest.skip(f"jupyter kernel unavailable: {exc}")


def test_jupyter_state_persists_and_notebook_written(tmp_path):
    interp = _make_interp(tmp_path)
    try:
        interp.add_section("p1")
        interp.execute("a = 20")
        r = interp.execute("print(a * 2 + 2)")
        assert "42" in r.stdout and not r.had_error
        err = interp.execute("1/0")
        assert err.had_error and "ZeroDivisionError" in err.error
        interp.save_notebook()
        assert (tmp_path / "notebook.ipynb").exists()
    finally:
        interp.shutdown()


def test_total_deadline_enforced_for_slow_cell(tmp_path):
    """A cell that sleeps longer than cell_timeout must hit the total deadline."""
    # Use a tight timeout so the test completes quickly (a few seconds overhead).
    interp = _make_interp(tmp_path, cell_timeout=2.0)
    try:
        result = interp.execute("import time; time.sleep(10)")
        assert result.had_error, "expected had_error=True for timed-out cell"
        assert "timeout" in result.error.lower(), (
            f"expected 'timeout' in error message, got: {result.error!r}"
        )
    finally:
        interp.shutdown()
