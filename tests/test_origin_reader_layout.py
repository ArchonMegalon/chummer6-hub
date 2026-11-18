"""Small source guards; actual responsive geometry is checked in the browser."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "Chummer.Run.Api/wwwroot/css/site.css").read_text(encoding="utf-8")
VIEW = (ROOT / "Chummer.Run.Api/Views/Accounts/OriginChapter.cshtml").read_text(encoding="utf-8")
READER = ".route-account-work-origin-chapters"
READY = READER + ":has(.origin-chapter-reader)"


def rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", CSS)
    if not match:
        raise AssertionError(f"Missing reader rule: {selector}")
    return match.group(1)


class OriginReaderLayoutTests(unittest.TestCase):
    def test_line_measure_belongs_to_prose_not_smaller_shell_font(self):
        article = rule(READER + " .origin-chapter-reader")
        prose = rule(READER + " .origin-chapter-reader__prose")
        self.assertIn("width: 100%", article)
        self.assertIn("max-width: none", article)
        self.assertIn("max-width: 74ch", prose)
        self.assertIn("font-size: clamp(", prose)
        self.assertIn("line-height: 1.7", prose)

    def test_compact_chrome_is_scoped_to_full_text_reader(self):
        self.assertIn("display: flex", rule(READY + " .site-header__inner"))
        self.assertIn("width: min(calc(100% - 2rem), 54rem)", rule(READY + " .site-main"))
        hero = rule(READY + " .minimal-page-hero")
        self.assertIn("background: none", hero)
        self.assertIn("box-shadow: none", hero)

    def test_mobile_uses_small_gutters_and_keeps_touch_target(self):
        mobile = CSS.split("/* A chapter is a reading surface", 1)[1]
        mobile = mobile.split("@media (max-width: 600px)", 1)[1].split("@media", 1)[0]
        self.assertIn("width: calc(100% - 1.5rem)", mobile)
        self.assertIn("padding: 1rem", mobile)
        self.assertIn("min-height: 44px", rule(READY + " .minimal-page-hero a"))

    def test_full_story_remains_encoded_complete_and_read_only(self):
        self.assertIn('class="origin-chapter-reader__prose">@Model.Text</div>', VIEW)
        self.assertIn('lang="@Model.Locale"', VIEW)
        self.assertIn("white-space: pre-wrap", VIEW)
        self.assertIn("does not change your runner", VIEW)
        self.assertNotIn("Html.Raw", VIEW)
        self.assertNotIn("<form", VIEW)


if __name__ == "__main__":
    unittest.main()
