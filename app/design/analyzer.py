from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

from app.design.models import SystemDesignArtifact
from app.models import RequirementsArtifact

load_dotenv()


class DesignGenerationError(RuntimeError):
    """Raised when architecture generation fails."""


def _required_environment_variable(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"{name} environment variable is required.")

    return value


AZURE_OPENAI_API_KEY = _required_environment_variable("AZURE_OPENAI_API_KEY")

AZURE_OPENAI_ENDPOINT = _required_environment_variable("AZURE_OPENAI_ENDPOINT")

AZURE_OPENAI_MODEL = _required_environment_variable("AZURE_OPENAI_MODEL")


class SystemDesignAnalyzer:
    """Generate a high-level architecture from requirements."""

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
        requirements: RequirementsArtifact,
    ) -> SystemDesignArtifact:
        """Generate a high-level system design."""

        prompt = self._build_prompt(requirements)

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior software architect. "
                            "Generate a high-level system architecture "
                            "from the supplied requirements."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                text_format=SystemDesignArtifact,
            )
        except Exception as exc:
            raise DesignGenerationError(
                "Azure OpenAI architecture generation failed."
            ) from exc

        if response.output_parsed is None:
            raise DesignGenerationError(
                "Azure OpenAI returned no parsed system design."
            )

        return response.output_parsed

    @staticmethod
    def _build_prompt(
        requirements: RequirementsArtifact,
    ) -> str:
        requirements_json = requirements.model_dump_json(indent=2)

        return f"""
Create a HIGH-LEVEL SYSTEM ARCHITECTURE from the requirements below.

This is MVP-2 of a requirements-to-design agent.

The purpose is to transform understood requirements into a
logical system architecture.

DO:

- Identify major logical system components.
- Give every component a unique ID.
- Describe each component's responsibility.
- Map each component to the requirement IDs that justify it.
- Identify important interactions between components.
- Give every interface a unique ID.
- Map each interface to the requirement IDs that justify it.
- Identify external services, hardware, or dependencies explicitly
  required by the requirements.
- For each external dependency, identify the components that use it.
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

Every requirement-to-component and requirement-to-interface mapping
must reference an actual requirement ID from the supplied requirements.

The architecture should be understandable to a product owner,
software architect, and engineering team.

The resulting architecture will also be rendered as a
high-level Graphviz diagram.

Accepted requirements:

{requirements_json}
"""
