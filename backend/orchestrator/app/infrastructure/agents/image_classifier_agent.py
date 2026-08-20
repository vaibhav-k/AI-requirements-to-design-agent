"""``ImageClassifierPort`` implementation backed by Microsoft Agent Framework.

Same wiring notes as ``requirements_agent.py``/``system_design_agent.py``
apply (``agent_framework.openai.OpenAIChatClient`` with ``base_url``
routing; structured output via ``ChatOptions(response_format=...)``; the
parsed instance comes back on ``AgentResponse.value``) - not repeated
here. The one addition this adapter needs beyond those two: the uploaded
image itself has to reach the model as multimodal input, not just text.
Microsoft Agent Framework represents that as an
``agent_framework.Message`` whose ``contents`` list mixes a
``Content.from_text(...)`` prompt part with a ``Content.from_data(...)``
image part (built by ``vision_support.image_content``) - the
Agent-Framework-native equivalent of the previous direct
``openai.OpenAI().responses.parse(...)`` call's ``input_text``/
``input_image`` content parts (``app/vision.py``'s git history before
this slice of the Clean Architecture migration).
"""

from __future__ import annotations

from agent_framework import ChatOptions, Content, Message
from agent_framework.openai import OpenAIChatClient

from app.application.errors import ImageClassificationError
from app.domain.vision import ImageClassification
from app.infrastructure.agents.vision_support import image_content

_INSTRUCTIONS = "You classify an uploaded image for a requirements-to-design tool."

_CLASSIFICATION_PROMPT = """
Classify this image. Decide whether it is:

(a) 'document' - a screenshot or photo of TEXT meant to be read:
requirements notes, an email, a spec, a whiteboard of bullet points, a
form, a table, a written note. Even if it contains a few small boxes or
icons, classify it as 'document' if its primary content is prose or
lists of text.

(b) 'diagram' - a SYSTEM DESIGN or WORKFLOW DIAGRAM: boxes/nodes
connected by arrows depicting components, services, data flow, a
sequence, or an architecture, meant to be understood as a structural
drawing rather than read as prose.
"""


class AgentFrameworkImageClassifierAgent:
    """Classifies an uploaded image via a Microsoft Agent Framework ``Agent``."""

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
            name="ImageInputClassifier",
            instructions=_INSTRUCTIONS,
        )

    async def classify(self, content: bytes, filename: str) -> ImageClassification:
        """Satisfies ``app.application.ports.ImageClassifierPort``."""

        message = Message(
            role="user",
            contents=[
                Content.from_text(_CLASSIFICATION_PROMPT),
                image_content(content, filename),
            ],
        )

        try:
            response = await self._agent.run(
                message,
                options=ChatOptions(response_format=ImageClassification),
            )
        except Exception as exc:
            raise ImageClassificationError(
                "Microsoft Agent Framework could not classify the uploaded image."
            ) from exc

        if not isinstance(response.value, ImageClassification):
            raise ImageClassificationError(
                "Microsoft Agent Framework returned no image classification."
            )

        return response.value
