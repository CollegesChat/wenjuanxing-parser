import json

from pydantic import TypeAdapter

from wenjuanxing_parser._models.questions import CustomSchemaGenerator
from wenjuanxing_parser.models import AnyQuestion

print(
    json.dumps(
        TypeAdapter(list[AnyQuestion]).json_schema(
            schema_generator=CustomSchemaGenerator
        ),
        indent=4,
        ensure_ascii=False,
    )
)