from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_MANUSCRIPT_PROVIDER_TOKENS = (
    "inkfluence",
    "youbooks",
    "first book",
    "firstbook",
    "chummer originbookengine",
)
DEFAULT_AUDIO_PROVIDER_TOKENS = (
    "inkfluence",
    "unmixr",
)
DEFAULT_VISUAL_PROVIDER_TOKENS = (
    "magicfit",
)


def _configured_tokens(env_name: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(env_name, "")
    configured = tuple(token.strip().lower() for token in raw.split(",") if token.strip())
    return tuple(dict.fromkeys(configured or defaults))


@dataclass(frozen=True)
class OriginProviderCapabilityRegistry:
    manuscript_provider_tokens: tuple[str, ...] = DEFAULT_MANUSCRIPT_PROVIDER_TOKENS
    audio_provider_tokens: tuple[str, ...] = DEFAULT_AUDIO_PROVIDER_TOKENS
    visual_provider_tokens: tuple[str, ...] = DEFAULT_VISUAL_PROVIDER_TOKENS

    @classmethod
    def from_env(cls) -> "OriginProviderCapabilityRegistry":
        return cls(
            manuscript_provider_tokens=_configured_tokens(
                "CHUMMER_ORIGIN_MANUSCRIPT_PROVIDER_TOKENS",
                DEFAULT_MANUSCRIPT_PROVIDER_TOKENS,
            ),
            audio_provider_tokens=_configured_tokens(
                "CHUMMER_ORIGIN_AUDIO_PROVIDER_TOKENS",
                DEFAULT_AUDIO_PROVIDER_TOKENS,
            ),
            visual_provider_tokens=_configured_tokens(
                "CHUMMER_ORIGIN_VISUAL_PROVIDER_TOKENS",
                DEFAULT_VISUAL_PROVIDER_TOKENS,
            ),
        )

    def manuscript_provider_allowed(self, value: object) -> bool:
        return _contains_any(value, self.manuscript_provider_tokens)

    def audio_provider_allowed(self, value: object) -> bool:
        return _contains_any(value, self.audio_provider_tokens)

    def visual_provider_allowed(self, value: object) -> bool:
        return _contains_any(value, self.visual_provider_tokens)

    def matched_audio_provider_label(self, *values: object) -> str:
        return _matched_label(self.audio_provider_tokens, *values)

    def matched_visual_provider_label(self, *values: object) -> str:
        return _matched_label(self.visual_provider_tokens, *values)


def _contains_any(value: object, tokens: tuple[str, ...]) -> bool:
    haystack = str(value or "").lower()
    return any(_contains_token(haystack, token) for token in tokens if token)


def _matched_label(tokens: tuple[str, ...], *values: object) -> str:
    for value in values:
        label = str(value or "").strip()
        haystack = label.lower()
        if label and any(_contains_token(haystack, token) for token in tokens if token):
            return label
    return ""


def _contains_token(haystack: str, token: str) -> bool:
    needle = token.strip().lower()
    if not needle:
        return False
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index > 0 else ""
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        if _token_boundary(before) and _token_boundary(after):
            return True
        start = index + 1


def _token_boundary(value: str) -> bool:
    return not value or not value.isalnum()
