"""基准测试：对比 from_dataframe 开启/关闭验证的性能差异"""

import time

import polars as pl
import pytest
from yaml12 import parse_yaml

from wenjuanxing_parser.loader import load_questions_from_yaml
from wenjuanxing_parser.models import QuestionnaireData

YAML_CONTENT = """
- num: 1
  title: 你的性别？
  type: radio
  required: true
  options:
    - text: 男
    - text: 女
    - text: 其他
- num: 2
  title: 你的学校全称是？
  type: text_area
  required: true
- num: 3
  title: 你的年级？
  type: radio
  required: true
  options:
    - text: 大一
    - text: 大二
    - text: 大三
    - text: 大四
    - text: 研究生
    - text: 其他
- num: 4
  title: 你喜欢的运动（可多选）？
  type: checkbox
  required: false
  options:
    - text: 篮球
    - text: 足球
    - text: 跑步
    - text: 游泳
    - text: 其他
- num: 5
  title: 你的自我介绍
  type: text_area
  required: false
"""

LONG_TEXTS = [
    "我是一名热爱计算机科学的大学生，平时喜欢研究各种开源项目，尤其是 Python 生态中的数据处理和机器学习相关的库。在校期间参与了多个课程项目和竞赛，积累了丰富的团队协作经验。",
    "大家好，我来自一个偏远的小山村，通过自己的努力考上了这所大学。我特别喜欢编程，尤其是前端开发，曾经在多个开源项目中贡献过代码。课余时间我喜欢跑步和阅读。",
    "我是一名研究生，研究方向是自然语言处理。在实验室里我主要负责大语言模型的微调与部署工作，对 PyTorch、Transformers 等框架非常熟悉。",
    "我是一名大三学生，正在准备考研。平时喜欢打篮球和游泳，也喜欢听音乐和看电影。",
    "我来自台湾，目前在大陆交换学习。对人工智能和数据科学有浓厚的兴趣，正在学习机器学习的相关课程。",
    "我是一名计算机科学与技术专业的学生，对网络安全非常感兴趣，曾经参加过多次 CTF 比赛并获得过不错的成绩。",
    "我是一名大一新生，对大学生活充满期待。虽然目前还没有确定具体的专业方向，但对人工智能和量子计算都很感兴趣。",
    "我是一名即将毕业的本科生，已经拿到了几家互联网公司的 offer。大学期间我积极参与实习，在多家知名企业积累了丰富的工作经验。",
]

ROW_COUNT = 20_000


@pytest.fixture(scope="module")
def benchmark_data():
    yaml_obj = parse_yaml(YAML_CONTENT)
    questions_map = load_questions_from_yaml(yaml_obj)

    genders = ["男", "女", "其他〖非二元性别〗"]
    grades = ["大一", "大二", "大三", "大四", "研究生〖硕士〗", "研究生〖博士〗"]
    sports_pool = ["篮球", "足球", "跑步", "游泳", "其他〖攀岩〗", "其他〖滑板〗"]

    rows = []
    for i in range(1, ROW_COUNT + 1):
        if i % 50 == 0:
            gender_val = "(空)"
        elif i % 7 == 0:
            gender_val = "其他〖具体就不告诉你〗"
        else:
            gender_val = genders[i % len(genders)]

        if i % 40 == 0:
            grade_val = "(跳过)"
        elif i % 11 == 0:
            grade_val = "研究生〖直博生在读〗"
        else:
            grade_val = grades[i % len(grades)]

        if i % 5 == 0:
            sport_val = "篮球┋足球┋游泳"
        elif i % 5 == 1:
            sport_val = "其他〖极限飞盘〗┋跑步"
        elif i % 5 == 2:
            sport_val = "(空)"
        elif i % 5 == 3:
            sport_val = "足球┋其他〖冰球〗"
        else:
            sport_val = "跑步"

        if i % 30 == 0:
            intro_val = ""
        else:
            intro_val = LONG_TEXTS[i % len(LONG_TEXTS)] + (
                f" 额外填充文本段{'重复内容' * (i % 20)}。" if i % 3 == 0 else ""
            )

        rows.append({
            "序号": i,
            "提交答卷时间": f"2026-06-{(i % 28) + 1:02d} {(i % 12) + 8:02d}:{i % 60:02d}:00",
            "所用时间": f"{10 + i % 300}秒",
            "来源": ["手机", "电脑", "平板"][i % 3],
            "来源详情": f"来自第{i}号测试设备的提交记录",
            "来自IP": f"192.168.{i % 10}.{i % 254}(北京市朝阳区)",
            "1、你的性别？": gender_val,
            "2、你的学校全称是？": f"{'测试' * (i % 5 + 1)}大学{'（' + '分校区' * (i % 3) + '）' if i % 4 == 0 else ''}",
            "3、你的年级？": grade_val,
            "4、你喜欢的运动（可多选）？": sport_val,
            "5、你的自我介绍": intro_val,
        })

    df = pl.DataFrame(rows)
    return df, questions_map


def test_benchmark_validate_on(benchmark_data):
    df, questions_map = benchmark_data
    start = time.perf_counter()
    survey = QuestionnaireData.from_dataframe(df, questions_map, validate=True)
    for _ in survey:
        pass
    elapsed = time.perf_counter() - start
    print(f"\n[validate=True ] {elapsed:.4f}s  ({ROW_COUNT} rows)")


def test_benchmark_validate_off(benchmark_data):
    df, questions_map = benchmark_data
    start = time.perf_counter()
    survey = QuestionnaireData.from_dataframe(df, questions_map, validate=False)
    for _ in survey:
        pass
    elapsed = time.perf_counter() - start
    print(f"\n[validate=False] {elapsed:.4f}s  ({ROW_COUNT} rows)")
