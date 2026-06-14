from __future__ import annotations

from pathlib import Path

from mcm_agent.utils.json_io import read_json, write_json


class ResearchReframingAgent:
    def run(self, workspace_root: Path) -> None:
        matrix = read_json(workspace_root / "data" / "data_feasibility_matrix.json", [])
        repair_actions = read_json(workspace_root / "data" / "search_repair_actions.json", [])
        options = []
        for row in matrix if isinstance(matrix, list) else []:
            if not isinstance(row, dict):
                continue
            if row.get("availability") not in {"private_or_unavailable", "proxy_required"}:
                continue
            options.extend(self._options_for_row(row, repair_actions))

        if not options:
            options.append(
                {
                    "data_need_id": "general",
                    "target_dataset": "unavailable data",
                    "strategy": "narrow_scope",
                    "proxy_variables": [],
                    "assumptions_required": [],
                    "recommended_model_change": "Narrow the research question to observable data.",
                    "risk_note": "No unavailable-data row was found in the feasibility matrix.",
                    "source_repair_action": "",
                }
            )

        write_json(workspace_root / "discussion" / "reframing_options.json", options)
        (workspace_root / "discussion" / "reframing_options.md").write_text(
            self._report(options),
            encoding="utf-8",
        )

    def _options_for_row(
        self,
        row: dict[str, object],
        repair_actions: object,
    ) -> list[dict[str, object]]:
        need_id = str(row.get("need_id", "unknown_need"))
        target = str(row.get("target_dataset", "unavailable data"))
        proxy_variables = self._string_list(row.get("proxy_variables"))
        repair_action = self._repair_action_for_need(need_id, repair_actions)
        action_name = str(repair_action.get("recommended_action", ""))
        return [
            {
                "data_need_id": need_id,
                "target_dataset": target,
                "strategy": "proxy_modeling",
                "proxy_variables": proxy_variables,
                "assumptions_required": [
                    "State that direct private data is unavailable.",
                    "Explain why each proxy is causally or operationally related to the target.",
                    "Run sensitivity analysis on proxy weights.",
                ],
                "recommended_model_change": (
                    "Replace direct private-data prediction with a transparent proxy-index "
                    "or multi-criteria scoring model."
                ),
                "risk_note": "Proxy variables support relative strategy design, not direct private-value claims.",
                "source_repair_action": action_name,
            },
            {
                "data_need_id": need_id,
                "target_dataset": target,
                "strategy": "user_provided_assumptions",
                "proxy_variables": proxy_variables,
                "assumptions_required": [
                    "User must explicitly provide or approve synthetic/private assumptions.",
                    "Paper must label these assumptions as scenario inputs.",
                    "Results must not be presented as observed real-world private values.",
                ],
                "recommended_model_change": (
                    "Use scenario simulation around user-approved assumptions and report "
                    "robustness bands."
                ),
                "risk_note": "Contest paper must avoid unsupported claims about private records.",
                "source_repair_action": action_name,
            },
        ]

    def _repair_action_for_need(
        self,
        need_id: str,
        repair_actions: object,
    ) -> dict[str, object]:
        if not isinstance(repair_actions, list):
            return {}
        for action in repair_actions:
            if isinstance(action, dict) and action.get("data_need_id") == need_id:
                return action
        return {}

    def _report(self, options: list[dict[str, object]]) -> str:
        lines = ["# Reframing Options", ""]
        for option in options:
            lines.extend(
                [
                    f"## {option['strategy']}: {option['target_dataset']}",
                    "",
                    f"- Data need: `{option['data_need_id']}`",
                    f"- Recommended model change: {option['recommended_model_change']}",
                    f"- Source repair action: {option.get('source_repair_action', '')}",
                    f"- Risk note: {option['risk_note']}",
                    "- Proxy variables:",
                ]
            )
            proxy_variables = self._string_list(option.get("proxy_variables"))
            if proxy_variables:
                lines.extend(f"  - {proxy}" for proxy in proxy_variables)
            else:
                lines.append("  - None.")
            lines.extend(["- Assumptions required:"])
            for assumption in self._string_list(option.get("assumptions_required")):
                lines.append(f"  - {assumption}")
            lines.append("")
        return "\n".join(lines)

    def _string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]
