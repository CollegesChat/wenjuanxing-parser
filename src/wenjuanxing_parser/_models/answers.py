"""答案容器定义"""

from pydantic.dataclasses import dataclass

from .base import ResponseStatus


@dataclass(frozen=True)
class ChosenOption:
    """存放选中选项及其附带文本的容器"""

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


@dataclass(frozen=True)
class UserAnswer:
    """
    带弱校验标记的答案容器。
    清洗层可以通过 if not answer.is_valid 快速定位并处理脏数据。
    """

    value: AnswerValue
    is_valid: bool = True
    error_msg: str | None = (
        None  # 用于记录具体的未通过原因（如：未匹配正则、必填项留空等）
    )
