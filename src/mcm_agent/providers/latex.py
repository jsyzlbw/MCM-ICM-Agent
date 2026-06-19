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
    # Detection priority: tectonic (single binary, auto-fetches fonts/packages,
    # supports XeTeX/CJK) > latexmk > xelatex.
    _ENGINES = ["tectonic", "latexmk", "xelatex"]

    def __init__(self, command: str | None = None) -> None:
        self.command = command  # None = auto-detect

    def _resolve_command(self) -> str | None:
        if self.command is not None:
            return self.command if shutil.which(self.command) else None
        for engine in self._ENGINES:
            if shutil.which(engine):
                return engine
        return None

    def _invocation(self, engine: str) -> list[str]:
        name = Path(engine).name
        if name == "tectonic":
            return [engine, "main.tex"]
        if name == "latexmk":
            return [engine, "-pdf", "-interaction=nonstopmode", "main.tex"]
        return [engine, "-interaction=nonstopmode", "main.tex"]

    def compile(self, paper_dir: Path) -> LatexCompileResult:
        log_path = paper_dir / "compile_log.txt"
        engine = self._resolve_command()
        if engine is None:
            if self.command is not None:
                reason = f"{self.command} not available"
            else:
                reason = "no latex engine available (install tectonic or latexmk)"
            log_path.write_text(reason + "\n", encoding="utf-8")
            return LatexCompileResult(success=False, log_path=str(log_path), reason=reason)

        result = subprocess.run(
            self._invocation(engine),
            cwd=paper_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        pdf_path = paper_dir / "main.pdf"
        succeeded = result.returncode == 0 and pdf_path.exists()
        return LatexCompileResult(
            success=succeeded,
            pdf_path=str(pdf_path) if pdf_path.exists() else None,
            log_path=str(log_path),
            reason="" if succeeded else f"{Path(engine).name} failed: {result.returncode}",
        )
