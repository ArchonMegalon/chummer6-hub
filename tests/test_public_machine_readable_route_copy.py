from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WWWROOT = REPO_ROOT / "Chummer.Run.Api" / "wwwroot"


def test_machine_readable_route_guides_keep_public_front_door_minimal() -> None:
    llms = (WWWROOT / "llms.txt").read_text(encoding="utf-8")
    ai = (WWWROOT / "ai.txt").read_text(encoding="utf-8")
    combined = f"{llms}\n{ai}"

    assert "The main public routes are Downloads, Help, and Contact." in llms
    assert "Participate is the public feedback and roadmap surface." in llms
    assert "Public feedback and roadmap: /participate" in ai

    for retired in (
        "The main public routes are Downloads, Help, Status, and Contact.",
        "/feedback : public feedback",
        "Public feedback: /feedback",
        "Planned work: /roadmap",
        "private support",
        "/proofs/",
        "HUB_LOCAL_RELEASE_PROOF",
    ):
        assert retired not in combined


def test_robots_keeps_internal_proof_shelf_out_of_crawlers() -> None:
    robots = (WWWROOT / "robots.txt").read_text(encoding="utf-8")

    assert "Disallow: /proofs/" in robots
