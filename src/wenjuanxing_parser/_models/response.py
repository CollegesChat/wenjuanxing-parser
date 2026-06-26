"""问卷响应处理"""

import re

from pydantic.dataclasses import dataclass

from .answers import AnswerValue, ChosenOption, UserAnswer
from .base import BasicData, PolarsValue, ResponseStatus
from .questions import Questionnaire


@dataclass(frozen=True)
class QuestionnaireResponse:
    answers: dict[int, UserAnswer]
    metadata: BasicData | None = None

    @classmethod
    def parse_from_dict(
        cls,
        meta_data: BasicData | None,
        row_answers_dict: dict[int, list[PolarsValue] | PolarsValue],
        questions_map: Questionnaire,
    ) -> "QuestionnaireResponse":
        """【独立步骤 1】纯粹的数据解析层：将原始多维/扁平数据无痛解包为结构化对象，不含任何业务校验。"""
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
                        for p in re.split(r"[┋┦]", raw_str):
                            s = p.strip()
                            if s == "(空)":
                                parts.append(ResponseStatus.EMPTY)
                            elif s == "(跳过)":
                                parts.append(ResponseStatus.SKIPPED)
                            else:
                                parts.append(s)

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
                        parts = [p.strip() for p in raw_str.split("┋") if p.strip()]
                        parsed_value = (
                            [cls._parse_single_option(p) for p in parts]
                            if parts
                            else None
                        )
                    elif question.type == "text_area":
                        parsed_value = raw_str

            # 仅组装干净的数据，校验属性保持默认值
            answers[q_num] = UserAnswer(value=parsed_value)

        return cls(metadata=meta_data, answers=answers)

    def validate(self, questions_map: Questionnaire) -> "QuestionnaireResponse":
        """【独立步骤 2】纯粹的业务校验层：传入配置元数据，对当前已解析的答卷数据动态计算弱校验，返回带状态的新答卷。"""
        validated_answers: dict[int, UserAnswer] = {}

        for q_num, user_ans in self.answers.items():
            question = questions_map.get(q_num)
            if not question:
                # 若题库里没配置该题，保持解析原样
                validated_answers[q_num] = user_ans
                continue

            parsed_value = user_ans.value
            is_valid = True
            error_msg = None

            # 校验规则 1：必填项检查 (Required Constraint)
            if question.required:
                if parsed_value is None:
                    is_valid = False
                    error_msg = "该题为必填项，但受访者未填写。"
                elif parsed_value in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED):
                    is_valid = False
                    error_msg = f"该题为必填项，但当前处于特殊状态: {parsed_value}。"
                elif isinstance(parsed_value, list) and len(parsed_value) == 0:
                    is_valid = False
                    error_msg = "该多选题为必选项，但未勾选任何选项。"
                elif isinstance(parsed_value, list):
                    if any(
                        v == "" or v in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED)
                        for v in parsed_value
                    ):
                        is_valid = False
                        error_msg = "该填空题为必填项，但存在未完成填写的空格。"

            # 校验规则 2：正则表达式匹配检查 (Regex Constraint) -> 仅作用于填空题
            if (
                is_valid
                and question.type == "fill_blank"
                and isinstance(parsed_value, list)
            ):
                regex_rules = getattr(question, "regex", [])
                for i, part in enumerate(parsed_value):
                    if i < len(regex_rules):
                        rule = regex_rules[i]
                        if (
                            part in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED)
                            or part == ""
                        ):
                            if question.required:
                                is_valid = False
                                error_msg = f"第 {i + 1} 个空格未填写。"
                                break
                            continue

                        if not re.match(rule, str(part)):
                            is_valid = False
                            error_msg = f"第 {i + 1} 个空格填写的文本 '{part}' 未通过格式校验规则。"
                            break

            validated_answers[q_num] = UserAnswer(
                value=parsed_value, is_valid=is_valid, error_msg=error_msg
            )

        # 返回打上验证标记的新对象实例
        return self.__class__(metadata=self.metadata, answers=validated_answers)

    @classmethod
    def from_clean_dict(
        cls,
        meta_data: BasicData | None,
        row_answers_dict: dict[int, list[PolarsValue] | PolarsValue],
        questions_map: Questionnaire,
    ) -> "QuestionnaireResponse":
        """【向后兼容管线】顺序调用解析和验证，保证上游原有调用代码无需任何修改。"""
        response = cls.parse_from_dict(meta_data, row_answers_dict, questions_map)
        return response.validate(questions_map)

    @staticmethod
    def _parse_single_option(raw_str: str) -> ChosenOption:
        """解析问卷星导出的带附加文本的选项 (如: 选项名〖附加文本〗)"""
        if "〖" in raw_str and raw_str.endswith("〗"):
            parts = raw_str.split("〖", 1)
            return ChosenOption(
                text=parts[0].strip(), additional_text=parts[1].rstrip("〗").strip()
            )
        if "(" in raw_str and raw_str.endswith(")"):
            parts = raw_str.split("(", 1)
            return ChosenOption(
                text=parts[0].strip(), additional_text=parts[1].rstrip(")").strip()
            )
        return ChosenOption(text=raw_str, additional_text=None)
