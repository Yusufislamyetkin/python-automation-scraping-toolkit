import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from toolkit.config import Settings, get_settings
from toolkit.services.dispatch import JobDispatcher

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    key: Annotated[str | None, Security(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    expected = settings.api_key.get_secret_value()
    if not key or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-API-Key")


def get_dispatcher(request: Request) -> JobDispatcher:
    return request.app.state.dispatcher  # type: ignore[no-any-return]
