"""
Search, Classification & Prioritisation Pydantic Schemas.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas.common import Filters, Incident


class SearchRequest(BaseModel):
    query: str
    filters: Optional[Filters] = None
    top_k: int = Field(10, ge=1, le=50)
    mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    alpha: float = Field(0.6, ge=0, le=1)


class ClassifyRequest(BaseModel):
    description: str


class PrioritizeRequest(BaseModel):
    incidents: list[Incident] = Field(..., min_length=1, max_length=200)
