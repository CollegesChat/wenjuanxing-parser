"""从数据框懒加载解析问卷数据"""

import math
import os
import re
import weakref
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Self

import polars as pl

from .base import IP, BasicData, PolarsValue
from .questions import AnyQuestion
from .response import QuestionnaireResponse

_ctx_registry: dict[int, dict[str, Any]] = {}
_next_ctx_id: int = 0


def _build_basic_data(matrix_dict: dict, idx: int) -> BasicData:
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


def _parse_row(ctx_id: int, idx: int) -> QuestionnaireResponse:
    ctx = _ctx_registry[ctx_id]
    matrix_dict = ctx["matrix_dict"]
    q_resolved_groups = ctx["q_resolved_groups"]
    questions_map = ctx["questions_map"]
    meta_extractor = ctx["meta_extractor"]
    df_ref = ctx["df_ref"]
    validate = ctx["validate"]

    if meta_extractor is not None:
        meta_data = meta_extractor(df_ref, idx)
    else:
        meta_data = _build_basic_data(matrix_dict, idx)

    row_answers_dict: dict[int, list[PolarsValue] | PolarsValue] = {}
    for q_num, col_dicts in q_resolved_groups.items():
        if len(col_dicts) == 1:
            row_answers_dict[q_num] = col_dicts[0][idx]
        else:
            row_answers_dict[q_num] = [col_dict[idx] for col_dict in col_dicts]

    if validate:
        return QuestionnaireResponse.from_clean_dict(
            meta_data=meta_data,
            row_answers_dict=row_answers_dict,
            questions_map=questions_map,
        )
    return QuestionnaireResponse.parse_from_dict(
        meta_data=meta_data,
        row_answers_dict=row_answers_dict,
        questions_map=questions_map,
    )


def _worker_parse_chunk(args: tuple[int, list[int]]) -> list[QuestionnaireResponse]:
    ctx_id, chunk = args
    return [_parse_row(ctx_id, idx) for idx in chunk]


@dataclass(frozen=True)
class QuestionnaireData:
    _height: int = field(repr=False)
    _ctx_id: int = field(repr=False)

    @classmethod
    def from_dataframe(
        cls,
        df: pl.DataFrame,
        questions_map: Mapping[int, AnyQuestion],
        meta_extractor: Callable[[pl.DataFrame, Any], BasicData | None] | None = None,
        q_num_extractor: Callable[[str], int | None] | None = None,
        validate: bool = False,
    ) -> Self:
        global _next_ctx_id
        df_cleaned_rows = df.clone()

        def default_q_num_extractor(col_name: str) -> int | None:
            match = re.match(r"^(\d+)[、\.]", col_name)
            return int(match.group(1)) if match else None

        get_q_num = q_num_extractor or default_q_num_extractor

        rename_map = {
            "序号": "meta_num",
            "提交答卷时间": "meta_date",
            "所用时间": "meta_time",
            "来源": "meta_source",
            "来源详情": "meta_detail",
            "来自IP": "meta_ip",
        }

        q_col_groups: dict[int, list[str]] = {}
        for col in df_cleaned_rows.columns:
            if col in rename_map:
                continue
            q_num = get_q_num(str(col))
            if q_num is not None and q_num in questions_map:
                q_col_groups.setdefault(q_num, []).append(str(col))

        valid_rename_map = {
            k: v for k, v in rename_map.items() if k in df_cleaned_rows.columns
        }
        df_meta_renamed = df_cleaned_rows.rename(valid_rename_map)
        matrix_dict = df_meta_renamed.to_dict(as_series=False)

        q_resolved_groups = {
            q_num: [matrix_dict[col] for col in columns]
            for q_num, columns in q_col_groups.items()
        }

        ctx_id = _next_ctx_id
        _next_ctx_id += 1
        _ctx_registry[ctx_id] = {
            "matrix_dict": matrix_dict,
            "q_resolved_groups": q_resolved_groups,
            "questions_map": questions_map,
            "meta_extractor": meta_extractor,
            "df_ref": df_cleaned_rows,
            "validate": validate,
        }
        instance = cls(_height=df_cleaned_rows.height, _ctx_id=ctx_id)
        weakref.finalize(instance, _ctx_registry.pop, ctx_id, None)
        return instance

    def __iter__(self) -> Iterator[QuestionnaireResponse]:
        threshold = (os.cpu_count() or 4) * 2000
        if self._height < threshold:
            for idx in range(self._height):
                yield _parse_row(self._ctx_id, idx)
        else:
            n_workers = os.cpu_count() or 4
            chunk_size = math.ceil(self._height / n_workers)
            chunks = [
                list(range(s, min(s + chunk_size, self._height)))
                for s in range(0, self._height, chunk_size)
            ]
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                for chunk_result in pool.map(
                    _worker_parse_chunk,
                    [(self._ctx_id, c) for c in chunks],
                ):
                    yield from chunk_result

    def __len__(self) -> int:
        return self._height
