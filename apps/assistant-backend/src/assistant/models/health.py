"""FastAPI model for health status check."""

from pydantic import BaseModel, ConfigDict


class HealthCheck(BaseModel):
    """Response to return when performing a health check."""

    model_config = ConfigDict(extra='forbid')

    status: str = 'OK'
