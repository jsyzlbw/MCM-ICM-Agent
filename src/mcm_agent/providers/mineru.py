from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from zipfile import ZipFile

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
    def __init__(self, command: str = "mineru", backend: str = "pipeline") -> None:
        self.command = command
        self.backend = backend

    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "mineru_cli.log"
        cmd = [self.command, "-p", str(input_path), "-o", str(output_dir), "-b", self.backend]
        result = subprocess.run(cmd, cwd=output_dir, capture_output=True, text=True, check=False)
        log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"MinerU CLI parse failed: {result.returncode}; log={log_path}")
        return self._collect_local_outputs(output_dir, output_dir)

    def _collect_local_outputs(self, result_root: Path, output_dir: Path) -> ParsedDocument:
        # Real MinerU writes a nested tree: <out>/<stem>/auto/<stem>.md (+ *_content_list.json,
        # images/). Locate those rather than assuming a flat "problem.md".
        md = self._find_first(result_root, ("*.md",))
        content = self._find_first(result_root, ("*_content_list.json", "*.json"))
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        if md:
            shutil.copy2(md, markdown_path)
        else:
            markdown_path.write_text("", encoding="utf-8")
        if content:
            shutil.copy2(content, json_path)
        else:
            json_path.write_text("{}", encoding="utf-8")
        images = [
            str(p)
            for p in (*sorted(result_root.rglob("*.jpg")), *sorted(result_root.rglob("*.png")))
        ]
        return ParsedDocument(
            markdown_path=str(markdown_path),
            json_path=str(json_path),
            image_paths=images,
        )

    @staticmethod
    def _find_first(root: Path, patterns: tuple[str, ...]) -> Path | None:
        for pattern in patterns:
            matches = sorted(p for p in root.rglob(pattern) if p.name not in {"problem.md"})
            if matches:
                return matches[0]
        return None


class RestMinerUProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        *,
        model_version: str = "vlm",
        language: str = "en",
        poll_interval_seconds: float = 3,
        poll_timeout_seconds: float = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_version = model_version
        self.language = language
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds

    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        result_dir = output_dir / "mineru_result"
        result_dir.mkdir(parents=True, exist_ok=True)

        batch_id, upload_url = self._create_upload_batch(input_path)
        self._upload_file(upload_url, input_path)
        zip_url = self._wait_for_full_zip(batch_id, input_path.name)
        archive_path = self._download_zip(zip_url, output_dir / "mineru_result.zip")
        self._extract_zip(archive_path, result_dir)

        full_markdown = self._find_first(result_dir, ("full.md",), "*.md")
        content_json = self._find_first(result_dir, ("*_content_list.json",), "*.json")
        layout_json = self._find_first(result_dir, ("middle.json", "*layout*.json"), "*.json")

        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        layout_path = output_dir / "problem_layout.json"
        formula_path = output_dir / "formulas.json"

        if full_markdown:
            shutil.copy2(full_markdown, markdown_path)
        else:
            markdown_path.write_text("", encoding="utf-8")

        if content_json:
            shutil.copy2(content_json, json_path)
        else:
            json_path.write_text(json.dumps({"source": str(input_path)}, indent=2), encoding="utf-8")

        parsed_layout_path: Path | None = None
        if layout_json:
            shutil.copy2(layout_json, layout_path)
            parsed_layout_path = layout_path

        formula_path.write_text("[]", encoding="utf-8")
        return ParsedDocument(
            markdown_path=str(markdown_path),
            json_path=str(json_path),
            layout_path=str(parsed_layout_path) if parsed_layout_path else None,
            formula_path=str(formula_path),
        )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _create_upload_batch(self, input_path: Path) -> tuple[str, str]:
        payload = {
            "files": [{"name": input_path.name, "data_id": input_path.stem}],
            "model_version": self.model_version,
            "enable_formula": True,
            "enable_table": True,
            "language": self.language,
        }
        response = httpx.post(
            f"{self.base_url}/api/v4/file-urls/batch",
            headers=self._headers(),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = self._extract_success_payload(response.json(), "create upload batch")
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls") or []
        if not batch_id or not file_urls:
            raise RuntimeError("MinerU create upload batch response missing batch_id or file_urls")
        return str(batch_id), str(file_urls[0])

    def _upload_file(self, upload_url: str, input_path: Path) -> None:
        response = httpx.put(upload_url, content=input_path.read_bytes(), timeout=120)
        response.raise_for_status()

    def _wait_for_full_zip(self, batch_id: str, file_name: str) -> str:
        deadline = time.monotonic() + self.poll_timeout_seconds
        last_state = "unknown"
        while time.monotonic() <= deadline:
            response = httpx.get(
                f"{self.base_url}/api/v4/extract-results/batch/{batch_id}",
                headers=self._headers(),
                timeout=60,
            )
            response.raise_for_status()
            data = self._extract_success_payload(response.json(), "poll batch result")
            for item in data.get("extract_result") or []:
                if item.get("file_name") not in {None, file_name}:
                    continue
                state = str(item.get("state", "")).lower()
                last_state = state or last_state
                if state == "done":
                    zip_url = item.get("full_zip_url")
                    if not zip_url:
                        raise RuntimeError("MinerU result is done but full_zip_url is missing")
                    return str(zip_url)
                if state in {"failed", "error"}:
                    detail = item.get("err_msg") or item.get("message") or item
                    raise RuntimeError(f"MinerU parse failed: {detail}")
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError(f"MinerU parse timed out: batch_id={batch_id}, last_state={last_state}")

    def _download_zip(self, zip_url: str, archive_path: Path) -> Path:
        response = httpx.get(zip_url, timeout=120)
        response.raise_for_status()
        archive_path.write_bytes(response.content)
        return archive_path

    @staticmethod
    def _extract_success_payload(payload: dict[str, object], operation: str) -> dict[str, object]:
        if payload.get("code") not in {0, "0", None}:
            raise RuntimeError(f"MinerU {operation} failed: {payload.get('msg') or payload}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"MinerU {operation} response missing data")
        return data

    @staticmethod
    def _extract_zip(archive_path: Path, output_dir: Path) -> None:
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = output_dir / member.filename
                if not target.resolve().is_relative_to(output_dir.resolve()):
                    raise RuntimeError(f"Unsafe path in MinerU archive: {member.filename}")
            archive.extractall(output_dir)

    @staticmethod
    def _find_first(root: Path, preferred_patterns: tuple[str, ...], fallback_pattern: str) -> Path | None:
        for pattern in preferred_patterns:
            matches = sorted(root.rglob(pattern))
            if matches:
                return matches[0]
        matches = sorted(root.rglob(fallback_pattern))
        return matches[0] if matches else None


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
