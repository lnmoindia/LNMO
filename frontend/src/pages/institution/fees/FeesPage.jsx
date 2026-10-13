import { Wallet } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../../../context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../../components/ui/tabs";
import StructuresTab from "./StructuresTab";
import AccountsTab from "./AccountsTab";
import ReceiptsTab from "./ReceiptsTab";
import DayBookTab from "./DayBookTab";
import ReminderSettings from "./ReminderSettings";
import DefaultersTab from "./DefaultersTab";
import MonthlySummaryTab from "./MonthlySummaryTab";

const TABS = ["structures", "accounts", "receipts", "daybook", "defaulters", "monthly"];

export default function FeesPage() {
  const { user } = useAuth();
  const readOnly = user?.role !== "institution_admin";
  const [params, setParams] = useSearchParams();
  const tab = TABS.includes(params.get("tab")) ? params.get("tab") : "structures";
  const setTab = (t) => setParams((p) => { const n = new URLSearchParams(p); n.set("tab", t); return n; }, { replace: true });
  return (
    <div className="space-y-6" data-testid="fees-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50 flex items-center gap-2"><Wallet className="text-emerald-600" /> Fees</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Fee structures, student ledgers and offline collection with numbered receipts.{readOnly ? " You have read-only access." : ""}
        </p>
      </div>
      <ReminderSettings readOnly={readOnly} />
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="structures" data-testid="fees-tab-structures">Structures</TabsTrigger>
          <TabsTrigger value="accounts" data-testid="fees-tab-accounts">Accounts</TabsTrigger>
          <TabsTrigger value="receipts" data-testid="fees-tab-receipts">Receipts</TabsTrigger>
          <TabsTrigger value="daybook" data-testid="fees-tab-daybook">Day Book</TabsTrigger>
          <TabsTrigger value="defaulters" data-testid="fees-tab-defaulters">Defaulters</TabsTrigger>
          <TabsTrigger value="monthly" data-testid="fees-tab-monthly">Monthly Summary</TabsTrigger>
        </TabsList>
        <TabsContent value="structures"><StructuresTab readOnly={readOnly} /></TabsContent>
        <TabsContent value="accounts"><AccountsTab readOnly={readOnly} /></TabsContent>
        <TabsContent value="receipts"><ReceiptsTab readOnly={readOnly} /></TabsContent>
        <TabsContent value="daybook"><DayBookTab /></TabsContent>
        <TabsContent value="defaulters"><DefaultersTab /></TabsContent>
        <TabsContent value="monthly"><MonthlySummaryTab /></TabsContent>
      </Tabs>
    </div>
  );
}
