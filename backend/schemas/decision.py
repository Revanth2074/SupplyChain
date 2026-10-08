"""
Decision Support Pydantic Schemas.
"""

from typing import Optional

from pydantic import BaseModel

from schemas.common import Incident


class DecisionRequest(BaseModel):
    incident: Incident
    costs: Optional[dict[str, dict[str, float]]] = None
