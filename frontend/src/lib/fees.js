import { toast } from "sonner";
import api, { errText } from "./api";
import { printFeeReceipt } from "./printDoc";

export const inr = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

const TONE = {
  paid: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
  partial: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400",
  pending: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  overdue: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400",
  reversed: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
  carried_forward: "bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-400",
};

export const StatusChip = ({ status, testid }) => (
  <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold capitalize ${TONE[status] || TONE.pending}`} data-testid={testid}>{String(status).replace("_", " ")}</span>
);

export const FREQ_LABEL = { annual: "Annual", term: "Per term", monthly: "Monthly", one_time: "One-time", arrears: "Arrears" };

export const printReceiptById = async (pid) => {
  try {
    const { data } = await api.get(`/fees/payments/${pid}/receipt`);
    printFeeReceipt(data);
  } catch (e) { toast.error(errText(e)); }
};

export const downloadReceiptPdf = async (pid, receiptNo) => {
  try {
    const { data } = await api.get(`/fees/payments/${pid}/receipt.pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url; a.download = `receipt-${receiptNo || pid}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (e) { toast.error(errText(e)); }
};
