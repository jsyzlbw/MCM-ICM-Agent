from pathlib import Path

from typer.testing import CliRunner

from mcm_agent.cli import app


def _seed_corpus(root: Path):
    d = root / "outstanding_papers" / "demo" / "2024" / "C"
    d.mkdir(parents=True)
    (d / "2400996.md").write_text("# Summary\n\nA data model.\n", encoding="utf-8")
    (d / "2400996.pdf").write_text("# Summary\n\nA data model.\n", encoding="utf-8")


def test_kb_build_and_status(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    _seed_corpus(corpus)
    kb = tmp_path / "kb"
    monkeypatch.setenv("MAG_LLM_PROVIDER", "fake")  # forces Fake embed/rerank/mineru bundle
    runner = CliRunner()
    res = runner.invoke(
        app,
        ["kb", "build", "--corpus", str(corpus), "--kb", str(kb), "--years", "2024", "--problems", "C"],
    )
    assert res.exit_code == 0, res.output
    assert (kb / "chroma").exists()

    res2 = runner.invoke(app, ["kb", "status", "--kb", str(kb)])
    assert res2.exit_code == 0 and "papers" in res2.output.lower()
