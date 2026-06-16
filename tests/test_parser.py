from pathlib import Path

import pandas as pd

from wenjuanxing_parser.loader import load_questions_from_yaml
from wenjuanxing_parser.models import QuestionnaireData


def test_parser_flow(tmp_path: Path):
    """测试从 YAML 载入题库并解析 CSV 数据的完整流程"""

    # 1. 建立测试用的最小化 YAML 内容
    yaml_content = """
    - num: 2
      title: 你的学校是全称是？
      type: text_area
      required: true
      blank_count: 1
      regex:
        - "^.{4,12}$"
    """
    yaml_file = tmp_path / 'test_config.yaml'
    yaml_file.write_text(yaml_content, encoding='utf-8')

    # 2. 建立测试用的最小化 CSV 内容（栏位名称必须与问卷星导出的简体一致）
    csv_content = (
        '序号,提交答卷时间,所用时间,来源,来源详情,来自IP,2、你的学校是全称是？\n'
        '1,2026-06-16 08:00:00,10秒,无,无,127.0.0.1(本地),北京大學\n'
    )
    csv_file = tmp_path / 'test_data.csv'
    csv_file.write_text(csv_content, encoding='utf-8')

    # 3. 执行你的程式码逻辑
    questions_map = load_questions_from_yaml(yaml_file)
    df = pd.read_csv(csv_file)
    survey_data = QuestionnaireData.from_dataframe(df, questions_map)

    # 4. 断言（Assert）结果是否正确
    assert len(survey_data.data) == 1

    first_response = survey_data.data[0]
    assert first_response.metadata.num == 1
    assert first_response.metadata.ip.location == '本地'

    # 检查题目答案与校验状态
    answer_obj = first_response.answers[2]
    assert answer_obj.value == '北京大學'
    assert answer_obj.is_valid is True
