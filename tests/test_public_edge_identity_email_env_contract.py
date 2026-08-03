from pathlib import Path


def test_identity_email_secret_env_is_optional_and_outside_the_repository() -> None:
    compose = Path("docker-compose.public-edge.yml").read_text(encoding="utf-8")

    assert "chummer-run-identity:" in compose
    assert (
        "CHUMMER_IDENTITY_EMAIL_SECRET_ENV_FILE:-"
        "/docker/fleet/state/chummer-secrets/chummer-run-identity/emailit.env"
    ) in compose
    assert "required: false" in compose
    assert "IDENTITY_EMAILIT_API_KEY: ${IDENTITY_EMAILIT_API_KEY:-}" in compose

    delivery = Path(
        "Chummer.Run.Identity/Services/IdentityEmailDeliveryService.cs"
    ).read_text(encoding="utf-8")
    assert 'configuration["CHUMMER_IDENTITY_EMAILIT_API_KEY_SECRET"]?.Trim()' in delivery
    assert '? configuration["IDENTITY_EMAILIT_API_KEY"]?.Trim()' in delivery


def test_identity_email_sign_in_remains_fail_closed_without_operator_activation() -> None:
    compose = Path("docker-compose.public-edge.yml").read_text(encoding="utf-8")

    assert "IDENTITY_EMAIL_PROVIDER_ORDER: ${IDENTITY_EMAIL_PROVIDER_ORDER:-none}" in compose
    assert "IDENTITY_EMAIL_START_ENABLED: ${IDENTITY_EMAIL_START_ENABLED:-false}" in compose


def test_identity_docker_context_includes_the_identity_service() -> None:
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert "!Chummer.Run.Identity/" in dockerignore
    assert "!Chummer.Run.Identity/**" in dockerignore

    dockerfile = Path("Chummer.Run.Identity/Dockerfile").read_text(encoding="utf-8")
    assert "COPY --from=run-services-source Directory.Build.props chummer.run-services/" in dockerfile
    assert dockerfile.count("-p:ChummerUseLocalCompatibilityTree=true") >= 3
    assert dockerfile.count("-p:ChummerWorkspaceRoot=/src") >= 3
