from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from toolkit.api.deps import require_api_key
from toolkit.api.schemas import LeadOut
from toolkit.config import Settings, get_settings
from toolkit.db.session import session_scope
from toolkit.integrations.factory import build_lead_sink
from toolkit.services.leads import LeadIn, ingest_lead

router = APIRouter(tags=["leads"], dependencies=[Depends(require_api_key)])


@router.post(
    "/leads",
    response_model=LeadOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Duplicate submission; the existing lead is returned"}},
)
async def create_lead(
    payload: LeadIn,
    response: Response,
    session: Annotated[AsyncSession, Depends(session_scope)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LeadOut:
    outcome = await ingest_lead(
        session,
        payload,
        threshold=settings.lead_score_threshold,
        sink=build_lead_sink(settings),
    )
    if outcome.duplicate:
        response.status_code = status.HTTP_200_OK
    lead = outcome.lead
    return LeadOut(
        id=lead.id,
        email=lead.email,
        score=lead.score,
        status=lead.status.value,
        qualified=outcome.qualified,
        duplicate=outcome.duplicate,
        company_domain=lead.company_domain,
        country=lead.country,
        score_reasons=outcome.reasons or list(lead.raw.get("score_reasons", [])),
    )
