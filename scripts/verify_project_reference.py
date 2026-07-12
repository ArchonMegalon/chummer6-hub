#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _resolve_include(project: Path, include: str) -> Path | None:
    expanded = include.strip()
    expanded = expanded.replace("$(MSBuildProjectDirectory)", str(project.parent))
    expanded = expanded.replace("$(MSBuildThisFileDirectory)", f"{project.parent}/")
    if "$(" in expanded:
        return None

    normalized = expanded.replace("\\", "/")
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = project.parent / candidate
    try:
        return candidate.resolve(strict=True)
    except OSError:
        return None


def _metadata_value(element: ET.Element, name: str) -> str:
    attribute_value = element.get(name, "").strip()
    if attribute_value:
        return attribute_value
    for child in element:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _is_unconditional_consumed_reference(element: ET.Element) -> bool:
    if element.get("Condition", "").strip():
        return False
    for metadata_name in ("ReferenceOutputAssembly", "BuildReference"):
        if _metadata_value(element, metadata_name).casefold() == "false":
            return False
    return True


def _is_static_unconditional_scope(ancestors: tuple[ET.Element, ...]) -> bool:
    if len(ancestors) != 2:
        return False
    project, item_group = ancestors
    if (
        _local_name(project.tag) != "Project"
        or _local_name(item_group.tag) != "ItemGroup"
    ):
        return False
    return not any(ancestor.get("Condition", "").strip() for ancestor in ancestors)


def _elements_with_ancestors(
    element: ET.Element,
    ancestors: tuple[ET.Element, ...] = (),
) -> Iterator[tuple[ET.Element, tuple[ET.Element, ...]]]:
    yield element, ancestors
    for child in element:
        yield from _elements_with_ancestors(child, (*ancestors, element))


def has_project_reference(project: Path, expected: Path) -> bool:
    try:
        root = ET.parse(project).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"cannot parse {project}: {exc}") from exc

    for element, ancestors in _elements_with_ancestors(root):
        if _local_name(element.tag) != "ProjectReference":
            continue
        if not _is_static_unconditional_scope(ancestors):
            continue
        if not _is_unconditional_consumed_reference(element):
            continue
        include = element.get("Include", "")
        if _resolve_include(project, include) == expected:
            return True
    return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify that MSBuild projects reference one exact owner project."
    )
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("projects", nargs="+", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        expected = args.expected.resolve(strict=True)
    except OSError as exc:
        print(f"expected owner project is unavailable: {args.expected}: {exc}", file=sys.stderr)
        return 2

    failed = False
    for project_arg in args.projects:
        project = project_arg.resolve()
        try:
            matches = has_project_reference(project, expected)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            failed = True
            continue
        if not matches:
            print(f"{project_arg} does not reference owner project {expected}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
