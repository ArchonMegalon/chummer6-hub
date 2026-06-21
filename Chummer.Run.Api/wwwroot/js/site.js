(() => {
  const ChummerUi = window.ChummerUi || (window.ChummerUi = {});

  ChummerUi.getAntiForgeryToken = function getAntiForgeryToken(root = document) {
    return root.querySelector("input[name='__RequestVerificationToken']")?.value || "";
  };

  ChummerUi.getRequestVerificationToken = function getRequestVerificationToken(root = document) {
    return ChummerUi.getAntiForgeryToken(root);
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

  ChummerUi.setText = function setText(node, value, fallback = "") {
    if (!node) return;
    node.textContent = value ?? fallback;
  };

  ChummerUi.toggleExclusive = function toggleExclusive(nodes, activeKey) {
    for (const [key, node] of Object.entries(nodes || {})) {
      if (!node) continue;
      node.hidden = key !== activeKey;
    }
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

  ChummerUi.readJsonResponse = async function readJsonResponse(response, fallback) {
    const data = await ChummerUi.readResponseData(response);
    if (!response.ok) {
      const error = new Error(data?.detail || data?.title || fallback || "Request failed.");
      const retryAfterRaw = response.headers.get("Retry-After");
      const retryAfterSeconds = retryAfterRaw ? Number.parseInt(retryAfterRaw, 10) : Number.NaN;
      error.payload = {
        ...(data && typeof data === "object" ? data : {}),
        status: Number.isFinite(data?.status) ? data.status : response.status,
        retryAfterSeconds: Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0
          ? retryAfterSeconds
          : null
      };
      throw error;
    }

    return data;
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
      const retryAfterRaw = response.headers.get("Retry-After");
      const retryAfterSeconds = retryAfterRaw ? Number.parseInt(retryAfterRaw, 10) : Number.NaN;
      error.payload = {
        ...(data && typeof data === "object" ? data : {}),
        status: Number.isFinite(data?.status) ? data.status : response.status,
        retryAfterSeconds: Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0
          ? retryAfterSeconds
          : null
      };
      throw error;
    }

    return data;
  };

  ChummerUi.withBusyState = async function withBusyState(targets, busyLabel, action) {
    const list = Array.isArray(targets) ? targets.filter(Boolean) : [targets].filter(Boolean);
    list.forEach((target) => ChummerUi.setButtonBusy(target, true, busyLabel));
    try {
      return await action();
    } finally {
      list.forEach((target) => ChummerUi.setButtonBusy(target, false, busyLabel));
    }
  };

  ChummerUi.copyToClipboard = async function copyToClipboard(text, button, copiedLabel = "Copied", resetDelayMs = 1200) {
    await navigator.clipboard.writeText(text);
    await ChummerUi.withBusyState(button, copiedLabel, async () => {
      await new Promise((resolve) => window.setTimeout(resolve, resetDelayMs));
    });
  };

  const normalizeAnalyticsValue = (value) => {
    if (value === undefined || value === null) return "";
    return String(value).trim();
  };

  ChummerUi.analyticsQueue = Array.isArray(window.ChummerAnalyticsQueue)
    ? window.ChummerAnalyticsQueue
    : (window.ChummerAnalyticsQueue = []);

  ChummerUi.trackPublicEvent = function trackPublicEvent(name, payload = {}) {
    const eventName = normalizeAnalyticsValue(name);
    if (!eventName) return;
    const record = {
      event: eventName,
      ts: new Date().toISOString(),
      route: normalizeAnalyticsValue(document.body?.dataset?.routeKey),
      surfaceClass: normalizeAnalyticsValue(document.body?.dataset?.surfaceClass),
      ...payload
    };
    ChummerUi.analyticsQueue.push(record);
    window.dispatchEvent(new CustomEvent("chummer:analytics", { detail: record }));

    const rybbitApi = window.rybbit;
    if (rybbitApi && typeof rybbitApi.track === "function") {
      try {
        rybbitApi.track(eventName, record);
      } catch {
        // Keep first-party event capture even when the provider bridge is unavailable.
      }
    } else if (rybbitApi && typeof rybbitApi.event === "function") {
      try {
        rybbitApi.event(eventName, record);
      } catch {
        // Keep first-party event capture even when the provider bridge is unavailable.
      }
    }
  };

  const readAnalyticsPayload = (node, action = "click") => {
    if (!node?.dataset) return null;
    const eventName = normalizeAnalyticsValue(node.dataset.analyticsEvent);
    if (!eventName) return null;
    const href = node instanceof HTMLAnchorElement ? node.getAttribute("href") || "" : "";
    const label =
      normalizeAnalyticsValue(node.dataset.analyticsLabel) ||
      normalizeAnalyticsValue(node.getAttribute("aria-label")) ||
      normalizeAnalyticsValue(node.textContent);
    return {
      eventName,
      payload: {
        action,
        surface: normalizeAnalyticsValue(node.dataset.analyticsSurface),
        label,
        href,
        tag: node.tagName.toLowerCase()
      }
    };
  };

  document.addEventListener("click", (event) => {
    const node = event.target instanceof Element
      ? event.target.closest("[data-analytics-event]")
      : null;
    if (!node || node.tagName === "DETAILS" || node.tagName === "SUMMARY") {
      return;
    }
    const analytics = readAnalyticsPayload(node, "click");
    if (analytics) {
      ChummerUi.trackPublicEvent(analytics.eventName, analytics.payload);
    }
  }, { capture: true });

  document.querySelectorAll("details summary[data-analytics-event]").forEach((summary) => {
    summary.addEventListener("click", () => {
      const analytics = readAnalyticsPayload(summary, "expand");
      if (analytics) {
        ChummerUi.trackPublicEvent(analytics.eventName, analytics.payload);
      }
    });
  });

  const header = document.querySelector("[data-site-header]");
  const syncHeader = () => {
    if (!header) return;
    header.dataset.condensed = window.scrollY > 18 ? "true" : "false";
  };

  syncHeader();
  window.addEventListener("scroll", syncHeader, { passive: true });

  document.querySelectorAll("[data-copy-source]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.getAttribute("data-copy-source"));
      if (!target) return;
      try {
        await ChummerUi.copyToClipboard(target.textContent || "", button, "Copied");
      } catch {
        // Keep the visible code available for manual copy.
      }
    });
  });

  document.querySelectorAll("[data-email-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.getAttribute("data-email-toggle"));
      if (!target) return;
      const hidden = target.hasAttribute("hidden");
      target.toggleAttribute("hidden", !hidden);
    });
  });

  const faqFilter = document.querySelector("[data-faq-filter]");
  if (faqFilter) {
    const faqItems = Array.from(document.querySelectorAll("[data-faq-item]"));
    const faqSections = Array.from(document.querySelectorAll("[data-faq-section]"));
    faqFilter.addEventListener("input", () => {
      const term = faqFilter.value.trim().toLowerCase();
      faqSections.forEach((section) => {
        let visibleCount = 0;
        section.querySelectorAll("[data-faq-item]").forEach((item) => {
          const haystack = (item.getAttribute("data-faq-text") || "").toLowerCase();
          const visible = !term || haystack.includes(term);
          item.hidden = !visible;
          if (visible) visibleCount += 1;
        });
        section.hidden = visibleCount === 0;
      });
    });
  }

  const accountTabs = Array.from(document.querySelectorAll("[data-account-tab]"));
  const accountPanels = Array.from(document.querySelectorAll("[data-account-panel]"));
  if (accountTabs.length > 0 && accountPanels.length > 0) {
    const panelIds = new Set(accountPanels.map((panel) => panel.id).filter(Boolean));
    const syncAccountPanels = () => {
      const requested = (window.location.hash || "#profile").slice(1);
      const activeId = panelIds.has(requested) ? requested : accountPanels[0].id;
      accountPanels.forEach((panel) => {
        panel.hidden = panel.id !== activeId;
      });
      accountTabs.forEach((tab) => {
        const href = tab.getAttribute("href") || "";
        const current = href === `#${activeId}`;
        tab.setAttribute("aria-current", current ? "page" : "false");
      });
    };

    window.addEventListener("hashchange", syncAccountPanels);
    syncAccountPanels();
  }
})();
