"""This module defines application-wide enumerations."""

from enum import StrEnum


class Environment(StrEnum):
    """Enumeration for application environments."""

    PRODUCTION = 'production'
    STAGING = 'staging'
    LOCAL = 'local'
    DEVELOPMENT = 'development'
