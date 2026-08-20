"""``POST /tools/diagrams/generate`` - render a design to an SVG diagram.

The deterministic half of what ``app/design/session.py``'s
``DiagramRendererPort`` used to call in-process on the orchestrator (see
``ArchitectureDiagramGenerator`` in ``src/infrastructure/diagram.py``,
moved here verbatim). Reached over MCP via ``backend/mcp-wrapper``, never
called directly by the orchestrator - see the root README's architecture
section.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.domain.design import SystemDesignArtifact
from src.domain.errors import DiagramGenerationError
from src.infrastructure.diagram import ArchitectureDiagramGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/diagrams", tags=["diagrams"])

_generator = ArchitectureDiagramGenerator()


@router.post("/generate")
async def generate(design: SystemDesignArtifact) -> dict[str, str]:
    """Render ``design`` as an SVG diagram.

    Returns ``{"svg": "<svg>...</svg>"}`` rather than the raw SVG as the
    response body, so a client can trivially distinguish a rendering
    failure (below) from a successful-but-empty result and so the
    response shape matches ``validate``'s JSON-object convention.
    """

    try:
        svg = _generator.generate(design)
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

    return {"svg": svg}
