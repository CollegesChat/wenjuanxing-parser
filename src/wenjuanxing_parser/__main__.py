from pathlib import Path

import pandas as pd

from wenjuanxing_parser.loader import load_questions_from_yaml
from wenjuanxing_parser.models import QuestionnaireData

if __name__ == '__main__':
    excel_path = Path(__file__).parent.parent.parent / 'data.xlsx'

    yaml_path = Path(__file__).parent.parent.parent / 'test.yaml'
    df = pd.read_excel(excel_path, sheet_name=0, engine='calamine')
    try:
        result = QuestionnaireData.from_dataframe(
            df,
            questions_map={},  # <-- 传空字典即可只解析basic data
        )

        print('✅ 恭喜！BasicData 全量矩阵解析测试成功！')
        print(f'📊 一次性成功加载了 {len(result.data)} 条用户基本信息。')

        if result.data:
            first_user = result.data[0].metadata
            print('\n🔍 --- 抽查第 1 条元数据解析结果 ---')
            print(f'序号: {first_user.num} (类型: {type(first_user.num)})')
            print(
                f'提交时间: {first_user.answer_date} (类型: {type(first_user.answer_date)})'
            )
            print(
                f'所用时间: {first_user.time_used} (类型: {type(first_user.time_used)})'
            )
            print(
                f'IP地址: {first_user.ip.address} (类型: {type(first_user.ip.address)})'
            )
            print(f'IP归属地: {first_user.ip.location}')
            print(df.dtypes)
            try:
                my_questions_map = load_questions_from_yaml(yaml_path)
                print(f'🎯 题库加载成功！共识别到 {len(my_questions_map)} 道题目配置。')
            except Exception as e:
                print(f'❌ 题库 YAML 校验失败，程序阻断！详情: {e}')
    except Exception:
        print('❌ BasicData 解析失败！')
        # 打印出具体的报错堆栈，方便定位是时间格式不对，还是IP括号切分崩了
        import traceback

        traceback.print_exc()
