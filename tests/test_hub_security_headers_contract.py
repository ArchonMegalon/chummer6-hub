from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "Chummer.Run.Api" / "Program.cs"
HEADERS = (
    ROOT
    / "Chummer.Run.Api"
    / "Services"
    / "HubSecurityHeaders.cs"
)


def test_security_headers_are_applied_from_response_on_starting() -> None:
    program = PROGRAM.read_text(encoding="utf-8")

    assert program.count(
        "HubSecurityHeaders.Apply(context.Response.Headers);"
    ) == 1
    on_starting = program.index("context.Response.OnStarting(() =>")
    apply_headers = program.index(
        "HubSecurityHeaders.Apply(context.Response.Headers);"
    )
    await_next = program.index("await next();", on_starting)

    assert on_starting < apply_headers < await_next


def test_security_header_contract_is_bounded_and_nonbreaking() -> None:
    source = HEADERS.read_text(encoding="utf-8")

    expected_values = (
        "base-uri 'self'; frame-ancestors 'none'; object-src 'none'",
        "same-origin-allow-popups",
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        "strict-origin-when-cross-origin",
        "max-age=31536000",
        "nosniff",
        "DENY",
        "none",
    )
    for value in expected_values:
        assert value in source

    assert "includeSubDomains" not in source
    assert "preload" not in source
    assert "script-src" not in source
    assert "unsafe-inline" not in source
    assert "unsafe-eval" not in source
    assert source.count("headers.TryAdd(") == len(expected_values)
    assert 'headers["Content-Security-Policy"] =' not in source
    assert 'headers["Referrer-Policy"] =' not in source
