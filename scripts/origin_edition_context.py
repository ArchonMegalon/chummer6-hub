from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_PROJECT_ID = "varga-mira-kestrel"
DEFAULT_FAMILY_NAME = "Varga"
DEFAULT_GIVEN_NAME = "Mira"
DEFAULT_RUNNER_NAME = "Kestrel"
DEFAULT_BASE_URL = "https://chummer.run"


class OriginEditionContextError(ValueError):
    pass


def _clean(value: str | None, fallback: str) -> str:
    text = str(value or "").strip().strip("/")
    return text or fallback


def _raw(value: str | None) -> str:
    return str(value or "").strip().strip("/")


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
        require_explicit: bool = False,
    ) -> "OriginEditionContext":
        raw_project_id = _raw(project_id or os.environ.get("CHUMMER_ORIGIN_EDITION_PROJECT_ID"))
        raw_family_name = _raw(family_name or os.environ.get("CHUMMER_ORIGIN_EDITION_FAMILY_NAME"))
        raw_given_name = _raw(given_name or os.environ.get("CHUMMER_ORIGIN_EDITION_GIVEN_NAME"))
        raw_runner_name = _raw(runner_name or os.environ.get("CHUMMER_ORIGIN_EDITION_RUNNER_NAME"))
        raw_base_url = str(base_url or os.environ.get("CHUMMER_ORIGIN_EDITION_BASE_URL") or "").strip().rstrip("/")
        raw_namespace = _raw(namespace or os.environ.get("CHUMMER_ORIGIN_EDITION_NAMESPACE"))
        if require_explicit:
            missing: list[str] = []
            if not raw_project_id:
                missing.append("CHUMMER_ORIGIN_EDITION_PROJECT_ID or --project-id")
            if not raw_base_url:
                missing.append("CHUMMER_ORIGIN_EDITION_BASE_URL or --base-url")
            if not raw_namespace:
                if not raw_family_name:
                    missing.append("CHUMMER_ORIGIN_EDITION_FAMILY_NAME or --family-name")
                if not raw_given_name:
                    missing.append("CHUMMER_ORIGIN_EDITION_GIVEN_NAME or --given-name")
                if not raw_runner_name:
                    missing.append("CHUMMER_ORIGIN_EDITION_RUNNER_NAME or --runner-name")
            if missing:
                raise OriginEditionContextError(
                    "explicit Origin Edition context required: " + ", ".join(missing)
                )
        return cls(
            project_id=_clean(raw_project_id, DEFAULT_PROJECT_ID),
            family_name=_clean(raw_family_name, DEFAULT_FAMILY_NAME),
            given_name=_clean(raw_given_name, DEFAULT_GIVEN_NAME),
            runner_name=_clean(raw_runner_name, DEFAULT_RUNNER_NAME),
            base_url=(raw_base_url or DEFAULT_BASE_URL).strip().rstrip("/"),
            namespace=_clean(raw_namespace, ""),
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
