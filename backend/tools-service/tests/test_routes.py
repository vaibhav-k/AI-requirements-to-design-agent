"""Smoke tests for tools-service's HTTP surface.

Exercises the FastAPI app directly (no real Graphviz binary required for
the validate path; the diagram path does need Graphviz's `dot` on PATH,
same as the orchestrator did before this split - see the Dockerfile).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

_VALID_DESIGN = {
    "architecture_summary": "A minimal architecture.",
    "components": [
        {
            "id": "api",
            "name": "API",
            "responsibility": "Handles requests.",
        }
    ],
}

_INVALID_DESIGN = {
    "architecture_summary": "Has a dangling interface.",
    "components": [],
    "interfaces": [
        {
            "id": "i1",
            "name": "Bad link",
            "purpose": "References a component that does not exist.",
            "source_component": "missing",
            "target_component": "also-missing",
        }
    ],
}


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_validate_accepts_valid_design() -> None:
    response = client.post("/tools/designs/validate", json=_VALID_DESIGN)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True


def test_validate_rejects_invalid_design() -> None:
    response = client.post("/tools/designs/validate", json=_INVALID_DESIGN)

    assert response.status_code == 422
    assert "unknown" in response.json()["detail"].lower()


def test_generate_diagram_returns_svg() -> None:
    response = client.post("/tools/diagrams/generate", json=_VALID_DESIGN)

    assert response.status_code == 200
    body = response.json()
    assert "<svg" in body["svg"]


_REQUIREMENTS = {
    "summary": "s",
    "business_goal": "g",
    "actors": [],
    "functional_requirements": [
        {"id": "FR-001", "description": "Handle requests.", "priority": "high"}
    ],
    "non_functional_requirements": [],
    "data_requirements": [],
    "integration_requirements": [],
    "constraints": [],
    "assumptions": [],
    "open_questions": [],
}


def test_export_work_breakdown_returns_csv() -> None:
    breakdown = {
        "features": [
            {
                "feature": "Customer Management",
                "stories": [
                    {
                        "story": "Create customer",
                        "tasks": [
                            {
                                "task": "Implement POST /customers endpoint",
                                "description": "Add the endpoint.",
                                "effort": "M",
                                "requirement_ids": ["FR-001"],
                                "architecture_ids": ["api"],
                            }
                        ],
                    }
                ],
            }
        ],
        "ambiguities": [],
    }

    response = client.post(
        "/tools/work-breakdown/export",
        json={
            "breakdown": breakdown,
            "requirements": _REQUIREMENTS,
            "design": _VALID_DESIGN,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["csv_text"].splitlines()[0] == (
        "feature,story,task,description,effort,requirement_ids,architecture_ids"
    )
    assert body["task_count"] == 1


def test_export_work_breakdown_rejects_untraceable_task() -> None:
    breakdown = {
        "features": [
            {
                "feature": "Customer Management",
                "stories": [
                    {
                        "story": "Create customer",
                        "tasks": [
                            {
                                "task": "Implement POST /customers endpoint",
                                "description": "Add the endpoint.",
                                "effort": "M",
                                "requirement_ids": [],
                                "architecture_ids": [],
                            }
                        ],
                    }
                ],
            }
        ],
        "ambiguities": [],
    }

    response = client.post(
        "/tools/work-breakdown/export",
        json={
            "breakdown": breakdown,
            "requirements": _REQUIREMENTS,
            "design": _VALID_DESIGN,
        },
    )

    assert response.status_code == 422
    assert "traceability" in response.json()["detail"].lower()
