from pathlib import Path

from mcm_agent.corpus.manifest import CorpusEntry, build_manifest


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    papers = root / "outstanding_papers" / "demo_repo" / "2024" / "C"
    papers.mkdir(parents=True)
    (papers / "2400996.pdf").write_bytes(b"%PDF-1.4 fake")
    (papers / "2401000.pdf").write_bytes(b"%PDF-1.4 fake2")
    dup = root / "outstanding_papers" / "other_repo" / "2024" / "C"
    dup.mkdir(parents=True)
    (dup / "2400996.pdf").write_bytes(b"%PDF-1.4 fake")  # same control# -> deduped
    return root


def test_build_manifest_extracts_metadata_and_dedups(tmp_path):
    root = _make_corpus(tmp_path)
    entries = build_manifest(root)
    assert all(isinstance(e, CorpusEntry) for e in entries)
    keys = {(e.year, e.control_number) for e in entries}
    assert (2024, "2400996") in keys
    assert (2024, "2401000") in keys
    assert len(entries) == 2  # the duplicate 2400996 collapsed
    one = next(e for e in entries if e.control_number == "2400996")
    assert one.problem == "C" and one.contest == "MCM" and one.problem_type == "data"
    assert one.pdf_path.endswith("2400996.pdf")


def test_repo_dir_year_range_does_not_misdate_papers(tmp_path):
    # Regression: a cloned-repo folder named with a YEAR RANGE must not override
    # the real per-paper year, and an ICM D paper from 2021 must map correctly.
    root = tmp_path / "corpus"
    d = root / "outstanding_papers" / "dick20_2004-2025" / "2021美赛特等奖" / "D"
    d.mkdir(parents=True)
    (d / "2100123.pdf").write_bytes(b"%PDF fake")
    entries = build_manifest(root)
    assert len(entries) == 1
    e = entries[0]
    assert e.year == 2021  # not 2004 or 2025 from the repo dir name
    assert e.problem == "D" and e.contest == "ICM"
    assert e.problem_type == "operations_research"


def test_single_year_repo_dir_used_as_fallback(tmp_path):
    # A flat repo (no year subfolder) named with exactly one year falls back to it.
    root = tmp_path / "corpus"
    d = root / "outstanding_papers" / "catcat-lee_2025_icm_e"
    d.mkdir(parents=True)
    (d / "2508861.pdf").write_bytes(b"%PDF fake")
    entries = build_manifest(root)
    assert len(entries) == 1
    assert entries[0].year == 2025 and entries[0].control_number == "2508861"


def test_mcm_icm_year_letter_folder_and_three_digit_controls(tmp_path):
    root = tmp_path / "corpus"
    base = root / "outstanding_papers" / "dick20_2004-2025"
    # 2019-style folders "ICM2019F" / "MCM2019A"
    (base / "2019美赛特等奖" / "ICM2019F").mkdir(parents=True)
    (base / "2019美赛特等奖" / "ICM2019F" / "1904381.pdf").write_bytes(b"%PDF")
    # 2005-style 3-digit control "B-770-Outstanding.pdf"
    (base / "2005美赛特等奖").mkdir(parents=True)
    (base / "2005美赛特等奖" / "B-770-Outstanding.pdf").write_bytes(b"%PDF")
    # title-named file with no digits
    (base / "2006美赛特等奖").mkdir(parents=True)
    (base / "2006美赛特等奖" / "A-Fastidious Farmer Algorithms.pdf").write_bytes(b"%PDF")
    entries = {e.paper_id: e for e in build_manifest(root)}
    assert entries["2019-1904381"].problem == "F" and entries["2019-1904381"].contest == "ICM"
    assert entries["2005-770"].problem == "B" and entries["2005-770"].control_number == "770"
    fastidious = next(e for e in entries.values() if e.year == 2006)
    assert fastidious.problem == "A"  # letter from filename prefix even without digits


def test_non_outstanding_award_folders_are_skipped(tmp_path):
    root = tmp_path / "corpus"
    base = root / "outstanding_papers" / "dick20_2004-2025" / "2013美赛特等奖"
    (base / "其他奖项").mkdir(parents=True)
    (base / "其他奖项" / "9999.pdf").write_bytes(b"%PDF")  # Meritorious etc -> skipped
    (base / "A").mkdir(parents=True)
    (base / "A" / "21185.pdf").write_bytes(b"%PDF")  # real Outstanding -> kept
    entries = build_manifest(root)
    assert len(entries) == 1 and entries[0].paper_id == "2013-21185"
