"""Web utilities for mapping service exceptions to HTTP responses."""

from fastapi import HTTPException, status

from assistant.models.llm import LLMCompletionError, LLMCompletionErrorKind


def llm_completion_error_to_http_exception(
    error: LLMCompletionError,
) -> HTTPException:
    """Convert LLMCompletionError to FastAPI HTTPException.

    Preserves exact error response formats expected by clients.

    Args:
        error: Service-level LLM completion error

    Returns:
        HTTPException with appropriate status code and detail
    """
    if error.kind == LLMCompletionErrorKind.timeout:
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=error.message,
        )

    if error.kind == LLMCompletionErrorKind.unreachable:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error.message,
        )

    if error.kind == LLMCompletionErrorKind.backend_error:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                'message': error.message,
                'status_code': error.backend_status_code,
            },
        )

    # invalid_response
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=error.message,
    )
