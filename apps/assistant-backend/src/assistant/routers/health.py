"""REST API handler for health checking."""

from fastapi import APIRouter, status

from assistant.models.health import HealthCheck

router = APIRouter()


@router.get(
    '',
    response_description='Return HTTP Status Code 200 (OK)',
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
    include_in_schema=False,
)
async def get_health() -> HealthCheck:
    """Perform a health check and return the service status."""
    return HealthCheck()
