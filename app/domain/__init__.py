"""Domain layer (Clean Architecture innermost ring).

Everything here is a pure entity or value object: plain data plus
validation, with **zero I/O and zero dependency on any framework,
SDK, or outer layer** (`app.application`, `app.infrastructure`,
`app.api`, `app.web`, `app.mcp`). Pydantic is the one exception this
project accepts as a "shared kernel" dependency — it buys validation
and (de)serialization for free and every layer already needs to pass
these models across process/HTTP/MCP boundaries, but domain modules
must never import `openai`, `azure.*`, `agent_framework`, `fastapi`,
or anything from `app.infrastructure`/`app.api`.

See the README's "Clean Architecture Migration" section for the full
layering rationale and migration plan. As of that migration's first
slice, only the requirements bounded context
(`app.domain.requirements`) has moved here; `app.design.models` (the
architecture/design bounded context) is scheduled for a later slice
and still lives at its original location.
"""

from __future__ import annotations
