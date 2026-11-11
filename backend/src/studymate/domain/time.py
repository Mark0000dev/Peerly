from datetime import datetime


def require_aware(value: datetime) -> None:
    if value.utcoffset() is None:
        raise ValueError("Domain timestamps must include a timezone")
