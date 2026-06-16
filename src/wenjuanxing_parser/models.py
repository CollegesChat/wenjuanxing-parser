from __future__ import annotations

import re
from datetime import datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, Literal, Mapping, Self

import pandas as pd
from pydantic import Field, TypeAdapter, model_validator
from pydantic.dataclasses import dataclass


# 1. 基础特殊状态枚举
class ResponseStatus(StrEnum):
    EMPTY = '(空)'
    SKIPPED = '(跳过)'


# 2. 基础类型别名
type QuestionType = Literal['radio', 'checkbox', 'fill_blank', 'text_area']
type IPAddress = IPv4Address | IPv6Address
type PandasValue = str | int | float | datetime | None


@dataclass(frozen=True)
class IP:
    address: IPAddress
    location: str


@dataclass(frozen=True)
class BasicData:
    """答卷基础元数据（Excel的前几列，每人一份）"""

    answer_date: datetime
    num: int
    time_used: timedelta
    source: str
    source_detail: str
    ip: IP


@dataclass(frozen=True)
class Option:
    """选项的定义"""

    text: str  # 选项文本，如 "男"、"其他"
    has_additional: bool = False  # 是否允许附加文本（如：其他____ 后面带有填空线）


@dataclass(frozen=True, kw_only=True)
class Question:
    """题目定义的基类"""

    num: int  # 题号
    title: str = ''  # 题干
    type: QuestionType = 'radio'
    required: bool = True
    prompt: str | None = None  # 填报提示/说明


@dataclass(frozen=True, kw_only=True)
class RadioQuestion(Question):
    options: list[Option]
    type: Literal['radio'] = 'radio'


@dataclass(frozen=True, kw_only=True)
class CheckboxQuestion(Question):
    options: list[Option]
    type: Literal['checkbox'] = 'checkbox'


@dataclass(frozen=True, kw_only=True)
class FillBlankQuestion(Question):
    blank_count: int = 1  # 填空题：记录这道题有几个空格需要填
    regex: list[str]
    type: Literal['fill_blank'] = 'fill_blank'

    @model_validator(mode='after')
    def validate_regex_count_matches_blanks(self) -> Self:
        if len(self.regex) != self.blank_count:
            raise ValueError(
                f'[题号 {self.num}] 校验失败: 该填空题声明了有 {self.blank_count} 个空格，'
                f'但你却配置了 {len(self.regex)} 个正则表达式校验规则！'
            )
        return self


@dataclass(frozen=True, kw_only=True)
class TextAreaQuestion(Question):
    type: Literal['text_area'] = 'text_area'


type AnyQuestion = Annotated[
    RadioQuestion | CheckboxQuestion | FillBlankQuestion | TextAreaQuestion,
    Field(discriminator='type'),
]


@dataclass(frozen=True)
class ChosenOption:
    """存放选中选项及其附带文本的容器"""

    text: str
    additional_text: str | None = None


# 3. 细化各种题型的内部容器类型
type RadioAnswer = ChosenOption
type CheckboxAnswer = list[ChosenOption]
type FillBlankAnswer = list[str | ResponseStatus]  # 允许格子级别包含枚举值
type TextAreaAnswer = str

# 统一的答案值类型（支持整题级状态）
type AnswerValue = (
    RadioAnswer
    | CheckboxAnswer
    | FillBlankAnswer
    | TextAreaAnswer
    | ResponseStatus
    | None
)


@dataclass(frozen=True)
class UserAnswer:
    """
    带弱校验标记的答案容器。
    清洗层可以通过 if not answer.is_valid 快速定位并处理脏数据。
    """

    value: AnswerValue
    is_valid: bool = True
    error_msg: str | None = (
        None  # 用于记录具体的未通过原因（如：未匹配正则、必填项留空等）
    )


@dataclass(frozen=True)
class QuestionnaireResponse:
    metadata: BasicData
    answers: dict[int, UserAnswer]

    @classmethod
    def from_clean_dict(
        cls,
        meta_data: BasicData,
        row_answers_dict: dict[int, list[PandasValue] | PandasValue],
        questions_map: Mapping[int, Question],
    ) -> QuestionnaireResponse:
        """根据行/多列映射组装单人答卷，并同步完成弱校验。"""
        answers: dict[int, UserAnswer] = {}

        for q_num, question in questions_map.items():
            raw_value = row_answers_dict.get(q_num)

            # A. 初始化解析出的底层值
            parsed_value: AnswerValue = None

            # 1. 拦截完全缺失
            if raw_value is None or (
                not isinstance(raw_value, list) and pd.isna(raw_value)
            ):
                parsed_value = None
            else:
                # 2. 前置判定整题是否属于 (空) 或 (跳过) 状态
                if isinstance(raw_value, list):
                    check_strs = [str(v).strip() for v in raw_value if pd.notna(v)]
                else:
                    check_strs = [str(raw_value).strip()]

                if len(set(check_strs)) == 1 and check_strs[0] in ('(空)', '(跳过)'):
                    parsed_value = (
                        ResponseStatus.EMPTY
                        if check_strs[0] == '(空)'
                        else ResponseStatus.SKIPPED
                    )

                # 3. 进入各题型的具体解包派发
                elif question.type == 'fill_blank':
                    blank_count = getattr(question, 'blank_count', 1)
                    if isinstance(raw_value, list):
                        parts = []
                        for v in raw_value:
                            if pd.isna(v):
                                parts.append('')
                            else:
                                s = str(v).strip()
                                if s == '(空)':
                                    parts.append(ResponseStatus.EMPTY)
                                elif s == '(跳过)':
                                    parts.append(ResponseStatus.SKIPPED)
                                elif s.lower() == 'nan':
                                    parts.append('')
                                else:
                                    parts.append(s)
                    else:
                        raw_str = str(raw_value).strip()
                        parts = []
                        for p in re.split(r'[┋┦]', raw_str):
                            s = p.strip()
                            if s == '(空)':
                                parts.append(ResponseStatus.EMPTY)
                            elif s == '(跳过)':
                                parts.append(ResponseStatus.SKIPPED)
                            else:
                                parts.append(s)

                    if len(parts) < blank_count:
                        parts.extend([''] * (blank_count - len(parts)))
                    parsed_value = parts[:blank_count]

                else:
                    raw_str = str(raw_value).strip()
                    if not raw_str or raw_str.lower() == 'nan':
                        parsed_value = None
                    elif question.type == 'radio':
                        parsed_value = cls._parse_single_option(raw_str)
                    elif question.type == 'checkbox':
                        parts = [p.strip() for p in raw_str.split('┋') if p.strip()]
                        parsed_value = (
                            [cls._parse_single_option(p) for p in parts]
                            if parts
                            else None
                        )
                    elif question.type == 'text_area':
                        parsed_value = raw_str

            # B. ✨ 核心功能扩展：动态执行“弱校验”计算
            is_valid = True
            error_msg = None

            # 校验规则 1：必填项检查 (Required Constraint)
            if question.required:
                if parsed_value is None:
                    is_valid = False
                    error_msg = '该题为必填项，但受访者未填写。'
                elif parsed_value in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED):
                    is_valid = False
                    error_msg = (
                        f'该题为必填项，但当前处于特殊状态: {parsed_value.value}。'  # type: ignore
                    )
                elif isinstance(parsed_value, list) and len(parsed_value) == 0:
                    is_valid = False
                    error_msg = '该多选题为必选项，但未勾选任何选项。'
                elif isinstance(parsed_value, list):
                    if any(
                        v == '' or v in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED)
                        for v in parsed_value
                    ):
                        is_valid = False
                        error_msg = '该填空题为必填项，但存在未完成填写的空格。'

            # 校验规则 2：正则表达式匹配检查 (Regex Constraint) -> 仅作用于填空题
            if (
                is_valid
                and question.type == 'fill_blank'
                and isinstance(parsed_value, list)
            ):
                regex_rules = getattr(question, 'regex', [])
                for i, part in enumerate(parsed_value):
                    if i < len(regex_rules):
                        rule = regex_rules[i]
                        # 如果是非必填题目，允许其子格子为空
                        if (
                            part in (ResponseStatus.EMPTY, ResponseStatus.SKIPPED)
                            or part == ''
                        ):
                            if question.required:
                                is_valid = False
                                error_msg = f'第 {i + 1} 个空格未填写。'
                                break
                            continue

                        # 执行正则匹配检查
                        if not re.match(rule, str(part)):
                            is_valid = False
                            error_msg = f"第 {i + 1} 个空格填写的文本 '{part}' 未通过格式校验规则。"
                            break

            # 装载入带状态的 UserAnswer 容器
            answers[q_num] = UserAnswer(
                value=parsed_value, is_valid=is_valid, error_msg=error_msg
            )

        return cls(metadata=meta_data, answers=answers)

    @staticmethod
    def _parse_single_option(raw_str: str) -> ChosenOption:
        """解析问卷星导出的带附加文本的选项 (如: 选项名〖附加文本〗)"""
        if '〖' in raw_str and raw_str.endswith('〗'):
            parts = raw_str.split('〖', 1)
            return ChosenOption(
                text=parts[0].strip(), additional_text=parts[1].rstrip('〗').strip()
            )
        if '(' in raw_str and raw_str.endswith(')'):
            parts = raw_str.split('(', 1)
            return ChosenOption(
                text=parts[0].strip(), additional_text=parts[1].rstrip(')').strip()
            )
        return ChosenOption(text=raw_str, additional_text=None)


@dataclass(frozen=True)
class QuestionnaireData:
    data: list[QuestionnaireResponse]

    @classmethod
    def from_dataframe(
        cls, df: pd.DataFrame, questions_map: Mapping[int, Question]
    ) -> QuestionnaireData:
        # 安全锁：踢掉由于尾部空行产生的空白行
        df_cleaned_rows = df.dropna(subset=['序号'])

        # 1. 建立基础元数据的列改名映射
        rename_map: dict[str, str] = {
            '序号': 'meta_num',
            '提交答卷时间': 'meta_date',
            '所用时间': 'meta_time',
            '来源': 'meta_source',
            '来源详情': 'meta_detail',
            '来自IP': 'meta_ip',
        }

        # 2. 核心联动：动态解析 DataFrame 中所有业务题目的列名，并按题号建组
        # 完美兼容普通单列（如: 2、你的学校...）和多空跨列填空（如: 4、(1)... 与 4、(2)...）
        q_col_groups: dict[int, list[str]] = {}
        for col_name in df_cleaned_rows.columns:
            if col_name in rename_map:
                continue

            # 使用正则抓取列名开头的题号 (形如 "1、", "22.", "4、(1)")
            match = re.match(r'^(\d+)[、.]', str(col_name))
            if match:
                q_num = int(match.group(1))
                if q_num in questions_map:
                    q_col_groups.setdefault(q_num, []).append(col_name)

        # 3. 将元数据列更名，并转换为嵌套字典提速处理
        df_meta_renamed = df_cleaned_rows.rename(columns=rename_map)
        matrix_dict = df_meta_renamed.to_dict(orient='dict')

        # 4. 横向遍历每一行，解耦拼装数据
        parsed_responses: list[QuestionnaireResponse] = []
        for idx in df_cleaned_rows.index:
            # 组装当前的元数据
            meta_data = cls._build_basic_data_from_matrix(matrix_dict, idx)

            # 汇集当前行的业务答案字典
            row_answers_dict: dict[int, list[PandasValue] | PandasValue] = {}
            for q_num, columns in q_col_groups.items():
                if len(columns) == 1:
                    row_answers_dict[q_num] = df_cleaned_rows.loc[idx, columns[0]]
                else:
                    # 跨列数据按原列序转换为列表送入解析层
                    row_answers_dict[q_num] = [
                        df_cleaned_rows.loc[idx, col] for col in columns
                    ]

            # 转换为结构化实体
            response_obj = QuestionnaireResponse.from_clean_dict(
                meta_data=meta_data,
                row_answers_dict=row_answers_dict,
                questions_map=questions_map,
            )
            parsed_responses.append(response_obj)

        # 5. 利用 TypeAdapter 一次性灌入 Pydantic 展开结构化校验
        adapter = TypeAdapter(cls)
        return adapter.validate_python({'data': parsed_responses})

    @staticmethod
    def _build_basic_data_from_matrix(matrix_dict: dict, idx: int) -> BasicData:
        """从元数据字典矩阵中通过行索引精确组装 BasicData"""
        raw_date = matrix_dict['meta_date'][idx]
        answer_date = pd.to_datetime(raw_date).to_pydatetime()

        raw_time = matrix_dict['meta_time'][idx]
        seconds = int(str(raw_time).replace('秒', ''))

        raw_ip_str = str(matrix_dict['meta_ip'][idx]).strip()
        if '(' in raw_ip_str and raw_ip_str.endswith(')'):
            ip_part, location_part = raw_ip_str.split('(', 1)
            ip_str = ip_part.strip()
            location = location_part.rstrip(')').strip()
        else:
            ip_str = raw_ip_str
            location = '未知'

        return BasicData(
            answer_date=answer_date,
            num=int(matrix_dict['meta_num'][idx]),
            time_used=timedelta(seconds=seconds),
            source=str(matrix_dict['meta_source'][idx]),
            source_detail=str(matrix_dict['meta_detail'][idx]),
            ip=IP(address=ip_address(ip_str), location=location),
        )
