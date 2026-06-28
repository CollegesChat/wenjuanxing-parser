"""基础数据类型、枚举和别名定义"""

from datetime import datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, Literal, TypeVar

from pydantic import BeforeValidator
from pydantic.dataclasses import dataclass

T = TypeVar("T")


# 基础特殊状态枚举
class ResponseStatus(StrEnum):
    EMPTY = "(空)"
    SKIPPED = "(跳过)"


# 基础类型别名
type QuestionType = Literal["radio", "checkbox", "fill_blank", "text_area"]
type PolarsValue = str | int | float | datetime | None
type IPAddress = Annotated[
    IPv4Address | IPv6Address | str,
    BeforeValidator(lambda v: ip_address(v) if isinstance(v, str) else v),
]


@dataclass(frozen=True)
class IP:
    address: IPAddress
    location: str


@dataclass(frozen=True)
class BasicData:
    """答卷基础元数据（Excel的前几列，每人一份）"""

    answer_date: datetime
    num: int
    time_used: timedelta
    source: str
    source_detail: str
    ip: IP
