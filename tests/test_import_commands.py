from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace, load_workspace_state


def test_question_import_copies_problem_and_updates_state(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    source = tmp_path / "problem.pdf"
    source.write_text("problem", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    result = session.run_once(f"/question {source}")

    state = load_workspace_state(workspace.root)
    assert "Imported problem" in result.message
    assert (workspace.root / "input/problem/problem.pdf").exists()
    assert state.init.problem_imported is True
    assert state.problem == "input/problem/problem.pdf"


def test_data_import_supports_directory(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    source_dir = tmp_path / "data_dir"
    source_dir.mkdir()
    (source_dir / "data.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    result = session.run_once(f"/data {source_dir}")

    state = load_workspace_state(workspace.root)
    assert "Imported data" in result.message
    assert (workspace.root / "input/data/data_dir/data.csv").exists()
    assert state.init.data_files == 1


def test_layout_import_copies_template(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    source = tmp_path / "template.tex"
    source.write_text("\\documentclass{article}", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    session.run_once(f"/layout {source}")

    state = load_workspace_state(workspace.root)
    assert (workspace.root / "input/layout/template.tex").exists()
    assert state.init.layout_imported is True


def test_rag_import_records_category(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    source = tmp_path / "paper.md"
    source.write_text("# paper", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    result = session.run_once(f"/rag papers {source}")

    state = load_workspace_state(workspace.root)
    assert "Imported rag/papers" in result.message
    assert (workspace.root / "knowledge/papers/paper.md").exists()
    assert state.init.rag_documents == 1
    assert state.resources[-1].metadata["category"] == "papers"
    assert (workspace.root / ".mag/rag_index.jsonl").exists()


def test_import_avoids_overwriting_existing_file(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    source = tmp_path / "problem.md"
    source.write_text("first", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    session.run_once(f"/question {source}")
    source.write_text("second", encoding="utf-8")
    session.run_once(f"/question {source}")

    imported = list((workspace.root / "input/problem").glob("problem*.md"))
    assert len(imported) == 2


def test_import_creates_git_checkpoint(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    source = tmp_path / "problem.md"
    source.write_text("problem", encoding="utf-8")
    session = InteractiveSession(workspace.root)

    session.run_once(f"/question {source}")

    log = __import__("subprocess").run(
        ["git", "log", "--oneline"],
        cwd=workspace.root,
        check=True,
        text=True,
        stdout=__import__("subprocess").PIPE,
    ).stdout
    assert "mag: import problem" in log
