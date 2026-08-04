(() => {
  "use strict";

  const installButton = document.getElementById("turn-install-button");
  const installStatus = document.getElementById("turn-install-status");
  const manualInstallHelp = document.getElementById("turn-manual-install-help");
  const displayModeQuery = typeof window.matchMedia === "function"
    ? window.matchMedia("(display-mode: standalone)")
    : null;
  const serviceWorkerRegistrationAttempts = 3;
  const serviceWorkerRetryDelaysMs = [500, 1500];
  const serviceWorkerActivationTimeoutMs = 8000;
  let installPrompt = null;

  const setStatus = (message) => {
    if (installStatus) {
      installStatus.textContent = message;
    }
  };

  const isInstalled = () => displayModeQuery?.matches === true
    || window.navigator.standalone === true;

  const showManualInstallHelp = () => {
    setStatus("Choose your browser's install command, or keep using Chummer Play in this browser.");
    manualInstallHelp?.focus({ preventScroll: false });
  };

  const markInstalled = () => {
    installPrompt = null;
    if (installButton) {
      installButton.disabled = true;
    }
    setStatus("Chummer Play is installed. No table data or role was added to this device.");
  };

  const restoreBrowserInstallState = () => {
    if (installButton) {
      installButton.disabled = false;
    }
    setStatus(installPrompt
      ? "This browser is ready to install the public Chummer Play shell."
      : "Use this browser's install command when you want Chummer Play on this device, or keep using it here.");
  };

  const syncDisplayModeState = () => {
    if (isInstalled()) {
      markInstalled();
      return;
    }
    restoreBrowserInstallState();
  };

  const waitForServiceWorkerActivation = (registration) => new Promise((resolve, reject) => {
    const worker = registration.active ?? registration.waiting ?? registration.installing ?? null;
    if (!worker) {
      reject(new Error("service worker registration has no worker"));
      return;
    }
    if (worker.state === "activated") {
      resolve();
      return;
    }
    if (worker.state === "redundant") {
      reject(new Error("service worker installation became redundant"));
      return;
    }

    let settled = false;
    let timeoutId = 0;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      worker.removeEventListener?.("statechange", onStateChange);
      if (error) reject(error);
      else resolve();
    };
    const onStateChange = () => {
      if (worker.state === "activated") {
        finish();
      } else if (worker.state === "redundant") {
        finish(new Error("service worker installation became redundant"));
      }
    };
    timeoutId = window.setTimeout(() => {
      finish(new Error("service worker activation timed out"));
    }, serviceWorkerActivationTimeoutMs);
    worker.addEventListener?.("statechange", onStateChange);
    onStateChange();
  });

  const waitForWindowLoad = () => {
    if (document.readyState === "complete") {
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      window.addEventListener("load", resolve, { once: true });
    });
  };

  const hasPendingServiceWorkerActivation = (registration) => {
    const worker = registration?.installing ?? registration?.waiting ?? registration?.active ?? null;
    return worker != null && ["installing", "installed", "activating"].includes(worker.state);
  };

  const registerServiceWorker = async ({ reportFailure = true } = {}) => {
    for (let attempt = 0; attempt < serviceWorkerRegistrationAttempts; attempt += 1) {
      let registration = null;
      try {
        registration = await navigator.serviceWorker.register("/mobile/service-worker.js", { scope: "/mobile/" });
        await waitForServiceWorkerActivation(registration);
        return true;
      } catch {
        // Do not restart a slow but progressing installation. Chromium can keep
        // an unregistered worker pending deletion until the page closes, so an
        // eager unregister here can turn a transient delay into a permanent
        // register/unregister loop for the current page.
        if (!hasPendingServiceWorkerActivation(registration)) {
          await registration?.unregister?.().catch(() => false);
        }
        if (attempt + 1 >= serviceWorkerRegistrationAttempts) {
          if (reportFailure) {
            setStatus("The install shell is available online. Service-worker installation is not available in this browser.");
          }
          return false;
        }
        await new Promise((resolve) => {
          window.setTimeout(resolve, serviceWorkerRetryDelaysMs[attempt]);
        });
      }
    }
    return false;
  };

  if ("serviceWorker" in navigator) {
    const startServiceWorkerRegistration = async () => {
      const immediateRegistrationSucceeded = await registerServiceWorker({ reportFailure: false });

      // Chromium can keep an unregistered worker pending deletion until its
      // last controlled page closes and briefly return that worker from a new
      // register() call. Preserve the immediate fresh-cutover attempt, then
      // always register again after the replacement page has fully loaded so
      // the surviving registration is confirmed after the deletion boundary.
      await waitForWindowLoad();
      await new Promise((resolve) => {
        window.setTimeout(resolve, 1000);
      });
      if (await registerServiceWorker({ reportFailure: false })) {
        return;
      }

      if (immediateRegistrationSucceeded) {
        try {
          const registration = await navigator.serviceWorker.getRegistration("/mobile/");
          if (registration) {
            await waitForServiceWorkerActivation(registration);
            return;
          }
        } catch {
          // The final status below is the fail-closed browser-facing result.
        }
      }
      setStatus("The install shell is available online. Service-worker installation is not available in this browser.");
    };
    void startServiceWorkerRegistration();
  }

  syncDisplayModeState();

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    if (installButton) {
      installButton.disabled = false;
    }
    setStatus("This browser is ready to install the public Chummer Play shell.");
  });

  installButton?.addEventListener("click", async () => {
    if (!installPrompt) {
      showManualInstallHelp();
      return;
    }

    const activePrompt = installPrompt;
    installPrompt = null;
    installButton.disabled = true;
    let accepted = false;
    try {
      await activePrompt.prompt();
      const choice = await activePrompt.userChoice;
      accepted = choice.outcome === "accepted";
      setStatus(accepted
        ? "Installation accepted. Join live play later from a trusted invitation."
        : "Installation was not completed. Use the browser instructions below or continue in the browser.");
    } catch {
      setStatus("The direct install prompt was unavailable. Use the browser instructions below or continue in the browser.");
      manualInstallHelp?.focus({ preventScroll: false });
    } finally {
      installButton.disabled = accepted || isInstalled();
    }
  });

  window.addEventListener("appinstalled", markInstalled);

  const handleDisplayModeChange = (event) => {
    if (event.matches) {
      markInstalled();
    } else if (window.navigator.standalone !== true) {
      restoreBrowserInstallState();
    }
  };
  if (typeof displayModeQuery?.addEventListener === "function") {
    displayModeQuery.addEventListener("change", handleDisplayModeChange);
  } else {
    displayModeQuery?.addListener?.(handleDisplayModeChange);
  }

  const cleanup = (event) => {
    if (event.persisted) return;
    if (typeof displayModeQuery?.removeEventListener === "function") {
      displayModeQuery.removeEventListener("change", handleDisplayModeChange);
    } else {
      displayModeQuery?.removeListener?.(handleDisplayModeChange);
    }
    window.removeEventListener("appinstalled", markInstalled);
  };
  window.addEventListener("pagehide", cleanup);
})();
