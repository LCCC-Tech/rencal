document.addEventListener("DOMContentLoaded", () => {
  const popup = document.getElementById("cookies-popup");
  const toast = document.getElementById("cookies-toast");
  const acceptBtn = document.getElementById("accept-all");
  const rejectBtn = document.getElementById("reject-nonessential");
  const manageBtnToast = document.getElementById("manage-preferences-toast");
  const closeCookiesToast = document.getElementById("close-cookies-toast");
  const toastMessage = document.getElementById("cookies-toast-message");

  if (!popup || !toast || !acceptBtn) return;

  // Starlight's main content column has `isolation: isolate` (a new
  // stacking context), which traps `position: fixed` descendants below
  // other fixed elements positioned outside it (e.g. the sidebar) even
  // with a very high z-index - z-index is only ever compared within the
  // same stacking context. Moving the popup/toast to be direct children
  // of <body> escapes that context entirely, regardless of where the
  // Footer override happens to render them in Starlight's DOM.
  document.body.appendChild(popup);
  document.body.appendChild(toast);

  let firstTabPressed = false;
  let forcedToastFocus = false;
  let toastAutoHideTimerId = null;

  /*** ────────────────
   * CONFIGURATION
   *────────────────*/
  const COOKIE_STORAGE_KEY = "cookieConsent";
  const CONSENT_DURATION_DAYS = 730;
  const TOAST_AUTO_HIDE_MS = 5000;
  // Fallback used only when a registrable domain can't be determined (e.g.
  // localhost) - the link is purely informational in that case.
  const FALLBACK_POLICY_URL = "https://www.lowcarboncontracts.uk/privacy-and-cookies";
  const FALLBACK_ACCESSIBILITY_URL = "https://www.lowcarboncontracts.uk/accessibility";

  const TOAST_TEXT = {
    accepted: "You chose to <strong>Accept all</strong> cookies",
    rejected:
      "You chose to <strong>Accept Essential</strong> cookies only <br /><span style='font-size: 12px'>Please note that your experience of some site features may be affected.</span>",
  };

  /*** ────────────────
   * REGISTRABLE DOMAIN
   * Ported from lccc-website's app/config/public_suffix.py so cookie
   * consent is scoped to the same root domain regardless of which
   * domain/subdomain this static site is deployed to.
   *────────────────*/
  const MULTI_LABEL_SECOND_LEVEL_LABELS = new Set([
    "co",
    "com",
    "org",
    "net",
    "gov",
    "edu",
    "ac",
    "mil",
    "ltd",
    "plc",
    "me",
    "sch",
    "nhs",
    "police",
  ]);

  const isIpAddress = hostname => {
    const parts = hostname.split(".");
    if (
      parts.length === 4 &&
      parts.every(part => /^\d+$/.test(part) && Number(part) >= 0 && Number(part) <= 255)
    ) {
      return true;
    }
    return hostname.includes(":");
  };

  const getRegistrableDomain = hostname => {
    hostname = (hostname || "").replace(/\.+$/, "").toLowerCase();
    if (!hostname || isIpAddress(hostname)) return "";

    const labels = hostname.split(".");
    if (labels.length < 2) return "";

    const tld = labels[labels.length - 1];
    const secondLevel = labels[labels.length - 2];

    const isMultiLabelSuffix =
      labels.length >= 3 && tld.length <= 3 && MULTI_LABEL_SECOND_LEVEL_LABELS.has(secondLevel);
    const suffixLabelCount = isMultiLabelSuffix ? 2 : 1;

    return labels.slice(-(suffixLabelCount + 1)).join(".");
  };

  const registrableDomain = getRegistrableDomain(window.location.hostname);
  const policyUrl = registrableDomain
    ? `${window.location.protocol}//${registrableDomain}/privacy-and-cookies`
    : FALLBACK_POLICY_URL;
  const accessibilityUrl = registrableDomain
    ? `${window.location.protocol}//${registrableDomain}/accessibility`
    : FALLBACK_ACCESSIBILITY_URL;

  document.querySelectorAll(".cookie-policy-link").forEach(link => {
    link.href = policyUrl;
  });

  document.querySelectorAll(".accessibility-link").forEach(link => {
    link.href = accessibilityUrl;
  });

  /*** ────────────────
   * COOKIE UTILITIES
   *────────────────*/
  const getCookie = name => {
    const match = document.cookie.match(
      new RegExp(`(?:^|; )${name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1")}=([^;]*)`)
    );
    return match ? decodeURIComponent(match[1]) : null;
  };

  const setCookie = (name, value, days) => {
    const maxAgeSeconds = Math.round(days * 24 * 60 * 60);
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    const domain = registrableDomain ? `; domain=${registrableDomain}` : "";
    document.cookie = `${name}=${encodeURIComponent(
      value
    )}; max-age=${maxAgeSeconds}; path=/; SameSite=Lax${secure}${domain}`;
  };

  const getStoredConsent = () => getCookie(COOKIE_STORAGE_KEY);

  const setStoredConsent = value => {
    setCookie(COOKIE_STORAGE_KEY, value, CONSENT_DURATION_DAYS);
    hide(popup);
  };

  // This site is deployed on a subdomain of a shared root domain (e.g.
  // dev-docs.lccctest.co.uk), and cookies set with `domain=<root>` by other
  // apps on that same root domain (like the main lccc-website) are visible
  // to document.cookie here too. So this must only ever clear cookies we
  // know are non-essential and ours to manage (currently just Google
  // Analytics) - never blanket-delete every cookie the browser exposes,
  // or we'd risk breaking sessions/state belonging to a different app.
  const removeNonEssentialCookies = () => {
    if (window.disableAnalytics) window.disableAnalytics();
  };

  /*** ────────────────
   * SHOW / HIDE HELPERS
   *────────────────*/
  const hide = el => {
    if (el) {
      el.classList.add("hidden");
      el.setAttribute("inert", "");
    }
  };

  const show = el => {
    if (el) {
      el.classList.remove("hidden");
      el.removeAttribute("inert");

      if (el === toast) {
        if (closeCookiesToast) closeCookiesToast.focus();
        if (toastAutoHideTimerId) clearTimeout(toastAutoHideTimerId);
        toastAutoHideTimerId = setTimeout(() => {
          hide(toast);
          toastAutoHideTimerId = null;
        }, TOAST_AUTO_HIDE_MS);
      }
    }
  };

  const updateToastText = status => {
    if (toastMessage) toastMessage.innerHTML = TOAST_TEXT[status] || "";
  };

  /*** ────────────────
   * GOOGLE ANALYTICS FUNCTIONS
   *────────────────*/
  window.enableAnalytics = function () {
    if (window.gaEnabled) return; // Already enabled
    const measurementId = document.querySelector('meta[name="ga-measurement-id"]')?.content;
    if (!measurementId) {
      console.info("GA measurementId missing; aborting analytics enable.");
      return;
    }

    if (!document.querySelector(`script[src*="gtag/js?id=${measurementId}"]`)) {
      const script = document.createElement("script");
      script.async = true;
      script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
      document.head.appendChild(script);
    }

    window.dataLayer = window.dataLayer || [];
    function gtag() {
      window.dataLayer.push(arguments);
    }
    window.gtag = gtag;
    gtag("js", new Date());
    gtag("consent", "update", { analytics_storage: "granted" });
    gtag("config", measurementId, { anonymize_ip: true });

    window.gaEnabled = true;
  };

  window.disableAnalytics = function () {
    if (!window.gaEnabled) {
      // Still clear any stray GA cookies even if we never enabled it
      // ourselves in this page load (e.g. consent revoked elsewhere).
    } else if (window.gtag) {
      try {
        window.gtag("consent", "update", { analytics_storage: "denied" });
      } catch (_) {
        // gtag threw; nothing more we can do here.
      }
    }

    const gaPatterns = [/^_ga($|_)/, /^_gid$/, /^_gat($|_)/];
    document.cookie.split(";").forEach(raw => {
      const name = raw.split("=")[0].trim();
      if (gaPatterns.some(rx => rx.test(name))) {
        ["", "." + window.location.hostname, registrableDomain ? "." + registrableDomain : ""]
          .filter(Boolean)
          .forEach(domainVariant => {
            document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=${domainVariant};`;
          });
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/;`;
      }
    });

    document.querySelectorAll('script[src*="googletagmanager.com/gtag/js"]').forEach(s => s.remove());

    delete window.gtag;
    delete window.dataLayer;
    window.gaEnabled = false;
  };

  /*** ────────────────
   * KEYBOARD FOCUS HANDLING
   *────────────────*/
  document.addEventListener("keydown", e => {
    if (e.key === "Tab" && !popup.classList.contains("hidden") && !firstTabPressed) {
      e.preventDefault();
      acceptBtn.focus();
      firstTabPressed = true;
      return;
    }

    if (e.key === "Tab" && !toast.classList.contains("hidden") && !forcedToastFocus) {
      e.preventDefault();
      if (manageBtnToast) manageBtnToast.focus();
      forcedToastFocus = true;
    }
  });

  /*** ────────────────
   * INITIALIZATION
   *────────────────*/
  popup.setAttribute("inert", "");
  toast.setAttribute("inert", "");

  const existingConsent = getStoredConsent();
  if (!existingConsent) {
    hide(toast);
    show(popup);
  } else {
    hide(popup);
    hide(toast);

    if (existingConsent === "accepted") {
      if (window.enableAnalytics) window.enableAnalytics();
    } else {
      if (window.disableAnalytics) window.disableAnalytics();
    }
  }

  /*** ────────────────
   * EVENT HANDLERS
   *────────────────*/
  const handleAcceptAll = () => {
    setStoredConsent("accepted");
    hide(popup);
    updateToastText("accepted");
    show(toast);
    if (window.enableAnalytics) window.enableAnalytics();
  };

  const handleRejectNonEssential = () => {
    setStoredConsent("rejected");
    removeNonEssentialCookies();
    hide(popup);
    updateToastText("rejected");
    show(toast);
  };

  const handleCloseToast = () => hide(toast);

  acceptBtn.addEventListener("click", handleAcceptAll);
  if (rejectBtn) rejectBtn.addEventListener("click", handleRejectNonEssential);
  if (closeCookiesToast) closeCookiesToast.addEventListener("click", handleCloseToast);

  // Enable CSS transitions after JS logic runs so the popup/toast don't
  // animate in on first paint.
  document.body.classList.add("cookies-animated");

  // Re-apply consent state when the page is restored from the
  // back-forward cache (bfcache); the browser does not re-fire
  // DOMContentLoaded in that case, so a consent change made on another
  // page (e.g. the main site, sharing this root-domain cookie) would
  // otherwise not be reflected until a hard reload.
  window.addEventListener("pageshow", event => {
    if (!event.persisted) return;
    const consent = getStoredConsent();
    if (consent === "accepted") {
      if (window.enableAnalytics && !window.gaEnabled) window.enableAnalytics();
    } else if (window.gaEnabled) {
      if (window.disableAnalytics) window.disableAnalytics();
    }
  });
});
