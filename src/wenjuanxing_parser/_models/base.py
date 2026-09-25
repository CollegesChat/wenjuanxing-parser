"""基础数据类型、枚举和别名定义"""

from datetime import datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, ip_address
from types import NotImplementedType
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.dataclasses import dataclass


class CleanReprModel(BaseModel):
    """
    最顶层基类：统一锁死严格禁止未知字段和冻结属性，
    并过滤 repr 中的 None/False/空字符串，保持输出简洁。
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    def __repr_args__(self) -> list[tuple[str | None, Any]]:
        original_args = super().__repr_args__()
        return [
            (k, v)
            for k, v in original_args
            if v is not None and v is not False and v != ''
        ]


def text_equal(text: str, other: object) -> bool | NotImplementedType:
    """按 text 判等：同族对象、裸字符串，以及任何带 text 属性的对象都可直接比。

    用鸭子类型取代双向 isinstance，让 Option 与 SelectedOption 不必互相导入。
    """
    other_text = getattr(other, "text", other)
    return text == other_text if isinstance(other_text, str) else NotImplemented


# 基础特殊状态枚举
class ResponseStatus(StrEnum):
    EMPTY = '(空)'
    """用户主动跳题"""
    SKIPPED = '(跳过)'
    """程序规则设置的跳题"""
    NONE = '无'
    """仅在填空题的附加文本出现，表示用户未填写任何内容，但题目本身是存在的"""


SKIPPED_OR_EMPTY = (ResponseStatus.EMPTY, ResponseStatus.SKIPPED)

# 基础类型别名
type QuestionType = Literal['radio', 'checkbox', 'fill_blank', 'text_area']
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
