from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError
from yaml12 import parse_yaml

from .models import (
    CheckboxQuestion,
    FillBlankQuestion,
    Option,
    Question,
    RadioQuestion,
    TextAreaQuestion,
)


def _find_yaml_line(yaml_text: str, q_num: int, loc_path: list[str | int]) -> int:
    """【高性能行号反查定位器】
    根据题号和 Pydantic 错误轨迹，在原始 YAML 文本中秒级检索最接近的行号。
    """
    lines = yaml_text.splitlines()
    target_line = 1

    # 第一步：锁定题号所在的起始行
    q_start_idx = 0
    for idx, line in enumerate(lines):
        if f'num:{q_num}' in line.replace(' ', '') or f"num: '{q_num}'" in line:
            q_start_idx = idx
            target_line = idx + 1
            break

    # 第二步：根据错误轨迹（如 ['options', 0]），在题目范围内进一步向下精确向下追踪
    current_idx = q_start_idx
    for path_node in loc_path:
        if isinstance(path_node, str):
            # 寻找类似 options: 或 regex: 的特征行
            for idx in range(current_idx, len(lines)):
                if f'{path_node}:' in lines[idx]:
                    current_idx = idx
                    target_line = idx + 1
                    break
        elif isinstance(path_node, int) and path_node >= 0:
            # 如果是列表索引（如第 0 个选项），向下数对应的出现次数
            occurrence = 0
            for idx in range(current_idx, len(lines)):
                # 如果遇到了下一道题的标志，立刻终止，防止越界飘到别的题目
                if idx > current_idx and 'num:' in lines[idx]:
                    break
                # YAML 列表项以 "-" 开头
                if lines[idx].strip().startswith('-'):
                    if occurrence == path_node:
                        current_idx = idx
                        target_line = idx + 1
                        break
                    occurrence += 1

    return target_line


def load_questions_from_yaml(yaml_path: str | Path) -> dict[int, Question]:
    """【类型安全版】py-yaml12 驱动题库加载器"""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        yaml_text = f.read()

    # 1. 明确告诉类型检查器，这里我们强制期待它是 Any 类型或者通过断言清洗
    raw_data: Any = parse_yaml(yaml_text)

    # 防御性守护：如果 YAML 压根不是个列表结构，直接返回空字典，防止下游崩溃
    if not isinstance(raw_data, list):
        return {}

    type_to_class = {
        'radio': RadioQuestion,
        'checkbox': CheckboxQuestion,
        'fill_blank': FillBlankQuestion,
        'text_area': TextAreaQuestion,
    }

    questions_map: dict[int, Question] = {}

    for item in raw_data:
        if not isinstance(item, dict):
            continue

        config = cast(dict[str, Any], item)

        if config.get('num') is None:
            continue

        q_num = int(config['num'])
        q_type = str(config.get('type', 'radio'))
        target_class = type_to_class.get(q_type, RadioQuestion)

        if 'options' in config and isinstance(config['options'], list):
            config['options'] = [
                Option(**cast(dict[str, Any], opt))
                for opt in config['options']
                if isinstance(opt, dict)
            ]

        # 触发 Pydantic 严格校验
        try:
            adapter = TypeAdapter(target_class)
            questions_map[q_num] = adapter.validate_python(config)
        except ValidationError as e:
            err = e.errors()[0]
            loc_list = list(err['loc'])
            loc_path = " -> ".join(str(p) for p in loc_list)

            # ⚡ 核心魔法：计算出该错误在 YAML 文件中的具体行号
            line_num = _find_yaml_line(yaml_text, q_num, loc_list)

            print('\nYAML 题库配置失败')
            print(f'错误定位: File "{yaml_path}", line {line_num}')
            print(f'错误上下文: 题号 [{q_num}] 内部的 -> {loc_path}')
            print(f'错误原因: {err["msg"]}\n')

            raise SystemExit(1)

    return questions_map
