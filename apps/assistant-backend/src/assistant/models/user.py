"""An authenticated user."""

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """An authenticated user."""

    model_config = ConfigDict(extra='forbid')

    email: str | None = Field(
        default=None,
        description="The user's email address.",
        json_schema_extra={'example': 'user@example.com'},
    )
    userid: str = Field(
        ...,
        description="The user's stable id.",
    )
    name: str | None = Field(
        default=None,
        description="The user's full name.",
        json_schema_extra={'example': 'John Doe'},
    )
