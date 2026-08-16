"""自定义警告模块"""


class QuestionnaireParserWarning(UserWarning):
    """问卷星解析器基础警告类"""



class BracketDelimiterWarning(QuestionnaireParserWarning):
    """当文本中包含可能导致歧义的特殊括号或分隔符时触发的警告"""

