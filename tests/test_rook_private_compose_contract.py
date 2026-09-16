from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _compose() -> str:
    return (ROOT / "docker-compose.rook-private.yml").read_text(encoding="utf-8")


def test_private_rook_profile_is_digest_pinned_and_not_public() -> None:
    compose = _compose()
    assert 'profiles: ["rook-private"]' in compose
    assert 'image: "${CHUMMER_RUN_AI_IMAGE:?Set CHUMMER_RUN_AI_IMAGE to an immutable digest-pinned image}"' in compose
    assert "    expose:" in compose
    assert "    ports:" not in compose
    assert "\n  public-origin:" not in compose
    assert "fleet-origin" in compose


def test_private_rook_profile_fails_closed_for_secrets_and_provider_activation() -> None:
    compose = _compose()
    assert 'path: "${CHUMMER_RUN_AI_ENV_FILE:?Set an owner-only environment file for the private service}"' in compose
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED: "false"' in compose
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED: "false"' in compose
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED: "false"' in compose
    for provider in (
        "AiMagicx",
        "OneMinAi",
        "ChatPlayground",
        "PromptingSystems",
        "BrowserAct",
        "MarkupGo",
        "PeekShot",
    ):
        assert f"AiGateway__Providers__{provider}__Enabled: \"false\"" in compose
    assert 'read_only: true' in compose
    assert 'cap_drop: ["ALL"]' in compose
