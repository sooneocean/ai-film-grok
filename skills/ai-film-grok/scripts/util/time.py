"""UTC timestamp helpers."""

from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
