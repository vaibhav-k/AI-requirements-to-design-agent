"""``POST /tools/designs/validate`` - check a design's semantic integrity.

The deterministic half of what ``app/design/session.py``'s validator call
used to do in-process on the orchestrator (see ``ArchitectureValidator``
in ``src/infrastructure/validator.py``, moved here verbatim). Reached
over MCP via ``backend/mcp-wrapper`` - see the root README's architecture
section.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.domain.design import SystemDesignArtifact
from src.domain.errors import ArchitectureValidationError
from src.infrastructure.validator import ArchitectureValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/designs", tags=["designs"])

_validator = ArchitectureValidator()


@router.post("/validate")
async def validate(design: SystemDesignArtifact) -> dict[str, object]:
    """Validate ``design``.

    Returns ``{"valid": true, "design": {...}}`` on success. On failure,
    responds ``422`` with the validation error messages in ``detail`` -
    the caller (``backend/mcp-wrapper``) surfaces that back to the
    orchestrator as an ``ArchitectureValidationError``, the same
    exception type this raised when validation ran in-process.
    """

    try:
        validated = _validator.validate(design)
    except ArchitectureValidationError as exc:
        logger.info("Architecture validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return {"valid": True, "design": validated.model_dump(mode="json")}
