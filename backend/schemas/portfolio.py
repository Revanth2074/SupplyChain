"""
Supplier Portfolio, Network & Early-Warning Pydantic Schemas.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class PortfolioRequest(BaseModel):
    suppliers: Optional[list[dict[str, Any]]] = Field(None, max_length=500)
    csv: Optional[str] = Field(None, max_length=500_000)
    severity: int = Field(3, ge=1, le=5)


class PortfolioCsvRequest(BaseModel):
    csv: Optional[str] = Field(None, max_length=500_000)
    severity: int = Field(3, ge=1, le=5)


class OfflineRequest(PortfolioCsvRequest):
    supplier: str
    disruption_type: Optional[str] = None


class SignalRequest(BaseModel):
    headline: str = Field(..., min_length=8, max_length=300)
    detail: Optional[str] = Field("", max_length=2000)
    send_to_synapt: bool = False


class SignalPatch(BaseModel):
    active: bool
