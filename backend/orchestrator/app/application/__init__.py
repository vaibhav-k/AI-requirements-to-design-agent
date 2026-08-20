"""Application layer (Clean Architecture - use cases and ports).

Use cases here orchestrate domain entities (``app.domain``) to satisfy
one specific application goal (e.g. "analyze free text into structured
requirements"). They depend only on the domain layer and on *ports*
(``app.application.ports`` - ``typing.Protocol`` interfaces) that this
layer defines but never implements.

Concrete implementations of those ports live in ``app.infrastructure``
(Azure OpenAI/Microsoft Agent Framework, Azure Blob Storage, Cosmos DB,
Graphviz, ...). This is the Dependency Inversion Principle at the heart
of Clean Architecture: the inner layer (application) owns the
interface; the outer layer (infrastructure) depends on and implements
it - never the reverse. Nothing in this package may import
``app.infrastructure``, ``app.api``, ``app.web``, or ``app.mcp``.
"""

from __future__ import annotations
