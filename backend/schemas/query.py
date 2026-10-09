"""
Agent Copilot Pydantic Schemas.
Request models for the multi-agent analysis workflow and the RAG Q&A endpoint.
"""

from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import Filters, Incident


class AnalyzeRequest(BaseModel):
    description: Optional[str] = Field(
        None, description="Free-text incident description",
        examples=["Ransomware attack on our Tier 2 electronics supplier in Asia-Pacific; no backup supplier; severity 4."])
    incident: Optional[Incident] = None
    filters: Optional[Filters] = None
    top_k: int = Field(8, ge=3, le=20)
    use_graph: bool = True
    judge: bool = True


class AskRequest(BaseModel):
    question: str = Field(..., examples=["Which response strategies recovered fastest for port congestion?"])
    filters: Optional[Filters] = None
    top_k: int = Field(6, ge=1, le=20)
    use_graph: bool = True
