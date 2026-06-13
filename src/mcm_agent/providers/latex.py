from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel


class LatexCompileResult(BaseModel):
    success: bool
    pdf_path: str | None = None
    log_path: str
    reason: str = ""


class LatexProvider:
    def __init__(self, command: str = "latexmk") -> None:
        self.command = command

    def compile(self, paper_dir: Path) -> LatexCompileResult:
        log_path = paper_dir / "compile_log.txt"
        if shutil.which(self.command) is None:
            log_path.write_text("latexmk not installed\n", encoding="utf-8")
            return LatexCompileResult(
                success=False,
                log_path=str(log_path),
                reason="latexmk not installed",
            )

        result = subprocess.run(
            [self.command, "-pdf", "-interaction=nonstopmode", "main.tex"],
            cwd=paper_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        pdf_path = paper_dir / "main.pdf"
        return LatexCompileResult(
            success=result.returncode == 0 and pdf_path.exists(),
            pdf_path=str(pdf_path) if pdf_path.exists() else None,
            log_path=str(log_path),
            reason="" if result.returncode == 0 else f"latexmk failed: {result.returncode}",
        )
