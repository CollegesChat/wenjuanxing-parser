"""内部模型模块，通过 facade 暴露"""

from .answers import (
    AnswerValue,
    CheckboxAnswer,
    ChosenOption,
    FillBlankAnswer,
    RadioAnswer,
    SelectedOption,
    TextAreaAnswer,
    UserAnswer,
)
from .base import (
    IP,
    BasicData,
    IPAddress,
    PolarsValue,
    QuestionType,
    ResponseStatus,
)
from .dataframe import QuestionnaireData
from .questions import (
    AnyQuestion,
    CheckboxQuestion,
    FillBlankQuestion,
    Option,
    Question,
    Questionnaire,
    RadioQuestion,
    TextAreaQuestion,
)
from .response import QuestionnaireResponse

__all__ = [
    "IP",
    "AnswerValue",
    "AnyQuestion",
    "BasicData",
    "CheckboxAnswer",
    "CheckboxQuestion",
    "ChosenOption",  # compatibility alias
    "FillBlankAnswer",
    "FillBlankQuestion",
    "IPAddress",
    # questions
    "Option",
    "PolarsValue",
    "Question",
    "QuestionType",
    "Questionnaire",
    # dataframe
    "QuestionnaireData",
    # response
    "QuestionnaireResponse",
    "RadioAnswer",
    "RadioQuestion",
    # base
    "ResponseStatus",
    # answers
    "SelectedOption",
    "TextAreaAnswer",
    "TextAreaQuestion",
    "UserAnswer",
]
