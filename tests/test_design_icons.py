from app.design.icons import (
    GENERIC_COMPONENT_ICON,
    GENERIC_DEPENDENCY_ICON,
    component_icon_path,
    dependency_icon_path,
)


def test_component_icon_matches_specific_keyword() -> None:
    path = component_icon_path(
        "Kubernetes Cluster", "Hosts all application containers."
    )

    assert path.endswith("kubernetes.png")


def test_component_icon_falls_back_to_generic_when_nothing_matches() -> None:
    path = component_icon_path(
        "Order Reconciliation Worker", "Reconciles nightly orders."
    )

    assert path.endswith(GENERIC_COMPONENT_ICON)


def test_dependency_icon_falls_back_to_generic_when_nothing_matches() -> None:
    path = dependency_icon_path("Acme Partner Feed", "Receives partner order updates.")

    assert path.endswith(GENERIC_DEPENDENCY_ICON)


def test_dependency_icon_prefers_key_vault_over_generic_storage_keyword() -> None:
    """Regression test: "Secret storage." (a Key Vault dependency's
    purpose text) contains the generic word "storage", which used to be
    checked before the more specific "key vault"/"secret" keywords and
    so incorrectly won — the dependency got a blob storage icon instead
    of the Key Vault one. Confirmed against a real rendered diagram
    before this was fixed."""

    path = dependency_icon_path("Key Vault", "Secret storage.")

    assert path.endswith("key-vault.png")


def test_component_icon_prefers_pipeline_name_over_container_in_body() -> None:
    """Regression test: a "CI/CD Pipeline" component whose responsibility
    happens to mention "container images" used to match the generic
    "container" keyword (found in the responsibility text) before ever
    reaching the "pipeline" keyword, since keyword order was checked
    against one combined "name + responsibility" string rather than the
    name first. Confirmed against a real rendered diagram before this
    was fixed."""

    path = component_icon_path(
        "CI/CD Pipeline",
        "Builds and deploys container images via Azure Pipelines.",
    )

    assert path.endswith("devops-pipeline.png")


def test_component_icon_checks_name_before_responsibility() -> None:
    """A keyword appearing only in the responsibility text (not the
    name) is still matched — name-first doesn't mean responsibility is
    ignored, only that it's checked second."""

    path = component_icon_path("Primary Store", "Backed by Azure Cosmos DB.")

    assert path.endswith("cosmos-db.png")
