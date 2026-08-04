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

  const registerServiceWorker = async () => {
    for (let attempt = 0; attempt < serviceWorkerRegistrationAttempts; attempt += 1) {
      try {
        await navigator.serviceWorker.register("/mobile/service-worker.js", { scope: "/mobile/" });
        return;
      } catch {
        if (attempt + 1 >= serviceWorkerRegistrationAttempts) {
          setStatus("The install shell is available online. Service-worker installation is not available in this browser.");
          return;
        }
        await new Promise((resolve) => {
          window.setTimeout(resolve, serviceWorkerRetryDelaysMs[attempt]);
        });
      }
    }
  };

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      void registerServiceWorker();
    }, { once: true });
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
