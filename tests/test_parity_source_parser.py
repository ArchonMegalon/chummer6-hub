from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parity_source_parser import extract_switch_expression_body


def _extract(text: str) -> str:
    return extract_switch_expression_body(
        text,
        variable_name="commandId",
        source="DesktopDialogFactory.cs",
    )


def test_extracts_direct_switch_expression() -> None:
    body = _extract(
        """
    return commandId switch
    {
        "open" => Open(),
        _ => Default()
    };
"""
    )

    assert '"open" => Open()' in body


def test_extracts_switch_wrapped_in_humanizer_call() -> None:
    body = _extract(
        """
    return HumanizeVisibleDialog(commandId switch
    {
        "open" => Open(),
        _ => Default()
    });
"""
    )

    assert '"open" => Open()' in body


def test_ignores_nested_and_textual_close_markers() -> None:
    body = _extract(
        """
    return Humanize(commandId switch
    {
        "open" => Build(
            "text that contains });",
            nested switch
            {
                true => "yes",
                false => "no"
            }),
        _ => Default()
    });
"""
    )

    assert 'false => "no"' in body
    assert "_ => Default()" in body


def test_accepts_crlf_source_and_multiple_wrapper_parentheses() -> None:
    body = _extract(
        "    return Outer(Inner(commandId switch\r\n"
        "    {\r\n"
        '        "open" => Open(),\r\n'
        "        _ => Default()\r\n"
        "    }));\r\n"
    )

    assert '"open" => Open()' in body


def test_rejects_missing_switch_expression() -> None:
    with pytest.raises(ValueError, match="missing a switch expression"):
        _extract("return Build(commandId);\n")


def test_rejects_ambiguous_switch_expressions() -> None:
    source = """
    return commandId switch
    {
        _ => First()
    };

    return commandId switch
    {
        _ => Second()
    };
"""

    with pytest.raises(ValueError, match="expected exactly one"):
        _extract(source)


def test_rejects_unterminated_wrapped_switch_expression() -> None:
    source = """
    return Humanize(commandId switch
    {
        _ => Default()
"""

    with pytest.raises(ValueError, match="unterminated"):
        _extract(source)


def test_ignores_same_indent_terminator_inside_block_comment() -> None:
    body = _extract(
        """
    return Humanize(commandId switch
    {
        "early" => Early(),
    /* hostile marker
    });
    */
        "late" => Late(),
        _ => Default()
    }); // real terminator may have a trailing comment
"""
    )

    assert '"early" => Early()' in body
    assert '"late" => Late()' in body


def test_ignores_fake_switch_starts_in_comments_and_string_literals() -> None:
    body = _extract(
        '''
    /* return commandId switch { _ => Fake() }; */
    return Humanize(commandId switch
    {
        "open" => Build("return commandId switch { };") ,
        _ => Default()
    });
'''
    )

    assert '"open" => Build' in body


def test_ignores_raw_verbatim_and_char_literal_braces() -> None:
    body = _extract(
        '''
    return Humanize(commandId switch
    {
        "raw" => Build("""raw }); commandId switch { text"""),
        "verbatim" => Build(@"quoted "" }); "" marker"),
        "char" => Build('}'),
        _ => Default()
    });
'''
    )

    assert '"char" => Build' in body
    assert "_ => Default()" in body


def test_rejects_two_switches_on_one_return_statement() -> None:
    source = """
    return Combine(
        commandId switch { _ => First() },
        commandId switch { _ => Second() });
"""

    with pytest.raises(ValueError, match="expected exactly one"):
        _extract(source)


def test_fake_switch_without_real_code_is_missing() -> None:
    with pytest.raises(ValueError, match="missing a switch expression"):
        _extract('return Log("commandId switch {");\n')


def test_interpolation_hole_literals_comments_and_braces_do_not_truncate_switch() -> None:
    body = _extract(
        r'''
    return Humanize(commandId switch
    {
        "early" => $"{Format(new[] { "}", "{" } /* } */)}",
        "verbatim" => $@"{Format("}")}",
        "late" => Late(),
        _ => Default()
    });
'''
    )

    assert '"verbatim" => $@' in body
    assert '"late" => Late()' in body


def test_ignores_fake_switch_start_inside_interpolation_hole_string() -> None:
    body = _extract(
        r'''
    return Log($"{Format("commandId switch {")}");
    return commandId switch { "real" => Real(), _ => Default() };
'''
    )

    assert '"real" => Real()' in body


def test_empty_raw_string_before_real_switch_does_not_mask_following_code() -> None:
    body = _extract(
        '''
    return Log("""""");
    return commandId switch { "real" => Real(), _ => Default() };
'''
    )

    assert '"real" => Real()' in body


def test_six_quote_multiline_raw_string_keeps_its_full_delimiter() -> None:
    body = _extract(
        '''
    return Log(""""""
raw }); commandId switch { text
"""""");
    return commandId switch { "real" => Real(), _ => Default() };
'''
    )

    assert '"real" => Real()' in body


@pytest.mark.parametrize("unterminated_literal", ['"unterminated', "'x"])
def test_rejects_unterminated_ordinary_string_and_char_literals(
    unterminated_literal: str,
) -> None:
    source = f'''
    return commandId switch
    {{
        "real" => {unterminated_literal}
        _ => Default()
    }};
'''

    with pytest.raises(ValueError, match="unterminated"):
        _extract(source)


def test_rejects_switch_that_borrows_later_statement_semicolon() -> None:
    source = '''
    return commandId switch
    {
        _ => Default()
    }
    Continue();
'''

    with pytest.raises(ValueError, match="unterminated"):
        _extract(source)
