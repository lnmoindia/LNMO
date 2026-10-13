import { useState } from "react";

// Dev-only, not in nav. Lets us smoke-verify the crash pipeline end-to-end in a browser:
// a render throw triggers the ErrorBoundary; an async throw triggers the window 'error' listener.
// Both funnel into reportCrash → POST /api/support/crash.
export default function CrashTest() {
  const [boom, setBoom] = useState(false);
  if (boom) throw new Error("CRASHTEST render error (intentional)");
  return (
    <div className="space-y-4" data-testid="crash-test-page">
      <h1 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">Crash test (dev)</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400">These buttons intentionally throw so we can confirm crashes are auto-captured. Not linked anywhere in the UI.</p>
      <div className="flex gap-3">
        <button
          onClick={() => setBoom(true)}
          data-testid="crash-test-render"
          className="rounded-xl bg-rose-600 text-white px-4 py-2.5 text-sm font-semibold hover:bg-rose-700"
        >
          Throw render error (ErrorBoundary)
        </button>
        <button
          onClick={() => { setTimeout(() => { throw new Error("CRASHTEST async error (intentional)"); }, 0); }}
          data-testid="crash-test-async"
          className="rounded-xl border border-slate-300 dark:border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          Throw async error (window listener)
        </button>
      </div>
    </div>
  );
}
