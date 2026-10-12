"""
Activity History Schemas.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

KINDS = ("analysis", "ask", "search", "graph", "simulation", "decision", "triage", "portfolio", "network",
         "signal", "incident", "feedback", "evaluation", "playbook", "insight")


class HistoryRequest(BaseModel):
    kind: str = Field(..., description=f"One of: {', '.join(KINDS)}")
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field("", max_length=600)
    ref: Optional[str] = Field(None, max_length=64, description="Id of the underlying object, e.g. an analysis id")
    data: Optional[dict[str, Any]] = Field(None, description="Inputs and a compact snapshot of the result")
