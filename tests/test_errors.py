"""错误 / 警告层次的回归测试。"""

import pytest

from wenjuanxing_parser.errors import (
    BlankConfigError,
    DelimiterWarning,
    InvalidQuestionsMapError,
    QuestionConfigError,
)
from wenjuanxing_parser.models import FillBlankQuestion, QuestionnaireResponse


def test_config_errors_are_not_swallowed_by_pydantic():
    """配置类异常绝不能继承 ValueError，否则会被 pydantic 改写成 ValidationError。

    这条不是复述类定义：它是 errors.py 里那条容易被人无意破坏的约定唯一防线。
    """
    assert not issubclass(QuestionConfigError, ValueError)

    with pytest.raises(BlankConfigError):
        FillBlankQuestion(num=1, type="fill_blank", blank_count=2, regex={5: "x"})


@pytest.mark.parametrize(
    "items",
    [
        ["a", "b", "c", "d"],  # 顺序项超出空格数
        [{9: "a"}],  # 显式位置越界
        [{2: "x"}, "a", "b"],  # 位置被占用后再溢出
    ],
)
def test_blank_config_overflow_raises_instead_of_hanging(items):
    """越界的空格配置必须抛错返回，不能陷入死循环。"""
    with pytest.raises(BlankConfigError):
        FillBlankQuestion(
            num=1, type="fill_blank", blank_count=3, default_blank_text=items
        )


def test_invalid_questions_map():
    with pytest.raises(InvalidQuestionsMapError):
        QuestionnaireResponse.parse_from_dict(None, {}, ["不是映射"])


def test_delimiter_inside_brackets_warns():
    """〖...〗 内部出现 ┋ 时应发出 DelimiterWarning。"""
    with pytest.warns(DelimiterWarning):
        QuestionnaireResponse._split_outside_brackets("选项A〖x┋y〗")
