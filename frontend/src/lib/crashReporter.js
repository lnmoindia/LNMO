// Global crash capture → POST /api/support/crash (works unauthenticated; cookies attached when present).
// Client-side throttle: the same error signature is sent at most once per minute per browser.
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const sent = new Map(); // signature -> last epoch ms
const THROTTLE_MS = 60_000;

const signature = (message, stack) => {
  const first = (stack || "").split("\n").map((s) => s.trim()).find(Boolean) || "";
  return `${message}|${first}`;
};

export async function reportCrash({ message, stack }) {
  try {
    const msg = String(message || "Unknown error").slice(0, 2000);
    const sig = signature(msg, stack);
    const now = Date.now();
    if (sent.has(sig) && now - sent.get(sig) < THROTTLE_MS) return;
    sent.set(sig, now);
    await fetch(`${API}/support/crash`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        message: msg,
        stack: String(stack || "").slice(0, 8000),
        page_url: window.location.href,
        route: window.location.pathname,
        user_agent: navigator.userAgent,
        app_version: process.env.REACT_APP_VERSION || "web",
      }),
    });
  } catch {
    /* never let the reporter throw */
  }
}

let installed = false;
export function installCrashHandlers() {
  if (installed) return;
  installed = true;
  window.addEventListener("error", (e) => {
    reportCrash({ message: e?.message || "Script error", stack: e?.error?.stack || `${e?.filename}:${e?.lineno}:${e?.colno}` });
  });
  window.addEventListener("unhandledrejection", (e) => {
    const r = e?.reason;
    reportCrash({ message: r?.message || String(r) || "Unhandled promise rejection", stack: r?.stack || "" });
  });
}
