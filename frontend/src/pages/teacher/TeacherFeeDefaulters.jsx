import { Wallet } from "lucide-react";
import DefaultersTab from "../institution/fees/DefaultersTab";

export default function TeacherFeeDefaulters() {
  return (
    <div className="space-y-4" data-testid="teacher-fee-defaulters-page">
      <div>
        <h1 className="font-heading text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50 flex items-center gap-2"><Wallet className="text-rose-600" /> Fee Defaulters</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Students of your class with overdue fees. View only.</p>
      </div>
      <DefaultersTab />
    </div>
  );
}
