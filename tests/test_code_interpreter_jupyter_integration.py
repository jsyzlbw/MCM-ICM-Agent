import pytest

jupyter_client = pytest.importorskip("jupyter_client")


def _make_interp(tmp_path):
    from mcm_agent.tools.code_interpreter import JupyterCodeInterpreter
    try:
        return JupyterCodeInterpreter(tmp_path, cell_timeout=30.0)
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
