from pathlib import Path

from mcm_agent.corpus.convert import ConvertResult, convert_entry
from mcm_agent.providers.mineru import FakeMinerUProvider


def test_convert_writes_markdown_and_is_idempotent(tmp_path: Path):
    pdf = tmp_path / "p.md"  # Fake MinerU echoes .md content through verbatim
    pdf.write_text("# Summary\n\nhello", encoding="utf-8")
    kb = tmp_path / "kb"
    r1 = convert_entry("2024-2400996", pdf, kb, FakeMinerUProvider())
    assert isinstance(r1, ConvertResult) and Path(r1.markdown_path).exists()
    assert r1.converted is True
    mtime1 = Path(r1.markdown_path).stat().st_mtime_ns

    r2 = convert_entry("2024-2400996", pdf, kb, FakeMinerUProvider())
    assert r2.converted is False  # skipped (cache hit)
    assert Path(r2.markdown_path).stat().st_mtime_ns == mtime1
