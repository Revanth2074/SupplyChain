"""
Synapt Context Substrate Pydantic Schemas.
"""

from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import Incident


class GraphRequest(BaseModel):
    question: str
    hops: Optional[int] = Field(None, ge=0, le=4)
    top_k: int = Field(5, ge=1, le=20)


class LabelRequest(BaseModel):
    description: str
    incident: Optional[Incident] = None
