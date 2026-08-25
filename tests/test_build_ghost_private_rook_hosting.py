from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.build-ghost-private-nonprod.yml").read_text(encoding="utf-8")
AI_DOCKERFILE = (ROOT / "Chummer.Run.AI/Dockerfile.private-nonprod").read_text(encoding="utf-8")
CANARY = (ROOT / "ops/build-ghost-private-nonprod/run-local-canary.sh").read_text(encoding="utf-8")
AI_DEPLOY = (ROOT / "ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh").read_text(
    encoding="utf-8"
)
PRESENTATION_DEPLOY = (
    ROOT / "ops/build-ghost-private-nonprod/deploy-presentation-with-rollback.sh"
).read_text(encoding="utf-8")
CADDY = (ROOT / "ops/build-ghost-private-nonprod/Caddyfile").read_text(encoding="utf-8")
HANDOFF = (ROOT / "ops/build-ghost-private-nonprod/ROOK_PRIVATE_HOSTING_HANDOFF.md").read_text(
    encoding="utf-8"
)


def service_block(name: str, next_name: str) -> str:
    return COMPOSE.split(f"\n  {name}:\n", 1)[1].split(f"\n  {next_name}:\n", 1)[0]


def test_presentation_reaches_rook_support_only_over_the_internal_ai_boundary() -> None:
    presentation = service_block("chummer-build-ghost-presentation", "chummer-build-ghost-ai")
    assert "CHUMMER_BUILD_GHOST_AI_BASE_URL: http://chummer-build-ghost-ai:8080" in presentation
    assert (
        "CHUMMER_AI_INTERNAL_API_TOKEN: ${CHUMMER_AI_INTERNAL_API_TOKEN:?"
        in presentation
    )
    assert "build-ghost-private: {}" in presentation
    assert "build-ghost-loopback" not in presentation
    assert "/api/v1/ai/build-ghost/support-experience" not in CADDY
    assert "/account/alice" not in CADDY


def test_live_provider_and_vidboard_inputs_are_literal_empty_and_remote_is_default_off() -> None:
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    for literal_empty in (
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_RECEIPT_PATH",
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_HMAC_KEY",
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_ACCOUNT_SCOPE_REF_DIGEST",
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SCENARIO_REF_DIGEST",
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_AVATAR_BINDING_DIGEST",
        "CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_HREF",
        "CHUMMER_BUILD_GHOST_ROOK_VIDBOARD_MEDIA_DIGEST",
        "CHUMMER_BUILD_GHOST_PERSONA_RELEASE_REGISTRY_PATH",
        "CHUMMER_BUILD_GHOST_MEETING_BROKER_BASE_URL",
        "CHUMMER_BUILD_GHOST_MEETING_BROKER_API_TOKEN",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_API_KEY",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_SCENARIO_ID",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MEETING_BOT_NAME",
    ):
        assert f'{literal_empty}: ""' in ai
        assert f"{literal_empty}: ${{" not in ai
    assert 'CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED: "false"' in ai
    assert "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED: ${" not in ai


def test_encrypted_store_has_a_distinct_private_named_volume_and_required_key() -> None:
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    assert (
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_PATH: "
        "/app/state/build-ghost-live-support"
    ) in ai
    assert (
        "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY: "
        "${CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY:?"
    ) in ai
    assert 'CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SINGLE_INSTANCE: "true"' in ai
    assert "build-ghost-live-support:/app/state/build-ghost-live-support" in ai
    assert "  build-ghost-live-support:\n" in COMPOSE
    assert (
        'install -d -o "$APP_UID" -g "$APP_UID" -m 0700 '
        "/app/state/build-ghost-live-support"
    ) in AI_DOCKERFILE
    assert "build-ghost-live-support" not in service_block(
        "chummer-build-ghost-presentation", "chummer-build-ghost-ai"
    )


def test_first_boot_initializer_is_no_network_and_refuses_to_repair_nonempty_drift() -> None:
    initializer = COMPOSE.split("\n  build-ghost-live-support-store-init:\n", 1)[1].split(
        "\n  build-ghost-cloudflare-access-edge:\n", 1
    )[0]
    assert 'user: "0:0"' in initializer
    assert "network_mode: none" in initializer
    assert "read_only: true" in initializer
    assert "cap_drop:\n      - ALL" in initializer
    assert "cap_add:\n      - CHOWN\n      - FOWNER" in initializer
    assert "no-new-privileges:true" in initializer
    assert 'if [ -z "$$(find "$$store" -mindepth 1 -maxdepth 1 -print -quit)" ]' in initializer
    assert '[ "$$(stat -c \'%a:%u\' -- "$$store")" = "700:$$runtime_uid" ]' in initializer
    assert "build-ghost-live-support:/live-support-store" in initializer
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    assert "build-ghost-live-support-store-init:" in ai
    assert "condition: service_completed_successfully" in ai


def test_bounded_deploys_recover_and_validate_the_existing_store_key_without_output() -> None:
    for script in (AI_DEPLOY, PRESENTATION_DEPLOY):
        assert "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY required" in script
        assert "^[A-Za-z0-9+/]{43}=$" in script
        assert "runtime-live-support-session-store-key-not-distinct" in script
        assert "CHUMMER_BUILD_GHOST_LIVE_SUPPORT_SESSION_STORE_KEY=" not in script
        assert "(.read_only // false) == false" in script
    assert "postcheck-live-support-store-topology-invalid" in AI_DEPLOY
    assert 'test "$(stat -c "%a:%u" -- "$path")" = "700:$(id -u)"' in AI_DEPLOY


def test_local_canary_proves_text_fallback_and_no_store_blockers_without_provider_io() -> None:
    assert "/api/v1/ai/build-ghost/support-experience" in CANARY
    assert '--header @-' in CANARY
    assert '--header "Authorization: Bearer $CHUMMER_AI_INTERNAL_API_TOKEN"' not in CANARY
    assert '.defaultSupport.channelKind == "rook_vidboard"' in CANARY
    assert '.defaultSupport.preRenderedVideoReady == false' in CANARY
    assert '.defaultSupport.availabilityStatus == "text-fallback"' in CANARY
    assert '.liveSupport.requestAvailable == false' in CANARY
    assert '.liveSupport.meetingProviders == []' in CANARY
    assert 'startswith("live-support-session-store-")' in CANARY
    assert "rook=text-fallback live_support=disabled store=private" in CANARY
    assert "api.toughtongueai.com" not in CANARY
    assert "zoom.us" not in CANARY
    assert "teams.microsoft.com" not in CANARY


def test_handoff_names_first_rollout_and_activation_stop_boundaries() -> None:
    for required in (
        "merged PR #237",
        "five-minute packet key",
        "full lane for the first transition",
        "exact mode 0700",
        "Do not rotate the journal key",
        "does not expose the signed-in Rook page",
        "Zoom, Teams, and Tough Tongue",
    ):
        assert required in HANDOFF
