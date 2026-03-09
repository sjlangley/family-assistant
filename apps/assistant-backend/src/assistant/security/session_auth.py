from fastapi import HTTPException, Request, status


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
