import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from toolkit.api.deps import get_dispatcher, require_api_key
from toolkit.api.routers.changes import to_change_out
from toolkit.api.schemas import JobOut, JobWithChanges
from toolkit.config import Settings, get_settings
from toolkit.db.models import ChangeEvent, ChangeType, JobRun
from toolkit.db.session import get_sessionmaker, session_scope
from toolkit.integrations.factory import build_change_sink
from toolkit.scraping.factory import Target
from toolkit.services.dispatch import JobDispatcher
from toolkit.services.jobs import create_job, run_scrape_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

Session = Annotated[AsyncSession, Depends(session_scope)]


@router.post(
    "/scrape",
    response_model=JobWithChanges,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def start_scrape(
    session: Session,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    dispatcher: Annotated[JobDispatcher, Depends(get_dispatcher)],
    sessionmaker: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
    target: Annotated[Target, Query()],
    wait: Annotated[
        bool, Query(description="Run inline and return change events (handy for n8n/Make)")
    ] = False,
) -> JobWithChanges:
    job = await create_job(session, "scrape", target)
    if not wait:
        await dispatcher.dispatch(job.id)
        return JobWithChanges.model_validate(job)

    done = await run_scrape_job(job.id, settings, sessionmaker, sink=build_change_sink(settings))
    events = await session.scalars(
        select(ChangeEvent)
        .options(selectinload(ChangeEvent.product))
        .where(ChangeEvent.job_run_id == job.id, ChangeEvent.type != ChangeType.NEW_PRODUCT)
    )
    response.status_code = status.HTTP_200_OK
    out = JobWithChanges.model_validate(done)
    out.changes = [to_change_out(e) for e in events]
    return out


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, session: Session) -> JobRun:
    job = await session.get(JobRun, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job
