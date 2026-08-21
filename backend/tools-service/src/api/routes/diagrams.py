"""``POST /tools/diagrams/generate`` - render a design to the two
architecture-generation-phase diagrams (Logical Architecture + Azure
Service Mapping).

The deterministic half of what ``app/design/session.py``'s
``DiagramRendererPort`` used to call in-process on the orchestrator (see
``ArchitectureDiagramGenerator`` in ``src/infrastructure/diagram.py``).
Reached over MCP via ``backend/mcp-wrapper``, never called directly by
the orchestrator - see the root README's architecture section.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.domain.design import DiagramMetadata, SystemDesignArtifact
from src.domain.errors import DiagramGenerationError
from src.infrastructure.diagram import ArchitectureDiagramGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/diagrams", tags=["diagrams"])

_generator = ArchitectureDiagramGenerator()


class GenerateDiagramsRequest(BaseModel):
    """Request body for ``/tools/diagrams/generate``.

    ``version``/``generated_at`` are supplied by the caller (the
    orchestrator's ``ArchitectureSession``, which already knows the
    design version being persisted and the current time) rather than
    computed here - the diagram-metadata block must be built
    deterministically from real values, never invented, per the
    architecture-generation phase's metadata requirement.
    """

    design: SystemDesignArtifact
    version: int = 1
    generated_at: str = "TBD"


def _metadata(
    title: str, description: str, request: GenerateDiagramsRequest
) -> DiagramMetadata:
    return DiagramMetadata(
        title=title,
        description=description,
        scope=request.design.architecture_summary[:280],
        author="TBD",
        version=request.version,
        last_updated=request.generated_at,
        external_references=[],
    )


@router.post("/generate")
async def generate(request: GenerateDiagramsRequest) -> dict[str, str]:
    """Render ``design`` as both required architecture diagrams.

    Returns ``{"logical_svg": "<svg>...</svg>", "azure_mapping_svg":
    "<svg>...</svg>"}`` rather than a bare pair, so a client can
    trivially distinguish a rendering failure (below) from a
    successful-but-empty result and so the response shape matches
    ``validate``'s JSON-object convention.
    """

    try:
        logical_svg = _generator.generate_logical(
            request.design,
            _metadata(
                "Logical Architecture Diagram",
                "Technology-agnostic components, actors, and their "
                "interactions/trust boundaries.",
                request,
            ),
        )
        azure_svg = _generator.generate_azure_mapping(
            request.design,
            _metadata(
                "Azure Service Mapping Diagram",
                "Every major logical component mapped to its concrete "
                "Azure service implementation, plus supporting Azure "
                "services.",
                request,
            ),
        )
    except DiagramGenerationError as exc:
        logger.exception("Diagram generation failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Diagram generation failed: {exc}",
        ) from exc
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Unexpected error generating diagram")
        if type(exc).__name__ in {"ExecutableNotFound", "FileNotFoundError"}:
            detail = (
                "Graphviz 'dot' executable not found; install the graphviz "
                "system package (the tools-service Dockerfile does this via "
                "apt-get)."
            )
        else:
            detail = f"Diagram generation failed: {type(exc).__name__}: {exc}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail
        ) from exc

    return {"logical_svg": logical_svg, "azure_mapping_svg": azure_svg}
