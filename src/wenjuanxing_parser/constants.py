"""公开的常量定义。"""

from datetime import timedelta
from typing import Final, TypedDict

from ._models.base import IP


class MissingBasicDataKwargs(TypedDict):
    time_used: timedelta
    source: str
    source_detail: str
    ip: IP


MISSING_BASIC_DATA_KWARGS: Final[MissingBasicDataKwargs] = {
    "time_used": timedelta(),
    "source": "直链访问",
    "source_detail": "N/A",
    "ip": IP(address="127.0.0.1", location="未知"),
}

__all__ = ["MISSING_BASIC_DATA_KWARGS"]
