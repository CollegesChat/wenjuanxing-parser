"""基础数据类型、枚举和别名定义"""

from datetime import datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, Any, Literal, Type, TypeVar

from pydantic import BeforeValidator
from pydantic.dataclasses import dataclass

T = TypeVar('T')


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


def smart_repr(cls: Type[T]) -> Type[T]:
    """
    自动过滤默认/空值的 Repr 装饰器
    支持标准 dataclass、Pydantic dataclass 以及普通类
    """
    def custom_repr(self: Any) -> str:
        # 兼容 Pydantic v2 和标准 dataclass 的字段获取
        if hasattr(self, '__pydantic_fields__'):
            field_names = self.__pydantic_fields__.keys()
        elif hasattr(self, '__dataclass_fields__'):
            field_names = self.__dataclass_fields__.keys()
        else:
            field_names = [k for k in self.__dict__.keys() if not k.startswith('_')]

        valid_fields = []
        for name in field_names:
            val = getattr(self, name)

            # 修复 Bug：用 is 显式区分 False 和 0
            if val is None or val is False or val == '':
                continue

            # 如果你想连空列表、空字典也过滤掉，可以解开下面这两行的注释：
            # if isinstance(val, (list, dict, set, tuple)) and not val:
            #     continue

            valid_fields.append(f'{name}={val!r}')

        return f'{self.__class__.__name__}({", ".join(valid_fields)})'

    # 动态绑定 repr 方法
    cls.__repr__ = custom_repr  # type: ignore
    return cls