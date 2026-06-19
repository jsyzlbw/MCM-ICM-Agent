from pathlib import Path
import stat


def test_install_script_is_present_and_shell_safe() -> None:
    script = Path("install.sh")

    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "mag" in text
    assert "mcm-agent" not in text


def test_install_script_prefers_isolated_tool_install() -> None:
    text = Path("install.sh").read_text(encoding="utf-8")

    assert "pipx" in text
    assert "python -m pip install --user" in text
    assert "mag -v" in text


def test_install_script_is_executable() -> None:
    mode = Path("install.sh").stat().st_mode

    assert mode & stat.S_IXUSR
