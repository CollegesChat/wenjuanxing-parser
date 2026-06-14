from __future__ import annotations

from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, Literal, Self

import pandas as pd
from pydantic import Field, TypeAdapter, model_validator
from pydantic.dataclasses import dataclass

# 1. 基础类型别名
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


@dataclass(
    frozen=True, kw_only=True
)  # ✨ 核心修复：开启 kw_only 完美解决继承默认值冲突
class Question:
    """题目定义的基类"""

    num: int  # 题号（非常重要！解耦后全靠题号进行 Mapping 关联）
    title: str = ''  # 题干
    type: QuestionType = 'radio'
    required: bool = True
    prompt: str | None = None  # 填报提示/说明


@dataclass(frozen=True, kw_only=True)
class RadioQuestion(Question):
    options: list[Option]  # 单选题也有多个选项供人选择，所以是 list[Option]
    type: Literal['radio'] = 'radio'


@dataclass(frozen=True, kw_only=True)
class CheckboxQuestion(Question):
    options: list[Option]  # 多选题
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
    """
    专门用来存放【被选中选项】的详细数据。
    完美解决：选了“断电”，同时附带写了“晚上11点”的场景。
    """

    text: str  # 选中的选项文本，如 "断电"
    additional_text: str | None = None  # 该选项后面附带的文本，如 "晚上11点断电"


# 单选：最终只可能有一个选中项
type RadioAnswer = ChosenOption

# 多选：可能有多个选中项，每个选中项都可能自带或不带附加文本
type CheckboxAnswer = list[ChosenOption]

# 填空：依然保持纯文本列表（按空格顺序）
type FillBlankAnswer = list[str]

# 问答：依然是一大段纯文本
type TextAreaAnswer = str

# 统一的答案值类型
type AnswerValue = (
    RadioAnswer | CheckboxAnswer | FillBlankAnswer | TextAreaAnswer | None
)


@dataclass(frozen=True)
class UserAnswer:
    """
    现在的 UserAnswer 容器，即使面对最复杂的组合多选题，
    也能以极高的精度不丢失任何数据地装载。
    """

    value: AnswerValue


@dataclass(frozen=True)
class QuestionnaireResponse:
    metadata: BasicData
    answers: dict[int, UserAnswer]

    @classmethod
    def from_clean_dict(
        cls,
        meta_data: BasicData,
        row_answers_dict: dict[int, PandasValue],
        questions_map: dict[int, Question],
    ) -> QuestionnaireResponse:
        """
        根据列驱动解析出的标准数据组装单行响应。
        row_answers_dict 此时原生为 { int(题号): 填报文本 }
        """
        answers: dict[int, UserAnswer] = {}

        for q_num, question in questions_map.items():
            raw_value = row_answers_dict.get(q_num)

            # 💡 核心数据切分与反序列化（留空，待后续补充各题型切割逻辑）
            # 目前统一封装为 None 占位
            answers[q_num] = UserAnswer(value=None)

        return cls(metadata=meta_data, answers=answers)


@dataclass(frozen=True)
class QuestionnaireData:
    data: list[QuestionnaireResponse]

    @classmethod
    def from_dataframe(
        cls, df: pd.DataFrame, questions_map: dict[int, Question]
    ) -> QuestionnaireData:
        # 安全锁：踢掉由于尾部空行产生的空白行
        df_cleaned_rows = df.dropna(subset=['序号'])

        # 1. 建立【列名映射字典】：{"原始中文字符串": 题号(int) / "meta_xxx"}
        rename_map: dict[str, str | int] = {
            '序号': 'meta_num',
            '提交答卷时间': 'meta_date',
            '所用时间': 'meta_time',
            '来源': 'meta_source',
            '来源详情': 'meta_detail',
            '来自IP': 'meta_ip',
        }

        for col_name in df_cleaned_rows.columns:
            if col_name in rename_map:
                continue
            for q_num in questions_map.keys():
                print(col_name)
                if col_name.startswith(f'{q_num}') or f'Q{q_num}' in col_name:
                    rename_map[col_name] = q_num
                    break

        # 2. 矩阵改名、过滤并导出默认的列驱动嵌套字典
        df_cleaned_cols = df_cleaned_rows.rename(columns=rename_map)[
            list(rename_map.values())
        ]
        matrix_dict = df_cleaned_cols.to_dict(orient='dict')

        # 3. 横向聚合拼装行响应列表
        parsed_responses: list[QuestionnaireResponse] = []
        for idx in df_cleaned_cols.index:
            meta_data = cls._build_basic_data_from_matrix(matrix_dict, idx)
            row_answers_dict: dict[int, PandasValue] = {
                q_num: matrix_dict[q_num][idx]
                for q_num in questions_map.keys()
                if q_num in matrix_dict
            }
            response = QuestionnaireResponse.from_clean_dict(
                meta_data, row_answers_dict, questions_map
            )
            parsed_responses.append(response)

        # 4. 利用 TypeAdapter 一次性灌入 Pydantic 展开严格校验
        adapter = TypeAdapter(cls)
        return adapter.validate_python({'data': parsed_responses})

    @staticmethod
    def _build_basic_data_from_matrix(matrix_dict: dict, idx: int) -> BasicData:
        """从列驱动嵌套字典中，通过行索引 idx 精准组装 BasicData 元数据"""
        raw_date = matrix_dict['meta_date'][idx]

        answer_date = pd.to_datetime(raw_date).to_pydatetime()
        raw_time = matrix_dict['meta_time'][idx]
        seconds = int(raw_time.replace('秒', ''))

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
