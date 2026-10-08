"""
Feedback Pydantic Schemas.
Request and response data models for the operator feedback loop.
"""

from typing import Optional

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    analysis_id: Optional[str] = Field(None, description="Analysis the rating refers to")
    rating: int = Field(..., ge=1, le=5, description="1 to 5 star rating")
    helpful: Optional[bool] = None
    chosen_strategy: Optional[str] = None
    comment: Optional[str] = Field(None, max_length=1000, description="Optional operator comment")
    actual_production_impact_pct: Optional[float] = Field(None, ge=0, le=100)
    actual_revenue_loss_usd: Optional[float] = Field(None, ge=0)
    actual_full_recovery_days: Optional[float] = Field(None, ge=0, le=1000)
    actual_partial_recovery_days: Optional[float] = Field(None, ge=0, le=1000)


class FeedbackResponse(BaseModel):
    id: str
    synapt_sent: bool
    boosts: int
