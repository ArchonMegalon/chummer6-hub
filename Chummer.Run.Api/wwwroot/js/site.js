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

  const header = document.querySelector("[data-site-header]");
  const navToggle = document.querySelector("[data-nav-toggle]");
  const navPanel = document.querySelector("[data-nav-panel]");
  const navClose = document.querySelector("[data-nav-close]");
  const navBackdrop = document.querySelector("[data-nav-backdrop]");
  const navStorageKey = "chummer.navPanelOpen";
  const forceDesktopNavCollapsed =
    document.body.classList.contains("route-downloads-release-upload");

  const syncHeader = () => {
    if (!header) return;
    header.dataset.condensed = window.scrollY > 18 ? "true" : "false";
  };

  syncHeader();
  window.addEventListener("scroll", syncHeader, { passive: true });

  if (navToggle && navPanel) {
    const isMobileNav = () => window.innerWidth <= 980;

    const setDesktopPreference = (open) => {
      try {
        window.localStorage.setItem(navStorageKey, open ? "1" : "0");
      } catch {
        // Ignore storage failures; state still applies for this session.
      }
    };

    const getDesktopPreference = () => {
      try {
        return window.localStorage.getItem(navStorageKey);
      } catch {
        return null;
      }
    };

    const applyNavState = () => {
      const mobile = isMobileNav();
      const open = document.body.classList.contains("nav-panel-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");

      if (mobile) {
        navPanel.hidden = !open;
        navPanel.setAttribute("aria-hidden", open ? "false" : "true");
        navPanel.toggleAttribute("inert", !open);
        if (navBackdrop) {
          navBackdrop.hidden = !open;
        }
        document.body.classList.toggle("nav-sheet-open", open);
        return;
      }

      navPanel.hidden = false;
      navPanel.setAttribute("aria-hidden", open ? "false" : "true");
      navPanel.toggleAttribute("inert", !open);
      if (navBackdrop) {
        navBackdrop.hidden = true;
      }
      document.body.classList.remove("nav-sheet-open");
    };

    const openNavPanel = () => {
      document.body.classList.add("nav-panel-open");
      applyNavState();
    };

    const closeNavPanel = () => {
      document.body.classList.remove("nav-panel-open");
      applyNavState();
    };

    const initializeNavPanel = () => {
      if (isMobileNav()) {
        closeNavPanel();
        return;
      }

      if (forceDesktopNavCollapsed) {
        closeNavPanel();
        return;
      }

      const stored = getDesktopPreference();
      if (stored === "1") {
        openNavPanel();
        return;
      }

      closeNavPanel();
    };

    initializeNavPanel();

    navToggle.addEventListener("click", () => {
      const open = document.body.classList.contains("nav-panel-open");
      if (open) {
        closeNavPanel();
        if (!isMobileNav()) {
          setDesktopPreference(false);
        }
        return;
      }

      openNavPanel();
      if (!isMobileNav()) {
        setDesktopPreference(true);
      }
    });

    if (navClose) {
      navClose.addEventListener("click", () => {
        closeNavPanel();
        if (!isMobileNav()) {
          setDesktopPreference(false);
        }
        navToggle.focus();
      });
    }

    if (navBackdrop) {
      navBackdrop.addEventListener("click", () => {
        closeNavPanel();
        navToggle.focus();
      });
    }

    navPanel.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        if (isMobileNav()) {
          closeNavPanel();
        }
      });
    });

    navPanel.querySelectorAll("form").forEach((form) => {
      form.addEventListener("submit", () => {
        if (isMobileNav()) {
          closeNavPanel();
        }
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && document.body.classList.contains("nav-panel-open")) {
        closeNavPanel();
        navToggle.focus();
      }
    });

    window.addEventListener("resize", () => {
      initializeNavPanel();
      applyNavState();
    });
  }

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
