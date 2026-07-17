(() => {
  const ChummerMobileAppHandoff = window.ChummerMobileAppHandoff || (window.ChummerMobileAppHandoff = {});

  const LOW_ERROR_CORRECTION_VERSIONS = [
    { version: 1, dataCodewords: 19, errorCodewords: 7, alignmentCenters: [] },
    { version: 2, dataCodewords: 34, errorCodewords: 10, alignmentCenters: [6, 18] },
    { version: 3, dataCodewords: 55, errorCodewords: 15, alignmentCenters: [6, 22] },
    { version: 4, dataCodewords: 80, errorCodewords: 20, alignmentCenters: [6, 26] },
    { version: 5, dataCodewords: 108, errorCodewords: 26, alignmentCenters: [6, 30] }
  ];
  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const DEVICE_PREFERENCE_KEY = "chummer.mobile-app-handoff.device.v1";
  const DEVICE_PREFERENCES = new Set(["auto", "mobile", "desktop"]);
  let memoryDevicePreference = "auto";
  let devicePreferenceLoaded = false;

  const appendBits = (target, value, length) => {
    for (let bit = length - 1; bit >= 0; bit -= 1) {
      target.push(((value >>> bit) & 1) !== 0);
    }
  };

  const multiplyGalois = (left, right) => {
    let product = 0;
    for (let bit = 7; bit >= 0; bit -= 1) {
      product = (product << 1) ^ ((product >>> 7) * 0x11d);
      product ^= ((right >>> bit) & 1) * left;
    }
    return product;
  };

  const buildErrorCorrectionDivisor = (degree) => {
    const result = new Array(degree).fill(0);
    result[degree - 1] = 1;
    let root = 1;
    for (let index = 0; index < degree; index += 1) {
      for (let coefficient = 0; coefficient < result.length; coefficient += 1) {
        result[coefficient] = multiplyGalois(result[coefficient], root);
        if (coefficient + 1 < result.length) {
          result[coefficient] ^= result[coefficient + 1];
        }
      }
      root = multiplyGalois(root, 0x02);
    }
    return result;
  };

  const buildErrorCorrectionCodewords = (data, degree) => {
    const divisor = buildErrorCorrectionDivisor(degree);
    const remainder = new Array(degree).fill(0);
    data.forEach((codeword) => {
      const factor = codeword ^ remainder.shift();
      remainder.push(0);
      for (let index = 0; index < remainder.length; index += 1) {
        remainder[index] ^= multiplyGalois(divisor[index], factor);
      }
    });
    return remainder;
  };

  const chooseVersion = (byteLength) => {
    const requiredBits = 4 + 8 + (byteLength * 8);
    return LOW_ERROR_CORRECTION_VERSIONS.find(({ dataCodewords }) => requiredBits <= dataCodewords * 8) || null;
  };

  const encodeDataCodewords = (bytes, version) => {
    const capacity = version.dataCodewords * 8;
    const bits = [];
    appendBits(bits, 0x4, 4);
    appendBits(bits, bytes.length, 8);
    bytes.forEach((byte) => appendBits(bits, byte, 8));

    for (let count = 0; count < 4 && bits.length < capacity; count += 1) {
      bits.push(false);
    }
    while (bits.length % 8 !== 0) {
      bits.push(false);
    }

    const codewords = [];
    for (let offset = 0; offset < bits.length; offset += 8) {
      let codeword = 0;
      for (let bit = 0; bit < 8; bit += 1) {
        codeword = (codeword << 1) | (bits[offset + bit] ? 1 : 0);
      }
      codewords.push(codeword);
    }
    for (let padIndex = 0; codewords.length < version.dataCodewords; padIndex += 1) {
      codewords.push(padIndex % 2 === 0 ? 0xec : 0x11);
    }
    return codewords;
  };

  const buildQrMatrix = (value) => {
    const bytes = new TextEncoder().encode(value);
    const version = chooseVersion(bytes.length);
    if (!version) {
      throw new Error("The mobile app link is too long to render as a local QR code.");
    }

    const dataCodewords = encodeDataCodewords(bytes, version);
    const errorCodewords = buildErrorCorrectionCodewords(dataCodewords, version.errorCodewords);
    const codewords = dataCodewords.concat(errorCodewords);
    const size = (version.version * 4) + 17;
    const modules = Array.from({ length: size }, () => new Array(size).fill(false));
    const functionModules = Array.from({ length: size }, () => new Array(size).fill(false));

    const setFunctionModule = (x, y, dark) => {
      modules[y][x] = dark;
      functionModules[y][x] = true;
    };

    const drawFinderPattern = (centerX, centerY) => {
      for (let yOffset = -4; yOffset <= 4; yOffset += 1) {
        for (let xOffset = -4; xOffset <= 4; xOffset += 1) {
          const x = centerX + xOffset;
          const y = centerY + yOffset;
          if (x < 0 || x >= size || y < 0 || y >= size) continue;
          const distance = Math.max(Math.abs(xOffset), Math.abs(yOffset));
          setFunctionModule(x, y, distance !== 2 && distance !== 4);
        }
      }
    };

    const drawAlignmentPattern = (centerX, centerY) => {
      for (let yOffset = -2; yOffset <= 2; yOffset += 1) {
        for (let xOffset = -2; xOffset <= 2; xOffset += 1) {
          const distance = Math.max(Math.abs(xOffset), Math.abs(yOffset));
          setFunctionModule(centerX + xOffset, centerY + yOffset, distance !== 1);
        }
      }
    };

    const formatBit = (bits, index) => ((bits >>> index) & 1) !== 0;
    const drawFormatBits = (mask) => {
      const data = (1 << 3) | mask;
      let remainder = data;
      for (let index = 0; index < 10; index += 1) {
        remainder = (remainder << 1) ^ ((remainder >>> 9) * 0x537);
      }
      const bits = ((data << 10) | remainder) ^ 0x5412;

      for (let index = 0; index <= 5; index += 1) setFunctionModule(8, index, formatBit(bits, index));
      setFunctionModule(8, 7, formatBit(bits, 6));
      setFunctionModule(8, 8, formatBit(bits, 7));
      setFunctionModule(7, 8, formatBit(bits, 8));
      for (let index = 9; index < 15; index += 1) setFunctionModule(14 - index, 8, formatBit(bits, index));

      for (let index = 0; index < 8; index += 1) setFunctionModule(size - 1 - index, 8, formatBit(bits, index));
      for (let index = 8; index < 15; index += 1) setFunctionModule(8, size - 15 + index, formatBit(bits, index));
      setFunctionModule(8, size - 8, true);
    };

    for (let index = 0; index < size; index += 1) {
      setFunctionModule(6, index, index % 2 === 0);
      setFunctionModule(index, 6, index % 2 === 0);
    }
    drawFinderPattern(3, 3);
    drawFinderPattern(size - 4, 3);
    drawFinderPattern(3, size - 4);

    const lastAlignmentIndex = version.alignmentCenters.length - 1;
    version.alignmentCenters.forEach((centerY, yIndex) => {
      version.alignmentCenters.forEach((centerX, xIndex) => {
        const overlapsFinder = (xIndex === 0 && yIndex === 0)
          || (xIndex === 0 && yIndex === lastAlignmentIndex)
          || (xIndex === lastAlignmentIndex && yIndex === 0);
        if (!overlapsFinder) drawAlignmentPattern(centerX, centerY);
      });
    });
    drawFormatBits(0);

    let bitIndex = 0;
    let upward = true;
    for (let right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right -= 1;
      for (let vertical = 0; vertical < size; vertical += 1) {
        const y = upward ? size - 1 - vertical : vertical;
        for (let column = 0; column < 2; column += 1) {
          const x = right - column;
          if (functionModules[y][x]) continue;
          if (bitIndex < codewords.length * 8) {
            modules[y][x] = ((codewords[bitIndex >>> 3] >>> (7 - (bitIndex & 7))) & 1) !== 0;
            bitIndex += 1;
          }
        }
      }
      upward = !upward;
    }

    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        if (!functionModules[y][x] && (x + y) % 2 === 0) {
          modules[y][x] = !modules[y][x];
        }
      }
    }
    drawFormatBits(0);
    return modules;
  };

  const renderQrSvg = (svg, value) => {
    const matrix = buildQrMatrix(value);
    const quietZone = 4;
    const size = matrix.length + (quietZone * 2);
    const darkPath = [];
    matrix.forEach((row, y) => {
      row.forEach((dark, x) => {
        if (dark) darkPath.push(`M${x + quietZone},${y + quietZone}h1v1h-1z`);
      });
    });

    svg.replaceChildren();
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("shape-rendering", "crispEdges");
    svg.setAttribute("data-qr-value", value);
    const background = document.createElementNS(SVG_NAMESPACE, "rect");
    background.setAttribute("width", "100%");
    background.setAttribute("height", "100%");
    background.setAttribute("fill", "#ffffff");
    const foreground = document.createElementNS(SVG_NAMESPACE, "path");
    foreground.setAttribute("d", darkPath.join(""));
    foreground.setAttribute("fill", "#111111");
    svg.append(background, foreground);
  };

  const normalizeDevicePreference = (value) =>
    DEVICE_PREFERENCES.has(value) ? value : "auto";

  const readDeviceSignals = () => {
    const userAgentData = window.navigator?.userAgentData;
    const userAgentDataMobile = typeof userAgentData?.mobile === "boolean"
      ? userAgentData.mobile
      : null;
    const standalone = window.navigator?.standalone === true
      || (typeof window.matchMedia === "function"
        && window.matchMedia("(display-mode: standalone)").matches);
    const coarsePointer = typeof window.matchMedia === "function"
      && window.matchMedia("(pointer: coarse)").matches;
    const maxTouchPoints = Number.isSafeInteger(window.navigator?.maxTouchPoints)
      ? Math.max(0, window.navigator.maxTouchPoints)
      : 0;
    return { standalone, userAgentDataMobile, coarsePointer, maxTouchPoints };
  };

  const resolveEffectiveDevice = (preference, signals = readDeviceSignals()) => {
    const normalizedPreference = normalizeDevicePreference(preference);
    if (normalizedPreference === "mobile" || normalizedPreference === "desktop") {
      return normalizedPreference;
    }
    if (signals?.standalone === true) return "mobile";
    if (typeof signals?.userAgentDataMobile === "boolean") {
      return signals.userAgentDataMobile ? "mobile" : "desktop";
    }
    return signals?.coarsePointer === true && signals?.maxTouchPoints > 0
      ? "mobile"
      : "desktop";
  };

  const usesMobilePresentation = () =>
    resolveEffectiveDevice(loadDevicePreference()) === "mobile";

  const loadDevicePreference = () => {
    if (devicePreferenceLoaded) return memoryDevicePreference;
    devicePreferenceLoaded = true;
    try {
      memoryDevicePreference = normalizeDevicePreference(
        window.localStorage.getItem(DEVICE_PREFERENCE_KEY));
    } catch {
      memoryDevicePreference = "auto";
    }
    return memoryDevicePreference;
  };

  const persistDevicePreference = (preference) => {
    memoryDevicePreference = normalizeDevicePreference(preference);
    try {
      window.localStorage.setItem(DEVICE_PREFERENCE_KEY, memoryDevicePreference);
    } catch {
      // The in-memory choice remains authoritative for this page lifetime.
    }
  };

  const devicePreferenceStatus = () => {
    const effectiveDevice = resolveEffectiveDevice(memoryDevicePreference);
    if (memoryDevicePreference === "mobile") {
      return "Mobile override: Build and Play open the install page on this device.";
    }
    if (memoryDevicePreference === "desktop") {
      return "Desktop override: Build and Play show QR, copy, and open-on-this-device controls.";
    }
    return effectiveDevice === "mobile"
      ? "Auto detected a mobile browser. Build and Play open their install page directly."
      : "Auto detected a desktop browser. Build and Play show a QR code to scan on a phone.";
  };

  const syncDevicePicker = () => {
    const effectiveDevice = resolveEffectiveDevice(memoryDevicePreference);
    document.querySelectorAll("[data-mobile-app-device-choice]").forEach((choice) => {
      if (choice instanceof HTMLInputElement) {
        choice.checked = choice.value === memoryDevicePreference;
      }
    });
    document.querySelectorAll("[data-mobile-app-device-status]").forEach((status) => {
      if (status instanceof HTMLElement) status.textContent = devicePreferenceStatus();
    });
    document.querySelectorAll("[data-mobile-app-handoff]").forEach((opener) => {
      if (!(opener instanceof HTMLAnchorElement)) return;
      opener.dataset.mobileAppEffectiveDevice = effectiveDevice;
      if (effectiveDevice === "desktop") {
        opener.setAttribute("aria-haspopup", "dialog");
      } else {
        opener.removeAttribute("aria-haspopup");
      }
    });
  };

  const bindDevicePickers = () => {
    loadDevicePreference();
    document.querySelectorAll("[data-mobile-app-device-choice]").forEach((choice) => {
      if (!(choice instanceof HTMLInputElement)
          || choice.dataset.mobileAppDeviceChoiceBound === "true") return;
      choice.addEventListener("change", () => {
        if (!choice.checked) return;
        persistDevicePreference(choice.value);
        syncDevicePicker();
      });
      choice.dataset.mobileAppDeviceChoiceBound = "true";
    });
    syncDevicePicker();
  };

  const ALLOWED_HANDOFF_PATHS = new Set([
    "/build",
    "/mobile/player",
    "/mobile/gm",
    "/mobile/observer"
  ]);

  const resolveTargetUrl = (path, configuredOrigin) => {
    if (!configuredOrigin) {
      throw new Error("The canonical Chummer origin is unavailable.");
    }
    const canonicalOrigin = new URL(configuredOrigin);
    const target = new URL(path, `${canonicalOrigin.origin}/`);
    if (target.origin !== canonicalOrigin.origin) {
      throw new Error("The mobile app handoff must stay on this Chummer origin.");
    }
    if (target.username || target.password || target.search || target.hash || !ALLOWED_HANDOFF_PATHS.has(target.pathname)) {
      throw new Error("The mobile app handoff target is not an allowed clean install route.");
    }
    return target.href;
  };

  const bindDialog = (dialog) => {
    if (!(dialog instanceof HTMLElement) || dialog.dataset.mobileAppHandoffBound === "true") return;
    const ui = window.ChummerUi;
    if (!ui?.bindModalDialog) return;

    const openers = Array.from(document.querySelectorAll("[data-mobile-app-handoff]"))
      .filter((node) => node instanceof HTMLAnchorElement && node.dataset.mobileAppHandoff === dialog.id);
    const closeButtons = dialog.querySelectorAll("[data-close-mobile-app-handoff]");
    const targetInput = dialog.querySelector("[data-mobile-app-link]");
    const openLink = dialog.querySelector("[data-mobile-app-open]");
    const showQrButton = dialog.querySelector("[data-show-mobile-app-qr]");
    const copyButton = dialog.querySelector("[data-copy-mobile-app-link]");
    const copyStatus = dialog.querySelector("[data-mobile-app-copy-status]");
    const suggestion = dialog.querySelector("[data-mobile-app-suggestion]");
    const qrCard = dialog.querySelector("[data-mobile-app-qr-card]");
    const qrSvg = dialog.querySelector("[data-mobile-app-qr]");
    if (openers.length === 0 || !(targetInput instanceof HTMLInputElement) || !(openLink instanceof HTMLAnchorElement)) return;

    let targetUrl;
    try {
      targetUrl = resolveTargetUrl(
        dialog.dataset.mobileAppPath || "",
        dialog.dataset.mobileAppOrigin || ""
      );
    } catch {
      return;
    }
    targetInput.value = targetUrl;
    openLink.href = targetUrl;
    openers.forEach((opener) => {
      opener.href = targetUrl;
    });
    if (qrSvg instanceof SVGElement) {
      try {
        renderQrSvg(qrSvg, targetUrl);
      } catch (error) {
        qrSvg.hidden = true;
        const qrStatus = dialog.querySelector("[data-mobile-app-qr-status]");
        if (qrStatus instanceof HTMLElement) {
          qrStatus.hidden = false;
          qrStatus.textContent = error instanceof Error
            ? error.message
            : "The QR code is unavailable. Use the link below instead.";
        }
      }
    }

    const modal = ui.bindModalDialog(dialog, {
      closeButtons,
      initialFocus: "[data-close-mobile-app-handoff]"
    });
    if (!modal) return;

    const setQrExpanded = (expanded, moveFocus = false) => {
      if (!(qrCard instanceof HTMLElement) || !(showQrButton instanceof HTMLButtonElement)) return;
      qrCard.hidden = !expanded;
      showQrButton.setAttribute("aria-expanded", expanded ? "true" : "false");
      showQrButton.textContent = expanded ? "Hide QR code" : "Show QR / send to phone";
      if (expanded && moveFocus) {
        qrCard.scrollIntoView({ block: "nearest", behavior: "auto" });
        showQrButton.focus({ preventScroll: true });
      } else if (!expanded && moveFocus) {
        showQrButton.focus();
      }
    };

    openers.forEach((opener) => {
      opener.addEventListener("click", (event) => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
          return;
        }
        const effectiveDevice = resolveEffectiveDevice(loadDevicePreference());
        if (effectiveDevice === "mobile") {
          return;
        }
        event.preventDefault();
        const suggestedAction = "qr";
        dialog.dataset.mobileAppSuggestedAction = suggestedAction;
        if (suggestion instanceof HTMLElement) {
          suggestion.textContent = "Desktop handoff: scan the QR code with your phone, copy the clean install link, or open it on this device.";
        }
        setQrExpanded(true);
        ui.clearNotice?.(copyStatus);
        modal.open(opener);
      });
    });

    showQrButton?.addEventListener("click", () => {
      const expanded = showQrButton instanceof HTMLButtonElement
        && showQrButton.getAttribute("aria-expanded") === "true";
      setQrExpanded(!expanded, true);
    });

    copyButton?.addEventListener("click", async () => {
      try {
        await ui.copyToClipboard(targetUrl, copyButton, "Copied");
        if (copyButton instanceof HTMLElement) copyButton.focus();
        ui.setNotice?.(copyStatus, "Mobile link copied.");
      } catch {
        targetInput.focus();
        targetInput.select();
        ui.setNotice?.(
          copyStatus,
          "Copy is unavailable here. The mobile link is selected so you can copy it manually.",
          true
        );
      }
    });

    dialog.dataset.mobileAppHandoffBound = "true";
  };

  const bindInlineHandoff = (handoff) => {
    if (!(handoff instanceof HTMLElement) || handoff.dataset.mobileAppInlineHandoffBound === "true") return;
    const qrSvg = handoff.querySelector("[data-mobile-app-inline-qr]");
    const qrStatus = handoff.querySelector("[data-mobile-app-inline-qr-status]");
    const openLink = handoff.querySelector("[data-mobile-app-inline-open]");
    if (!(qrSvg instanceof SVGElement) || !(openLink instanceof HTMLAnchorElement)) return;

    try {
      const targetUrl = resolveTargetUrl(
        handoff.dataset.mobileAppPath || "",
        handoff.dataset.mobileAppOrigin || ""
      );
      renderQrSvg(qrSvg, targetUrl);
      openLink.href = targetUrl;
      handoff.dataset.mobileAppInlineHandoffBound = "true";
    } catch (error) {
      qrSvg.hidden = true;
      if (qrStatus instanceof HTMLElement) {
        qrStatus.hidden = false;
        qrStatus.textContent = error instanceof Error
          ? error.message
          : "The QR code is unavailable. Use the clean role link instead.";
      }
    }
  };

  const init = () => {
    bindDevicePickers();
    document.querySelectorAll("[data-mobile-app-handoff-dialog]").forEach(bindDialog);
    document.querySelectorAll("[data-mobile-app-inline-handoff]").forEach(bindInlineHandoff);
    syncDevicePicker();
  };

  ChummerMobileAppHandoff.buildQrMatrix = buildQrMatrix;
  ChummerMobileAppHandoff.usesMobilePresentation = usesMobilePresentation;
  ChummerMobileAppHandoff.readDeviceSignals = readDeviceSignals;
  ChummerMobileAppHandoff.resolveEffectiveDevice = resolveEffectiveDevice;
  ChummerMobileAppHandoff.resolveTargetUrl = resolveTargetUrl;
  ChummerMobileAppHandoff.init = init;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
