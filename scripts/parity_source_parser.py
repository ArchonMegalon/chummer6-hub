from __future__ import annotations

import re


_CSHARP_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RETURN_TOKEN = re.compile(r"(?<![@A-Za-z0-9_])return(?![A-Za-z0-9_])")


class _UnterminatedCSharpSyntax(ValueError):
    pass


def _blank_non_newlines(masked: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if masked[index] not in {"\r", "\n"}:
            masked[index] = " "


def _quote_run_length(text: str, start: int) -> int:
    end = start
    while end < len(text) and text[end] == '"':
        end += 1
    return end - start


def _looks_like_empty_raw_literal(text: str, quote_start: int, quote_count: int) -> bool:
    if quote_count < 6 or quote_count % 2 != 0:
        return False
    end = quote_start + quote_count
    if end >= len(text):
        return True
    if text.startswith("u8", end):
        end += 2
        if end >= len(text):
            return True
    while end < len(text) and text[end].isspace():
        end += 1
    return end >= len(text) or text[end] in ";,.)]}:?+-*/%&|^!=<>"


def _block_comment_end(text: str, start: int) -> int:
    closing = text.find("*/", start + 2)
    if closing < 0:
        raise _UnterminatedCSharpSyntax("unterminated block comment")
    return closing + 2


def _line_comment_end(text: str, start: int) -> int:
    end = start + 2
    while end < len(text) and text[end] not in {"\r", "\n"}:
        end += 1
    return end


def _regular_string_end(text: str, quote_start: int, *, verbatim: bool) -> int:
    index = quote_start + 1
    while index < len(text):
        char = text[index]
        if verbatim:
            if char == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    index += 2
                    continue
                return index + 1
        else:
            if char == "\\":
                if index + 1 >= len(text) or text[index + 1] in {"\r", "\n"}:
                    raise _UnterminatedCSharpSyntax("unterminated ordinary string")
                index += 2
                continue
            if char == '"':
                return index + 1
            if char in {"\r", "\n"}:
                raise _UnterminatedCSharpSyntax("unterminated ordinary string")
        index += 1
    raise _UnterminatedCSharpSyntax("unterminated string")


def _interpolation_hole_end(text: str, start: int, *, closing_braces: int) -> int:
    depth = 0
    index = start
    while index < len(text):
        if text.startswith("//", index):
            index = _line_comment_end(text, index)
            continue
        if text.startswith("/*", index):
            index = _block_comment_end(text, index)
            continue
        literal_end = _quoted_literal_end(text, index)
        if literal_end is not None:
            index = literal_end
            continue
        if text[index] == "'":
            index = _char_literal_end(text, index)
            continue
        if text[index] == "{":
            depth += 1
            index += 1
            continue
        if text[index] == "}":
            run = 1
            while index + run < len(text) and text[index + run] == "}":
                run += 1
            if depth == 0 and run >= closing_braces:
                return index + closing_braces
            consumed = min(depth, run)
            depth -= consumed
            index += max(1, consumed)
            continue
        index += 1
    raise _UnterminatedCSharpSyntax("unterminated interpolation hole")


def _interpolated_string_end(text: str, quote_start: int, *, verbatim: bool) -> int:
    index = quote_start + 1
    while index < len(text):
        char = text[index]
        if not verbatim and char == "\\":
            if index + 1 >= len(text) or text[index + 1] in {"\r", "\n"}:
                raise _UnterminatedCSharpSyntax("unterminated interpolated string")
            index += 2
            continue
        if char == '"':
            if verbatim and index + 1 < len(text) and text[index + 1] == '"':
                index += 2
                continue
            return index + 1
        if char == "{":
            if index + 1 < len(text) and text[index + 1] == "{":
                index += 2
                continue
            index = _interpolation_hole_end(text, index + 1, closing_braces=1)
            continue
        if char == "}" and index + 1 < len(text) and text[index + 1] == "}":
            index += 2
            continue
        if not verbatim and char in {"\r", "\n"}:
            raise _UnterminatedCSharpSyntax("unterminated interpolated string")
        index += 1
    raise _UnterminatedCSharpSyntax("unterminated interpolated string")


def _raw_string_end(
    text: str,
    quote_start: int,
    *,
    quote_count: int,
    dollar_count: int,
) -> int:
    if _looks_like_empty_raw_literal(text, quote_start, quote_count):
        return quote_start + quote_count

    delimiter = '"' * quote_count
    index = quote_start + quote_count
    while index < len(text):
        if text.startswith(delimiter, index):
            return index + quote_count
        if dollar_count and text[index] == "{":
            run = 1
            while index + run < len(text) and text[index + run] == "{":
                run += 1
            if run >= dollar_count:
                index = _interpolation_hole_end(
                    text,
                    index + dollar_count,
                    closing_braces=dollar_count,
                )
                continue
        index += 1
    raise _UnterminatedCSharpSyntax("unterminated raw string")


def _quoted_literal_end(text: str, start: int) -> int | None:
    """Return the end of one C# string/raw-string literal beginning at start."""
    quote_start: int | None = None
    verbatim = False
    interpolated = False
    dollar_count = 0

    if text.startswith("$@\"", start) or text.startswith("@$\"", start):
        quote_start = start + 2
        verbatim = True
        interpolated = True
        dollar_count = 1
    elif text.startswith("@\"", start):
        quote_start = start + 1
        verbatim = True
    elif text[start] == "$":
        quote_start = start
        while quote_start < len(text) and text[quote_start] == "$":
            quote_start += 1
        dollar_count = quote_start - start
        if quote_start >= len(text) or text[quote_start] != '"':
            return None
        interpolated = True
    elif text[start] == '"':
        quote_start = start
    else:
        return None

    quote_count = _quote_run_length(text, quote_start)
    if quote_count >= 3:
        return _raw_string_end(
            text,
            quote_start,
            quote_count=quote_count,
            dollar_count=dollar_count,
        )
    if interpolated:
        return _interpolated_string_end(text, quote_start, verbatim=verbatim)
    return _regular_string_end(text, quote_start, verbatim=verbatim)


def _char_literal_end(text: str, start: int) -> int:
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 >= len(text) or text[index + 1] in {"\r", "\n"}:
                raise _UnterminatedCSharpSyntax("unterminated char literal")
            index += 2
            continue
        if char == "'":
            return index + 1
        if char in {"\r", "\n"}:
            raise _UnterminatedCSharpSyntax("unterminated char literal")
        index += 1
    raise _UnterminatedCSharpSyntax("unterminated char literal")


def _mask_csharp_non_code(text: str) -> str:
    """Mask comments and literals while preserving offsets and physical newlines."""
    masked = list(text)
    index = 0
    while index < len(text):
        if text.startswith("//", index):
            end = _line_comment_end(text, index)
            _blank_non_newlines(masked, index, end)
            index = end
            continue
        if text.startswith("/*", index):
            end = _block_comment_end(text, index)
            _blank_non_newlines(masked, index, end)
            index = end
            continue
        literal_end = _quoted_literal_end(text, index)
        if literal_end is not None:
            _blank_non_newlines(masked, index, literal_end)
            index = literal_end
            continue
        if text[index] == "'":
            end = _char_literal_end(text, index)
            _blank_non_newlines(masked, index, end)
            index = end
            continue
        index += 1
    return "".join(masked)


def _return_statement_end(masked: str, start: int) -> tuple[int, bool]:
    parentheses = 0
    brackets = 0
    braces = 0
    index = start
    while index < len(masked):
        char = masked[index]
        if char == "(":
            parentheses += 1
        elif char == ")":
            if parentheses == 0:
                return index, False
            parentheses -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            if brackets == 0:
                return index, False
            brackets -= 1
        elif char == "{":
            braces += 1
        elif char == "}":
            if braces == 0:
                return index, False
            braces -= 1
        elif char == ";" and parentheses == 0 and brackets == 0 and braces == 0:
            return index, True
        index += 1
    return len(masked), False


def _brace_depth(masked: str, start: int, end: int) -> int:
    depth = 0
    for char in masked[start:end]:
        if char == "{":
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
    return depth


def _matching_brace(masked: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def extract_switch_expression_body(
    text: str,
    *,
    variable_name: str,
    source: str,
) -> str:
    """Extract exactly one top-level C# return switch body, including wrappers."""
    if _CSHARP_IDENTIFIER.fullmatch(variable_name) is None:
        raise ValueError(f"invalid C# variable name: {variable_name}")

    try:
        masked = _mask_csharp_non_code(text)
    except _UnterminatedCSharpSyntax as exc:
        raise ValueError(
            f"{source} has an unterminated switch expression for {variable_name}"
        ) from exc
    switch_pattern = re.compile(
        rf"(?<![.@A-Za-z0-9_]){re.escape(variable_name)}(?![A-Za-z0-9_])"
        rf"\s+switch(?![A-Za-z0-9_])\s*\{{"
    )
    candidates: dict[int, tuple[re.Match[str], int, bool]] = {}
    for return_match in _RETURN_TOKEN.finditer(masked):
        statement_end, terminated = _return_statement_end(masked, return_match.end())
        for switch_match in switch_pattern.finditer(
            masked,
            return_match.end(),
            statement_end,
        ):
            if _brace_depth(masked, return_match.end(), switch_match.start()) != 0:
                continue
            candidates.setdefault(
                switch_match.start(),
                (switch_match, statement_end, terminated),
            )

    if not candidates:
        raise ValueError(f"{source} is missing a switch expression for {variable_name}")
    if len(candidates) != 1:
        raise ValueError(
            f"{source} has {len(candidates)} switch expressions for {variable_name}; expected exactly one"
        )

    switch_match, statement_end, terminated = next(iter(candidates.values()))
    opening = switch_match.end() - 1
    closing = _matching_brace(masked, opening)
    wrapper_tail = "" if closing is None else masked[closing + 1 : statement_end]
    has_valid_wrapper_tail = all(char.isspace() or char == ")" for char in wrapper_tail)
    if (
        not terminated
        or closing is None
        or closing >= statement_end
        or not has_valid_wrapper_tail
    ):
        raise ValueError(f"{source} has an unterminated switch expression for {variable_name}")
    return text[opening + 1 : closing]
