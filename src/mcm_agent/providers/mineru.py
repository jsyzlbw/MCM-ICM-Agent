from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import httpx
from pydantic import BaseModel, Field


class ParsedDocument(BaseModel):
    markdown_path: str
    json_path: str
    layout_path: str | None = None
    table_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    formula_path: str | None = None
    page_count: int | None = None
    warnings: list[str] = Field(default_factory=list)


class FakeMinerUProvider:
    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        layout_path = output_dir / "problem_layout.json"
        formula_path = output_dir / "formulas.json"

        if input_path.suffix.lower() == ".md":
            markdown = input_path.read_text(encoding="utf-8")
        else:
            markdown = f"# Parsed Problem\n\nFake MinerU output for {input_path.name}.\n"

        markdown_path.write_text(markdown, encoding="utf-8")
        json_path.write_text(
            json.dumps({"source": str(input_path), "markdown_path": str(markdown_path)}, indent=2),
            encoding="utf-8",
        )
        layout_path.write_text(json.dumps({"pages": []}, indent=2), encoding="utf-8")
        formula_path.write_text(json.dumps([], indent=2), encoding="utf-8")

        return ParsedDocument(
            markdown_path=str(markdown_path),
            json_path=str(json_path),
            layout_path=str(layout_path),
            formula_path=str(formula_path),
            page_count=1,
        )


class LocalMinerUProvider:
    def __init__(self, command: str = "mineru") -> None:
        self.command = command

    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "mineru_cli.log"
        result = subprocess.run(
            [self.command, "-p", str(input_path), "-o", str(output_dir)],
            cwd=output_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"MinerU CLI parse failed: {result.returncode}; log={log_path}")

        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        return ParsedDocument(markdown_path=str(markdown_path), json_path=str(json_path))


class RestMinerUProvider:
    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with input_path.open("rb") as handle:
            response = httpx.post(
                f"{self.base_url}/parse",
                headers=headers,
                files={"file": (input_path.name, handle)},
                timeout=120,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"MinerU REST parse failed: {response.status_code}")

        payload = response.json()
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        markdown_path.write_text(str(payload.get("markdown", "")), encoding="utf-8")
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return ParsedDocument(markdown_path=str(markdown_path), json_path=str(json_path))


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
