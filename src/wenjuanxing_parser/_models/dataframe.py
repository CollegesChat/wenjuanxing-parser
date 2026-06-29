"""从数据框解析问卷数据"""

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Self

import polars as pl
from pydantic import TypeAdapter
from pydantic.dataclasses import dataclass

from .base import IP, BasicData, PolarsValue
from .questions import AnyQuestion
from .response import QuestionnaireResponse


@dataclass(frozen=True)
class QuestionnaireData:
    data: list[QuestionnaireResponse]

    @classmethod
    def from_dataframe(
        cls,
        df: pl.DataFrame,
        questions_map: Mapping[int, AnyQuestion],
        meta_extractor: Callable[[pl.DataFrame, Any], BasicData | None] | None = None,
        q_num_extractor: Callable[[str], int | None]
        | None = None,  # ✨ 新增：支持自定义题号提取器
        validate: bool = False,
    ) -> Self:
        """从原生 Polars DataFrame 解析完整的问卷数据集"""
        # 防止篡改原数据，清洗前拷贝 (Polars 使用 clone)
        df_cleaned_rows = df.clone()

        # 默认的题号提取逻辑：匹配形如 "1、" 或 "12." 开始的字符串
        def default_q_num_extractor(col_name: str) -> int | None:
            match = re.match(r"^(\d+)[、\.]", col_name)
            return int(match.group(1)) if match else None

        # 优先使用用户传入的提取器
        get_q_num = q_num_extractor or default_q_num_extractor

        # 1. 建立元数据更名映射
        rename_map = {
            "序号": "meta_num",
            "提交答卷时间": "meta_date",
            "所用时间": "meta_time",
            "来源": "meta_source",
            "来源详情": "meta_detail",
            "来自IP": "meta_ip",
        }

        # 2. 动态扫描列，过滤出业务题目列，并建立 题号 -> [列名] 的映射关系
        q_col_groups: dict[int, list[str]] = {}
        for col in df_cleaned_rows.columns:
            if col in rename_map:
                continue

            # 使用提取器解析题号
            q_num = get_q_num(str(col))
            if q_num is not None and q_num in questions_map:
                q_col_groups.setdefault(q_num, []).append(str(col))

        # 3. 将元数据列更名，过滤掉不存在的列防止 Polars 抛错，并转换为字典提速处理
        valid_rename_map = {
            k: v for k, v in rename_map.items() if k in df_cleaned_rows.columns
        }
        df_meta_renamed = df_cleaned_rows.rename(valid_rename_map)
        matrix_dict = df_meta_renamed.to_dict(as_series=False)

        # 🌟 【重大优化点】提前提取题目列对应的字典引用，彻底消灭循环内的重复的列名 Hash 查找
        q_resolved_groups = {
            q_num: [matrix_dict[col] for col in columns]
            for q_num, columns in q_col_groups.items()
        }

        # 4. 横向遍历每一行 (使用 Polars 的 height 获取行数)，解耦拼装数据
        parsed_responses: list[QuestionnaireResponse] = []
        for idx in range(df_cleaned_rows.height):
            if meta_extractor is not None:
                meta_data = meta_extractor(df_cleaned_rows, idx)
            else:
                meta_data = cls._build_basic_data_from_matrix(matrix_dict, idx)

            # 汇集当前行的业务答案字典
            row_answers_dict: dict[int, list[PolarsValue] | PolarsValue] = {}
            for q_num, col_dicts in q_resolved_groups.items():
                # 🌟 优化：直接从预取内置 Python 列表通过行索引 idx 取值，耗时降至纳秒级
                if len(col_dicts) == 1:
                    row_answers_dict[q_num] = col_dicts[0][idx]
                else:
                    row_answers_dict[q_num] = [col_dict[idx] for col_dict in col_dicts]

            if validate:
                response_obj = QuestionnaireResponse.from_clean_dict(
                    meta_data=meta_data,
                    row_answers_dict=row_answers_dict,
                    questions_map=questions_map,
                )
            else:
                response_obj = QuestionnaireResponse.parse_from_dict(
                    meta_data=meta_data,
                    row_answers_dict=row_answers_dict,
                    questions_map=questions_map,
                )
            parsed_responses.append(response_obj)

        # 5. 仅在显式要求时利用 TypeAdapter 展开结构化校验
        if validate:
            adapter = TypeAdapter(cls)
            return adapter.validate_python({"data": parsed_responses})
        return cls(data=parsed_responses)

    @staticmethod
    def _build_basic_data_from_matrix(matrix_dict: dict, idx: int) -> BasicData:
        """从元数据字典矩阵中通过行索引精确组装 BasicData"""
        from ipaddress import ip_address

        raw_date = matrix_dict["meta_date"][idx]
        if isinstance(raw_date, datetime):
            answer_date = raw_date
        elif isinstance(raw_date, date):
            answer_date = datetime.combine(raw_date, datetime.min.time())
        elif isinstance(raw_date, str):
            try:
                answer_date = datetime.fromisoformat(raw_date)
            except ValueError:
                for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        answer_date = datetime.strptime(raw_date, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError(f"无法解析的时间格式: {raw_date}")
        else:
            answer_date = raw_date

        raw_time = matrix_dict["meta_time"][idx]
        seconds = int(str(raw_time).replace("秒", ""))

        raw_ip_str = str(matrix_dict["meta_ip"][idx]).strip()
        if "(" in raw_ip_str and raw_ip_str.endswith(")"):
            ip_part, location_part = raw_ip_str.split("(", 1)
            ip_str = ip_part.strip()
            location = location_part.rstrip(")").strip()
        else:
            ip_str = raw_ip_str
            location = "未知"

        return BasicData(
            answer_date=answer_date,
            num=int(matrix_dict["meta_num"][idx]),
            time_used=timedelta(seconds=seconds),
            source=str(matrix_dict["meta_source"][idx]),
            source_detail=str(matrix_dict["meta_detail"][idx]),
            ip=IP(address=ip_address(ip_str), location=location),
        )
