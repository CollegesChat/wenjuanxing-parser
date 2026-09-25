"""错误 / 警告层次的回归测试。"""

import warnings

import pytest

from wenjuanxing_parser.errors import (
    BlankConfigError,
    BracketWarning,
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


def test_blank_config_dict_branch_reports_field_name():
    """dict 格式的越界报错必须用字段名，与 list 分支用的可读名区分开。

    这两处报错文本历史上就不一致，锁住它以免重构时被无意合并。
    """
    with pytest.raises(BlankConfigError, match="default_blank_text 的键 3"):
        FillBlankQuestion(
            num=1, type="fill_blank", blank_count=2, default_blank_text={3: "x"}
        )


def test_invalid_questions_map():
    with pytest.raises(InvalidQuestionsMapError):
        # 故意传入非映射，验证 InvalidQuestionsMapError 能穿透
        QuestionnaireResponse.parse_from_dict(None, {}, ["不是映射"])  # type: ignore


def test_delimiter_inside_brackets_warns():
    """〖...〗 内部出现 ┋ 时应发出 DelimiterWarning。"""
    with pytest.warns(DelimiterWarning):
        QuestionnaireResponse._split_outside_brackets("选项A〖x┋y〗")


@pytest.mark.parametrize(
    "raw",
    [
        "选项A〖附加〖嵌套〗",  # 嵌套
        "选项A〖未闭合",  # 缺少右括号
        "多余右括号〗啊",  # 多余右括号
        "〗〖",  # 括号顺序颠倒
    ],
)
def test_genuine_bracket_anomalies_warn(raw):
    """真正的括号异常必须触发 BracketWarning。"""
    with pytest.warns(BracketWarning):
        QuestionnaireResponse._parse_single_option(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "断电〖测试〗┋断网〖测试〗",  # 多组并列，以 ┋ 分隔
        "选项A〖x〗选项B〖y〗",  # 多组并列，无分隔符
        "选项A〖附加文本〗",  # 单组正常
        "普通文本",  # 无括号
    ],
)
def test_multiple_balanced_pairs_do_not_warn(raw):
    """多组并列的合法括号不得触发 BracketWarning。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error", BracketWarning)
        QuestionnaireResponse._parse_single_option(raw)
