"""``SystemDesignAgentPort`` implementation backed by Microsoft Agent Framework.

The design-generation analogue of ``requirements_agent.py`` — same
wiring notes apply (``agent_framework.openai.OpenAIChatClient`` with
``base_url`` routing rather than the removed Azure-specific client;
structured output via ``ChatOptions(response_format=...)``; the parsed
instance comes back on ``AgentResponse.value``). See that module's
docstring for the full rationale; not repeated here.

Replaces the project's previous direct ``openai.OpenAI().responses.parse(
..., text_format=SystemDesignArtifact)`` call (``app/design/analyzer.py``'s
git history before this slice of the Clean Architecture migration).
"""

from __future__ import annotations

from agent_framework import ChatOptions
from agent_framework.openai import OpenAIChatClient

from app.application.errors import DesignGenerationError
from app.design.models import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact

_INSTRUCTIONS = (
    "You are a senior software architect. Generate a high-level system "
    "architecture from the supplied requirements."
)


class AgentFrameworkSystemDesignAgent:
    """Generates/refines a system design via a Microsoft Agent Framework ``Agent``."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        model: str,
    ) -> None:
        client = OpenAIChatClient(
            api_key=api_key,
            base_url=endpoint.rstrip("/") + "/",
            model=model,
        )

        self._agent = client.as_agent(
            name="SystemDesignArchitect",
            instructions=_INSTRUCTIONS,
        )

    async def generate(
        self,
        requirements: RequirementsArtifact,
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> SystemDesignArtifact:
        """Satisfies ``app.application.ports.SystemDesignAgentPort``."""

        prompt = _build_prompt(requirements, previous_design, refinement_input)

        try:
            response = await self._agent.run(
                prompt,
                options=ChatOptions(response_format=SystemDesignArtifact),
            )
        except Exception as exc:
            raise DesignGenerationError(
                "Microsoft Agent Framework architecture generation failed."
            ) from exc

        if not isinstance(response.value, SystemDesignArtifact):
            raise DesignGenerationError(
                "Microsoft Agent Framework returned no parsed system design."
            )

        return response.value


def _build_prompt(
    requirements: RequirementsArtifact,
    previous_design: SystemDesignArtifact | None = None,
    refinement_input: str | None = None,
) -> str:
    """Build the architecture generation prompt.

    Content unchanged from the pre-migration ``SystemDesignAnalyzer
    ._build_prompt`` — only where it runs (behind a Microsoft Agent
    Framework ``Agent`` instead of a raw ``openai.OpenAI`` client) has
    changed. See ``tests/test_infrastructure_system_design_agent.py``
    for the regression test guarding its
    interface-vs-external-dependency constraint.
    """

    requirements_json = requirements.model_dump_json(indent=2)

    refinement_context = ""

    if previous_design is not None:
        refinement_context = f"""
The user is refining a previously generated architecture rather than
starting over.

Previous architecture:

{previous_design.model_dump_json(indent=2)}

Requested change:

{refinement_input or ""}

Use the previous architecture as the starting point. Preserve components,
interfaces, and external dependencies that are still valid. Apply the
requested change. Do not silently remove or rename existing components,
interfaces, or dependencies unless the requested change explicitly calls
for it — prefer adding or adjusting over wholesale regeneration, so
existing IDs remain stable across a refinement wherever possible. Also
preserve each existing component's "domain" string exactly as-is unless
the requested change specifically moves it to a different group; give
any newly added component a domain consistent with the existing set
(reuse an existing domain string where it fits, rather than inventing a
near-duplicate).
"""

    return f"""
Create a HIGH-LEVEL SYSTEM ARCHITECTURE from the requirements below.

This is MVP-2 of a requirements-to-design agent.

The purpose is to transform understood requirements into a
logical system architecture.
{refinement_context}

DO:

- Identify major logical system components.
- Give every component a unique ID.
- Describe each component's responsibility.
- Assign every component a short "domain" — a group/category name (e.g.
  "Client & Identity", "Data Platform", "Integration", "Finance
  Services") shared by every component that belongs together logically.
  Use the SAME domain string, character-for-character, for every
  component in that group, and keep the number of distinct domains
  small (roughly 3-8 for a typical design) — this is what lets the
  rendered diagram visually cluster related components together instead
  of scattering them.
- Map each component to the requirement IDs that justify it.
- Identify important interactions BETWEEN COMPONENTS ONLY.
- Give every interface a unique ID.
- Map each interface to the requirement IDs that justify it.
- Identify external services, hardware, or dependencies explicitly
  required by the requirements.
- For each external dependency, identify the components that use it,
  by listing their component IDs in that dependency's own
  "used_by_components" field.
- Keep the architecture technology-neutral where possible.
- Clearly distinguish requirements from assumptions.
- Identify unresolved architecture questions.

DO NOT:

- Write application code.
- Design database schemas.
- Specify table structures.
- Specify class diagrams.
- Specify detailed APIs.
- Specify deployment topology.
- Specify Kubernetes.
- Specify cloud networking.
- Choose frameworks without a requirement-driven reason.
- Invent detailed infrastructure.
- Over-engineer the solution.
- Create an interface whose source or target is an external dependency.
  A component's use of an external dependency (e.g. "Payment Service calls
  the Stripe API") is captured ONLY by listing the component's ID under
  that dependency's "used_by_components" — never as an interface. Every
  interface's source_component and target_component must each be the ID
  of an item in "components"; an external dependency's ID is never valid
  there, in either direction.

Every requirement-to-component and requirement-to-interface mapping
must reference an actual requirement ID from the supplied requirements.

The architecture should be understandable to a product owner,
software architect, and engineering team.

The resulting architecture will also be rendered as a
high-level Graphviz diagram.

Accepted requirements:

{requirements_json}
"""
