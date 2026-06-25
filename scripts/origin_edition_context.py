from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_PROJECT_ID = "varga-mira-kestrel"
DEFAULT_FAMILY_NAME = "Varga"
DEFAULT_GIVEN_NAME = "Mira"
DEFAULT_RUNNER_NAME = "Kestrel"
DEFAULT_BASE_URL = "https://chummer.run"


def _clean(value: str | None, fallback: str) -> str:
    text = str(value or "").strip().strip("/")
    return text or fallback


@dataclass(frozen=True)
class OriginEditionContext:
    project_id: str = DEFAULT_PROJECT_ID
    family_name: str = DEFAULT_FAMILY_NAME
    given_name: str = DEFAULT_GIVEN_NAME
    runner_name: str = DEFAULT_RUNNER_NAME
    base_url: str = DEFAULT_BASE_URL
    namespace: str = ""

    @classmethod
    def default(cls) -> "OriginEditionContext":
        return cls()

    @classmethod
    def from_env(
        cls,
        *,
        project_id: str | None = None,
        family_name: str | None = None,
        given_name: str | None = None,
        runner_name: str | None = None,
        base_url: str | None = None,
        namespace: str | None = None,
    ) -> "OriginEditionContext":
        return cls(
            project_id=_clean(project_id or os.environ.get("CHUMMER_ORIGIN_EDITION_PROJECT_ID"), DEFAULT_PROJECT_ID),
            family_name=_clean(family_name or os.environ.get("CHUMMER_ORIGIN_EDITION_FAMILY_NAME"), DEFAULT_FAMILY_NAME),
            given_name=_clean(given_name or os.environ.get("CHUMMER_ORIGIN_EDITION_GIVEN_NAME"), DEFAULT_GIVEN_NAME),
            runner_name=_clean(runner_name or os.environ.get("CHUMMER_ORIGIN_EDITION_RUNNER_NAME"), DEFAULT_RUNNER_NAME),
            base_url=(base_url or os.environ.get("CHUMMER_ORIGIN_EDITION_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/"),
            namespace=_clean(namespace or os.environ.get("CHUMMER_ORIGIN_EDITION_NAMESPACE"), ""),
        )

    @property
    def resolved_namespace(self) -> str:
        if self.namespace:
            return self.namespace
        return f"origin.chummer.run/{self.family_name}/{self.given_name}/{self.runner_name}"

    def branch(self, evidence_root: Path) -> Path:
        return evidence_root / self.resolved_namespace

    @property
    def owner_url(self) -> str:
        return f"{self.base_url}/account/work/origin-dossiers/{self.project_id}"

    @property
    def account_library_url(self) -> str:
        return f"{self.base_url}/account/work#origin-dossier-library"
