"""``_parse_single_option`` 附加文本提取行为的回归测试。"""

import pytest

from wenjuanxing_parser.models import QuestionnaireResponse


@pytest.mark.parametrize(
    ("raw", "text", "additional"),
    [
        ("选项名〖附加文本〗", "选项名", "附加文本"),  # 标准形态
        ("普通文本", "普通文本", None),  # 无附加文本
        ("选项A〖〗", "选项A", None),  # 空附加文本等价于没有
        (" 选项A 〖 测试 〗 ", "选项A", "测试"),  # 两段各自去空白
        ("选项A〖附加", "选项A", "附加"),  # 未闭合：降级保留旧行为
        ("选项A〖x〗后缀", "选项A后缀", "x"),  # 配对之后的后缀拼回 text
        ("选项A〖附加文本〗〗", "选项A〗", "附加文本"),  # 多余的括号被保住而非吞掉
        ("断电〖测试〗┋断网〖测试〗", "断电┋断网〖测试〗", "测试"),  # 多组并列只取第一组
    ],
)
def test_extraction(raw, text, additional):
    result = QuestionnaireResponse._parse_single_option(raw)
    assert result.text == text
    assert result.additional_text == additional
