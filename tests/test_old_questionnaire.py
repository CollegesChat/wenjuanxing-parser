import io
import logging
import re
from datetime import datetime, timedelta
from itertools import islice
from typing import Any

import pandas as pd
from niquests import get
from yaml12 import parse_yaml

from wenjuanxing_parser.loader import load_questions_from_yaml
from wenjuanxing_parser.models import IP, BasicData, QuestionnaireData

yaml = parse_yaml(
    get(
        url="https://github.com/CollegesChat/questionnaire/raw/refs/heads/main/v1.yaml"
    ).text
)  # type: ignore

with get(
    "https://github.com/CollegesChat/university-information/raw/refs/heads/master/questionnaires/results_desensitized.csv",
    stream=True,
) as r:
    # 过滤掉空行，并利用 islice 仅截取前 10 行的迭代器
    lines = islice(
        (line.decode() for line in r.iter_lines(decode_unicode=True) if line), 10
    )
    # 直接将迭代器传给 pd.read_csv
    df = pd.read_csv(io.StringIO("\n".join(lines)))


class LegacyBasicData(BasicData):
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"answer_date={self.answer_date!r}, "
            f"num={self.num!r})"
        )


# 使用自定义 mark 标记这是一个本地测试
def test_old():
    def meta_extractor(df: pd.DataFrame, idx: Any) -> BasicData | None:
        row = df.loc[idx]
        return LegacyBasicData(  # 4. 移除了括号末尾的硬编码逗号，确保返回纯粹的实体对象，通过 ty check 校验
            answer_date=datetime.fromisoformat(str(row['开始时间'])),
            num=int(row['答题序号']),
            time_used=timedelta(0),
            source='null',
            source_detail='null',
            ip=IP(address='127.0.0.1', location='null'),
        )

    def qnum_extractor(col_name: str) -> int | None:
        # 匹配 Q1 或 Q1:
        match = re.match(r"^[qQ](\d+)", col_name)
        return int(match.group(1)) if match else None

    questionnaire = load_questions_from_yaml(yaml)
    logging.info(
        QuestionnaireData.from_dataframe(
            df, questionnaire, meta_extractor, qnum_extractor
        )
    )
