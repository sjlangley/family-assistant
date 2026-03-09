"""REST API handler for user authentication."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from assistant.models.user import User
from assistant.security.security import get_current_google_user

router = APIRouter()

CurrentGoogleUser = Annotated[User, Depends(get_current_google_user)]


@router.post(
    '/login',
    response_description='Logged in user information',
    status_code=status.HTTP_200_OK,
    response_model=User,
    include_in_schema=False,
)
async def login(user: CurrentGoogleUser, request: Request) -> User:
    """Authenticate the user and return the user information."""
    session_cookie = {
        'email': user.email,
        'userid': user.userid,
        'name': user.name,
        'authenticated': True,
    }

    request.session.clear()
    request.session.update(session_cookie)

    return user


@router.post(
    '/logout',
    response_description='Return HTTP Status Code 204 (No Content)',
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def logout(request: Request):
    """Clear the user session to log out."""
    request.session.clear()
