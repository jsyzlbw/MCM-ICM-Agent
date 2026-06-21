from __future__ import annotations

import base64
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    error: str
    had_error: bool
    images: tuple[str, ...] = field(default=())


@runtime_checkable
class CodeInterpreter(Protocol):
    def add_section(self, title: str) -> None: ...
    def execute(self, code: str) -> ExecResult: ...
    def save_notebook(self) -> None: ...
    def shutdown(self) -> None: ...


class JupyterCodeInterpreter:
    """Persistent Jupyter kernel that keeps variables across cells and serializes a notebook.ipynb.

    Importing this module does NOT require jupyter_client to be installed — all
    jupyter/nbformat imports are deferred to __init__ and methods so that
    FakeCodeInterpreter tests work in environments without a kernel.
    """

    def __init__(self, workspace_root: Path, *, cell_timeout: float = 60.0) -> None:
        # Lazy imports — do not move to module top-level.
        import jupyter_client.manager as _jcm
        import nbformat as _nbf
        import nbformat.v4 as _nbf4

        self._nbf = _nbf
        self._nbf4 = _nbf4
        self.workspace_root = Path(workspace_root)
        self.cell_timeout = cell_timeout
        self._cell_index = 0

        # Start the kernel — raises on failure (caller degrades).
        self._km, self._kc = _jcm.start_new_kernel(kernel_name="python3")
        self._kc.wait_for_ready(timeout=30)

        # In-memory notebook.
        self._nb = _nbf4.new_notebook()

        # Run setup cell: chdir + matplotlib backend + best-effort CJK font.
        setup_code = (
            "import os as _os\n"
            f"_os.chdir({str(self.workspace_root)!r})\n"
            "import matplotlib as _mpl\n"
            "_mpl.use('Agg')\n"
            "try:\n"
            "    import matplotlib.font_manager as _fm\n"
            "    _cjk = [f.name for f in _fm.fontManager.ttflist\n"
            "            if any(k in f.name for k in ('CJK', 'Noto', 'SimSun', 'Microsoft YaHei'))]\n"
            "    if _cjk:\n"
            "        _mpl.rcParams['font.family'] = _cjk[0]\n"
            "except Exception:\n"
            "    pass\n"
        )
        self._run_cell(setup_code, record=False)

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def add_section(self, title: str) -> None:
        """Append a markdown cell to the in-memory notebook."""
        md_cell = self._nbf4.new_markdown_cell(f"## {title}")
        self._nb.cells.append(md_cell)

    def execute(self, code: str) -> ExecResult:
        """Send code to the kernel, collect outputs, return ExecResult."""
        result = self._run_cell(code, record=True)
        return result

    def save_notebook(self) -> None:
        """Write the in-memory notebook to workspace/notebook.ipynb."""
        nb_path = self.workspace_root / "notebook.ipynb"
        self._nbf.write(self._nb, str(nb_path))

    def shutdown(self) -> None:
        """Stop the kernel and client cleanly."""
        try:
            self._kc.stop_channels()
        except Exception:
            pass
        try:
            self._km.shutdown_kernel(now=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_cell(self, code: str, *, record: bool) -> ExecResult:
        """Execute code in the kernel and collect iopub messages until idle."""
        cell_idx = self._cell_index
        self._cell_index += 1

        msg_id = self._kc.execute(code)

        stdout_parts: list[str] = []
        error_parts: list[str] = []
        result_text_parts: list[str] = []
        image_paths: list[str] = []
        had_error = False
        outputs: list[dict] = []

        # Drain iopub until we see execute_reply status idle for this msg_id.
        while True:
            try:
                msg = self._kc.get_iopub_msg(timeout=self.cell_timeout)
            except queue.Empty:
                # Timeout — interrupt and mark as error.
                try:
                    self._km.interrupt_kernel()
                except Exception:
                    pass
                timeout_msg = f"[timeout after {self.cell_timeout}s]"
                error_parts.append(timeout_msg)
                had_error = True
                break

            msg_type = msg["msg_type"]
            parent_id = msg.get("parent_header", {}).get("msg_id", "")

            # Only process messages that belong to our execute request.
            if parent_id != msg_id:
                continue

            content = msg.get("content", {})

            if msg_type == "stream":
                text = content.get("text", "")
                stdout_parts.append(text)
                outputs.append(self._nbf4.new_output(
                    output_type="stream",
                    name=content.get("name", "stdout"),
                    text=text,
                ))

            elif msg_type in ("execute_result", "display_data"):
                data = content.get("data", {})
                text_repr = data.get("text/plain", "")
                if text_repr:
                    result_text_parts.append(text_repr)
                png_b64 = data.get("image/png")
                if png_b64:
                    img_path = self._save_image(png_b64, cell_idx)
                    if img_path:
                        image_paths.append(img_path)
                if msg_type == "execute_result":
                    nb_out = self._nbf4.new_output(
                        output_type="execute_result",
                        data=data,
                        metadata=content.get("metadata", {}),
                        execution_count=content.get("execution_count"),
                    )
                else:
                    nb_out = self._nbf4.new_output(
                        output_type="display_data",
                        data=data,
                        metadata=content.get("metadata", {}),
                    )
                outputs.append(nb_out)

            elif msg_type == "error":
                traceback_lines = content.get("traceback", [])
                # Strip ANSI escape codes for readability.
                import re as _re
                ansi_escape = _re.compile(r"\x1b\[[0-9;]*m")
                clean_tb = "\n".join(ansi_escape.sub("", ln) for ln in traceback_lines)
                error_parts.append(clean_tb)
                had_error = True
                outputs.append(self._nbf4.new_output(
                    output_type="error",
                    ename=content.get("ename", ""),
                    evalue=content.get("evalue", ""),
                    traceback=traceback_lines,
                ))

            elif msg_type == "status":
                if content.get("execution_state") == "idle":
                    break

        stdout = "".join(stdout_parts)
        if result_text_parts:
            stdout = (stdout + "\n".join(result_text_parts)).strip()
        error = "\n".join(error_parts)

        if record:
            code_cell = self._nbf4.new_code_cell(source=code)
            code_cell.outputs = outputs  # type: ignore[attr-defined]
            self._nb.cells.append(code_cell)

        return ExecResult(
            stdout=stdout,
            error=error,
            had_error=had_error,
            images=tuple(image_paths),
        )

    def _save_image(self, png_b64: str, cell_idx: int) -> str | None:
        """Decode base64 PNG and save to figures/cell_<n>.png."""
        try:
            figures_dir = self.workspace_root / "figures"
            figures_dir.mkdir(parents=True, exist_ok=True)
            img_path = figures_dir / f"cell_{cell_idx}.png"
            img_path.write_bytes(base64.b64decode(png_b64))
            return str(img_path)
        except Exception:
            return None
