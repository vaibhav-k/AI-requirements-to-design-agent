"""``SystemDesignAgentPort`` implementation backed by Microsoft Agent Framework.

The design-generation analogue of ``requirements_agent.py`` - same
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
from app.domain.design import SystemDesignArtifact
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
                options=ChatOptions(response_format=SystemDesignArtifact),  # pyright: ignore[reportArgumentType]  # agent_framework's
                # ChatOptions TypedDict types response_format as
                # type[BaseModel] | Mapping[str, Any] | None (see its source),
                # but pyright resolves the constructor's parameter type as
                # type[None] | Mapping[str, Any] | None here - a pyright/
                # TypedDict-constructor stub-resolution gap, not a real type
                # error; mypy (this project's configured checker) accepts the
                # exact same call with zero issues.
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
    ._build_prompt`` - only where it runs (behind a Microsoft Agent
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
interfaces, actors, external dependencies, azure_mappings, and
supporting_azure_services that are still valid. Apply the requested
change. Do not silently remove or rename existing components,
interfaces, or dependencies unless the requested change explicitly calls
for it - prefer adding or adjusting over wholesale regeneration, so
existing IDs remain stable across a refinement wherever possible (this
matters even more now than before: azure_mappings/supporting_azure_
services entries reference component/actor/dependency IDs by string, so
renaming an ID silently breaks that traceability). Also preserve each
existing component's "domain" and "trust_zone" exactly as-is, and each
existing interface's "flow_type", unless the requested change
specifically changes them; give any newly added component a domain
consistent with the existing set (reuse an existing domain string where
it fits, rather than inventing a near-duplicate).
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
- Assign every component a short "domain" - a group/category name (e.g.
  "Client & Identity", "Data Platform", "Integration", "Finance
  Services") shared by every component that belongs together logically.
  Use the SAME domain string, character-for-character, for every
  component in that group, and keep the number of distinct domains
  small (roughly 3-8 for a typical design) - this is what lets the
  rendered diagram visually cluster related components together instead
  of scattering them.
- Assign every component a "trust_zone" - a short, technology-neutral
  security/trust boundary name (e.g. "Public", "DMZ", "Private",
  "Internal"). Use "TBD" only when the requirements genuinely give no
  basis to judge this.
- Map each component to the requirement IDs that justify it.
- Identify important interactions BETWEEN COMPONENTS, and between a
  component and an actor (see "actors" below).
- Give every interface a unique ID.
- Classify every interface's "flow_type" as "sync" (a request/response
  call, e.g. HTTPS/gRPC) or "async" (an event/message, e.g. publish/
  consume via a queue or topic).
- Map each interface to the requirement IDs that justify it.
- Identify external human/system actors that interact with the system
  from OUTSIDE its boundary (end users, administrators, third-party
  systems that call IN) as "actors" - give each a unique ID, a "kind" of
  "user" or "external_system", and a short description. An interface's
  source/target may reference an actor's ID exactly like a component's.
- Identify external services, hardware, or dependencies this system
  calls OUT to, explicitly required by the requirements, as
  "external_dependencies".
- For each external dependency, identify the components that use it,
  by listing their component IDs in that dependency's own
  "used_by_components" field.
- For every major component, actor, and external dependency, add an
  "azure_mappings" entry recommending its concrete Azure implementation:
  a real, current, official Azure service name ("azure_service"), a
  short category ("service_category", e.g. "Compute", "Data",
  "Identity", "Integration"), a one-or-two-sentence "rationale" for why
  that service fits (and, when more than one Azure service is
  genuinely viable, why this one was chosen over the alternatives -
  list the others considered in "alternatives_considered"), a
  "connectivity" classification ("public-endpoint", "private-endpoint",
  "vnet-internal", or "internal-only"), and a "trust_zone" ("Public",
  "DMZ", "Private VNet", or "Internal"). Prefer managed/cloud-native
  Azure services over self-managed infrastructure when both are viable.
  Do not map a pure external actor (a human user) to an Azure service -
  only map components, external dependencies, and external systems that
  genuinely have (or need) an Azure-side implementation.
- Add "supporting_azure_services" entries for Azure services the
  architecture needs but that don't map 1:1 to any single component -
  identity/auth (e.g. Microsoft Entra ID), networking (e.g. Virtual
  Network, Application Gateway, Azure Firewall), security, secrets
  (e.g. Azure Key Vault), monitoring/logging (e.g. Azure Monitor,
  Application Insights), and CI/CD (e.g. Azure DevOps, GitHub Actions)
  when the requirements or the shape of the architecture call for them.
  Give each a "category" from that same list, a "purpose", a
  "rationale", and list the component IDs it supports in
  "applies_to_components".
- Keep "components"/"interfaces"/"external_dependencies" themselves
  technology-neutral - all Azure-specific detail belongs in
  "azure_mappings"/"supporting_azure_services" instead, never folded
  into a component's own name/responsibility.
- Clearly distinguish requirements from assumptions.
- Identify unresolved architecture questions.

DO NOT:

- Write application code.
- Design database schemas.
- Specify table structures.
- Specify class diagrams.
- Specify detailed APIs.
- Specify deployment topology (VNet/subnet layout, VM sizing, scaling
  rules, and the like) beyond the single recommended Azure service (and
  its connectivity/trust-zone classification) each "azure_mappings"/
  "supporting_azure_services" entry calls for.
- Specify Kubernetes unless a requirement specifically calls for it.
- Choose frameworks without a requirement-driven reason.
- Invent detailed infrastructure beyond the Azure service
  recommendations this prompt explicitly asks for.
- Over-engineer the solution.
- Create an interface whose source or target is an external dependency.
  A component's use of an external dependency (e.g. "Payment Service calls
  the Stripe API") is captured ONLY by listing the component's ID under
  that dependency's "used_by_components" - never as an interface. Every
  interface's source_component and target_component must each be the ID
  of an item in "components" or "actors"; an external dependency's ID is
  never valid there, in either direction.
- Invent a numeric "version" or a "last_updated" timestamp for a
  diagram, or an "author" for it - those are generated deterministically
  by the diagram-rendering code, never by you.

Every requirement-to-component and requirement-to-interface mapping
must reference an actual requirement ID from the supplied requirements.

The architecture should be understandable to a product owner,
software architect, and engineering team.

The resulting architecture will also be rendered as two complementary
high-level Graphviz diagrams: a technology-agnostic Logical Architecture
Diagram (components, actors, and their interactions/trust boundaries)
and an Azure Service Mapping Diagram (every major component/actor/
external dependency mapped to its concrete Azure implementation, via
"azure_mappings"/"supporting_azure_services"). A reviewer must be able
to take any major component from the first diagram and immediately find
its corresponding Azure implementation on the second - this only works
if every major component/actor/external dependency this design actually
needs on Azure has a matching "azure_mappings" entry with the SAME id.

Accepted requirements:

{requirements_json}
"""
