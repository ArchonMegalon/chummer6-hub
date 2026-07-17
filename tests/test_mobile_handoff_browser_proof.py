from __future__ import annotations

from pathlib import Path

import pytest


playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "Chummer.Run.Api" / "wwwroot" / "js" / "mobile-app-handoff.js").read_text(encoding="utf-8")


@pytest.fixture()
def page():
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def _mount(page, *, user_agent_data_mobile: bool | None) -> None:
    page.set_content(
        """
        <a href="/mobile/player" data-mobile-app-handoff="play-handoff">Play</a>
        <fieldset data-mobile-app-device-picker aria-describedby="device-status">
          <legend>Device handoff</legend>
          <label><input type="radio" name="device" value="auto" data-mobile-app-device-choice="auto" checked> Auto</label>
          <label><input type="radio" name="device" value="mobile" data-mobile-app-device-choice="mobile"> Mobile</label>
          <label><input type="radio" name="device" value="desktop" data-mobile-app-device-choice="desktop"> Desktop / QR</label>
        </fieldset>
        <p id="device-status" data-mobile-app-device-status role="status" aria-live="polite"></p>
        <div id="play-handoff" data-mobile-app-handoff-dialog
             data-mobile-app-path="https://chummer.run/mobile/player"
             data-mobile-app-origin="https://chummer.run" hidden>
          <button data-close-mobile-app-handoff>Close</button>
          <p data-mobile-app-suggestion></p>
          <div id="qr" data-mobile-app-qr-card tabindex="-1" hidden>
            <svg data-mobile-app-qr></svg>
            <p data-mobile-app-qr-status hidden></p>
          </div>
          <input data-mobile-app-link>
          <button data-show-mobile-app-qr aria-controls="qr" aria-expanded="false">Show QR / send to phone</button>
          <button data-copy-mobile-app-link>Copy</button>
          <a data-mobile-app-open>Open</a>
          <p data-mobile-app-copy-status hidden></p>
        </div>
        """
    )
    page.evaluate(
        """
        mobile => Object.defineProperty(navigator, "userAgentData", {
          configurable: true,
          value: typeof mobile === "boolean" ? { mobile } : undefined
        })
        """,
        user_agent_data_mobile,
    )
    page.evaluate(
        """
        window.ChummerUi = {
          bindModalDialog(dialog) {
            return { open() { dialog.hidden = false; } };
          },
          clearNotice() {},
          setNotice() {},
          copyToClipboard() { return Promise.resolve(); }
        };
        """
    )
    page.add_script_tag(content=SCRIPT)


def test_desktop_recommends_and_expands_qr_while_button_can_collapse(page) -> None:
    _mount(page, user_agent_data_mobile=False)
    page.click("[data-mobile-app-handoff]")

    assert page.locator("[data-mobile-app-qr-card]").is_visible()
    assert page.locator("[data-show-mobile-app-qr]").get_attribute("aria-expanded") == "true"
    assert page.locator("[data-mobile-app-qr]").get_attribute("data-qr-value") == "https://chummer.run/mobile/player"

    page.click("[data-show-mobile-app-qr]")
    assert page.locator("[data-mobile-app-qr-card]").is_hidden()
    assert page.locator("[data-show-mobile-app-qr]").get_attribute("aria-expanded") == "false"


def test_mobile_auto_keeps_native_navigation_instead_of_opening_the_dialog(page) -> None:
    _mount(page, user_agent_data_mobile=True)
    page.evaluate(
        """
        document.querySelector("[data-mobile-app-handoff]").addEventListener("click", event => {
          window.mobileHandoffWasPrevented = event.defaultPrevented;
          event.preventDefault();
        });
        """
    )
    page.click("[data-mobile-app-handoff]")

    assert page.evaluate("window.mobileHandoffWasPrevented") is False
    assert page.locator("[data-mobile-app-handoff-dialog]").is_hidden()
    assert page.locator("[data-mobile-app-handoff]").get_attribute(
        "data-mobile-app-effective-device"
    ) == "mobile"
    assert page.locator("[data-mobile-app-handoff]").get_attribute("aria-haspopup") is None


def test_desktop_override_on_mobile_opens_qr_and_is_announced(page) -> None:
    _mount(page, user_agent_data_mobile=True)
    page.check('[data-mobile-app-device-choice="desktop"]')
    page.click("[data-mobile-app-handoff]")

    assert page.locator("[data-mobile-app-qr-card]").is_visible()
    assert page.locator("[data-show-mobile-app-qr]").get_attribute("aria-expanded") == "true"
    assert "desktop override" in page.locator("[data-mobile-app-device-status]").inner_text().lower()
    assert page.locator("[data-mobile-app-handoff]").get_attribute("aria-haspopup") == "dialog"
