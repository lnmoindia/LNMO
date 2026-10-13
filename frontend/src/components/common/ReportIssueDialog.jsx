import { useState } from "react";
import { toast } from "sonner";
import { ImagePlus, X } from "lucide-react";
import api, { errText } from "../../lib/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "../ui/dialog";

const CATEGORIES = [
  { value: "bug", label: "Bug — something is broken" },
  { value: "question", label: "Question — I need help" },
  { value: "suggestion", label: "Suggestion — an idea" },
];

export default function ReportIssueDialog({ open, onClose }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("bug");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);

  const reset = () => { setTitle(""); setDescription(""); setCategory("bug"); setFile(null); };

  const submit = async () => {
    if (!title.trim()) { toast.error("Please add a short title"); return; }
    if (file && file.size > 5 * 1024 * 1024) { toast.error("Screenshot must be under 5 MB"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("title", title.trim());
      fd.append("description", description.trim());
      fd.append("category", category);
      fd.append("page_url", window.location.href);
      fd.append("route", window.location.pathname);
      if (file) fd.append("screenshot", file);
      const { data } = await api.post("/support/issues", fd);
      toast.success(`Thanks! Ticket #${String(data.id).slice(0, 8)} created`);
      reset(); onClose();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !busy && (reset(), onClose())}>
      <DialogContent className="sm:max-w-lg" data-testid="report-issue-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">Report an issue</DialogTitle>
          <DialogDescription>Tell us what happened. We'll attach your current page automatically.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label>Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger data-testid="report-category"><SelectValue /></SelectTrigger>
              <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Short summary" data-testid="report-title" />
          </div>
          <div className="space-y-1.5">
            <Label>What happened?</Label>
            <Textarea rows={4} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Steps, what you expected, what you saw…" data-testid="report-description" />
          </div>
          <div className="space-y-1.5">
            <Label>Screenshot (optional)</Label>
            {file ? (
              <div className="flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm">
                <ImagePlus size={15} className="text-indigo-600 shrink-0" />
                <span className="truncate flex-1">{file.name}</span>
                <button onClick={() => setFile(null)} className="text-slate-400 hover:text-rose-500" data-testid="report-screenshot-remove"><X size={15} /></button>
              </div>
            ) : (
              <label className="flex items-center gap-2 rounded-lg border border-dashed border-slate-300 dark:border-slate-700 px-3 py-2.5 text-sm text-slate-500 cursor-pointer hover:border-indigo-400" data-testid="report-screenshot-label">
                <ImagePlus size={15} /> Add a screenshot
                <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="report-screenshot-input" />
              </label>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => { reset(); onClose(); }} disabled={busy}>Cancel</Button>
            <Button className="bg-indigo-700 hover:bg-indigo-800 text-white" onClick={submit} disabled={busy} data-testid="report-submit">{busy ? "Sending…" : "Send report"}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
