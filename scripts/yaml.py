from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any


class YAMLError(Exception):
    pass


@dataclass(frozen=True)
class _Line:
    indent: int
    text: str


_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$")
_KEY_RE = re.compile(r"^([^:\[\]\{\}]+):(.*)$")


def safe_load(stream: Any) -> Any:
    text = stream.read() if hasattr(stream, "read") else str(stream)
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    lines = _prepare_lines(text)
    if not lines:
        return None
    try:
        payload, index = _parse_block(lines, 0, lines[0].indent)
    except Exception as exc:
        if isinstance(exc, YAMLError):
            raise
        raise YAMLError(str(exc)) from exc
    if index < len(lines):
        raise YAMLError(f"unexpected trailing YAML content: {lines[index].text}")
    return payload


def safe_dump(data: Any, sort_keys: bool = False, allow_unicode: bool = False, **_: Any) -> str:
    del allow_unicode
    return _dump_value(data, 0, sort_keys)


def _prepare_lines(text: str) -> list[_Line]:
    prepared: list[_Line] = []
    for raw_line in text.splitlines():
        expanded = raw_line.expandtabs(2).rstrip()
        if not expanded.strip() or expanded.lstrip().startswith("#"):
            continue
        indent = len(expanded) - len(expanded.lstrip(" "))
        prepared.append(_Line(indent, expanded[indent:]))
    return prepared


def _parse_block(lines: list[_Line], index: int, indent: int) -> tuple[Any, int]:
    if lines[index].indent < indent:
        raise YAMLError("invalid indentation")
    if lines[index].text.startswith("- "):
        return _parse_list(lines, index, lines[index].indent)
    return _parse_mapping(lines, index, lines[index].indent)


def _parse_mapping(lines: list[_Line], index: int, indent: int) -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise YAMLError(f"unexpected indentation before {line.text!r}")
        if line.text.startswith("- "):
            break
        split = _split_key_value(line.text)
        if split is None:
            raise YAMLError(f"expected mapping entry, got {line.text!r}")
        key, raw_value = split
        index += 1
        payload[key], index = _parse_entry_value(lines, index, indent, raw_value)
    return payload, index


def _parse_list(lines: list[_Line], index: int, indent: int) -> tuple[list[Any], int]:
    payload: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            raise YAMLError(f"unexpected indentation before {line.text!r}")
        if not line.text.startswith("- "):
            break

        item_text = line.text[2:].strip()
        index += 1
        if not item_text:
            if index < len(lines) and lines[index].indent >= indent:
                value, index = _parse_block(lines, index, lines[index].indent)
            else:
                value = None
            payload.append(value)
            continue

        split = _split_key_value(item_text)
        if split is None:
            if _is_unclosed_quoted_scalar(item_text):
                item_text, index = _consume_quoted_scalar_continuations(lines, index, indent, item_text)
            value = _parse_scalar(item_text)
            if isinstance(value, str):
                value, index = _consume_scalar_continuations(lines, index, indent, value)
            payload.append(value)
            continue

        item: dict[str, Any] = {}
        key, raw_value = split
        item[key], index = _parse_entry_value(lines, index, indent, raw_value)
        field_indent = indent + 2
        while index < len(lines):
            next_line = lines[index]
            if next_line.indent <= indent:
                break
            if next_line.indent != field_indent or next_line.text.startswith("- "):
                break
            next_split = _split_key_value(next_line.text)
            if next_split is None:
                break
            next_key, next_raw_value = next_split
            index += 1
            item[next_key], index = _parse_entry_value(lines, index, field_indent, next_raw_value)
        payload.append(item)
    return payload, index


def _parse_entry_value(lines: list[_Line], index: int, indent: int, raw_value: str) -> tuple[Any, int]:
    value_text = raw_value.strip()
    if value_text:
        if _is_unclosed_quoted_scalar(value_text):
            value_text, index = _consume_quoted_scalar_continuations(lines, index, indent, value_text)
        value = _parse_scalar(value_text)
        if isinstance(value, str):
            value, index = _consume_scalar_continuations(lines, index, indent, value)
        return value, index

    if index >= len(lines):
        return None, index
    next_line = lines[index]
    if next_line.indent > indent or (next_line.indent == indent and next_line.text.startswith("- ")):
        return _parse_block(lines, index, next_line.indent)
    return None, index


def _is_unclosed_quoted_scalar(value: str) -> bool:
    stripped = value.strip()
    if len(stripped) < 2 or stripped[0] not in {"'", '"'}:
        return False
    return not _quoted_scalar_is_closed(stripped)


def _quoted_scalar_is_closed(value: str) -> bool:
    quote = value[0]
    if not value.endswith(quote):
        return False
    if quote == "'":
        return len(value) > 1

    backslashes = 0
    for char in reversed(value[:-1]):
        if char != "\\":
            break
        backslashes += 1
    return backslashes % 2 == 0


def _consume_quoted_scalar_continuations(
    lines: list[_Line],
    index: int,
    indent: int,
    value: str,
) -> tuple[str, int]:
    parts = [value]
    while index < len(lines):
        line = lines[index]
        if line.indent <= indent:
            break
        parts.append(line.text.strip())
        index += 1
        joined = " ".join(part for part in parts if part)
        if _quoted_scalar_is_closed(joined):
            return joined, index
    return " ".join(part for part in parts if part), index


def _consume_scalar_continuations(
    lines: list[_Line],
    index: int,
    indent: int,
    value: str,
) -> tuple[str, int]:
    parts = [value]
    while index < len(lines):
        line = lines[index]
        if line.indent <= indent:
            break
        if line.text.startswith("- ") or _split_key_value(line.text) is not None:
            break
        parts.append(line.text.strip())
        index += 1
    return " ".join(part for part in parts if part), index


def _split_key_value(text: str) -> tuple[str, str] | None:
    match = _KEY_RE.match(text)
    if match is None:
        return None
    key = match.group(1).strip()
    raw_value = match.group(2)
    if not key:
        return None
    if raw_value and not raw_value.startswith(" "):
        return None
    return key, raw_value


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    lowered = value.lower()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.match(value):
        try:
            return int(value)
        except ValueError:
            return value
    if _FLOAT_RE.match(value):
        try:
            return float(value)
        except ValueError:
            return value
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [_parse_scalar(item) for item in _split_inline_items(value[1:-1])]
    if value.startswith("{") and value.endswith("}"):
        result: dict[str, Any] = {}
        for item in _split_inline_items(value[1:-1]):
            split = _split_key_value(item)
            if split is None:
                raise YAMLError(f"invalid inline mapping item: {item!r}")
            key, raw = split
            result[key] = _parse_scalar(raw.strip())
        return result
    return value


def _split_inline_items(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    for char in value:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        if char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        current.append(char)
    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _dump_value(value: Any, indent: int, sort_keys: bool) -> str:
    if isinstance(value, dict):
        return _dump_mapping(value, indent, sort_keys)
    if isinstance(value, list):
        return _dump_list(value, indent, sort_keys)
    return " " * indent + _format_scalar(value) + "\n"


def _dump_mapping(value: dict[Any, Any], indent: int, sort_keys: bool) -> str:
    lines: list[str] = []
    keys = sorted(value) if sort_keys else list(value.keys())
    prefix = " " * indent
    for key in keys:
        item = value[key]
        key_text = str(key)
        if _is_scalar(item):
            lines.append(f"{prefix}{key_text}: {_format_scalar(item)}\n")
        else:
            lines.append(f"{prefix}{key_text}:\n")
            lines.append(_dump_value(item, indent + 2, sort_keys))
    return "".join(lines)


def _dump_list(value: list[Any], indent: int, sort_keys: bool) -> str:
    lines: list[str] = []
    prefix = " " * indent
    for item in value:
        if _is_scalar(item):
            lines.append(f"{prefix}- {_format_scalar(item)}\n")
        elif isinstance(item, dict) and item:
            keys = sorted(item) if sort_keys else list(item.keys())
            first_key = keys[0]
            first_value = item[first_key]
            if _is_scalar(first_value):
                lines.append(f"{prefix}- {first_key}: {_format_scalar(first_value)}\n")
            else:
                lines.append(f"{prefix}- {first_key}:\n")
                lines.append(_dump_value(first_value, indent + 4, sort_keys))
            for key in keys[1:]:
                nested = item[key]
                if _is_scalar(nested):
                    lines.append(f"{prefix}  {key}: {_format_scalar(nested)}\n")
                else:
                    lines.append(f"{prefix}  {key}:\n")
                    lines.append(_dump_value(nested, indent + 4, sort_keys))
        else:
            lines.append(f"{prefix}-\n")
            lines.append(_dump_value(item, indent + 2, sort_keys))
    return "".join(lines)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if _needs_quotes(text):
        return repr(text)
    return text


def _needs_quotes(value: str) -> bool:
    lowered = value.lower()
    return (
        value != value.strip()
        or "\n" in value
        or lowered in {"null", "none", "true", "false", "~"}
        or value[0] in "-?:!&*#'\"{}[]"
        or ": " in value
        or value.endswith(":")
    )
