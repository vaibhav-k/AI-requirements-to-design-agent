from __future__ import annotations

import asyncio

import pytest

from app.infrastructure.sync_bridge import run_sync


async def _return(value: object) -> object:
    return value


def test_run_sync_returns_the_coroutines_result() -> None:
    result = run_sync(_return(42), caller="test")

    assert result == 42


def test_run_sync_raises_when_called_from_a_running_event_loop() -> None:
    """The whole point of ``run_sync`` - the guard the old facade classes
    (``app/analyzer.py``, ``app/design/analyzer.py``, ``app/vision.py``)
    each duplicated so ``asyncio.run()`` never nests inside a caller's own
    running event loop, which raises a much more confusing error."""

    async def call_from_running_loop() -> None:
        run_sync(_return(1), caller="test")

    with pytest.raises(RuntimeError, match="running event loop"):
        asyncio.run(call_from_running_loop())
