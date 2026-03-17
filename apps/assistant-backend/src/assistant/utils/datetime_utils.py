"""Datetime utilities for UTC timestamp handling."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current datetime in UTC timezone.

    Returns:
        datetime: Current datetime with UTC timezone.
    """
    return datetime.now(timezone.utc)


def convert_to_utc(dt_object: datetime) -> datetime:
    """
    Converts a datetime object to its equivalent in the UTC timezone.

    If the input datetime object is naive (has no timezone information),
    it is assumed to be in UTC. If it is timezone-aware, it is converted
    to UTC.

    Args:
        dt_object: The datetime object to convert.

    Returns:
        A new datetime object representing the same point in time, but
        localized to the UTC timezone.
    """
    if dt_object.tzinfo is None:
        # If the datetime object is naive, assume it's in UTC.
        # This is a common convention in many systems if no timezone is
        # specified.
        return dt_object.replace(tzinfo=timezone.utc)
    else:
        # If the datetime object is already timezone-aware,
        # convert it to UTC.
        return dt_object.astimezone(timezone.utc)
