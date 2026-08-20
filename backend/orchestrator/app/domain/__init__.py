"""Domain layer (Clean Architecture innermost ring).

Everything here is a pure entity or value object: plain data plus
validation, with **zero I/O and zero dependency on any framework,
SDK, or outer layer** (`app.application`, `app.infrastructure`,
`app.api`, `app.web`, `app.mcp`). Pydantic is the one exception this
project accepts as a "shared kernel" dependency - it buys validation
and (de)serialization for free and every layer already needs to pass
these models across process/HTTP/MCP boundaries, but domain modules
must never import `openai`, `azure.*`, `agent_framework`, `fastapi`,
or anything from `app.infrastructure`/`app.api`.

See the README's "Clean Architecture Migration" section for the full
layering rationale and migration plan. The requirements bounded context
(`app.domain.requirements`), the architecture/design bounded context
(`app.domain.design`), vision-related value objects (`app.domain.vision`),
and the requirements-to-architecture run entity (`app.domain.session`'s
`SessionRecord`) all live here.
"""

from __future__ import annotations
