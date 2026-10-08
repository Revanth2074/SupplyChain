"""
Incident Desk Pydantic Schemas.
Incidents opened from an analysis, their SLA status and tracked actions.
"""

from typing import Optional

from pydantic import BaseModel, Field


class IncidentRequest(BaseModel):
    analysis_id: str


class IncidentPatch(BaseModel):
    status: Optional[str] = None
    owner: Optional[str] = Field(None, max_length=80)


class ActionRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    owner: str = Field("Operations", max_length=80)
    due_hours: float = Field(24, gt=0, le=24 * 90)


class ActionPatch(BaseModel):
    status: Optional[str] = None
    actual_recovery_days: Optional[float] = Field(None, ge=0, le=1000)
    actual_loss_usd: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=500)
