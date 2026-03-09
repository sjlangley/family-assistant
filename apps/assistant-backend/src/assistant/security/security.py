"""Security model for handling authentication and authorization."""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from assistant.enums import Environment
from assistant.models.user import User
from assistant.security.google_bearer_token import verify_bearer_token
from assistant.settings import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

_AUTH_BYPASS_ALLOWED_ENVS = {Environment.LOCAL}


async def get_current_google_user(
    token: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    # Provide a special environment variable to bypass bearer token
    # verification for local development and testing.
    if (
        settings.auth_disabled
        and settings.environment in _AUTH_BYPASS_ALLOWED_ENVS
    ):
        logger.warning(
            'Bypassing bearer token verification in %s environment',
            settings.environment.value,
        )
        return User(
            email='anonymous',
            userid='00000000-0000-0000-0000-000000000000',
        )

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Authorization header missing',
        )

    return await verify_bearer_token(token.credentials)
