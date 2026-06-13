from __future__ import annotations

from pathlib import Path


def create_demo_inputs(base_dir: Path) -> tuple[Path, list[Path], Path, Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    problem = base_dir / "problem.md"
    attachment = base_dir / "sample.csv"
    idea = base_dir / "user_idea.md"
    skills = base_dir / "skills" / "figure-designer"
    skills.mkdir(parents=True, exist_ok=True)

    problem.write_text(
        "# Demo Problem\n\nBuild a predictive baseline and recommend a robust policy.",
        encoding="utf-8",
    )
    attachment.write_text("x,y\n1,2\n2,4\n3,6\n", encoding="utf-8")
    idea.write_text("Prefer interpretable models and vector figures.", encoding="utf-8")
    (skills / "SKILL.md").write_text(
        "Figure design requires data source tracking. Pre-submission review checks macro logic.",
        encoding="utf-8",
    )
    return problem, [attachment], idea, base_dir / "skills"
