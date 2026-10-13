import { createContext, useContext, useState, useEffect, useCallback } from "react";
import ReportIssueDialog from "../components/common/ReportIssueDialog";

const Ctx = createContext({ openReport: () => {} });
export const useReportIssue = () => useContext(Ctx);

export function ReportIssueProvider({ children }) {
  const [open, setOpen] = useState(false);
  const openReport = useCallback(() => setOpen(true), []);

  // ErrorBoundary's "Report what happened" sets this flag before reloading to a safe route.
  useEffect(() => {
    try {
      if (localStorage.getItem("open_report_issue") === "1") {
        localStorage.removeItem("open_report_issue");
        setOpen(true);
      }
    } catch { /* ignore */ }
  }, []);

  return (
    <Ctx.Provider value={{ openReport }}>
      {children}
      <ReportIssueDialog open={open} onClose={() => setOpen(false)} />
    </Ctx.Provider>
  );
}
