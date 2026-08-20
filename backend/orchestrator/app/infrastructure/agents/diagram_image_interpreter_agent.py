"""``DiagramImageInterpreterPort`` implementation backed by Microsoft
Agent Framework.

The diagram-image analogue of ``image_classifier_agent.py`` - same
wiring notes apply (see that module's docstring for the full multimodal-
input rationale, not repeated here).

Replaces the project's previous direct
``openai.OpenAI().responses.parse(..., text_format=SystemDesignArtifact)``
call (``app/vision.py``'s git history before this slice of the Clean
Architecture migration).
"""

from __future__ import annotations

from agent_framework import ChatOptions, Content, Message
from agent_framework.openai import OpenAIChatClient

from app.application.errors import DiagramInterpretationError
from app.domain.design import SystemDesignArtifact
from app.infrastructure.agents.vision_support import image_content

_INSTRUCTIONS = (
    "You are a senior software architect. Look at the supplied system "
    "design / workflow diagram image and redraw it as a clean, "
    "well-architected system design: identify every component, "
    "interface, and external dependency it depicts, correct anything "
    "that is structurally unclear, redundant, or inconsistent, and "
    "return the requested structured architecture - not a description "
    "of the image."
)


class AgentFrameworkDiagramImageInterpreterAgent:
    """Derives a system design from a diagram image via a Microsoft
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
            name="DiagramImageInterpreter",
            instructions=_INSTRUCTIONS,
        )

    async def interpret(
        self,
        content: bytes,
        filename: str,
        previous_design: SystemDesignArtifact | None = None,
        notes: str | None = None,
    ) -> SystemDesignArtifact:
        """Satisfies ``app.application.ports.DiagramImageInterpreterPort``."""

        prompt_text = _build_prompt(previous_design, notes)

        message = Message(
            role="user",
            contents=[
                Content.from_text(prompt_text),
                image_content(content, filename),
            ],
        )

        try:
            response = await self._agent.run(
                message,
                options=ChatOptions(response_format=SystemDesignArtifact),
            )
        except Exception as exc:
            raise DiagramInterpretationError(
                "Microsoft Agent Framework could not interpret the uploaded diagram."
            ) from exc

        if not isinstance(response.value, SystemDesignArtifact):
            raise DiagramInterpretationError(
                "Microsoft Agent Framework returned no parsed system design "
                "from the diagram."
            )

        return response.value


def _build_prompt(
    previous_design: SystemDesignArtifact | None,
    notes: str | None,
) -> str:
    """Build the diagram-interpretation prompt.

    Content unchanged from the pre-migration
    ``DiagramImageInterpreter._build_prompt`` - only where it runs
    (behind a Microsoft Agent Framework ``Agent`` instead of a raw
    ``openai.OpenAI`` client) has changed.
    """

    refinement_context = ""

    if previous_design is not None:
        refinement_context = f"""
This image refines a previously generated architecture rather than
replacing it outright.

Previous architecture:

{previous_design.model_dump_json(indent=2)}

Preserve components, interfaces, and external dependencies that are still
consistent with the image; apply whatever the image adds or changes. Do
not silently remove or rename existing components, interfaces, or
dependencies unless the image clearly calls for it. Preserve each
existing component's "domain" string exactly as-is unless the image
clearly moves it to a different group; give any newly added component a
domain consistent with the existing set.
"""

    notes_context = f"\nAdditional notes from the uploader:\n{notes}\n" if notes else ""

    return f"""
Examine the attached image of a system design or workflow diagram.
{refinement_context}{notes_context}
Identify:

- Every major logical component depicted (boxes/nodes), each with a
  unique ID, a name, and its responsibility.
- Each component's "domain" - a short group/category name. If the image
  itself visually groups components (a labeled outer box/section/swimlane
  containing several inner boxes, a color-coded region, etc.), use that
  section's label as the domain, character-for-character, for every
  component inside it. If the image has no visible grouping, infer a
  small number of sensible domains (roughly 3-8) from what the
  components do, and use the SAME domain string for every component that
  belongs together - this is what lets the redrawn diagram visually
  cluster related components instead of scattering them.
- Every interface/relationship between components (arrows), each with a
  unique ID, name, purpose, source component, and target component.
- Every external dependency depicted (third-party services, databases, or
  external systems drawn distinctly from the system's own components),
  each with a unique ID, name, purpose, and which components use it.
- Open questions or assumptions needed to fill gaps the image leaves
  ambiguous - an unlabeled arrow, an illegible or ambiguous box.

Return the redrawn architecture as the requested structured format: a
clean, well-architected version of what the image depicts, not a literal
transcription of any illegible or inconsistent labeling in the source
image.
"""
