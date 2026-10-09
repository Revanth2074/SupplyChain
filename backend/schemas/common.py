"""
Shared Pydantic Schemas.
The incident profile and the metadata filters used across search, analysis and prediction.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Filters(BaseModel):
    disruption_type: Optional[list[str]] = None
    industry: Optional[list[str]] = None
    supplier_tier: Optional[list[int]] = None
    supplier_region: Optional[list[str]] = None
    supplier_size: Optional[list[str]] = None
    response_type: Optional[list[str]] = None
    disruption_severity: Optional[list[int]] = None
    severity_min: Optional[int] = Field(None, ge=1, le=5)
    severity_max: Optional[int] = Field(None, ge=1, le=5)
    has_backup_supplier: Optional[bool] = None


class Incident(BaseModel):
    disruption_type: Optional[str] = None
    industry: Optional[str] = None
    supplier_tier: Optional[int] = Field(None, ge=1, le=4)
    supplier_region: Optional[str] = None
    supplier_size: Optional[str] = None
    has_backup_supplier: Optional[bool] = None
    disruption_severity: Optional[int] = Field(None, ge=1, le=5)
    response_type: Optional[str] = None
    response_time_days: Optional[int] = Field(None, ge=0, le=365)
    production_impact_pct: Optional[float] = Field(None, ge=0, le=100)
    revenue_loss_usd: Optional[float] = Field(None, ge=0)
    label: Optional[str] = None


def compact(m: Optional[BaseModel]) -> dict | None:
    """Model -> dict without empty values (None when nothing is set)."""
    if not m:
        return None
    d = {k: v for k, v in m.model_dump().items() if v not in (None, [], "")}
    return d or None
