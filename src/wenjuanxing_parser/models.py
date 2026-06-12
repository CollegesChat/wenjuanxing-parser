from datetime import datetime
from typing import Literal

from pydantic.dataclasses import dataclass

# 1. 基础类型别名
type QuestionType = Literal['radio', 'checkbox', 'fill_blank', 'text_area']


@dataclass(frozen=True)
class BasicData:
    """答卷基础元数据（Excel的前几列，每人一份）"""

    answer_date: datetime
    num: int
    time_used: int
    source: str
    source_detail: str
    ip: str


@dataclass(frozen=True)
class Option:
    """选项的定义"""

    text: str  # 选项文本，如 "男"、"其他"
    has_additional: bool = False  # 是否允许附加文本（如：其他____ 后面带有填空线）


@dataclass(frozen=True)
class Question:
    """题目定义的基类"""

    num: int  # 题号（非常重要！解耦后全靠题号进行 Mapping 关联）
    title: str = ''  # 题干
    type: QuestionType = 'radio'
    required: bool = True
    prompt: str | None = None  # 填报提示/说明


@dataclass(frozen=True)
class RadioQuestion(Question):
    options: list[Option]  # 单选题也有多个选项供人选择，所以是 list[Option]


@dataclass(frozen=True)
class CheckboxQuestion(Question):
    options: list[Option]  # 多选题


@dataclass(frozen=True)
class FillBlankQuestion(Question):
    blank_count: int = 1  # 填空题：记录这道题有几个空格需要填


@dataclass(frozen=True)
class TextAreaQuestion(Question):
    pass  # 问答题：不需要额外定义结构


@dataclass(frozen=True)
class ChosenOption:
    """
    专门用来存放【被选中选项】的详细数据。
    完美解决：选了“断电”，同时附带写了“晚上11点”的场景。
    """

    text: str  # 选中的选项文本，如 "断电"
    additional_text: str | None = None  # 该选项后面附带的文本，如 "晚上11点断电"


# 单选：最终只可能有一个选中项
type RadioAnswer = ChosenOption

# 多选：可能有多个选中项，每个选中项都可能自带或不带附加文本
type CheckboxAnswer = list[ChosenOption]

# 填空：依然保持纯文本列表（按空格顺序）
type FillBlankAnswer = list[str]

# 问答：依然是一大段纯文本
type TextAreaAnswer = str

# 统一的答案值类型
type AnswerValue = RadioAnswer | CheckboxAnswer | FillBlankAnswer | TextAreaAnswer | None


@dataclass(frozen=True)
class UserAnswer:
    """
    现在的 UserAnswer 容器，即使面对最复杂的组合多选题，
    也能以极高的精度不丢失任何数据地装载。
    """

    value: AnswerValue


@dataclass(frozen=True)
class QuestionnaireResponse:
    """
    这就是 Excel 里的“一行”数据：
    代表【某一个具体用户】提交的完整答卷。
    """

    metadata: BasicData  # 这个人的基本信息
    answers: dict[int, UserAnswer]  # 题号(int) -> 这个人在该题的回答(UserAnswer)


@dataclass(frozen=True)
class Questionnaire:
    data: list[QuestionnaireResponse]

    def __init__(self):
        pass