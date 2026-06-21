from pydantic import TypeAdapter

from .models import AnyQuestion, Question


def load_questions_from_yaml(raw_data: list | dict) -> dict[int, Question]:
    """直接复用 models.py 中的 AnyQuestion，实现单点维护题型推导逻辑"""
    # 兼容直接传入字典（含 questions 键）或直接传入列表的格式
    raw_list = (
        raw_data.get("questions", raw_data) if isinstance(raw_data, dict) else raw_data
    )
    if not isinstance(raw_list, list):
        return {}

    questions_map: dict[int, Question] = {}

    # 🌟 直接借用 models.py 定义的万能问题适配器
    question_adapter = TypeAdapter(AnyQuestion)

    for item in raw_list:
        if not isinstance(item, dict) or item.get("num") is None:
            continue

        # 1. Pydantic 会自动触发 _infer_question_type 完成类型推导
        # 2. 自动根据 type 匹配到正确的 Dataclass（如 TextAreaQuestion）
        # 3. 自动将嵌套的 options: list[dict] 转换成 list[Option] 实例
        q_obj = question_adapter.validate_python(item)

        questions_map[q_obj.num] = q_obj

    return questions_map
