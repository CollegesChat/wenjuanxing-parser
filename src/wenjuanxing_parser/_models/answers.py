"""答案容器定义"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from .base import ResponseStatus  # 保持原有的状态枚举导入


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


class ChosenOption(CleanReprModel):
    """存放选中选项及其附带文本的容器"""

    model_config = ConfigDict(frozen=True)

    text: str
    additional_text: str | None = None


# 细化各种题型的内部容器类型
type RadioAnswer = ChosenOption
type CheckboxAnswer = list[ChosenOption]
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
    清洗层可以通过 if not answer.is_valid 快速定位并处理脏数据。
    """

    model_config = ConfigDict(frozen=True)

    value: AnswerValue
    is_valid: bool = True
    error_msg: str | None = (
        None  # 用于记录具体的未通过原因（如：未匹配正则、必填项留空等）
    )
