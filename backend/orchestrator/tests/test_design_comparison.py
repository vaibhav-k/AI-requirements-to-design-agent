from app.design.comparison import compare_architectures
from app.domain.design import (
    DesignAssumption,
    DesignComponent,
    DesignInterface,
    DesignQuestion,
    ExternalDependency,
    SystemDesignArtifact,
)


def make_design(**overrides: object) -> SystemDesignArtifact:
    defaults: dict[str, object] = {"architecture_summary": "A design."}
    defaults.update(overrides)
    return SystemDesignArtifact.model_validate(defaults)


def test_compare_reports_no_changes_between_identical_versions() -> None:
    design = make_design(
        components=[
            DesignComponent(id="C-001", name="API", responsibility="Handles requests.")
        ]
    )

    result = compare_architectures(1, 1, design, design)

    assert result.from_version == 1
    assert result.to_version == 1
    assert result.architecture_summary_changed is False
    assert result.components.added == []
    assert result.components.removed == []
    assert result.components.changed == []
    assert [c.id for c in result.components.unchanged] == ["C-001"]


def test_compare_detects_added_removed_and_changed_components() -> None:
    before = make_design(
        components=[
            DesignComponent(id="C-001", name="API", responsibility="Handles requests."),
            DesignComponent(id="C-002", name="DB", responsibility="Stores data."),
        ]
    )
    after = make_design(
        components=[
            DesignComponent(
                id="C-001",
                name="API",
                responsibility="Handles requests and auth.",
            ),
            DesignComponent(
                id="C-003", name="Notifier", responsibility="Sends notifications."
            ),
        ]
    )

    result = compare_architectures(1, 2, before, after)

    assert [c.id for c in result.components.added] == ["C-003"]
    assert [c.id for c in result.components.removed] == ["C-002"]
    assert len(result.components.changed) == 1
    assert result.components.changed[0].before.responsibility == "Handles requests."
    assert (
        result.components.changed[0].after.responsibility
        == "Handles requests and auth."
    )
    assert result.components.unchanged == []


def test_compare_detects_architecture_summary_change() -> None:
    before = make_design(architecture_summary="Original.")
    after = make_design(architecture_summary="Refined.")

    result = compare_architectures(1, 2, before, after)

    assert result.architecture_summary_changed is True
    assert result.from_architecture_summary == "Original."
    assert result.to_architecture_summary == "Refined."


def test_compare_diffs_interfaces_external_dependencies_assumptions_and_questions() -> (
    None
):
    before = make_design(
        interfaces=[
            DesignInterface(
                id="I-001",
                name="Call",
                purpose="p",
                source_component="C-001",
                target_component="C-002",
            )
        ],
        external_dependencies=[
            ExternalDependency(id="D-001", name="DB", purpose="store")
        ],
        assumptions=[DesignAssumption(id="A-001", assumption="x", reason="y")],
        open_questions=[DesignQuestion(id="Q-001", question="?", reason="y")],
    )
    after = make_design()

    result = compare_architectures(1, 2, before, after)

    assert [i.id for i in result.interfaces.removed] == ["I-001"]
    assert [d.id for d in result.external_dependencies.removed] == ["D-001"]
    assert [a.id for a in result.assumptions.removed] == ["A-001"]
    assert [q.id for q in result.open_questions.removed] == ["Q-001"]
