from wenjuanxing_parser.models import ResponseStatus, UserAnswer

ua = UserAnswer(value=ResponseStatus.SKIPPED)

# 改成赋值给变量，迫使 Pyright 检查这一行的表达式类型
result = ResponseStatus.SKIPPED in ua
