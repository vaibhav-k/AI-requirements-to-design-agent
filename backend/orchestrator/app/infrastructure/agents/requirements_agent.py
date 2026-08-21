"""``RequirementsAgentPort`` implementation backed by Microsoft Agent Framework.

Replaces the project's previous direct ``openai.OpenAI().responses.parse(
..., text_format=RequirementsArtifact)`` call (see ``app/analyzer.py``'s
git history before the Clean Architecture migration) with a Microsoft
Agent Framework ``Agent``. See
https://github.com/microsoft/agent-framework and
https://learn.microsoft.com/en-us/agent-framework/overview/ for the
framework itself - it's Microsoft's unified successor to Semantic Kernel
and AutoGen, combining Semantic Kernel's enterprise features (typed,
session-based state; middleware; telemetry) with AutoGen's simpler agent
abstractions.

Wiring notes (verified directly against the installed
``agent-framework-core``/``agent-framework-openai`` 1.x packages, since
the framework's public docs disagree with themselves across pages about
class names as the API has evolved):

* ``agent_framework.azure.AzureOpenAIChatClient`` - the class this
  module would most naturally reach for - was removed upstream. Current
  guidance is to use ``agent_framework.openai.OpenAIChatClient`` for
  both OpenAI and Azure OpenAI, with explicit Azure routing via
  ``base_url``/``azure_endpoint``. See
  https://learn.microsoft.com/en-us/agent-framework/agents/providers/openai.
* This project's ``AZURE_OPENAI_ENDPOINT`` is the Azure OpenAI *v1*
  endpoint (``https://<resource>.openai.azure.com/openai/v1/``, OpenAI
  SDK-compatible) - the same value the old ``openai.OpenAI(base_url=...)``
  call used directly. ``OpenAIChatClient`` accepts that shape via its own
  ``base_url`` parameter, so no new environment variable or API-version
  configuration is needed for this migration.
* Structured output uses ``ChatOptions(response_format=RequirementsArtifact)``
  passed to ``Agent.run(..., options=...)``; the parsed Pydantic instance
  comes back on ``AgentResponse.value`` (typed ``Any`` by the framework,
  hence the ``isinstance`` check below rather than a bare cast).
"""

from __future__ import annotations

from agent_framework import ChatOptions
from agent_framework.openai import OpenAIChatClient

from app.domain.requirements import RequirementsArtifact

_INSTRUCTIONS = (
    "You are a precise software requirements analyst. Return only the "
    "requested structured requirements."
)


class AgentFrameworkRequirementsAgent:
    """Analyzes/refines requirements via a Microsoft Agent Framework ``Agent``."""

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
            name="RequirementsAnalyst",
            instructions=_INSTRUCTIONS,
        )

    async def analyze(
        self,
        user_input: str,
        previous_artifact: RequirementsArtifact | None = None,
    ) -> RequirementsArtifact:
        """Satisfies ``app.application.ports.RequirementsAgentPort``."""

        prompt = _build_prompt(user_input, previous_artifact)

        response = await self._agent.run(
            prompt,
            options=ChatOptions(response_format=RequirementsArtifact),  # pyright: ignore[reportArgumentType]  # agent_framework's
            # ChatOptions TypedDict types response_format as
            # type[BaseModel] | Mapping[str, Any] | None (see its source),
            # but pyright resolves the constructor's parameter type as
            # type[None] | Mapping[str, Any] | None here - a pyright/
            # TypedDict-constructor stub-resolution gap, not a real type
            # error; mypy (this project's configured checker) accepts the
            # exact same call with zero issues.
        )

        if not isinstance(response.value, RequirementsArtifact):
            raise RuntimeError(
                "Microsoft Agent Framework returned no parsed requirements."
            )

        return response.value


def _build_prompt(
    user_input: str,
    previous_artifact: RequirementsArtifact | None,
) -> str:
    """Build the requirements analysis prompt.

    Content unchanged from the pre-migration ``RequirementsAnalyzer
    ._build_prompt`` - only where it runs (behind a Microsoft Agent
    Framework ``Agent`` instead of a raw ``openai.OpenAI`` client) has
    changed.
    """

    previous_context = ""

    if previous_artifact is not None:
        previous_context = f"""
The user is refining a previous requirements analysis.

Previous analysis:

{previous_artifact.model_dump_json(indent=2)}

Use the previous analysis as the starting point.

Preserve information that is still valid.

Apply the user's new information.

Do not silently remove requirements unless the user
explicitly contradicts or removes them.
"""

    return f"""
You are an AI requirements analyst.

Analyze the user's software/system requirements and produce
a structured understanding of what they are trying to build.

The goal at this stage is NOT to design the architecture.

Do NOT propose:

- databases
- microservices
- APIs
- cloud architecture
- programming languages
- frameworks
- deployment architecture

Focus on understanding the requirements.

Identify:

1. Overall business goal.
2. Actors/users involved.
3. Functional requirements.
4. Non-functional requirements.
5. Data requirements.
6. Integration requirements.
7. Explicit constraints.
8. Assumptions.
9. Open questions.

IMPORTANT:

- Do not invent requirements.
- Distinguish explicit requirements from assumptions.
- Put ambiguous information into open_questions.
- Every significant assumption needs a reason.
- Every open question needs a reason.
- Keep requirements concise and testable where possible.
- Assign IDs such as FR-001, FR-002, NFR-001.
- Assign priorities using high, medium, or low.
- Use high confidence only for explicit information.
- Do not make architecture decisions.

{previous_context}

USER INPUT:

{user_input}
"""
