"""REST API handler for current user APIs."""

from fastapi import APIRouter, Request, status

from assistant.models.user import User
from assistant.security.session_auth import require_auth

router = APIRouter()


@router.get(
    '/current',
    response_description='Logged in user information',
    status_code=status.HTTP_200_OK,
    response_model=User,
    include_in_schema=False,
)
async def get_current_user(request: Request) -> User:
    """Authenticate the user and return the user information."""
    session = require_auth(request)
    user = User(
        email=session.get('email'),
        # pyrefly: ignore [bad-argument-type]
        userid=session.get('userid'),
        name=session.get('name'),
    )

    return user
