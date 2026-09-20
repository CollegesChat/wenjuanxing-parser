"""问卷响应处理"""
import re
import warnings

from pydantic.dataclasses import dataclass

from ..errors import BracketWarning, DelimiterWarning, InvalidQuestionsMapError
from .answers import AnswerValue, SelectedOption, UserAnswer
from .base import SKIPPED_OR_EMPTY, BasicData, PolarsValue, ResponseStatus
from .questions import Questionnaire

# 问卷星用来承载「选项附加文本」与「多选并列」的固定记号。
# 用户极少手打这些符号，所以一旦出现就意味着解析结果可能存在偏差。
BRACKET_OPEN = "〖"
BRACKET_CLOSE = "〗"
DELIMITER = "┋"

_PLAIN = rf"[^{BRACKET_OPEN}{BRACKET_CLOSE}]"  # 任意一个非括号字符
_NOT_CLOSE = rf"[^{BRACKET_CLOSE}]"  # 任意非闭括号字符（允许内含开括号）

# 合法文本的完整语法：若干组「普通文本 + 一组平坦括号」，最后以普通文本收尾。
# 括号内部不允许再出现括号，因此「多组并列」合法而「嵌套」不合法。
# 任何偏离这套语法的情况（未闭合 / 多余右括号 / 嵌套）都匹配失败，即判定为异常。
_WELL_FORMED_TEXT = re.compile(
    rf"(?:{_PLAIN}*{BRACKET_OPEN}{_PLAIN}*{BRACKET_CLOSE})*{_PLAIN}*", re.DOTALL
)

# 第一组「完整配对」的括号，及其前后缀。head 用惰性匹配，确保取到最靠前的一组。
_OPTION_PAIR = re.compile(
    rf"^(?P<head>.*?){BRACKET_OPEN}(?P<additional>{_PLAIN}*){BRACKET_CLOSE}(?P<tail>.*)$",
    re.DOTALL,
)

# 括号内部混入了多选分隔符（用户把分隔符当普通字符填了进去）
_DELIMITER_INSIDE = re.compile(
    rf"{BRACKET_OPEN}{_NOT_CLOSE}*{DELIMITER}{_NOT_CLOSE}*{BRACKET_CLOSE}"
)


def _has_bracket_anomaly(text: str) -> bool:
    """判断括号是否不合乎「平坦配对」语法。

    直接问一句「这段文字合不合语法」即可，比手写扫描更短，也不会漏掉任何一种异常。
    """
    return _WELL_FORMED_TEXT.fullmatch(text) is None


@dataclass(frozen=True)
class QuestionnaireResponse:
    answers: dict[int, UserAnswer]
    metadata: BasicData | None = None

    @classmethod
    def _parse_answers(
        cls,
        row_answers_dict: dict[int, list[PolarsValue] | PolarsValue],
        questions_map: Questionnaire,
    ) -> dict[int, UserAnswer]:
        """解析原始答案，不构造 QuestionnaireResponse。"""
        answers: dict[int, UserAnswer] = {}
        if not isinstance(questions_map, dict):
            raise InvalidQuestionsMapError("questions_map 必须是一个字典映射！")

        for q_num, question in questions_map.items():
            raw_value = row_answers_dict.get(q_num)
            parsed_value: AnswerValue = None

            # 1. 拦截完全缺失 (Polars 字典导出后空值为 None)
            if raw_value is None or (
                not isinstance(raw_value, list) and str(raw_value).lower() == "nan"
            ):
                parsed_value = None
            else:
                # 2. 前置判定整题是否属于 (空) 或 (跳过) 状态
                if isinstance(raw_value, list):
                    check_strs = [
                        str(v).strip()
                        for v in raw_value
                        if v is not None and str(v).lower() != "nan"
                    ]
                else:
                    check_strs = [str(raw_value).strip()]

                if len(set(check_strs)) == 1 and check_strs[0] in SKIPPED_OR_EMPTY:
                    parsed_value = ResponseStatus(check_strs[0])

                # 3. 进入各题型的具体解包派发
                elif question.type == "fill_blank":
                    blank_count = getattr(question, "blank_count", 1)
                    if isinstance(raw_value, list):
                        parts = []
                        for v in raw_value:
                            if v is None or str(v).lower() == "nan":
                                parts.append("")
                            else:
                                s = str(v).strip()
                                if s in SKIPPED_OR_EMPTY:
                                    parts.append(ResponseStatus(s))
                                elif s.lower() == "nan":
                                    parts.append("")
                                else:
                                    parts.append(s)
                    else:
                        raw_str = str(raw_value).strip()
                        parts = []
                        for p in cls._split_outside_brackets(raw_str):
                            if p == ResponseStatus.EMPTY:
                                parts.append(ResponseStatus.EMPTY)
                            elif p == ResponseStatus.SKIPPED:
                                parts.append(ResponseStatus.SKIPPED)
                            else:
                                parts.append(p)

                    # 问卷星导出时通常已自动填入默认文本，此处兜底处理未填写的空格
                    default_texts = getattr(question, "default_blank_text", None)
                    if default_texts:
                        for i in range(len(parts)):
                            if (
                                isinstance(parts[i], str)
                                and parts[i].strip() == ""
                                and (i + 1) in default_texts
                            ):
                                parts[i] = default_texts[i + 1]

                    if len(parts) < blank_count:
                        parts.extend([""] * (blank_count - len(parts)))
                    parsed_value = parts[:blank_count]

                else:
                    raw_str = str(raw_value).strip()
                    if not raw_str or raw_str.lower() == "nan":
                        parsed_value = None
                    elif question.type == "radio":
                        parsed_value = cls._parse_single_option(raw_str)
                    elif question.type == "checkbox":
                        parts = cls._split_outside_brackets(raw_str)
                        parsed_value = (
                            [cls._parse_single_option(p) for p in parts]
                            if parts
                            else None
                        )
                    elif question.type == "text_area":
                        parsed_value = raw_str

            # 仅组装干净的数据，校验属性保持默认值
            answers[q_num] = UserAnswer(value=parsed_value)

        return answers

    @classmethod
    def parse_from_dict(
        cls,
        meta_data: BasicData | None,
        row_answers_dict: dict[int, list[PolarsValue] | PolarsValue],
        questions_map: Questionnaire,
    ) -> "QuestionnaireResponse":
        """【独立步骤 1】解析原始数据并构造未验证的答卷对象。"""
        answers = cls._parse_answers(row_answers_dict, questions_map)
        return cls(metadata=meta_data, answers=answers)

    @staticmethod
    def _validate_answers(
        answers: dict[int, UserAnswer],
        questions_map: Questionnaire,
    ) -> dict[int, UserAnswer]:
        """对已解析的答案执行业务校验，不构造 QuestionnaireResponse。"""
        validated_answers: dict[int, UserAnswer] = {}

        for q_num, user_ans in answers.items():
            question = questions_map.get(q_num)
            if not question:
                # 若题库里没配置该题，保持解析原样
                validated_answers[q_num] = user_ans
                continue

            parsed_value = user_ans.value
            valid: bool | None = None
            error_msg = None

            # 校验规则 1：必填项检查 (Required Constraint)
            if question.required:
                if parsed_value is None:
                    valid = False
                    error_msg = "该题为必填项，但受访者未填写。"
                elif parsed_value in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED):
                    valid = False
                    error_msg = f"该题为必填项，但当前处于特殊状态: {parsed_value}。"
                elif isinstance(parsed_value, list) and len(parsed_value) == 0:
                    valid = False
                    error_msg = "该多选题为必选项，但未勾选任何选项。"
                elif isinstance(parsed_value, list):
                    if any(
                        v == "" or v in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED)
                        for v in parsed_value
                    ):
                        valid = False
                        error_msg = "该填空题为必填项，但存在未完成填写的空格。"

            # 校验规则 2：正则表达式匹配检查 (Regex Constraint) -> 仅作用于填空题
            if (
                valid is not False
                and question.type == "fill_blank"
                and isinstance(parsed_value, list)
            ):
                regex_rules = getattr(question, "regex", None) or {}
                for i, part in enumerate(parsed_value):
                    if (i + 1) in regex_rules:
                        rule = regex_rules[i + 1]
                        if (
                            part in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED)
                            or part == ""
                        ):
                            if question.required:
                                valid = False
                                error_msg = f"第 {i + 1} 个空格未填写。"
                                break
                            continue

                        if not re.match(rule, str(part)):
                            valid = False
                            error_msg = f"第 {i + 1} 个空格填写的文本 '{part}' 未通过格式校验规则。"
                            break

            if valid is None:
                valid = True

            validated_answers[q_num] = UserAnswer(
                value=parsed_value, valid=valid, error_msg=error_msg
            )

        return validated_answers

    def validate(self, questions_map: Questionnaire) -> "QuestionnaireResponse":
        """【独立步骤 2】校验当前答卷并返回新的答卷对象。"""
        validated_answers = self._validate_answers(self.answers, questions_map)
        return self.__class__(metadata=self.metadata, answers=validated_answers)

    @classmethod
    def from_clean_dict(
        cls,
        meta_data: BasicData | None,
        row_answers_dict: dict[int, list[PolarsValue] | PolarsValue],
        questions_map: Questionnaire,
    ) -> "QuestionnaireResponse":
        """【向后兼容管线】顺序调用解析和验证，保证上游原有调用代码无需任何修改。"""
        answers = cls._parse_answers(row_answers_dict, questions_map)
        validated_answers = cls._validate_answers(answers, questions_map)
        return cls(metadata=meta_data, answers=validated_answers)

    @staticmethod
    def _split_outside_brackets(text: str) -> list[str]:
        """纯正则提取版本：直接按分隔符切出各个文本片段。

        若检测到括号内混入了分隔符，将主动发出 DelimiterWarning 警告提示解析风险。
        """
        # 1. 主动检测是否存在括号内混入分隔符的情况（即用户主动输入了分隔符）
        if _DELIMITER_INSIDE.search(text):
            warnings.warn(
                f"检测到 {BRACKET_OPEN}...{BRACKET_CLOSE} 内部包含分隔符 '{DELIMITER}'"
                f"（可能为用户主动填写的文本）解析结果可能存在偏差：{text!r}",
                DelimiterWarning,
                stacklevel=2,
            )

        # 2. 纯正则提取非分隔符片段，去除首尾空白并滤除空串
        return [
            p.strip() for p in re.findall(rf"[^{DELIMITER}]+", text) if p.strip()
        ]

    @staticmethod
    def _parse_single_option(raw_str: str) -> SelectedOption:
        """解析问卷星导出的带附加文本的选项 (如: 选项名〖附加文本〗)

        仅检测异常括号并抛出 BracketWarning 警告；提取时以**第一组完整配对**的括号为准，
        括号之外的前后缀原样拼回 ``text``，不丢弃任何字符。
        """
        # 1. 检测逻辑：只监测，不阻断
        if _has_bracket_anomaly(raw_str):
            warnings.warn(
                f"检测到选项文本中包含不匹配或嵌套的括号 '{BRACKET_OPEN}/{BRACKET_CLOSE}'，"
                f"可能为用户主动填写的文本，解析提取结果可能存在偏差：{raw_str!r}",
                category=BracketWarning,
                stacklevel=2,
            )

        match = _OPTION_PAIR.match(raw_str)
        if match is not None:
            return SelectedOption(
                text=(match["head"] + match["tail"]).strip(),
                additional_text=match["additional"].strip() or None,
            )

        # 没有完整配对：若存在未闭合的开括号，其后全部视为附加文本；否则整串就是选项文本。
        head, opened, rest = raw_str.partition(BRACKET_OPEN)
        if opened:
            return SelectedOption(
                text=head.strip(), additional_text=rest.strip() or None
            )
        return SelectedOption(text=raw_str.strip(), additional_text=None)
