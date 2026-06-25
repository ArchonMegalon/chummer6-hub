#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path("/docker/chummercomplete")
DESIGN_BOUNDARY = ROOT / "chummer-design" / "products" / "chummer" / "BEHUMAN_EVENT_PROVIDER_BOUNDARY.md"
POSTURE_SERVICE = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "Services" / "Community" / "BeHumanEventAdapterPostureService.cs"
POSTURE_TESTS = ROOT / "chummer.run-services" / "Chummer.Tests" / "BeHumanEventAdapterPostureServiceTests.cs"
INTEGRATION_TESTS = ROOT / "chummer.run-services" / "Chummer.Tests" / "BeHumanEventAdapterIntegrationTests.cs"
SERVICE_COLLECTION = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "ServiceCollectionBoundedContextExtensions.cs"
PUBLIC_CONTROLLER = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
PARTICIPATE_VIEW = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Partizipate.cshtml"
VIEW_MODELS = ROOT / "chummer.run-services" / "Chummer.Run.Api" / "ViewModels" / "SiteViewModels.cs"


def main() -> int:
    missing = [
        path
        for path in (
            DESIGN_BOUNDARY,
            POSTURE_SERVICE,
            POSTURE_TESTS,
            INTEGRATION_TESTS,
            SERVICE_COLLECTION,
            PUBLIC_CONTROLLER,
            PARTICIPATE_VIEW,
            VIEW_MODELS,
        )
        if not path.is_file()
    ]
    if missing:
        for path in missing:
            print(f"missing:{path}")
        print("NOT_READY")
        return 1

    boundary_text = DESIGN_BOUNDARY.read_text(encoding="utf-8")
    posture_text = POSTURE_SERVICE.read_text(encoding="utf-8")
    service_collection_text = SERVICE_COLLECTION.read_text(encoding="utf-8")
    public_controller_text = PUBLIC_CONTROLLER.read_text(encoding="utf-8")
    participate_view_text = PARTICIPATE_VIEW.read_text(encoding="utf-8")
    view_models_text = VIEW_MODELS.read_text(encoding="utf-8")

    required_boundary_markers = [
        "event",
        "rules truth",
        "account identity",
        "support case truth",
        "Do not claim a public registration capacity until a provider verification receipt exists.",
    ]
    required_posture_markers = [
        "BEHUMAN_EVENT_ADAPTER_READY",
        "NOT_READY",
        "Provider verification receipt is missing or invalid.",
        "disabled by default",
    ]
    required_integration_markers = [
        ("service_collection", "services.AddSingleton<BeHumanEventAdapterPostureService>();", service_collection_text),
        ("controller", "BeHumanEventAdapterPostureService", public_controller_text),
        ("controller", "BuildBeHumanEventAdapterPanel()", public_controller_text),
        ("controller", "BeHumanEventAdapter: BuildBeHumanEventAdapterPanel()", public_controller_text),
        ("view_models", "BeHumanEventAdapterPanelViewModel? BeHumanEventAdapter = null", view_models_text),
        ("view", "BeHuman can help host public community events, but it does not get product truth.", participate_view_text),
        ("view", "Capacity stays unclaimed until a verified first-party receipt exists.", participate_view_text),
    ]

    for marker in required_boundary_markers:
        if marker not in boundary_text:
            print(f"boundary_missing:{marker}")
            print("NOT_READY")
            return 1

    for marker in required_posture_markers:
        if marker not in posture_text:
            print(f"service_missing:{marker}")
            print("NOT_READY")
            return 1

    for label, marker, text in required_integration_markers:
        if marker not in text:
            print(f"{label}_missing:{marker}")
            print("NOT_READY")
            return 1

    print("BEHUMAN_EVENT_ADAPTER_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
