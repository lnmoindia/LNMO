import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, Trash2, Pencil, Check, X } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";

const blank = (fields) => {
  const v = {};
  fields.forEach((f) => { v[f.name] = f.type === "checkbox" ? false : f.default ?? ""; });
  return v;
};

/** Compact create-and-list widget used inside the setup wizard. */
export const InlineList = ({ endpoint, fields, columns, extra = {}, params = {}, filter, hideFields = [], onChange, testid, emptyText = "Nothing added yet." }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(blank(fields));
  const [options, setOptions] = useState({});
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/${endpoint}`, { params: { limit: 200, ...params } });
      setItems(data.items || []);
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setLoading(false);
    }
  }, [endpoint, JSON.stringify(params)]); // eslint-disable-line react-hooks/exhaustive-deps

  const depSource = { ...form, ...extra };
  const fetchOpts = useCallback((f, depVal) => {
    const p = f.dependsOn && depVal ? { [f.dependsOn]: depVal } : {};
    api.get(`/${f.optionsUrl}`, { params: p })
      .then((r) => setOptions((o) => ({ ...o, [f.name]: r.data })))
      .catch(() => setOptions((o) => ({ ...o, [f.name]: [] })));
  }, []);

  const loadOptions = useCallback(() => {
    fields.filter((f) => f.optionsUrl && !f.dependsOn).forEach((f) => fetchOpts(f));
  }, [fields, fetchOpts]);

  useEffect(() => { load(); loadOptions(); }, [load, loadOptions]);

  const depKey = fields.filter((f) => f.optionsUrl && f.dependsOn).map((f) => `${f.name}:${depSource[f.dependsOn] || ""}`).join("|");
  const prevDepKey = useRef(null);
  useEffect(() => {
    fields.filter((f) => f.optionsUrl && f.dependsOn).forEach((f) => fetchOpts(f, depSource[f.dependsOn]));
    if (prevDepKey.current !== null && prevDepKey.current !== depKey) {
      setForm((v) => {
        const next = { ...v };
        fields.forEach((f) => { if (f.dependsOn) next[f.name] = f.type === "checkbox" ? false : ""; });
        return next;
      });
    }
    prevDepKey.current = depKey;
  }, [depKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (name, val) => setForm((v) => {
    const next = { ...v, [name]: val };
    fields.forEach((f) => { if (f.dependsOn === name) next[f.name] = f.type === "checkbox" ? false : ""; });
    return next;
  });
  const visibleFields = fields.filter((f) => !hideFields.includes(f.name) && (!f.showIf || f.showIf(form)));
  const shown = filter ? items.filter(filter) : items;

  const add = async () => {
    setSaving(true);
    try {
      await api.post(`/${endpoint}`, { ...form, ...extra });
      setForm(blank(fields));
      await load();
      loadOptions();
      onChange && onChange();
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row) => {
    try {
      await api.delete(`/${endpoint}/${row.id}`);
      await load();
      loadOptions();
      onChange && onChange();
    } catch (e) {
      toast.error(errText(e));
    }
  };

  const startEdit = (row) => {
    const v = {};
    fields.forEach((f) => { v[f.name] = row[f.name] ?? (f.type === "checkbox" ? false : ""); });
    setEditForm(v);
    setEditingId(row.id);
  };
  const cancelEdit = () => { setEditingId(null); setEditForm({}); };
  const setEdit = (name, val) => setEditForm((v) => ({ ...v, [name]: val }));
  const saveEdit = async (row) => {
    setSaving(true);
    try {
      const payload = {};
      fields.forEach((f) => { payload[f.name] = editForm[f.name]; });
      await api.put(`/${endpoint}/${row.id}`, payload);
      setEditingId(null);
      setEditForm({});
      await load();
      loadOptions();
      onChange && onChange();
      toast.success("Saved");
    } catch (e) {
      toast.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const fieldByName = Object.fromEntries(fields.map((f) => [f.name, f]));
  const canAdd = visibleFields.filter((f) => f.required).every((f) => String(form[f.name] || "").trim());

  return (
    <div className="space-y-4" data-testid={testid}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 items-end rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-4">
        {visibleFields.map((f) => (
          <div key={f.name} className="space-y-1">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
              {f.label}{f.required && <span className="text-red-500 ml-0.5">*</span>}
            </label>
            {f.type === "checkbox" ? (
              <button
                type="button"
                onClick={() => set(f.name, !form[f.name])}
                data-testid={`inline-${f.name}-toggle`}
                className={`h-9 w-full rounded-md border px-3 text-sm transition-colors ${
                  form[f.name]
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300"
                    : "border-slate-200 dark:border-slate-700 text-slate-500"
                }`}
              >
                {form[f.name] ? "Yes" : "No"}
              </button>
            ) : f.type === "select" || f.optionsUrl ? (
              <Select value={form[f.name] || ""} onValueChange={(v) => set(f.name, v)}>
                <SelectTrigger data-testid={`inline-field-${f.name}`}><SelectValue placeholder={`Select ${f.label.toLowerCase()}`} /></SelectTrigger>
                <SelectContent>
                  {(f.optionsUrl ? options[f.name] || [] : f.options || []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                type={f.type || "text"}
                value={form[f.name] || ""}
                onChange={(e) => set(f.name, e.target.value)}
                placeholder={f.placeholder}
                data-testid={`inline-field-${f.name}`}
              />
            )}
          </div>
        ))}
        <div className="sm:col-span-2 lg:col-span-3 flex justify-end">
          <Button onClick={add} disabled={!canAdd || saving} className="bg-indigo-700 hover:bg-indigo-800 text-white" data-testid={`${testid}-add-btn`}>
            <Plus size={15} className="mr-1" /> {saving ? "Adding…" : "Add"}
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-900/60 text-left">
            <tr>
              {columns.map((c) => <th key={c.key} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{c.label}</th>)}
              <th className="px-4 py-2 w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {loading ? (
              <tr><td colSpan={columns.length + 1} className="px-4 py-6 text-center text-slate-400">Loading…</td></tr>
            ) : shown.length === 0 ? (
              <tr><td colSpan={columns.length + 1} className="px-4 py-6 text-center text-slate-400">{emptyText}</td></tr>
            ) : shown.map((row) => {
              const editing = editingId === row.id;
              return (
              <tr key={row.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                {columns.map((c) => {
                  const f = fieldByName[c.key];
                  if (editing && f) {
                    return (
                      <td key={c.key} className="px-4 py-2">
                        {f.type === "select" || f.optionsUrl ? (
                          <Select value={editForm[f.name] || ""} onValueChange={(v) => setEdit(f.name, v)}>
                            <SelectTrigger data-testid={`${testid}-edit-${f.name}`} className="h-8"><SelectValue placeholder={f.label} /></SelectTrigger>
                            <SelectContent>
                              {(f.optionsUrl ? options[f.name] || [] : f.options || []).map((o) => (
                                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : f.type === "checkbox" ? (
                          <button type="button" onClick={() => setEdit(f.name, !editForm[f.name])} data-testid={`${testid}-edit-${f.name}`}
                            className={`h-8 px-3 rounded-md border text-sm ${editForm[f.name] ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300" : "border-slate-200 dark:border-slate-700 text-slate-500"}`}>
                            {editForm[f.name] ? "Yes" : "No"}
                          </button>
                        ) : (
                          <Input type={f.type || "text"} value={editForm[f.name] || ""} onChange={(e) => setEdit(f.name, e.target.value)}
                            placeholder={f.placeholder} className="h-8" data-testid={`${testid}-edit-${f.name}`} />
                        )}
                      </td>
                    );
                  }
                  return (
                    <td key={c.key} className="px-4 py-2.5 text-slate-700 dark:text-slate-300">
                      {c.render ? c.render(row) : (row[c.key] ?? "—")}
                    </td>
                  );
                })}
                <td className="px-4 py-2.5 whitespace-nowrap">
                  {editing ? (
                    <div className="flex items-center gap-2">
                      <button onClick={() => saveEdit(row)} disabled={saving} data-testid={`${testid}-edit-save`} className="text-emerald-600 hover:text-emerald-700 transition-colors"><Check size={16} /></button>
                      <button onClick={cancelEdit} data-testid={`${testid}-edit-cancel`} className="text-slate-400 hover:text-slate-600 transition-colors"><X size={16} /></button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <button onClick={() => startEdit(row)} data-testid={`${testid}-edit`} className="text-slate-400 hover:text-indigo-600 transition-colors"><Pencil size={14} /></button>
                      <button onClick={() => remove(row)} data-testid={`${testid}-delete`} className="text-slate-400 hover:text-red-600 transition-colors"><Trash2 size={15} /></button>
                    </div>
                  )}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default InlineList;
