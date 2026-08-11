from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

from .models import RequirementsArtifact

load_dotenv()


def require_environment_variable(
    name: str,
    value: str | None,
) -> str:
    """Return a required environment variable."""

    if not value:
        raise RuntimeError(f"{name} environment variable is required.")

    return value


AZURE_OPENAI_API_KEY = require_environment_variable(
    "AZURE_OPENAI_API_KEY",
    os.getenv("AZURE_OPENAI_API_KEY"),
)

AZURE_OPENAI_ENDPOINT = require_environment_variable(
    "AZURE_OPENAI_ENDPOINT",
    os.getenv("AZURE_OPENAI_ENDPOINT"),
)

AZURE_OPENAI_MODEL = require_environment_variable(
    "AZURE_OPENAI_MODEL",
    os.getenv("AZURE_OPENAI_MODEL"),
)


class RequirementsAnalyzer:
    """Analyze user input into structured requirements."""

    def __init__(
        self,
        model: str = AZURE_OPENAI_MODEL,
    ) -> None:
        self.client = OpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            base_url=AZURE_OPENAI_ENDPOINT.rstrip("/") + "/",
        )
        self.model = model

    def analyze(
        self,
        user_input: str,
        previous_artifact: RequirementsArtifact | None = None,
    ) -> RequirementsArtifact:
        """Analyze requirements and return a structured artifact."""

        prompt = self._build_prompt(
            user_input,
            previous_artifact,
        )

        response = self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise software requirements "
                        "analyst. Return only the requested "
                        "structured requirements."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            text_format=RequirementsArtifact,
        )

        if response.output_parsed is None:
            raise RuntimeError("Azure OpenAI returned no parsed requirements.")

        return response.output_parsed

    @staticmethod
    def _build_prompt(
        user_input: str,
        previous_artifact: RequirementsArtifact | None,
    ) -> str:
        """Build the requirements analysis prompt."""

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
