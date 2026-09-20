"""统一的异常与警告定义。

本模块是本库所有自定义异常与警告的**唯一来源**，避免类型散落在各个业务模块里就地抛出，
上层调用方可以按需精确捕获：

* 警告（``QuestionnaireParserWarning`` 系）：不阻断解析，仅提示原始文本存在歧义，
  提取结果可能有偏差。
* 异常（``QuestionnaireParserError`` 系）：阻断解析，题库配置或原始数据不符合预期。

继承标准库异常的原则：

* 在 **pydantic 校验器内部**抛出的异常（``QuestionConfigError`` 系）**不能**继承
  ``ValueError`` / ``AssertionError``——pydantic 会把这两个类型统一吞成
  ``ValidationError``，自定义类型就对调用方不可见了。因此这一支是纯粹的
  ``QuestionnaireParserError``，以保证它能原样穿透校验流程。
* 其余异常保留对应的标准库基类（``ValueError`` / ``TypeError`` / ``IndexError``），
  使历史上面向标准库异常编写的 ``except`` 逻辑无需改动仍然有效。
"""

__all__ = [
    "BlankConfigError",
    "BracketWarning",
    "DateFormatError",
    "DelimiterWarning",
    "InvalidQuestionsMapError",
    "QuestionConfigError",
    "QuestionnaireParserError",
    "QuestionnaireParserWarning",
    "RawValueError",
    "ResponseIndexError",
    "UnsupportedFileError",
]


# ------------------------------------------------------------------ 警告


class QuestionnaireParserWarning(UserWarning):
    """本库所有自定义警告的基类。"""


class BracketWarning(QuestionnaireParserWarning):
    """文本中出现不匹配或嵌套的括号（如 ``〖`` / ``〗``）。

    可能为用户主动填写的内容，附加文本的提取结果存在偏差。
    """


class DelimiterWarning(QuestionnaireParserWarning):
    """文本片段内部出现分隔符（如 ``┋``）。

    可能为用户主动填写的内容，按分隔符拆分的结果存在偏差。
    """


# ------------------------------------------------------------------ 异常


class QuestionnaireParserError(Exception):
    """本库所有自定义异常的基类。"""


class QuestionConfigError(QuestionnaireParserError):
    """题库配置（YAML / 字典）不符合预期。

    故意**不**继承 ``ValueError``：本类在 pydantic 的 ``model_validator`` 内抛出，
    继承 ``ValueError`` 会被 pydantic 改写为 ``ValidationError``。
    """


class BlankConfigError(QuestionConfigError):
    """填空题的空格配置非法：数量超过空格总数，或键超出 ``[1, blank_count]``。"""


class RawValueError(QuestionnaireParserError, ValueError):
    """原始数据中的某个值无法解析。"""


class DateFormatError(RawValueError):
    """答卷时间的原始字符串无法解析为 ``datetime``。"""


class UnsupportedFileError(RawValueError):
    """数据文件的格式（扩展名）不受支持。"""


class InvalidQuestionsMapError(QuestionnaireParserError, TypeError):
    """``questions_map`` 不是合法的题号到题目的映射。"""


class ResponseIndexError(QuestionnaireParserError, IndexError):
    """答卷下标越界。"""
