"""题目定义及类型"""

from typing import Annotated, Any, Literal, Mapping

from pydantic import BeforeValidator, Field, model_validator
from pydantic.dataclasses import dataclass

from .base import QuestionType


@dataclass(frozen=True)
class Option:
    """选项的定义"""

    text: str  # 选项文本，如 "男"、"其他"
    has_additional: bool = False  # 是否允许附加文本（如：其他____ 后面带有填空线）


@dataclass(frozen=True, kw_only=True)
class Question:
    """题目定义的基类"""

    num: int  # 题号
    title: str = ""  # 题干
    type: QuestionType = "radio"
    required: bool = True
    prompt: str | None = None  # 填报提示/说明


@dataclass(frozen=True, kw_only=True)
class RadioQuestion(Question):
    options: list[Option]
    type: Literal["radio"] = "radio"


@dataclass(frozen=True, kw_only=True)
class CheckboxQuestion(Question):
    options: list[Option]
    type: Literal["checkbox"] = "checkbox"


@dataclass(frozen=True, kw_only=True)
class TextAreaQuestion(Question):
    type: Literal["text_area"] = "text_area"
    length_limit: int | None = None


@dataclass(frozen=True, kw_only=True)
class FillBlankQuestion(Question):
    blank_count: int = Field(
        2, ge=2, description="fill_blank 类型的多项填空题，空格数必须大于 1"
    )
    regex: list[str] = Field(default_factory=list)
    type: Literal["fill_blank"] = "fill_blank"

    @model_validator(mode="after")
    def validate_fill_blank_constraints(self):
        # 限制 2：校验正则规则数量与格子数是否匹配
        if self.regex and len(self.regex) != self.blank_count:
            raise ValueError(
                f"[题号 {self.num}] 校验失败: 该填空题声明了有 {self.blank_count} 个空格，"
                f"但你却配置了 {len(self.regex)} 个正则表达式校验规则！"
            )
        return self


def _infer_question_type(v: Any) -> Any:
    """静默推导文本题型：当未指定或为 text 时，根据特征转换为 fill_blank 或 text_area"""
    if isinstance(v, dict):
        q_type = v.get("type")
        if q_type in (None, "text"):
            # 如果声明了 blank_count 或者 regex 是个列表，推导为填空题
            if "blank_count" in v or isinstance(v.get("regex"), list):
                v["type"] = "fill_blank"
            else:
                # 否则（如 regex 是字符串或缺省），推导为大文本简答题
                v["type"] = "text_area"
    return v


type AnyQuestion = Annotated[
    Annotated[
        RadioQuestion | CheckboxQuestion | FillBlankQuestion | TextAreaQuestion,
        Field(discriminator="type"),
    ],
    BeforeValidator(_infer_question_type),
]

type Questionnaire = Mapping[int, Question]
