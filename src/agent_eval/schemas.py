"""Only JSON-serializable artifacts cross the evaluator boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EvalCase(StrictModel):
    id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    split: Literal["discovery", "development", "test"] = "test"
    input: dict[str, JsonValue]
    output: JsonValue
    tool_trace: list[dict[str, JsonValue]] = Field(default_factory=list)
    final_state: dict[str, JsonValue] | None = None
