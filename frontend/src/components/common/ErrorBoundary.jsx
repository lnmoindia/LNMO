import React from "react";
import { reportCrash } from "../../lib/crashReporter";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || "Something went wrong" };
  }

  componentDidCatch(error, info) {
    reportCrash({ message: error?.message || "React render crash", stack: error?.stack || info?.componentStack || "" });
  }

  handleReport = () => {
    try { localStorage.setItem("open_report_issue", "1"); } catch { /* ignore */ }
    window.location.assign("/");
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#0B0F17] px-6" data-testid="crash-fallback">
        <div className="max-w-md text-center space-y-5">
          <div className="mx-auto h-14 w-14 rounded-2xl bg-rose-100 dark:bg-rose-500/15 flex items-center justify-center text-2xl">⚠️</div>
          <div className="space-y-2">
            <h1 className="font-heading text-2xl font-bold text-slate-900 dark:text-slate-50">Something went wrong</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">We've logged this automatically and the team will take a look. You can tell us what you were doing to help us fix it faster.</p>
          </div>
          <div className="flex items-center justify-center gap-3">
            <button onClick={() => window.location.reload()} data-testid="crash-reload-btn" className="rounded-xl bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 px-4 py-2.5 text-sm font-semibold hover:opacity-90 transition-opacity">Reload page</button>
            <button onClick={this.handleReport} data-testid="crash-report-btn" className="rounded-xl border border-slate-300 dark:border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">Report what happened</button>
          </div>
        </div>
      </div>
    );
  }
}
