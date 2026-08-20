"""``POST /tools/work-breakdown/export`` - validate a work breakdown's
traceability and render it to CSV.

The deterministic half of the Work Breakdown Agent pipeline: the
orchestrator's ``AgentFrameworkWorkBreakdownAgent`` produces the
structured Feature -> Story -> Task artifact (an LLM call, so it belongs
on the orchestrator); this endpoint does the traceability checking and
CSV rendering, neither of which needs a model call - see
``src/infrastructure/work_breakdown_export.py``. Reached over MCP via
``backend/mcp-wrapper``, same as ``diagrams``/``validation``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.domain.errors import WorkBreakdownExportError
from src.domain.work_breakdown import WorkBreakdownExport, WorkBreakdownExportRequest
from src.infrastructure.work_breakdown_export import WorkBreakdownExporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/work-breakdown", tags=["work-breakdown"])

_exporter = WorkBreakdownExporter()


@router.post("/export")
async def export(request: WorkBreakdownExportRequest) -> WorkBreakdownExport:
    """Validate ``request.breakdown`` against ``request.requirements``/
    ``request.design`` and render it to CSV.

    Returns the ``WorkBreakdownExport`` (CSV text plus validation
    summary) directly on success. On failure, responds ``422`` with the
    validation error message in ``detail`` - the caller
    (``backend/mcp-wrapper``) surfaces that back to the orchestrator as a
    ``WorkBreakdownExportError``.
    """

    try:
        return _exporter.export(request)
    except WorkBreakdownExportError as exc:
        logger.info("Work breakdown export failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
