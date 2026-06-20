from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json, write_json

_SPEC_PATH = "work/discussion/model_spec.json"


class ModelVariable(BaseModel):
    symbol: str
    meaning: str


class SubproblemModel(BaseModel):
    """One problem-specific model, the single source of truth shared by the
    solver (which implements it) and the writer (which narrates it)."""

    subproblem_id: str
    title: str
    approach: str = ""  # short name of the method (problem-specific, not a canned route id)
    variables: list[ModelVariable] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    equations: list[str] = Field(default_factory=list)  # LaTeX, no $ delimiters
    algorithm_steps: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    data_inputs: list[str] = Field(default_factory=list)


class ModelSpec(BaseModel):
    version: int = 1
    problem_restatement: str = ""
    subproblems: list[SubproblemModel] = Field(default_factory=list)


def write_model_spec(root: Path, spec: ModelSpec) -> None:
    write_json(Path(root) / _SPEC_PATH, spec.model_dump(mode="json"))


def read_model_spec(root: Path) -> ModelSpec | None:
    data = read_json(Path(root) / _SPEC_PATH, None)
    if not isinstance(data, dict):
        return None
    try:
        return ModelSpec.model_validate(data)
    except Exception:
        return None
