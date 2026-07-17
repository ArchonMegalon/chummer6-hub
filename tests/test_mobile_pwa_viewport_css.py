from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_CSS = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "css" / "site.css"


def test_route_choice_detail_pills_wrap_long_receipt_routes() -> None:
    css = SITE_CSS.read_text(encoding="utf-8")
    rule_start = css.index(".route-callout__details span,")
    rule_end = css.index("}", rule_start)
    rule = css[rule_start:rule_end]

    assert ".route-choice-card__details span" in rule
    assert "min-width: 0;" in rule
    assert "max-width: 100%;" in rule
    assert "overflow-wrap: anywhere;" in rule
    assert "word-break: break-word;" in rule
