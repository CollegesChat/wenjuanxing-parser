from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter
from yaml12 import parse_yaml

from .models import (
    CheckboxQuestion,
    FillBlankQuestion,
    Option,
    Question,
    RadioQuestion,
    TextAreaQuestion,
)


def load_questions_from_yaml(yaml_path: str | Path) -> dict[int, Question]:
    with open(yaml_path, 'r', encoding='utf-8') as f:
        yaml_text = f.read()

    raw_data: Any = parse_yaml(yaml_text)

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

            adapter = TypeAdapter(target_class)
            questions_map[q_num] = adapter.validate_python(config)

    return questions_map
