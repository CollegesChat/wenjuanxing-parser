"""题目定义及类型"""

from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from pydantic.json_schema import GenerateJsonSchema

from .base import QuestionType  # 保持原有的基础枚举/类型导入


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


class CleanReprModel(BaseModel):
    """
    最顶层基类：统一锁死严格禁止未知字段和冻结属性。
    下属所有子类模型（包括 Option、Question 等）将自动无缝继承此家规，绝不覆盖！
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    def __repr_args__(self) -> list[tuple[str | None, Any]]:
        original_args = super().__repr_args__()
        # 显式区分 False 和 0，过滤掉 None、False、空字符串
        return [
            (k, v)
            for k, v in original_args
            if v is not None and v is not False and v != ""
        ]


class AdditionalInfo(CleanReprModel):
    # 🌟 删除了 model_config，自动完美继承父类的 extra="forbid" 和 frozen=True
    prompt: str | None = None
    required: bool = False


class Option(CleanReprModel):
    """选项的定义"""

    # 🌟 删除了 model_config，确保选项深处的未知字段也能被 forbid 锁死
    text: str  # 选项文本，如 "男"、"其他"
    additional_text: AdditionalInfo | bool = False


class Question(CleanReprModel):
    """题目定义的基类"""

    num: int  # 题号
    title: str = ""  # 题干
    type: QuestionType = "radio"
    required: bool = True
    prompt: str | None = None  # 填报提示/说明


class RadioQuestion(Question):
    options: list[Option]
    type: Literal["radio"] = "radio"


class CheckboxQuestion(Question):
    options: list[Option]
    type: Literal["checkbox"] = "checkbox"


class TextAreaQuestion(Question):
    type: Literal["text_area"] = "text_area"
    length_limit: int | None = None


class FillBlankQuestion(Question):
    blank_count: int = Field(
        2, ge=2, description="fill_blank 类型的多项填空题，空格数必须大于 1"
    )
    regex: list[str] | None = None
    type: Literal["fill_blank"] = "fill_blank"

    @model_validator(mode="after")
    def validate_fill_blank_constraints(self):
        # 校验正则规则数量与格子数是否匹配
        if self.regex and len(self.regex) != self.blank_count:
            raise ValueError(
                f"[题号 {self.num}] 校验失败: 该填空题声明了有 {self.blank_count} 个空格，"
                f"但你却配置了 {len(self.regex)} 个正则表达式校验规则！"
            )
        return self


def _infer_question_type(v: Any) -> Any:
    """静默推导文本题型：当未指定或为 text 时，根据特征转换为 fill_blank 或 text_area"""
    if isinstance(v, dict):
        q_type = v.get("type")
        if q_type in (None, "text"):
            if "blank_count" in v or isinstance(v.get("regex"), list):
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
