"""题目定义及类型"""

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator
from pydantic.json_schema import GenerateJsonSchema

from ..errors import BlankConfigError
from .base import CleanReprModel, QuestionType, text_equal

# 填空题空格配置类型：支持 dict 显式指定位置，或 list 混合（str 按顺序，dict 显式指定）
# BlankConfigValue 是不含 None 的那部分，供调用方在判空后使用，避免空值一路带进遍历
type BlankConfigValue = dict[int, str] | list[str | dict[int, str]]
type BlankConfig = BlankConfigValue | None


class CustomSchemaGenerator(GenerateJsonSchema):
    """
    黑魔法生成器：在导出 Schema 时，偷偷帮编辑器把 discriminator 补上。
    这样 yaml-language-server 就能瞬间开眼，100% 识别 extra="forbid" 并精准定位错别字画红线！
    """

    # 🌟 修复此处：将第二个参数修改为 mode，完美对齐 Pydantic 官方基类签名
    def generate(self, schema: Any, mode: Any = "validation") -> Any:
        json_schema = super().generate(schema, mode)

        # 1. 如果根节点就是 anyOf，注入辨识器
        if "anyOf" in json_schema:
            json_schema["discriminator"] = {"propertyName": "type"}

        # 2. 如果复用组件定义 $defs 里面有 anyOf（比如 AnyQuestion），也注入辨识器
        if "$defs" in json_schema:
            for def_schema in json_schema["$defs"].values():
                if "anyOf" in def_schema:
                    def_schema["discriminator"] = {"propertyName": "type"}

        return json_schema


class AdditionalInfo(CleanReprModel):
    # 🌟 删除了 model_config，自动完美继承父类的 extra="forbid" 和 frozen=True
    prompt: str | None = Field(None, title="提示文本")
    required: bool = Field(False, title="是否必填")


class Option(CleanReprModel):
    """选项的定义"""

    # 🌟 删除了 model_config，确保选项深处的未知字段也能被 forbid 锁死
    text: str = Field(..., title="选项文本")  # 选项文本，如 "男"、"其他"
    additional_text: AdditionalInfo | bool = Field(False, title="附加文本")

    def __eq__(self, other: object) -> bool:
        return text_equal(self.text, other)

    def __hash__(self) -> int:
        return hash(self.text)


class Question(CleanReprModel):
    """题目定义的基类"""

    num: int = Field(..., title="题号")  # 题号
    title: str = Field("", title="题干")  # 题干
    type: QuestionType = Field("radio", title="题型")
    required: bool = Field(True, title="是否必填")
    prompt: str | None = Field(None, title="填报提示")  # 填报提示/说明


class RadioQuestion(Question):
    options: list[Option] = Field(..., title="选项列表")
    type: Literal["radio"] = "radio"


class CheckboxQuestion(Question):
    options: list[Option] = Field(..., title="选项列表")
    type: Literal["checkbox"] = "checkbox"


class TextAreaQuestion(Question):
    type: Literal["text_area"] = "text_area"
    length_limit: int | None = Field(None, title="字数限制")


class FillBlankQuestion(Question):
    blank_count: int = Field(
        2,
        ge=1,
        title="空格数量",
        description="fill_blank 类型的多项填空题，空格数必须大于 1",
    )
    regex: BlankConfig = Field(
        None,
        title="正则校验规则",
        description="各空格的正则校验规则。支持混合格式：str 按顺序对应，dict 显式指定位置。少于 blank_count 时，未指定的空格不校验；多于则报错。",
    )
    type: Literal["fill_blank"] = "fill_blank"
    default_blank_text: BlankConfig = Field(
        None,
        title="默认填充文本",
        description='各空格的默认填充文本。dict 格式：键为空格序号（从1起），值为默认文本；list 格式支持混合：str 按顺序填充，dict 显式指定位置（如 ["北京", {5: "广州"}, "上海"]）。',
    )

    @staticmethod
    def _parse_mixed_list(
        items: list,
        blank_count: int,
        field_name: str,
        num: int,
    ) -> dict[int, str]:
        """解析混合格式 list，返回 dict[int, str]。"""
        result: dict[int, str] = {}
        seq_pos = 1
        for item in items:
            if isinstance(item, str):
                if item:
                    # 仅跳过已被显式 dict 占用的位置；越界判定必须在自增之前，
                    # 否则 seq_pos 一旦越界就会在 while 里无限自增。
                    while seq_pos in result:
                        seq_pos += 1
                    if seq_pos > blank_count:
                        raise BlankConfigError(
                            f"[题号 {num}] 校验失败: {field_name} 数量超过空格数 {blank_count}！"
                        )
                    result[seq_pos] = item
                    seq_pos += 1
            elif isinstance(item, dict):
                if not item:
                    continue
                for key, val in item.items():
                    if not (1 <= key <= blank_count):
                        raise BlankConfigError(
                            f"[题号 {num}] 校验失败: {field_name} 的键 {key} "
                            f"超出范围 [1, {blank_count}]！"
                        )
                    result[key] = val
                max_key = max(item.keys())
                seq_pos = max(seq_pos, max_key + 1)
        return result

    def _normalize_blank_config(
        self, value: BlankConfigValue, field_name: str, label: str
    ) -> BlankConfigValue:
        """把任意格式的空格配置统一成 dict[int, str]。

        field_name 与 label 必须分开传：越界报错里用的是字段名，数量超限报错里
        用的是人类可读名，两者历史上就不一致，合并会静默改变错误消息。
        """
        if isinstance(value, list):
            return self._parse_mixed_list(value, self.blank_count, label, self.num)

        for key in value:
            if not (1 <= key <= self.blank_count):
                raise BlankConfigError(
                    f"[题号 {self.num}] 校验失败: {field_name} 的键 {key} "
                    f"超出范围 [1, {self.blank_count}]！"
                )
        return value

    @model_validator(mode="after")
    def validate_fill_blank_constraints(self):
        if self.regex is not None:
            object.__setattr__(
                self,
                "regex",
                self._normalize_blank_config(self.regex, "regex", "regex"),
            )
        if self.default_blank_text is not None:
            object.__setattr__(
                self,
                "default_blank_text",
                self._normalize_blank_config(
                    self.default_blank_text, "default_blank_text", "默认文本"
                ),
            )
        return self


def _infer_question_type(v: Any) -> Any:
    """静默推导文本题型：当未指定或为 text 时，根据特征转换为 fill_blank 或 text_area"""
    if isinstance(v, dict):
        q_type = v.get("type")
        if q_type in (None, "text"):
            if (
                "blank_count" in v
                or isinstance(v.get("regex"), list)
                or isinstance(v.get("default_blank_text"), (list, dict))
            ):
                v["type"] = "fill_blank"
            elif "options" in v:  # 只要有 options 字段就盲猜是选择题（默认radio）
                v["type"] = "radio"
            else:
                v["type"] = "text_area"
    return v


type AnyQuestion = Annotated[
    RadioQuestion | CheckboxQuestion | FillBlankQuestion | TextAreaQuestion,  # 1. 类型
    BeforeValidator(_infer_question_type),  # 2. 元数据
]

type Questionnaire = Mapping[int, AnyQuestion]
