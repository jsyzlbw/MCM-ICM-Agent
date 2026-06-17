from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DiscussionDecision(BaseModel):
    status: Literal["locked", "needs_data_scout"]
    selected_route: str
    new_data_needs: list[str] = Field(default_factory=list)
    requires_data_scout: bool = False
    adopted_reframing_strategy: str = ""
    adopted_reframing_option_id: str = ""
    language: str = "en"

    @model_validator(mode="after")
    def sync_data_scout_flag(self) -> DiscussionDecision:
        self.requires_data_scout = self.status == "needs_data_scout" or bool(self.new_data_needs)
        if self.requires_data_scout:
            self.status = "needs_data_scout"
        return self
