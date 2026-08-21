"""``TechnicalWriterAgentPort`` implementation backed by Microsoft Agent
Framework.

The technical-design analogue of ``work_breakdown_agent.py`` - same
wiring notes apply (``agent_framework.openai.OpenAIChatClient`` with
``base_url`` routing; structured output via
``ChatOptions(response_format=...)``; the parsed instance comes back on
``AgentResponse.value``). See ``requirements_agent.py``'s docstring for
the full wiring rationale, not repeated here.

The instructions below borrow the document shape from
Parnell-AI-Persona-Agent's own Technical Writer agent (flat, leveled
sections; one section marked to carry the architecture diagram; roughly
16-20 sections; an 8-10 page budget) rather than inventing a new one -
see ``app/domain/technical_design.py``'s module docstring for the
contract-level reasoning. What's new here, matching this project's own
Work Breakdown Agent, is grounding the document in the *actual*
requirement, architecture, and work-breakdown content supplied rather
than leaving traceability to chance: the prompt hands the model the full
JSON of all three upstream artifacts and instructs it to describe what
they actually contain, never to invent capabilities or components.
"""

from __future__ import annotations

from agent_framework import ChatOptions
from agent_framework.openai import OpenAIChatClient

from app.application.errors import TechnicalDesignGenerationError
from app.domain.design import SystemDesignArtifact
from app.domain.requirements import RequirementsArtifact
from app.domain.technical_design import MAX_SECTION_LEVEL, TechnicalDesignArtifact
from app.domain.work_breakdown import WorkBreakdownArtifact

_INSTRUCTIONS = f"""
You are a Technical Writer agent that compiles a technical design
document from three upstream artifacts: a requirements analysis, a
system architecture, and an implementation work breakdown. Treat all
three as the authoritative source of truth. Describe what they actually
contain - do not invent requirements, components, or work that isn't
supported by the inputs.

Produce a structured document a technical reviewer and a delivery lead
can both read: a short executive summary, then a body of sections
covering (as supported by the inputs) the system's purpose, its
architecture and key components, the interfaces between components and
with external dependencies, cross-cutting concerns such as data,
integration, and non-functional requirements, and a summary of the
planned implementation work.

Sections are a FLAT ordered list, each carrying its own heading depth in
`level` (1-{MAX_SECTION_LEVEL}) rather than a nested tree - never skip a
level; a level-2 section belongs to the nearest preceding level-1
section. Aim for roughly 12-18 sections; the rendered document has an
8-10 page budget, so prefer a table or bullets over a long paragraph when
the content is naturally tabular or list-shaped. Each section's `body`
should be 1-3 short paragraphs of real content, never a placeholder.

Mark exactly one section's `include_diagram` `true` - the section whose
subject is the architecture overview - so the approved architecture
diagram is embedded there. Do not mark more than one.

Do not redesign the architecture, reinterpret the requirements, or
reorganize the work breakdown - describe what was already approved.
"""

_REFINE_RULES = """

You are refining a previously generated technical design document rather
than starting over. Preserve sections that are still accurate. Apply the
requested change. Do not silently remove or retitle existing sections
unless the requested change explicitly calls for it - prefer adding or
adjusting content over wholesale regeneration.
"""


class AgentFrameworkTechnicalWriterAgent:
    """Generates/refines a technical design document via a Microsoft
    Agent Framework ``Agent``."""

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
            name="TechnicalWriterAgent",
            instructions=_INSTRUCTIONS,
        )

    async def generate(
        self,
        requirements: RequirementsArtifact,
        design: SystemDesignArtifact,
        work_breakdown: WorkBreakdownArtifact,
        previous_document: TechnicalDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> TechnicalDesignArtifact:
        """Satisfies ``app.application.ports.TechnicalWriterAgentPort``."""

        prompt = _build_prompt(
            requirements, design, work_breakdown, previous_document, refinement_input
        )

        try:
            response = await self._agent.run(
                prompt,
                options=ChatOptions(response_format=TechnicalDesignArtifact),  # pyright: ignore[reportArgumentType]  # agent_framework's
                # ChatOptions TypedDict types response_format as
                # type[BaseModel] | Mapping[str, Any] | None (see its source),
                # but pyright resolves the constructor's parameter type as
                # type[None] | Mapping[str, Any] | None here - a pyright/
                # TypedDict-constructor stub-resolution gap, not a real type
                # error; mypy (this project's configured checker) accepts the
                # exact same call with zero issues.
            )
        except Exception as exc:
            raise TechnicalDesignGenerationError(
                "Microsoft Agent Framework technical design generation failed."
            ) from exc

        if not isinstance(response.value, TechnicalDesignArtifact):
            raise TechnicalDesignGenerationError(
                "Microsoft Agent Framework returned no parsed technical "
                "design document."
            )

        return response.value


def _build_prompt(
    requirements: RequirementsArtifact,
    design: SystemDesignArtifact,
    work_breakdown: WorkBreakdownArtifact,
    previous_document: TechnicalDesignArtifact | None,
    refinement_input: str | None,
) -> str:
    refinement_context = ""

    if previous_document is not None:
        # Folded into the prompt (rather than swapped into the agent's
        # `instructions`) so this stays a single, always-`str`
        # `ChatOptions(response_format=...)` call - matching every other
        # agent adapter in this package, none of which vary `instructions`
        # per call.
        refinement_context = f"""
{_REFINE_RULES}

Previous technical design document:

{previous_document.model_dump_json(indent=2)}

Requested change:

{refinement_input or ""}
"""

    return f"""
Compile the technical design document described in your instructions
from the requirements, architecture, and work breakdown below.
{refinement_context}
Requirements (RequirementsArtifact JSON):

{requirements.model_dump_json(indent=2)}

Architecture (SystemDesignArtifact JSON):

{design.model_dump_json(indent=2)}

Work breakdown (WorkBreakdownArtifact JSON):

{work_breakdown.model_dump_json(indent=2)}
"""
