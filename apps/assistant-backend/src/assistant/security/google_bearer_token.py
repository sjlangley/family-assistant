"""Verifies the bearer token in the Authorization header."""

import asyncio
from functools import lru_cache
import logging
from typing import Any

import cachecontrol
from fastapi import HTTPException, status
from google.auth import exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
import requests

from assistant.models.user import User
from assistant.settings import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_google_request():
    session: Any = requests.Session()
    cached_session = cachecontrol.CacheControl(session)
    return google_requests.Request(session=cached_session)


def verify_bearer_token(token: str) -> User:
    try:
        request = get_google_request()
        payload = google_id_token.verify_oauth2_token(
            token,
            request=request,
            audience=settings.client_id,
        )
    except exceptions.GoogleAuthError as e:
        logger.error('Google ID token verification failed', exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Authentication failed',
        ) from e
    except ValueError as e:
        logger.info('Bearer token verification failed: %s', e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
        ) from e

    userid = payload.get('sub')
    email = payload.get('email')
    hosted_domain = payload.get('hd')

    if not userid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid token payload',
        )

    if (
        settings.allowed_hosted_domains
        and hosted_domain not in settings.allowed_hosted_domains
    ):
        logger.warning('Unauthorized hosted domain: %s', hosted_domain)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Unauthorized hosted domain',
        )

    return User(
        userid=userid,
        email=email,
        name=payload.get('name'),
    )
