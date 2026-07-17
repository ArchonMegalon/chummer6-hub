(() => {
  const ChummerUi = window.ChummerUi || (window.ChummerUi = {});
  const modalInertState = new WeakMap();

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
    if (busy) {
      button.setAttribute("aria-busy", "true");
    } else {
      button.removeAttribute("aria-busy");
    }
    button.textContent = busy ? busyLabel : button.dataset.defaultLabel;
  };

  ChummerUi.setNotice = function setNotice(node, message, isError = false) {
    if (!node) return;
    node.setAttribute("role", isError ? "alert" : "status");
    node.setAttribute("aria-live", isError ? "assertive" : "polite");
    node.setAttribute("aria-atomic", "true");
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

  ChummerUi.bindModalDialog = function bindModalDialog(dialog, options = {}) {
    if (!(dialog instanceof HTMLElement)) return null;

    const openButtons = Array.from(options.openButtons || []).filter((node) => node instanceof HTMLElement);
    const closeButtons = Array.from(options.closeButtons || []).filter((node) => node instanceof HTMLElement);
    const focusableSelector = [
      "a[href]",
      "button:not([disabled])",
      "input:not([disabled]):not([type='hidden'])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      "[contenteditable]:not([contenteditable='false'])",
      "[tabindex]:not([tabindex='-1'])"
    ].join(",");
    let returnFocus = null;
    let focusFrame = 0;
    const inertedBackground = new Set();

    const makeBackgroundInert = () => {
      let branch = dialog;
      while (branch instanceof HTMLElement && branch !== document.body) {
        const parent = branch.parentElement;
        if (!(parent instanceof HTMLElement)) break;

        for (const sibling of parent.children) {
          if (!(sibling instanceof HTMLElement) || sibling === branch || inertedBackground.has(sibling)) continue;
          let state = modalInertState.get(sibling);
          if (!state) {
            state = { count: 0, wasInert: sibling.inert };
            modalInertState.set(sibling, state);
          }
          state.count += 1;
          sibling.inert = true;
          inertedBackground.add(sibling);
        }

        branch = parent;
      }
    };

    const restoreBackground = () => {
      for (const node of inertedBackground) {
        const state = modalInertState.get(node);
        if (!state) continue;
        state.count -= 1;
        if (state.count <= 0) {
          node.inert = state.wasInert;
          modalInertState.delete(node);
        }
      }
      inertedBackground.clear();
    };

    const isFocusable = (node) =>
      node instanceof HTMLElement
      && node.tabIndex >= 0
      && !node.hidden
      && node.getAttribute("aria-hidden") !== "true"
      && node.getClientRects().length > 0;

    const focusableNodes = () =>
      Array.from(dialog.querySelectorAll(focusableSelector)).filter(isFocusable);

    const preferredFocus = () => {
      if (options.initialFocus instanceof HTMLElement && dialog.contains(options.initialFocus)) {
        return options.initialFocus;
      }
      if (typeof options.initialFocus === "string") {
        const configured = dialog.querySelector(options.initialFocus);
        if (isFocusable(configured)) return configured;
      }
      return focusableNodes()[0] || null;
    };

    const scheduleFocus = (resolveTarget) => {
      if (focusFrame) window.cancelAnimationFrame(focusFrame);
      focusFrame = window.requestAnimationFrame(() => {
        focusFrame = 0;
        const target = resolveTarget();
        if (target instanceof HTMLElement && target.isConnected) {
          target.focus();
        }
      });
    };

    const syncBodyLock = () => {
      const hasOpenModal = document.querySelector('[role="dialog"][aria-modal="true"]:not([hidden])');
      document.body.classList.toggle("dialog-open", Boolean(hasOpenModal));
    };

    const open = (trigger) => {
      const active = trigger instanceof HTMLElement ? trigger : document.activeElement;
      returnFocus = active instanceof HTMLElement ? active : null;
      dialog.hidden = false;
      makeBackgroundInert();
      syncBodyLock();
      scheduleFocus(() => preferredFocus() || dialog);
    };

    const close = () => {
      if (dialog.hidden) return;
      const focusTarget = returnFocus;
      returnFocus = null;
      dialog.hidden = true;
      restoreBackground();
      syncBodyLock();
      scheduleFocus(() => focusTarget);
    };

    const handleKeydown = (event) => {
      if (dialog.hidden) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close();
        return;
      }
      if (event.key !== "Tab") return;

      const nodes = focusableNodes();
      if (nodes.length === 0) {
        event.preventDefault();
        if (!dialog.hasAttribute("tabindex")) dialog.setAttribute("tabindex", "-1");
        dialog.focus();
        return;
      }

      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    const handleBackdropClick = (event) => {
      if (options.closeOnBackdrop !== false && event.target === dialog) close();
    };

    const openerBindings = openButtons.map((button) => {
      const handler = () => open(button);
      button.addEventListener("click", handler);
      return [button, handler];
    });
    const closerBindings = closeButtons.map((button) => {
      const handler = () => close();
      button.addEventListener("click", handler);
      return [button, handler];
    });
    dialog.addEventListener("keydown", handleKeydown);
    dialog.addEventListener("click", handleBackdropClick);

    if (!dialog.hidden) {
      makeBackgroundInert();
      syncBodyLock();
      scheduleFocus(() => preferredFocus() || dialog);
    }

    return {
      open,
      close,
      destroy() {
        openerBindings.forEach(([button, handler]) => button.removeEventListener("click", handler));
        closerBindings.forEach(([button, handler]) => button.removeEventListener("click", handler));
        dialog.removeEventListener("keydown", handleKeydown);
        dialog.removeEventListener("click", handleBackdropClick);
        if (focusFrame) window.cancelAnimationFrame(focusFrame);
        restoreBackground();
        syncBodyLock();
      }
    };
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
    const googleStartLink = event.target instanceof Element
      ? event.target.closest("a[href^='/auth/google/start']")
      : null;
    if (googleStartLink instanceof HTMLAnchorElement
      && event.button === 0
      && !event.metaKey
      && !event.ctrlKey
      && !event.shiftKey
      && !event.altKey) {
      const url = new URL(googleStartLink.href, window.location.origin);
      url.searchParams.set("flow", `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`);
      googleStartLink.href = `${url.pathname}${url.search}${url.hash}`;
    }

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

  const participateFilter = document.querySelector("[data-participate-filter]");
  if (participateFilter) {
    const participateItems = Array.from(document.querySelectorAll("[data-participate-item]"));
    const participateStatusFilter = document.querySelector("[data-participate-status-filter]");
    const participateEmpty = document.querySelector("[data-participate-empty]");
    const syncParticipateItems = () => {
      const term = participateFilter.value.trim().toLowerCase();
      const status = participateStatusFilter ? participateStatusFilter.value.trim().toLowerCase() : "";
      let visibleCount = 0;
      participateItems.forEach((item) => {
        const haystack = (item.getAttribute("data-participate-text") || "").toLowerCase();
        const itemStatus = (item.getAttribute("data-participate-status") || "").toLowerCase();
        const matchesTerm = !term || haystack.includes(term);
        const matchesStatus = !status || itemStatus === status;
        const visible = matchesTerm && matchesStatus;
        item.hidden = !visible;
        if (visible) visibleCount += 1;
      });
      if (participateEmpty) {
        participateEmpty.hidden = visibleCount !== 0;
      }
    };

    participateFilter.addEventListener("input", syncParticipateItems);
    if (participateStatusFilter) {
      participateStatusFilter.addEventListener("change", syncParticipateItems);
    }
    syncParticipateItems();
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
