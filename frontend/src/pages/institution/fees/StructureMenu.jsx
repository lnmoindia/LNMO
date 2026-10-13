import { useState } from "react";
import { Archive, ArchiveRestore, MoreHorizontal, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../../components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../../../components/ui/dropdown-menu";

export const usageText = (u) => `Used by ${u.students} student${u.students === 1 ? "" : "s"} / ${u.invoices} invoice${u.invoices === 1 ? "" : "s"} — archive instead`;

export function StructureMenu({ st, onChanged }) {
  const [dlg, setDlg] = useState(null); // delete | archive | unarchive
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState("");
  const used = st.usage?.used;
  const run = async (kind) => {
    setBusy(true);
    try {
      if (kind === "delete") await api.delete(`/fees/structures/${st.id}`);
      else await api.post(`/fees/structures/${st.id}/${kind}`);
      toast.success(kind === "delete" ? "Fee structure deleted" : kind === "archive" ? "Archived — hidden from new invoices" : "Unarchived");
      setDlg(null); onChanged();
    } catch (e) {
      if (kind === "delete" && e?.response?.status === 409) { setBlocked(errText(e)); setDlg("archive"); }
      else toast.error(errText(e));
    } finally { setBusy(false); }
  };
  const open = (k) => { setBlocked(""); setDlg(k); };
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline" className="px-2" data-testid={`fee-structure-menu-${st.id}`}><MoreHorizontal size={15} /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          {st.archived ? (
            <DropdownMenuItem onSelect={() => open("unarchive")} data-testid={`fee-structure-unarchive-${st.id}`}><ArchiveRestore size={14} className="mr-2" /> Unarchive</DropdownMenuItem>
          ) : (
            <DropdownMenuItem onSelect={() => open("archive")} data-testid={`fee-structure-archive-${st.id}`}><Archive size={14} className="mr-2" /> Archive</DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={used} onSelect={() => open("delete")} className="text-red-600 focus:text-red-600" data-testid={`fee-structure-delete-${st.id}`}>
            <Trash2 size={14} className="mr-2" /> Delete
          </DropdownMenuItem>
          {used && <p className="px-2 pb-1.5 text-[11px] leading-snug text-slate-500" data-testid={`fee-structure-delete-reason-${st.id}`}>{usageText(st.usage)}</p>}
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={Boolean(dlg)} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent className="max-w-md" data-testid="fee-structure-action-dialog">
          <DialogHeader>
            <DialogTitle>{dlg === "delete" ? `Delete ${st.name}?` : dlg === "archive" ? `Archive ${st.name}?` : `Unarchive ${st.name}?`}</DialogTitle>
            <DialogDescription>
              {dlg === "delete" ? "This can't be undone." : dlg === "archive"
                ? "It won't be offered for new students or new invoices. Existing accounts, invoices, payments, receipts and reports keep working."
                : "It will be available again for applying to students and generating invoices."}
            </DialogDescription>
          </DialogHeader>
          {blocked && <p className="text-sm rounded-lg bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 px-3 py-2" data-testid="fee-structure-delete-blocked">{blocked}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDlg(null)}>Cancel</Button>
            <Button disabled={busy} onClick={() => run(dlg)} className={dlg === "delete" ? "bg-red-600 hover:bg-red-700 text-white" : "bg-indigo-700 hover:bg-indigo-800 text-white"} data-testid="fee-structure-action-confirm">
              {busy ? <Loader2 size={14} className="animate-spin" /> : dlg === "delete" ? "Delete" : dlg === "archive" ? "Archive" : "Unarchive"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
