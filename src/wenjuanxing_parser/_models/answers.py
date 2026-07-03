"""答案容器定义"""
import warnings
from typing import Any, overload

from pydantic import BaseModel, ConfigDict

try:
    from typing import deprecated  # type: ignore
except ImportError:
    from typing_extensions import deprecated

from .base import ResponseStatus


class CleanReprModel(BaseModel):
    """
    提供类似于 smart_repr 过滤空值/默认值功能的基类
    """

    def __repr_args__(self) -> list[tuple[str | None, Any]]:
        original_args = super().__repr_args__()
        return [
            (k, v)
            for k, v in original_args
            if v is not None and v is not False and v != ""
        ]


class SelectedOption(CleanReprModel):
    """存放选中选项及其附带文本的容器"""

    model_config = ConfigDict(frozen=True)

    text: str
    additional_text: str | None = None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SelectedOption):
            return self.text == other.text
        if isinstance(other, str):
            return self.text == other
        from .questions import Option

        if isinstance(other, Option):
            return self.text == other.text
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.text)


# 向后兼容别名
ChosenOption = SelectedOption


# 细化各种题型的内部容器类型
type RadioAnswer = SelectedOption
type CheckboxAnswer = list[SelectedOption]
type TextAreaAnswer = str
type FillBlankAnswer = list[TextAreaAnswer | ResponseStatus]  # 允许格子级别包含枚举值

# 统一的答案值类型（支持整题级状态）
type AnswerValue = (
    RadioAnswer
    | CheckboxAnswer
    | FillBlankAnswer
    | TextAreaAnswer
    | ResponseStatus
    | None
)


class UserAnswer(CleanReprModel):
    """
    带弱校验标记的答案容器。
    清洗层可以通过 if answer.valid is False 快速定位并处理脏数据。
    """

    model_config = ConfigDict(frozen=True)

    value: AnswerValue
    valid: bool | None = None
    error_msg: str | None = (
        None  # 用于记录具体的未通过原因（如：未匹配正则、必填项留空等）
    )

    @property
    def is_skipped(self) -> bool:
        return self.value is ResponseStatus.SKIPPED

    @property
    def is_empty(self) -> bool:
        return self.value is ResponseStatus.EMPTY

    @overload
    def __contains__(self, item: str) -> bool: ...
    @overload
    def __contains__(self, item: SelectedOption) -> bool: ...
    @overload
    @deprecated("传入 ResponseStatus 已废弃，使用 `ResponseStatus is answer` 代替")
    def __contains__(self, item: ResponseStatus) -> bool: ...

    def __contains__(self, item: object) -> bool:
        if isinstance(item, ResponseStatus):
            warnings.warn(
                "使用 'ResponseStatus in answer' 已不推荐，"
                "请使用 answer.is_skipped 或 answer.is_empty",
                DeprecationWarning,
                stacklevel=2,
            )
            return self.value is item or (
                isinstance(self.value, list) and item in self.value
            )

        if isinstance(item, str):
            text = item
        elif hasattr(item, "text"):
            text = item.text
        else:
            return False

        val = self.value
        if isinstance(val, SelectedOption):
            return val.text == text
        if isinstance(val, list):
            return any(
                (v.text if isinstance(v, SelectedOption) else v) == text for v in val
            )
        return False


