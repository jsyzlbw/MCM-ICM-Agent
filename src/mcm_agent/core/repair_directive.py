"""Helper to read the targeted repair directive written by O6 (MockJudgeGateAgent).

The directive lives at ``review/repair_directive.json`` inside the workspace root.
O6 writes it on ``needs_repair`` and deletes it on ``pass``.

Usage::

    from mcm_agent.core.repair_directive import read_repair_directive

    directive = read_repair_directive(workspace_root)
    if directive and directive.get("target_stage") == "solver_coder":
        ...
"""
from __future__ import annotations

import json
from pathlib import Path


def read_repair_directive(workspace_root: Path) -> dict | None:
    """Read ``review/repair_directive.json`` and return it as a dict, or None.

    Returns:
        The parsed dict if the file exists and contains a valid JSON object.
        None if the file does not exist, cannot be parsed, or is not a dict.

    Never raises.
    """
    path = workspace_root / "review" / "repair_directive.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None
