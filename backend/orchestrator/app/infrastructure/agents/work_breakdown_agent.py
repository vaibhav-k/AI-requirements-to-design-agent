"""``WorkBreakdownAgentPort`` implementation backed by Microsoft Agent Framework.

The work-breakdown analogue of ``requirements_agent.py``/
``system_design_agent.py`` - same wiring notes apply
(``agent_framework.openai.OpenAIChatClient`` with ``base_url`` routing;
structured output via ``ChatOptions(response_format=...)``; the parsed
instance comes back on ``AgentResponse.value``). See
``requirements_agent.py``'s docstring for the full wiring rationale, not
repeated here.

The prompt below is this project's Work Breakdown Agent specification,
carried over field-for-field: the Feature -> Story -> Task hierarchy, the
effort scale, the exact CSV column order (rendered downstream by
``backend/tools-service``, not by this agent - see
``app.domain.work_breakdown``), and every "do not invent / do not
fabricate / flag rather than silently resolve" rule. The one addition
this implementation makes beyond the original specification text: the
prompt is given the *actual* requirement and architecture IDs pulled
from the supplied artifacts and told to use only those, rather than
relying on the model to somehow avoid fabricating IDs it was never shown
a ground-truth list for.
"""

from __future__ import annotations

from agent_framework import ChatOptions
from agent_framework.openai import OpenAIChatClient

from app.application.errors import WorkBreakdownGenerationError
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact

_INSTRUCTIONS = """
You are a Work Breakdown Agent that transforms product requirements and
solution architecture into an actionable, traceable work breakdown
suitable for import into tools such as Monday.com or Azure DevOps.

You will receive the outputs of two upstream agents: a Requirements
Analyzer and an Architecture Designer. Treat these two outputs as the
authoritative source of truth. Do not invent requirements, architecture
elements, IDs, or scope that are not supported by the inputs.

Create a complete implementation work breakdown using the hierarchy:
Feature -> Story -> Task.

Feature: a major capability or logical area of the solution.
Story: a meaningful user, business, or technical outcome that
contributes to a feature.
Task: a concrete, actionable implementation activity required to
complete a story.

Avoid vague tasks such as "Implement feature", "Do development",
"Complete backend", or "Build solution". Instead, create specific tasks
such as "Create customer profile database schema", "Implement POST
/customers endpoint", "Add JWT validation middleware", "Create customer
profile form", or "Add integration tests for customer creation API".

Trace every work item back to the upstream inputs. For each Feature,
Story, and Task, identify the relevant Requirement ID(s) and
Architecture/Design ID(s). If multiple requirements or architecture
elements drive the work item, include all applicable IDs. Preserve the
exact IDs provided by the upstream agents - never fabricate one, never
normalize or reformat one. Only ever use an ID from the "Valid
requirement IDs" or "Valid architecture IDs" lists given to you below; if
no ID from either list applies to a work item, that is itself a defect -
reconsider whether the item belongs in the breakdown at all.

Ensure the work breakdown provides implementation coverage for
functional requirements, non-functional requirements, business
requirements that require engineering work, APIs, UI/frontend,
backend/services, data models and databases, integrations, authentication
and authorization, security, infrastructure, configuration, deployment,
observability/logging/monitoring, data migration, error handling,
testing, and documentation - but only include an area when it is
supported or required by the provided requirements and architecture. Do
not introduce unsupported scope.

Estimate effort for each Task using this scale: XS = less than 0.5 day,
S = 0.5-1 day, M = 1-3 days, L = 3-5 days, XL = more than 5 days. Effort
represents implementation effort, not calendar duration. Avoid XL tasks
where the work can reasonably be decomposed into smaller tasks. Features
and Stories do not carry effort estimates - only Tasks do.

Rules:

1. Every implementation-relevant requirement should map to at least one
   Feature, Story, or Task.
2. Every architecture component or design element that requires
   implementation should map to one or more work items.
3. Every work item must have traceability to at least one valid
   Requirement ID and/or Architecture ID.
4. Do not create work solely because it is common engineering practice
   unless it is supported by the requirements or architecture.
5. Do not omit cross-cutting implementation work when it is explicitly
   required by the architecture or requirements.
6. Break complex stories into multiple actionable tasks.
7. Tasks should be small enough to be independently assigned to an
   engineer where practical.
8. Do not duplicate tasks across multiple stories unless the work
   genuinely needs to occur independently.
9. Keep Feature and Story names stable and reusable. Do not create
   unnecessary variations of the same feature.
10. Testing should be represented explicitly when meaningful testing
    work is required.
11. Include deployment, infrastructure, migration, security, monitoring,
    and documentation work when supported by the inputs.
12. Do not redesign the architecture.
13. Do not modify or reinterpret requirements.
14. Do not introduce new product capabilities that are not supported by
    the inputs.
15. If the requirements and architecture conflict, do not silently
    resolve the conflict. Record it as an ambiguity of kind
    "conflicting_inputs" instead.

Before producing the final breakdown, work through these steps
internally: parse the requirements (ID, type, description, priority);
parse the architecture (ID, component/service, responsibilities,
interfaces, data stores, integrations, security, infrastructure, related
requirement IDs); build a Requirement -> Architecture -> Feature -> Story
-> Task traceability map and identify gaps (a requirement with no
architecture mapping, an architecture element with no requirement
mapping, either kind of element needing implementation but having no
work item); group related requirements/architecture elements into
Features; identify the Stories each Feature needs; break each Story into
concrete Tasks covering every implementation activity it requires;
attach exact Requirement/Architecture IDs to every Feature, Story, and
Task; estimate every Task's effort; and finally verify no fabricated IDs,
no missing implementation-relevant requirements or architecture
elements, no unsupported scope, no unnecessary duplicate work, and that
every task is actionable.

Record every gap identified above as an ambiguity: a requirement with no
architecture mapping is "requirement_without_architecture"; an
architecture element with no requirement mapping is
"architecture_without_requirement"; a requirement needing implementation
but with no work item is "requirement_without_work_item"; an architecture
element needing implementation but with no work item is
"architecture_without_work_item"; anything else worth flagging
(assumptions made, information the inputs left ambiguous) is
"assumption". Make the most conservative interpretation supported by the
inputs rather than inventing an answer, and record the issue as an
ambiguity instead.
"""


class AgentFrameworkWorkBreakdownAgent:
    """Generates/refines a work breakdown via a Microsoft Agent Framework ``Agent``."""

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
            name="WorkBreakdownAgent",
            instructions=_INSTRUCTIONS,
        )

    async def generate(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        previous_breakdown: WorkBreakdownArtifact | None = None,
        refinement_input: str | None = None,
    ) -> WorkBreakdownArtifact:
        """Satisfies ``app.application.ports.WorkBreakdownAgentPort``."""

        prompt = _build_prompt(
            requirements, design, previous_breakdown, refinement_input
        )

        try:
            response = await self._agent.run(
                prompt,
                options=ChatOptions(response_format=WorkBreakdownArtifact),  # pyright: ignore[reportArgumentType]  # agent_framework's
                # ChatOptions TypedDict types response_format as
                # type[BaseModel] | Mapping[str, Any] | None (see its source),
                # but pyright resolves the constructor's parameter type as
                # type[None] | Mapping[str, Any] | None here - a pyright/
                # TypedDict-constructor stub-resolution gap, not a real type
                # error; mypy (this project's configured checker) accepts the
                # exact same call with zero issues.
            )
        except Exception as exc:
            raise WorkBreakdownGenerationError(
                "Microsoft Agent Framework work breakdown generation failed."
            ) from exc

        if not isinstance(response.value, WorkBreakdownArtifact):
            raise WorkBreakdownGenerationError(
                "Microsoft Agent Framework returned no parsed work breakdown."
            )

        return response.value


def _valid_requirement_ids(requirements: RequirementsArtifact) -> list[str]:
    return [
        requirement.id
        for requirement in (
            *requirements.functional_requirements,
            *requirements.non_functional_requirements,
        )
    ]


def _valid_architecture_ids(design: SystemDesignArtifact) -> list[str]:
    return [
        *(component.id for component in design.components),
        *(interface.id for interface in design.interfaces),
        *(dependency.id for dependency in design.external_dependencies),
    ]


def _build_prompt(
    requirements: RequirementsArtifact,
    design: SystemDesignArtifact,
    previous_breakdown: WorkBreakdownArtifact | None,
    refinement_input: str | None,
) -> str:
    requirement_ids = _valid_requirement_ids(requirements)
    architecture_ids = _valid_architecture_ids(design)

    refinement_context = ""

    if previous_breakdown is not None:
        refinement_context = f"""
The user is refining a previously generated work breakdown rather than
starting over.

Previous work breakdown:

{previous_breakdown.model_dump_json(indent=2)}

Requested change:

{refinement_input or ""}

Use the previous work breakdown as the starting point. Preserve
Features, Stories, and Tasks that are still valid. Apply the requested
change. Do not silently remove or rename existing Features or Stories
unless the requested change explicitly calls for it - prefer adding or
adjusting over wholesale regeneration.
"""

    return f"""
Generate the work breakdown described in your instructions from the
requirements and architecture below.
{refinement_context}
Valid requirement IDs (use only these - never invent one):

{requirement_ids}

Valid architecture IDs (use only these - never invent one):

{architecture_ids}

Requirements (RequirementsArtifact JSON):

{requirements.model_dump_json(indent=2)}

Architecture (SystemDesignArtifact JSON):

{design.model_dump_json(indent=2)}
"""
