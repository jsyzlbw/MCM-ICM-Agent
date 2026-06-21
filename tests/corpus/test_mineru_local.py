from pathlib import Path

from mcm_agent.providers.mineru import LocalMinerUProvider


def test_collect_locates_nested_markdown(tmp_path: Path):
    out = tmp_path / "out"
    auto = out / "mypaper" / "auto"
    auto.mkdir(parents=True)
    (auto / "mypaper.md").write_text("# Real Markdown\n\nbody", encoding="utf-8")
    (auto / "mypaper_content_list.json").write_text("[]", encoding="utf-8")
    parsed = LocalMinerUProvider()._collect_local_outputs(out, out)
    assert Path(parsed.markdown_path).read_text(encoding="utf-8").startswith("# Real Markdown")
    assert parsed.json_path.endswith(".json")


def test_backend_flag_in_command(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        auto = Path(kwargs["cwd"]) / "doc" / "auto"
        auto.mkdir(parents=True, exist_ok=True)
        (auto / "doc.md").write_text("# X", encoding="utf-8")

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("mcm_agent.providers.mineru.subprocess.run", fake_run)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    parsed = LocalMinerUProvider(backend="vlm-mlx-engine").parse_document(pdf, tmp_path / "out")
    assert "-b" in captured["cmd"] and "vlm-mlx-engine" in captured["cmd"]
    assert Path(parsed.markdown_path).read_text(encoding="utf-8") == "# X"
