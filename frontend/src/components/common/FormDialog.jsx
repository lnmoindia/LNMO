import { useEffect, useState } from "react";
import api from "../../lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";

export const FormDialog = ({ open, onClose, title, fields, initial, onSubmit, submitting, error }) => {
  const [values, setValues] = useState({});
  const [dynOptions, setDynOptions] = useState({});
  const isEdit = Boolean(initial?.id);

  useEffect(() => {
    if (open) {
      const v = {};
      fields.forEach((f) => { v[f.name] = initial?.[f.name] ?? f.default ?? ""; });
      setValues(v);
      fields.filter((f) => f.optionsUrl).forEach((f) => {
        api.get(`/${f.optionsUrl}`)
          .then((r) => setDynOptions((d) => ({ ...d, [f.name]: r.data })))
          .catch(() => setDynOptions((d) => ({ ...d, [f.name]: [] })));
      });
    }
  }, [open, initial]); // eslint-disable-line

  const visible = fields.filter((f) => !(isEdit && f.createOnly));
  const set = (name, val) => setValues((v) => ({ ...v, [name]: val }));

  const submit = (e) => {
    e.preventDefault();
    onSubmit(values);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-testid="form-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading">{isEdit ? `Edit ${title}` : `New ${title}`}</DialogTitle>
          <DialogDescription>{isEdit ? "Update the details below." : "Fill in the details below."}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          {visible.map((f) => (
            <div key={f.name} className="space-y-1.5">
              <Label htmlFor={f.name}>{f.label}{f.required && <span className="text-red-500 ml-0.5">*</span>}</Label>
              {f.type === "select" || f.optionsUrl ? (
                <Select value={values[f.name] || ""} onValueChange={(v) => set(f.name, v)}>
                  <SelectTrigger data-testid={`field-${f.name}`}><SelectValue placeholder={`Select ${f.label.toLowerCase()}`} /></SelectTrigger>
                  <SelectContent>
                    {(f.optionsUrl ? dynOptions[f.name] || [] : f.options).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              ) : f.type === "textarea" ? (
                <Textarea id={f.name} value={values[f.name] || ""} onChange={(e) => set(f.name, e.target.value)} data-testid={`field-${f.name}`} />
              ) : (
                <Input
                  id={f.name}
                  type={f.type || "text"}
                  required={f.required}
                  value={values[f.name] || ""}
                  onChange={(e) => set(f.name, e.target.value)}
                  data-testid={`field-${f.name}`}
                />
              )}
            </div>
          ))}
          {error && <p className="text-sm text-red-600" data-testid="form-error">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} data-testid="form-cancel-btn">Cancel</Button>
            <Button type="submit" disabled={submitting} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid="form-submit-btn">
              {submitting ? "Saving…" : isEdit ? "Save changes" : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};
