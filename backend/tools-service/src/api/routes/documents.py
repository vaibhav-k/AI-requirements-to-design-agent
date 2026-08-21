"""``POST /tools/technical-design/export`` - render a technical design
document to ``.docx``.

The deterministic half of the Technical Writer agent pipeline: the
orchestrator's ``AgentFrameworkTechnicalWriterAgent`` produces the
structured document (an LLM call, so it belongs on the orchestrator);
this endpoint does the actual ``.docx`` rendering, which needs no model
call - see ``src/infrastructure/document_export.py``. Reached over MCP
via ``backend/mcp-wrapper``, same as ``diagrams``/``validation``/
``work_breakdown``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.domain.errors import TechnicalDesignExportError
from src.domain.technical_design import (
    TechnicalDesignExport,
    TechnicalDesignExportRequest,
)
from src.infrastructure.document_export import TechnicalDesignExporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/technical-design", tags=["technical-design"])

_exporter = TechnicalDesignExporter()


@router.post("/export")
async def export(request: TechnicalDesignExportRequest) -> TechnicalDesignExport:
    """Render ``request.document`` to ``.docx``, embedding the
    architecture diagram rendered from ``request.design`` and a
    traceability appendix built from ``request.requirements``/
    ``request.work_breakdown``.

    Returns the ``TechnicalDesignExport`` (base64 ``.docx`` bytes plus
    rendering summary) directly on success. On failure, responds ``422``
    with the error message in ``detail`` - the caller
    (``backend/mcp-wrapper``) surfaces that back to the orchestrator as a
    ``TechnicalDesignExportError``.
    """

    try:
        return _exporter.export(request)
    except TechnicalDesignExportError as exc:
        logger.info("Technical design export failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
