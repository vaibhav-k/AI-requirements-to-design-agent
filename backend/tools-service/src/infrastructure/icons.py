"""Icon selection for architecture diagrams (see ``app/design/diagram.py``).

Maps a component's or external dependency's name/responsibility text to
one of a small, curated set of vendored Azure Architecture Icons under
``app/design/icons/azure/`` (see that directory's ``NOTICE.md`` for where
the PNGs came from), via keyword matching. This is a best-effort
heuristic, not an exhaustive service catalog: every component and every
external dependency still gets *some* icon, falling back to a generic
"service" or "external dependency" icon respectively when no keyword
matches, rather than mixing icon and plain-box nodes in the same
diagram.
"""

from __future__ import annotations

from pathlib import Path

_ICONS_DIR = Path(__file__).parent / "icons" / "azure"

GENERIC_COMPONENT_ICON = "generic-service.png"
GENERIC_DEPENDENCY_ICON = "generic-external.png"

# Ordered most-specific-first: the first keyword found wins, so a
# specific multi-word Azure product/concept name must come before any
# single generic word it could otherwise be shadowed by - e.g. "key
# vault" must be checked before "storage", or an external dependency
# named "Key Vault" with purpose "Secret storage" would match the
# generic "storage" keyword first and get the wrong icon. The single
# generic fallback words at the end of this tuple are deliberately last
# for the same reason: "pipeline" must be checked before "container", or
# a "CI/CD Pipeline" component whose responsibility happens to mention
# "container images" would get a generic container icon instead of the
# pipeline one.
_KEYWORD_ICON_MAP: tuple[tuple[str, str], ...] = (
    # Specific multi-word (or otherwise unambiguous) product/concept names.
    ("kubernetes", "kubernetes.png"),
    ("aks", "kubernetes.png"),
    ("container registry", "container-registry.png"),
    ("docker registry", "container-registry.png"),
    ("serverless", "function.png"),
    ("app service", "app-service.png"),
    ("web app", "app-service.png"),
    ("virtual machine", "virtual-machine.png"),
    ("cosmos", "cosmos-db.png"),
    ("key vault", "key-vault.png"),
    ("secret", "key-vault.png"),
    ("active directory", "identity.png"),
    ("authentication", "identity.png"),
    ("authorization", "identity.png"),
    ("service bus", "service-bus.png"),
    ("message queue", "queue.png"),
    ("redis", "cache.png"),
    ("load balancer", "load-balancer.png"),
    ("api management", "api-gateway.png"),
    ("ingress", "api-gateway.png"),
    ("logic app", "logic-app.png"),
    ("workflow", "logic-app.png"),
    ("continuous integration", "devops-pipeline.png"),
    ("ci/cd", "devops-pipeline.png"),
    ("pipeline", "devops-pipeline.png"),
    ("virtual network", "virtual-network.png"),
    ("vnet", "virtual-network.png"),
    ("browser", "client.png"),
    ("mobile app", "client.png"),
    ("frontend", "client.png"),
    ("front end", "client.png"),
    ("user interface", "client.png"),
    ("telemetry", "monitor.png"),
    ("logging", "monitor.png"),
    # Generic single-word fallbacks - checked last; see the note above.
    ("function", "function.png"),
    ("container", "container.png"),
    ("sql", "sql-database.png"),
    ("database", "sql-database.png"),
    ("blob", "blob-storage.png"),
    ("storage", "blob-storage.png"),
    ("queue", "queue.png"),
    ("cache", "cache.png"),
    ("identity", "identity.png"),
    ("monitor", "monitor.png"),
    ("gateway", "api-gateway.png"),
    ("client", "client.png"),
)


def _best_matching_icon(name: str, detail: str, fallback: str) -> str:
    """Check `name` against every keyword before falling back to `detail`
    (a component's responsibility, or a dependency's purpose).

    A component's/dependency's name is the label an architect (or the
    LLM) chose specifically to identify it; the detail text is free-form
    prose that can easily mention an unrelated but keyword-matching term
    in passing (e.g. a "CI/CD Pipeline" component whose responsibility
    happens to say it "deploys container images" - checking name first
    means "pipeline" from the name wins over "container" from the
    responsibility, without depending on those two keywords' relative
    order in `_KEYWORD_ICON_MAP`).
    """

    for text in (name, detail):
        lowered = text.lower()

        for keyword, filename in _KEYWORD_ICON_MAP:
            if keyword in lowered:
                return filename

    return fallback


def component_icon_path(name: str, responsibility: str) -> str:
    """Absolute path to the icon PNG best matching a component's name and
    responsibility, or the generic component icon if nothing matches."""

    filename = _best_matching_icon(name, responsibility, GENERIC_COMPONENT_ICON)
    return str(_ICONS_DIR / filename)


def dependency_icon_path(name: str, purpose: str) -> str:
    """Absolute path to the icon PNG best matching an external
    dependency's name and purpose, or the generic external-dependency
    icon if nothing matches."""

    filename = _best_matching_icon(name, purpose, GENERIC_DEPENDENCY_ICON)
    return str(_ICONS_DIR / filename)


def actor_icon_path(kind: str) -> str:
    """Absolute path to the generic, technology-neutral icon for an
    external `Actor` (see ``app/domain/design.py``), chosen by
    ``kind`` ("user" vs "external_system") rather than keyword-matched
    free text - an actor's name/description is about *who* they are,
    not a hint toward any particular icon, so this deliberately doesn't
    go through ``_best_matching_icon``.

    Used by both the Logical Architecture Diagram (always) and the
    Azure Service Mapping Diagram (an actor is external to the system
    and typically has no Azure implementation of its own, but is still
    rendered - with this same icon and id - so interfaces that
    terminate at it remain traceable between the two diagrams).
    """

    filename = "client.png" if kind == "user" else GENERIC_DEPENDENCY_ICON
    return str(_ICONS_DIR / filename)
