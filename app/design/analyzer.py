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
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> SystemDesignArtifact:
        """Generate a high-level system design.

        Passing ``previous_design`` (with an accompanying
        ``refinement_input`` describing the requested change) refines that
        design instead of generating a fresh one from scratch — the
        architecture analogue of ``RequirementsAnalyzer.analyze``'s own
        ``previous_artifact`` parameter.
        """

        prompt = self._build_prompt(requirements, previous_design, refinement_input)

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
        previous_design: SystemDesignArtifact | None = None,
        refinement_input: str | None = None,
    ) -> str:
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
