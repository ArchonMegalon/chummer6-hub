(() => {
  const ChummerUi = window.ChummerUi || (window.ChummerUi = {});

  ChummerUi.getAntiForgeryToken = function getAntiForgeryToken(root = document) {
    return root.querySelector("input[name='__RequestVerificationToken']")?.value || "";
  };

  ChummerUi.setButtonBusy = function setButtonBusy(button, busy, busyLabel) {
    if (!button) return;
    if (!button.dataset.defaultLabel) {
      button.dataset.defaultLabel = button.textContent || "";
    }

    button.disabled = busy;
    button.textContent = busy ? busyLabel : button.dataset.defaultLabel;
  };

  ChummerUi.setNotice = function setNotice(node, message, isError = false) {
    if (!node) return;
    node.hidden = false;
    node.textContent = message;
    node.classList.toggle("status-copy--error", isError);
    node.classList.toggle("status-copy--success", !isError);
  };

  ChummerUi.clearNotice = function clearNotice(node) {
    if (!node) return;
    node.hidden = true;
    node.textContent = "";
    node.classList.remove("status-copy--error", "status-copy--success");
  };

  ChummerUi.humanizeStatus = function humanizeStatus(value, fallback = "Not connected") {
    if (!value) return fallback;
    const normalized = String(value).trim().toLowerCase();
    switch (normalized) {
      case "active":
      case "linked":
        return "Ready";
      case "pending":
        return "Pending";
      case "pending_verification":
        return "Verification sent";
      case "verified":
        return "Verified";
      case "revoked":
        return "Revoked";
      default:
        return String(value).replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
    }
  };

  ChummerUi.describeError = function describeError(error, fallback) {
    return error instanceof Error && error.message ? error.message : fallback;
  };

  ChummerUi.readResponseData = async function readResponseData(response) {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch {
      return { detail: text };
    }
  };

  ChummerUi.requestJson = async function requestJson(url, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    const token = options.token ?? ChummerUi.getAntiForgeryToken();

    if (options.json !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    if (method !== "GET" && token && !headers.has("RequestVerificationToken")) {
      headers.set("RequestVerificationToken", token);
    }

    const response = await fetch(url, {
      ...options,
      method,
      headers,
      body: options.json !== undefined ? JSON.stringify(options.json) : options.body
    });
    const data = await ChummerUi.readResponseData(response);
    if (!response.ok) {
      const error = new Error(data?.detail || data?.title || "Request failed.");
      error.payload = data;
      throw error;
    }

    return data;
  };

  const header = document.querySelector("[data-site-header]");
  const navToggle = document.querySelector("[data-nav-toggle]");
  const navSheet = document.querySelector("[data-nav-sheet]");

  const syncHeader = () => {
    if (!header) return;
    header.dataset.condensed = window.scrollY > 18 ? "true" : "false";
  };

  syncHeader();
  window.addEventListener("scroll", syncHeader, { passive: true });

  if (navToggle && navSheet) {
    navToggle.addEventListener("click", () => {
      const expanded = navToggle.getAttribute("aria-expanded") === "true";
      navToggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      navSheet.hidden = expanded;
    });
  }

  document.querySelectorAll("[data-email-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.getAttribute("data-email-toggle"));
      if (!target) return;
      const hidden = target.hasAttribute("hidden");
      target.toggleAttribute("hidden", !hidden);
    });
  });
})();
