import json

from app.design.models import (
    DesignComponent,
    SystemDesignArtifact,
)
from app.mcp.server import (
    design_schema,
    validate_system_design,
)


def test_design_schema_is_valid_json() -> None:
    result = design_schema()

    schema = json.loads(result)

    assert "properties" in schema
    assert "components" in schema["properties"]
    assert "external_dependencies" in schema["properties"]


def test_mcp_validation_tool() -> None:
    design = SystemDesignArtifact(
        architecture_summary="Valid architecture.",
        components=[
            DesignComponent(
                id="api",
                name="API",
                responsibility="Handles requests.",
            )
        ],
    )

    result = validate_system_design(design.model_dump_json())

    parsed = json.loads(result)

    assert parsed["valid"] is True
