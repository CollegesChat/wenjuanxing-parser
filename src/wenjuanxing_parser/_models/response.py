"""问卷响应处理"""

import re
import warnings

from pydantic.dataclasses import dataclass

from ..warnings import BracketDelimiterWarning
from .answers import AnswerValue, SelectedOption, UserAnswer
from .base import BasicData, PolarsValue, ResponseStatus
from .questions import Questionnaire


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
            raise TypeError("questions_map 必须是一个字典映射！")

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

                if len(set(check_strs)) == 1 and check_strs[0] in ("(空)", "(跳过)"):
                    parsed_value = (
                        ResponseStatus.EMPTY
                        if check_strs[0] == "(空)"
                        else ResponseStatus.SKIPPED
                    )

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
                                if s == "(空)":
                                    parts.append(ResponseStatus.EMPTY)
                                elif s == "(跳过)":
                                    parts.append(ResponseStatus.SKIPPED)
                                elif s.lower() == "nan":
                                    parts.append("")
                                else:
                                    parts.append(s)
                    else:
                        raw_str = str(raw_value).strip()
                        parts = []
                        for p in cls._split_outside_brackets(raw_str):
                            if p == "(空)":
                                parts.append(ResponseStatus.EMPTY)
                            elif p == "(跳过)":
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
        """纯正则提取版本：直接按 ┋ 提取文本片段。
        若检测到 〖...〗 内部包含 ┋，将主动发出 warnings 警告提示解析风险。
        """
        # 1. 主动检测是否存在 〖...〗 内部包含 ┋ 的情况（即用户主动输入了分隔符）
        if re.search(r"〖[^〗]*┋[^〗]*〗", text):
            warnings.warn(
                f"检测到 〖...〗 内部包含分隔符 '┋'（可能为用户主动填写的文本）解析结果可能存在偏差：{text!r}",
                BracketDelimiterWarning,
                stacklevel=2,
            )

        # 2. 纯正则提取非 ┋ 字符片段，去除首尾空白并滤除空串
        return [p.strip() for p in re.findall(r"[^┋]+", text) if p.strip()]

    @staticmethod
    def _parse_single_option(raw_str: str) -> SelectedOption:
        """解析问卷星导出的带附加文本的选项 (如: 选项名〖附加文本〗)

        仅检测异常括号/分隔符并抛出警告，不修改原本的解析提取逻辑。
        """
        # 1. 检测逻辑：只监测，不阻断
        left_count = raw_str.count("〖")
        right_count = raw_str.count("〗")

        if left_count != right_count or left_count > 1:
            warnings.warn(
                f"检测到选项文本中包含不匹配或嵌套的括号 '〖/〗'，可能为用户主动填写的文本，解析提取结果可能存在偏差：{raw_str!r}",
                category=BracketDelimiterWarning,
                stacklevel=2,
            )

        # 2. 原封不动的提取逻辑
        if "〖" in raw_str:
            parts = raw_str.split("〖", 1)
            text = parts[0].strip()
            additional = parts[1].rstrip("〗").strip() if len(parts) > 1 else ""
            return SelectedOption(
                text=text, additional_text=additional if additional else None
            )
        return SelectedOption(text=raw_str, additional_text=None)
