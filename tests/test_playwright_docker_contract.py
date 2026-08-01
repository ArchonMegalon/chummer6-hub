from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "legacy" / "tooling" / "docker" / "Docker" / "Dockerfile.playwright"
DOCKERIGNORE = ROOT / ".dockerignore"
FIXTURE = ROOT / "Chummer.Tests" / "TestFiles" / "BLUE.chum5"
HUB_E2E_SCRIPT = ROOT / "scripts" / "e2e-hub.sh"
HUB_PLAYWRIGHT_SCRIPT = ROOT / "scripts" / "e2e-hub-playwright.cjs"


def test_playwright_character_fixture_is_present_and_in_docker_context() -> None:
    assert FIXTURE.is_file()
    assert FIXTURE.stat().st_size > 0

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert (
        "COPY Chummer.Tests/TestFiles/BLUE.chum5 /work/testdata/BLUE.chum5"
        in dockerfile
    )

    dockerignore_lines = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert "!Chummer.Tests/" in dockerignore_lines
    assert "!Chummer.Tests/TestFiles/" in dockerignore_lines
    assert "!Chummer.Tests/TestFiles/BLUE.chum5" in dockerignore_lines


def test_local_reverse_proxy_browser_receives_public_host_and_proto() -> None:
    script = HUB_E2E_SCRIPT.read_text(encoding="utf-8")
    browser_run = script[script.index("timeout \"${HUB_PLAYWRIGHT_TIMEOUT_SECONDS}\"s docker run") :]
    assert 'playwright_docker_args+=(--add-host "$HUB_PUBLIC_HOST:127.0.0.1")' in script
    assert '-e CHUMMER_HUB_PLAYWRIGHT_BASE_URL="$playwright_base_url"' in browser_run
    assert '-e CHUMMER_HUB_PLAYWRIGHT_FORWARDED_PROTO="https"' in browser_run

    playwright = HUB_PLAYWRIGHT_SCRIPT.read_text(encoding="utf-8")
    assert "extraHTTPHeaders.Host" not in playwright
