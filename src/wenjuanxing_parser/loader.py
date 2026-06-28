from collections.abc import Mapping

from pydantic import TypeAdapter

from .models import AnyQuestion


def load_questions_from_yaml(raw_data: list | dict) -> Mapping[int, AnyQuestion]:
    """直接复用 models.py 中的 AnyQuestion，实现单点维护题型推导逻辑"""
    # 兼容直接传入字典（含 questions 键）或直接传入列表的格式
    raw_list = (
        raw_data.get("questions", raw_data) if isinstance(raw_data, dict) else raw_data
    )
    if not isinstance(raw_list, list):
        return {}

    questions_map: Mapping[int, AnyQuestion] = {}
    question_adapter = TypeAdapter(AnyQuestion)

    for item in raw_list:
        if not isinstance(item, dict) or item.get("num") is None:
            continue
        q_obj = question_adapter.validate_python(item)

        questions_map[q_obj.num] = q_obj

    return questions_map
