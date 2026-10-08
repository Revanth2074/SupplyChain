"""
Evaluation Pydantic Schemas (LLM-as-Judge, DeepEval suite).
"""

from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import Incident


class JudgeRequest(BaseModel):
    report: str
    incident: Optional[Incident] = None
    case_ids: list[str] = []


class EvalRequest(BaseModel):
    limit: Optional[int] = Field(None, ge=1, le=20)
    use_graph: bool = False
    include_feedback: bool = True
