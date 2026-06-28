import argparse
import sys
from pathlib import Path

import polars as pl
from yaml12 import parse_yaml

from wenjuanxing_parser import load_questions_from_yaml
from wenjuanxing_parser._models.questions import CustomSchemaGenerator

from .models import (
    AnyQuestion,
    ChosenOption,
    QuestionnaireData,
    ResponseStatus,
)


def load_questions(config_path: Path) -> dict[int, AnyQuestion]:
    """读取 YAML 并利用 Pydantic 自动反序列化"""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = parse_yaml(f.read())

    return load_questions_from_yaml(raw)  # type: ignore


def load_dataframe(data_path: Path) -> pl.DataFrame:
    """自动识别扩展名并使用 Polars 读取数据"""
    suffix = data_path.suffix.lower()
    if suffix == ".csv":
        return pl.read_csv(data_path)
    elif suffix == ".xlsx":
        return pl.read_excel(data_path, engine="calamine")
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，仅支持 .csv 或 .xlsx")


def format_value(val) -> str:
    """将各种高度结构化的 AnswerValue 漂亮地扁平化为输出文字"""
    if val is None or isinstance(val, ResponseStatus):
        return ""

    if isinstance(val, ChosenOption):
        if val.additional_text:
            sep = "" if val.additional_text[0] in "，。、；：,.;:" else "，"
            return f"{val.text}{sep}{val.additional_text}"
        return val.text

    if isinstance(val, list):
        # 适用于填空题多空格或多选题组，过滤空值后用逗号串接
        parts = [format_value(v) for v in val if v]
        return "，".join(p for p in parts if p)

    return str(val)


def main():
    parser = argparse.ArgumentParser(description="问卷星数据自动解析与精简文字导出工具")
    parser.add_argument(
        "-d",
        "--data",
        type=str,
        default="data.csv",
        help="问卷数据文件路径 (支援 .csv/.xlsx，预设: data.csv)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="v2.yaml",
        help="题库定义 YAML 路径 (预设: v2.yaml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="导出文本路径 (预设直接打印到终端)",
    )

    args = parser.parse_args()
    data_path = Path(args.data)
    config_path = Path(args.config)

    # ✨ 智慧容错：如果预设的 data.csv 不存在，但旁边躺著一个 data.xlsx，自动切换
    if (
        not data_path.exists()
        and args.data == "data.csv"
        and Path("data.xlsx").exists()
    ):
        data_path = Path("data.xlsx")

    if not data_path.exists():
        print(f"❌ 错误：找不到数据文件 '{data_path}'", file=sys.stderr)
        sys.exit(1)
    if not config_path.exists():
        print(f"❌ 错误：找不到配置文件 '{config_path}'", file=sys.stderr)
        sys.exit(1)

    try:
        # 1. 载入题库与原始 DataFrame
        questions_map = load_questions(config_path)
        df = load_dataframe(data_path)

        # 2. 灌入先前写好的矩阵解析管线（包含弱校验逻辑）
        survey_data = QuestionnaireData.from_dataframe(df, questions_map)

        # 3. 横向聚合：按「题号」重新洗牌数据，组装目标文字格式
        output_lines = []
        for q_num, question in sorted(questions_map.items()):
            q_answers = []
            for response in survey_data.data:
                assert response.metadata is not None
                user_id = response.metadata.num
                ans_obj = response.answers.get(q_num)

                if ans_obj:
                    text_str = format_value(ans_obj.value).strip()
                    if text_str:
                        q_answers.append(f"A{user_id}: {text_str}")

            # 当这道题确实有人回答时，才输出题干与答案清单
            if q_answers:
                output_lines.append(f"Q: {question.title}")
                output_lines.extend(q_answers)

        # 4. 输出结果
        final_text = "\n".join(output_lines)
        if args.output:
            Path(args.output).write_text(final_text, encoding="utf-8")
            print(f"🎉 成功将结构化文本导出至: {args.output}")
        else:
            print(final_text)

    except Exception as e:
        print(f"💥 运行时发生错误: {e}", file=sys.stderr)
        raise e
        sys.exit(1)


if __name__ == "__main__":
    import json

    from pydantic import TypeAdapter

    print(
        json.dumps(
            TypeAdapter(list[AnyQuestion]).json_schema(
                schema_generator=CustomSchemaGenerator
            ),
            indent=4,
            ensure_ascii=False,
        )
    )
    main()
