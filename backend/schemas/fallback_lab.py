"""
Fallback Lab Pydantic Schemas (simulated outages and self-test).
"""

from pydantic import BaseModel, Field

from services.faults import MAX_MINUTES


class SwitchRequest(BaseModel):
    enabled: bool
    minutes: float = Field(30, ge=1, le=MAX_MINUTES)


class SelfTestRequest(BaseModel):
    full_workflow: bool = True
