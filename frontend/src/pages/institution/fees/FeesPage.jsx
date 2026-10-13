import { Wallet } from "lucide-react";
import { useAuth } from "../../../context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../../components/ui/tabs";
import StructuresTab from "./StructuresTab";
import AccountsTab from "./AccountsTab";
import ReceiptsTab from "./ReceiptsTab";
import DayBookTab from "./DayBookTab";
import ReminderSettings from "./ReminderSettings";

export default function FeesPage() {
  const { user } = useAuth();
  const readOnly = user?.role !== "institution_admin";
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
      <Tabs defaultValue="structures">
        <TabsList>
          <TabsTrigger value="structures" data-testid="fees-tab-structures">Structures</TabsTrigger>
          <TabsTrigger value="accounts" data-testid="fees-tab-accounts">Accounts</TabsTrigger>
          <TabsTrigger value="receipts" data-testid="fees-tab-receipts">Receipts</TabsTrigger>
          <TabsTrigger value="daybook" data-testid="fees-tab-daybook">Day Book</TabsTrigger>
        </TabsList>
        <TabsContent value="structures"><StructuresTab readOnly={readOnly} /></TabsContent>
        <TabsContent value="accounts"><AccountsTab readOnly={readOnly} /></TabsContent>
        <TabsContent value="receipts"><ReceiptsTab readOnly={readOnly} /></TabsContent>
        <TabsContent value="daybook"><DayBookTab /></TabsContent>
      </Tabs>
    </div>
  );
}
