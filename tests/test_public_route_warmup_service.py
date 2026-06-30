from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_public_route_warmup_runs_after_kestrel_starts_and_covers_slow_routes() -> None:
    service = read("Chummer.Run.Api/Services/PublicRouteWarmupService.cs")
    registrations = read("Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs")

    assert "services.AddHostedService<PublicRouteWarmupService>();" in registrations
    assert "_lifetime.ApplicationStarted.Register" in service
    assert "http://127.0.0.1:8080" in service
    assert "HttpCompletionOption.ResponseHeadersRead" in service
    assert "ReadAsByteArrayAsync" in service

    for route in (
        '"/mobile"',
        '"/play"',
        '"/play/continuity"',
        '"/edition-studio"',
        '"/docs/chummer6-quickstart"',
        '"/faq"',
        '"/privacy"',
        '"/ready"',
        '"/rules"',
        '"/jackpoint"',
        '"/runsites"',
        '"/ledger/map"',
        '"/ledger/factions"',
        '"/ledger/factions/ashline-circle"',
        '"/ledger/newsroom/turn-1-newsreel"',
        '"/ledger/newsroom/turn-2-newsreel"',
    ):
        assert route in service
