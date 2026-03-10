from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from assistant.models.user import User


def require_auth(request: Request) -> dict:
    if not request.session.get('authenticated'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Not authenticated',
        )

    userid = request.session.get('userid')
    if not isinstance(userid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid session data',
        )

    return request.session


# Current user dependency with caching per request
def get_current_user(
    request: Request, session: dict = Depends(require_auth)
) -> User:
    # Check if the User object is already cached on the request
    if hasattr(request.state, 'current_user'):
        return request.state.current_user

    # Construct or fetch User (e.g., DB call)
    user = User(
        email=session.get('email'),
        # pyrefly: ignore [bad-argument-type]
        userid=session.get('userid'),
        name=session.get('name'),
    )

    # Cache it on the request
    request.state.current_user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
