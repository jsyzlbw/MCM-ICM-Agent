import io
import contextlib
import traceback
from pathlib import Path

from mcm_agent.tools.code_interpreter import ExecResult, CodeInterpreter


class FakeCodeInterpreter:
    """In-process test double: persistent namespace, real file writes, no kernel."""
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.ns: dict[str, object] = {}
        self.sections: list[str] = []
        self.executed: list[str] = []

    def add_section(self, title: str) -> None:
        self.sections.append(title)

    def execute(self, code: str) -> ExecResult:
        import os
        self.executed.append(code)
        buf = io.StringIO()
        prev = os.getcwd()
        os.chdir(self.workspace_root)
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(code, "<cell>", "exec"), self.ns)  # noqa: S102 (test double)
            return ExecResult(stdout=buf.getvalue(), error="", had_error=False)
        except Exception:
            return ExecResult(stdout=buf.getvalue(), error=traceback.format_exc(), had_error=True)
        finally:
            os.chdir(prev)

    def save_notebook(self) -> None:
        (self.workspace_root / "notebook.ipynb").write_text("{}", encoding="utf-8")

    def shutdown(self) -> None:
        pass


def test_exec_result_fields():
    r = ExecResult(stdout="hi", error="", had_error=False)
    assert r.stdout == "hi" and r.had_error is False and r.images == ()


def test_fake_interpreter_is_stateful_and_writes_files(tmp_path):
    interp = FakeCodeInterpreter(tmp_path)
    interp.add_section("p1")
    interp.execute("x = 41")
    r = interp.execute("print(x + 1)")
    assert "42" in r.stdout and r.had_error is False
    interp.execute("from pathlib import Path; Path('out.txt').write_text('ok')")
    assert (tmp_path / "out.txt").read_text() == "ok"
    err = interp.execute("raise ValueError('boom')")
    assert err.had_error and "boom" in err.error
    # protocol structural check
    assert isinstance(interp, CodeInterpreter)
