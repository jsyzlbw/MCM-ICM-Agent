from __future__ import annotations

from pathlib import Path
import shutil

from mcm_agent.config import Settings, load_settings
from mcm_agent.core.models import TaskInput
from mcm_agent.core.workspace_safety import WorkspaceSafety
from mcm_agent.providers.base import ProviderBundle
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.workflows.mvp import run_mvp_workflow


STAGE_LABELS = {
    "intake": "正在读取输入",
    "document_extraction": "正在解析题目",
    "problem_understanding": "正在理解题目",
    "data_feasibility_scout": "正在检查数据可得性",
    "user_discussion": "正在确认研究方向",
    "methodology_rag": "正在检索方法",
    "modeling_council": "正在提出候选模型",
    "model_judge": "正在裁决模型路线",
    "search_data": "正在搜索并注册数据来源",
    "data_eda": "正在清洗与画像数据",
    "solver_coder": "正在写代码求解",
    "validation_gate": "正在验证结果",
    "figure_planning": "正在规划图表",
    "visualization": "正在生成图表",
    "claim_planning": "正在规划论文论断",
    "paper_writer": "正在撰写论文",
    "paper_evidence_binding": "正在绑定论文证据",
    "typesetting": "正在排版与编译",
    "pre_submission_review": "正在终审",
    "submission_packager": "正在打包提交",
    # gate / repair sub-stages
    "mineru_extraction": "正在解析题目",
    "extraction_quality_gate": "正在校验题目解析",
    "modeling_quality_gate": "正在校验模型计划",
    "source_verifier": "正在核验数据来源",
    "figure_quality_gate": "正在校验图表质量",
    "final_gatekeeper": "正在终检",
}


class WorkspaceWorkflowAdapter:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def to_task_input(self) -> TaskInput:
        problem_files = sorted(path for path in (self.root / "input/problem").iterdir() if path.is_file())
        if not problem_files:
            raise FileNotFoundError("No problem file found in input/problem")
        attachments = []
        data_dir = self.root / "input/data"
        if data_dir.exists():
            attachments = sorted(path for path in data_dir.iterdir())
        layout_dir = self.root / "input/layout"
        template_dir = layout_dir if layout_dir.exists() and any(layout_dir.iterdir()) else None
        return TaskInput(
            problem_file=problem_files[0],
            attachments=attachments,
            template_dir=template_dir,
        )

    def build_providers(self) -> tuple[Settings, ProviderBundle]:
        settings = load_settings(workspace_root=self.root)
        bundle = build_provider_bundle(settings, workspace_root=self.root)
        return settings, bundle

    def run_default_workflow(self, *, auto_approve: bool = True, progress=None) -> None:
        settings, providers = self.build_providers()
        language = self._locked_language()
        if language:
            settings = settings.model_copy(update={"mcm_agent_default_language": language})
        run_mvp_workflow(
            self.root,
            self.to_task_input(),
            providers=providers,
            settings=settings,
            auto_approve=auto_approve,
            controller=self._progress_controller(progress),
        )
        self.sync_outputs()
        WorkspaceSafety(self.root).checkpoint("mag: run workflow")

    @staticmethod
    def _progress_controller(progress):
        if progress is None:
            return None

        def _controller(record) -> str:
            progress(STAGE_LABELS.get(record.stage_id, record.stage_id))
            return "continue"

        return _controller

    def _locked_language(self) -> str:
        from mcm_agent.utils.json_io import read_json

        script = read_json(self.root / "work" / "discussion" / "locked_research_script.json", {})
        if isinstance(script, dict):
            language = script.get("language")
            if isinstance(language, str) and language.strip():
                return language.strip()
        return ""

    def sync_outputs(self) -> None:
        draft_dir = self.root / "output" / "draft"
        final_dir = self.root / "output" / "final"
        package_dir = self.root / "output" / "package"
        draft_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)
        package_dir.mkdir(parents=True, exist_ok=True)

        copies = [
            (self.root / "paper" / "main.tex", draft_dir / "main.tex"),
            (self.root / "paper" / "main.pdf", draft_dir / "main.pdf"),
            (self.root / "paper" / "main.tex", final_dir / "main.tex"),
            (self.root / "paper" / "main.pdf", final_dir / "main.pdf"),
            (
                self.root / "final_submission" / "submission_package.zip",
                package_dir / "submission_package.zip",
            ),
        ]
        for source, target in copies:
            if source.exists():
                shutil.copy2(source, target)
