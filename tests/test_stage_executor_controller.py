from datetime import UTC, datetime

from mcm_agent.core.stage_executor import StageExecutor, StageResult


def _topology(tmp_path):
    # linear: a -> b -> c
    (tmp_path / "workflow_topology.json").write_text(
        '{"edges":['
        '{"from_node":"a","to_node":"b","condition":"pass"},'
        '{"from_node":"b","to_node":"c","condition":"pass"}]}',
        encoding="utf-8",
    )
    (tmp_path / "task_state.json").write_text(
        '{"workspace_id":"w","current_phase":"initialized",'
        f'"created_at":"{datetime.now(UTC).isoformat()}",'
        f'"updated_at":"{datetime.now(UTC).isoformat()}"}}',
        encoding="utf-8",
    )


def _handlers():
    return {
        "a": lambda root: StageResult(outputs=["a.txt"]),
        "b": lambda root: StageResult(outputs=["b.txt"]),
        "c": lambda root: StageResult(outputs=["c.txt"]),
    }


def test_controller_stop_halts_after_current_stage(tmp_path):
    _topology(tmp_path)
    executor = StageExecutor(tmp_path, handlers=_handlers())

    seen = []

    def controller(record):
        seen.append(record.stage_id)
        return "stop" if record.stage_id == "a" else "continue"

    records = executor.run_until_complete("a", controller=controller)

    assert [r.stage_id for r in records] == ["a"]
    assert seen == ["a"]


def test_controller_continue_runs_to_end(tmp_path):
    _topology(tmp_path)
    executor = StageExecutor(tmp_path, handlers=_handlers())
    records = executor.run_until_complete("a", controller=lambda record: "continue")
    assert [r.stage_id for r in records] == ["a", "b", "c"]


def test_controller_pause_breaks_loop(tmp_path):
    _topology(tmp_path)
    executor = StageExecutor(tmp_path, handlers=_handlers())

    def controller(record):
        return "pause" if record.stage_id == "b" else "continue"

    records = executor.run_until_complete("a", controller=controller)
    assert [r.stage_id for r in records] == ["a", "b"]


def test_resume_mvp_workflow_passes_controller(tmp_path):
    from mcm_agent.core.workspace import create_workspace
    from mcm_agent.workflows.demo_fixtures import create_demo_inputs
    from mcm_agent.workflows.mvp import resume_mvp_workflow
    from mcm_agent.core.models import TaskInput

    create_workspace(tmp_path / "ws")
    problem, attachments, idea, skills = create_demo_inputs(tmp_path / "demo_inputs")

    stopped_after = []

    def controller(record):
        stopped_after.append(record.stage_id)
        return "stop" if record.stage_id == "intake" else "continue"

    resume_mvp_workflow(
        tmp_path / "ws",
        TaskInput(problem_file=problem, attachments=attachments, user_idea_file=idea),
        supervisor_skills_dir=skills,
        auto_approve=True,
        from_stage="intake",
        controller=controller,
    )

    assert stopped_after == ["intake"]
    lines = (tmp_path / "ws" / "stage_runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
