from __future__ import annotations

from pathlib import Path

import pytest


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = RUN_SERVICES_ROOT.parent
CANONICAL_STATUS_VIEW = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Status.cshtml"
CANONICAL_DOWNLOADS_VIEW = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Downloads.cshtml"
CANONICAL_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
CRITICAL_EXACT_MIRROR_PATHS = [
    Path("Chummer.Run.Api/Controllers/PublicLandingController.cs"),
    Path("Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"),
    Path("Chummer.Run.Api/Views/PublicLanding/Home.cshtml"),
    Path("Chummer.Run.Api/Views/PublicLanding/Horizons.cshtml"),
    Path("Chummer.Run.Api/wwwroot/service-worker.js"),
]
MIRROR_ROOTS = {
    "public_edge_main": WORKSPACE_ROOT / "chummer.run-services-public-edge-main",
    "participate_main": WORKSPACE_ROOT / "chummer.run-services-participate-main",
}
STATUS_CONTROLLER_NEEDLE = 'BuildPublicOrAuthenticatedChromeAsync("Status", "Current Chummer release status.", "/status", cancellationToken)'
STALE_STATUS_CONTROLLER_NEEDLE = 'BuildPublicOrAuthenticatedChromeAsync("Updated", "Current Chummer release status.", "/status", cancellationToken)'


def iter_available_mirror_paths(relative_path: Path) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []
    for mirror_name, mirror_root in MIRROR_ROOTS.items():
        candidate = mirror_root / relative_path
        if candidate.is_file():
            paths.append((mirror_name, candidate))
    return paths


def test_operational_status_view_mirrors_match_canonical_source_if_present() -> None:
    canonical = CANONICAL_STATUS_VIEW.read_text(encoding="utf-8")
    mirror_paths = iter_available_mirror_paths(Path("Chummer.Run.Api/Views/PublicLanding/Status.cshtml"))
    if not mirror_paths:
        pytest.skip("operational public-edge mirror trees are not present in this workspace slice")

    for mirror_name, path in mirror_paths:
        assert path.read_text(encoding="utf-8") == canonical, (
            f"{mirror_name} status view drifted from the canonical chummer.run-services status page"
        )


def test_operational_downloads_view_mirrors_match_canonical_source_if_present() -> None:
    canonical = CANONICAL_DOWNLOADS_VIEW.read_text(encoding="utf-8")
    mirror_paths = iter_available_mirror_paths(Path("Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"))
    if not mirror_paths:
        pytest.skip("operational public-edge mirror trees are not present in this workspace slice")

    for mirror_name, path in mirror_paths:
        assert path.read_text(encoding="utf-8") == canonical, (
            f"{mirror_name} downloads view drifted from the canonical chummer.run-services downloads page"
        )


def test_operational_status_controller_mirrors_keep_status_chrome_title_if_present() -> None:
    canonical = CANONICAL_CONTROLLER.read_text(encoding="utf-8")
    assert STATUS_CONTROLLER_NEEDLE in canonical
    assert STALE_STATUS_CONTROLLER_NEEDLE not in canonical

    mirror_paths = iter_available_mirror_paths(Path("Chummer.Run.Api/Controllers/PublicLandingController.cs"))
    if not mirror_paths:
        pytest.skip("operational public-edge mirror trees are not present in this workspace slice")

    for mirror_name, path in mirror_paths:
        source = path.read_text(encoding="utf-8")
        assert STATUS_CONTROLLER_NEEDLE in source, (
            f"{mirror_name} controller lost the canonical /status chrome title contract"
        )
        assert STALE_STATUS_CONTROLLER_NEEDLE not in source, (
            f"{mirror_name} controller still exposes the stale Updated /status chrome title"
        )


@pytest.mark.parametrize("relative_path", CRITICAL_EXACT_MIRROR_PATHS)
def test_operational_critical_public_surface_mirrors_match_canonical_source_if_present(relative_path: Path) -> None:
    canonical_path = RUN_SERVICES_ROOT / relative_path
    canonical = canonical_path.read_text(encoding="utf-8")
    mirror_paths = iter_available_mirror_paths(relative_path)
    if not mirror_paths:
        pytest.skip("operational public-edge mirror trees are not present in this workspace slice")

    for mirror_name, path in mirror_paths:
        assert path.read_text(encoding="utf-8") == canonical, (
            f"{mirror_name} mirrored surface drifted from canonical {relative_path}"
        )
