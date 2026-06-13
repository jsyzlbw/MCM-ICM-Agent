from __future__ import annotations

from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.utils.json_io import read_json


SECTION_CONTENT = {
    "abstract.tex": "\\section*{Abstract}\nThis paper presents an evidence-backed modeling workflow.\n",
    "introduction.tex": "\\section{Introduction}\nWe analyze the problem using structured decomposition and reproducible experiments.\n",
    "assumptions.tex": "\\section{Assumptions}\nRegistered evidence and validated code outputs define the factual basis of the paper.\n",
    "model.tex": "\\section{Model}\nThe selected model route balances interpretability, feasibility, and paper clarity.\n",
    "results.tex": "\\section{Results}\nValidated evidence items support the numerical claims in this section.\n",
    "sensitivity.tex": "\\section{Sensitivity Analysis}\nRobustness is checked with baseline sensitivity analysis.\n",
    "conclusion.tex": "\\section{Conclusion}\nThe workflow produces traceable and reviewable contest submission artifacts.\n",
}


class PaperWriterAgent:
    def run(self, workspace_root: Path) -> None:
        paper_dir = workspace_root / "paper"
        section_dir = paper_dir / "sections"
        section_dir.mkdir(parents=True, exist_ok=True)

        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
        unresolved_path = workspace_root / "unresolved_issues.md"
        if not evidence:
            unresolved_path.write_text(
                unresolved_path.read_text(encoding="utf-8")
                + "[[UNRESOLVED:\n"
                + 'reason = "No verified evidence available for paper writing"\n'
                + 'needed_input = "Run SolverCoderAgent and ValidationAgent"\n'
                + 'affected_section = "paper/sections/results.tex"\n'
                + "]]\n",
                encoding="utf-8",
            )

        for filename, content in SECTION_CONTENT.items():
            (section_dir / filename).write_text(content, encoding="utf-8")

        (paper_dir / "references.bib").write_text(
            "@misc{registered_sources,\n  title={Registered data sources},\n  year={2026}\n}\n",
            encoding="utf-8",
        )
        (paper_dir / "main.tex").write_text(
            "\n".join(
                [
                    "\\documentclass[12pt]{article}",
                    "\\usepackage{graphicx}",
                    "\\usepackage{amsmath}",
                    "\\usepackage{booktabs}",
                    "\\begin{document}",
                    "\\input{sections/abstract}",
                    "\\input{sections/introduction}",
                    "\\input{sections/assumptions}",
                    "\\input{sections/model}",
                    "\\input{sections/results}",
                    "\\input{sections/sensitivity}",
                    "\\input{sections/conclusion}",
                    "\\bibliographystyle{plain}",
                    "\\bibliography{references}",
                    "\\end{document}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        Coordinator(workspace_root).emit(
            "paper.draft.ready",
            payload={"artifact_ids": ["paper_draft_v1"]},
            source="PaperWriterAgent",
        )
