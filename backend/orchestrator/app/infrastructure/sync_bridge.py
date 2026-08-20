"""Bridge an async application-layer call into a synchronous one.

Every use case in ``app.application.use_cases`` exposes only an async
``execute()`` - pure orchestration against an async port, no opinion on
how (or whether) a caller happens to be running on an event loop. Several
callers aren't ``async`` themselves: the CLI (``app/main.py``), the MCP
tool functions (``app/mcp/server.py``), and the sync FastAPI routes
(``start_run``/``refine_run`` in ``app/api/routes/requirements.py``,
which FastAPI runs in a worker thread with no event loop of its own) all
need a synchronous call. ``run_sync`` is the one place that bridge lives,
replacing the copy-pasted ``asyncio.run(...)``-behind-a-``RuntimeError``-
guard that used to live in each of ``app/analyzer.py``,
``app/design/analyzer.py``, and ``app/vision.py``'s facade classes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")


def run_sync(coro: Coroutine[object, object, T], *, caller: str) -> T:
    """Run ``coro`` to completion and return its result.

    Raises ``RuntimeError`` if called from inside a *running* event loop
    (i.e. from an ``async def`` function) instead of deadlocking or
    crashing confusingly - ``asyncio.run`` cannot nest inside one; the
    caller should await the coroutine directly instead.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        coro.close()
        raise RuntimeError(
            f"{caller} cannot be called from a running event loop - "
            "await the underlying coroutine directly instead."
        )

    return asyncio.run(coro)
