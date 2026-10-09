"""
Supplier Portfolio & Dependency Network Routes.
Scores a supplier portfolio against every disruption type (risk heatmap), builds the
supplier -> part -> product -> customer network and simulates a supplier going offline.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from schemas import OfflineRequest, PortfolioCsvRequest, PortfolioRequest
from services import network, portfolio
from services.bootstrap import ready

router = APIRouter(tags=["Portfolio & Network"])


def scored_portfolio(csv: str | None, severity: int = 3) -> dict:
    """Score the uploaded portfolio CSV (or the bundled sample); 422 on invalid rows."""
    try:
        return portfolio.score(portfolio.rows_or_sample(csv), severity)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/portfolio/sample", response_class=PlainTextResponse)
def portfolio_sample():
    return portfolio.sample_csv()


@router.post("/portfolio")
def portfolio_score(req: PortfolioRequest):
    """Score a supplier portfolio across all disruption types -> heatmap + ranked risk list."""
    ready()
    try:
        rows = portfolio.parse_csv(req.csv) if req.csv else (req.suppliers or [])
        return portfolio.score(rows, req.severity)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/network")
def network_ep(req: PortfolioCsvRequest):
    ready()
    return network.build(scored_portfolio(req.csv, req.severity))


@router.post("/network/offline")
def network_offline(req: OfflineRequest):
    ready()
    try:
        return network.offline(scored_portfolio(req.csv, req.severity), req.supplier, req.disruption_type)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
