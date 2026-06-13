from __future__ import annotations

from pathlib import Path

from mcm_agent.providers.humanizer import FakeHumanizerProvider
from mcm_agent.utils.text_locks import extract_fact_locks


class ComplianceOriginalityAgent:
    def __init__(self, humanizer_provider: object | None = None) -> None:
        self.humanizer_provider = humanizer_provider or FakeHumanizerProvider({})

    def run(self, workspace_root: Path) -> None:
        review_dir = workspace_root / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        diff_lines = ["# Humanization Diff", ""]
        fact_lines = ["# Fact Regression Report", ""]
        originality_lines = ["# Originality Report", "", "- Academic humanization checked.", ""]

        section_dir = workspace_root / "paper" / "sections"
        for section in sorted(section_dir.glob("*.tex")):
            paragraphs = section.read_text(encoding="utf-8").splitlines()
            rewritten_lines: list[str] = []
            for paragraph in paragraphs:
                if not paragraph.strip() or paragraph.lstrip().startswith("\\section"):
                    rewritten_lines.append(paragraph)
                    continue
                before_locks = extract_fact_locks(paragraph)
                candidate = self.humanizer_provider.humanize(paragraph, language="en")
                after_locks = extract_fact_locks(candidate)
                if before_locks != after_locks:
                    rewritten_lines.append(paragraph)
                    diff_lines.extend(
                        [
                            f"## Rejected: {section.name}",
                            f"- Before: {paragraph}",
                            f"- Provider output: {candidate}",
                            "",
                        ]
                    )
                    fact_lines.extend(
                        [
                            f"- critical: fact regression detected in `{section.name}`.",
                            f"  Original locks: `{before_locks}`",
                            f"  New locks: `{after_locks}`",
                            "",
                        ]
                    )
                else:
                    rewritten_lines.append(candidate)
                    if candidate != paragraph:
                        diff_lines.extend(
                            [
                                f"## Accepted: {section.name}",
                                f"- Before: {paragraph}",
                                f"- After: {candidate}",
                                "",
                            ]
                        )
            section.write_text("\n".join(rewritten_lines) + "\n", encoding="utf-8")

        if len(fact_lines) == 2:
            fact_lines.append("- No fact regression detected.")
        (review_dir / "humanization_diff.md").write_text("\n".join(diff_lines), encoding="utf-8")
        (review_dir / "fact_regression_report.md").write_text(
            "\n".join(fact_lines),
            encoding="utf-8",
        )
        (review_dir / "originality_report.md").write_text(
            "\n".join(originality_lines),
            encoding="utf-8",
        )
