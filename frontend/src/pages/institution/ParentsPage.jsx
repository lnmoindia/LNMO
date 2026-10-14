import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Search, Users2, ChevronLeft, ChevronRight, Phone, Mail } from "lucide-react";
import api, { errText } from "../../lib/api";
import { Input } from "../../components/ui/input";
import { Button } from "../../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";

export const staffBase = (pathname) => (pathname.startsWith("/teacher") ? "/teacher" : "/app");
const STATUS = { linked: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400", invited: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400", not_invited: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400" };
const LABEL = { linked: "Linked", invited: "Invited", not_invited: "Not invited" };
export const StatusPill = ({ s }) => <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${STATUS[s]}`} data-testid={`parent-status-${s}`}>{LABEL[s]}</span>;

export default function ParentsPage() {
  const { pathname } = useLocation();
  const base = staffBase(pathname);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [cls, setCls] = useState("all");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => { const t = setTimeout(() => { setSearch(q); setPage(1); }, 300); return () => clearTimeout(t); }, [q]);
  useEffect(() => {
    const [class_name, section] = cls === "all" ? ["", ""] : cls.split("||");
    api.get("/parents", { params: { search, class_name, section, status: status === "all" ? "" : status, page, limit: 25 } })
      .then((r) => setD(r.data)).catch((e) => setErr(errText(e)));
  }, [search, cls, status, page]);
  const classOpts = useMemo(() => {
    const out = [];
    const seen = new Set();
    (d?.classes || []).forEach((c) => {
      if (!seen.has(c.class_name)) { seen.add(c.class_name); out.push([`${c.class_name}||`, c.class_name]); }
      if (c.section) out.push([`${c.class_name}||${c.section}`, `${c.class_name} · ${c.section}`]);
    });
    return out;
  }, [d?.classes]);

  if (err) return <p className="py-16 text-center text-slate-400" data-testid="parents-error">{err}</p>;
  return (
    <div className="space-y-6" data-testid="parents-page">
      <div>
        <h1 className="font-heading text-3xl font-bold text-slate-900 dark:text-slate-50">Parents</h1>
        <p className="text-sm text-slate-500 mt-1">{d?.can_edit ? "Every parent and guardian at your school." : "Parents of the students in your classes (view only)."}</p>
      </div>
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, phone, email or child…" className="pl-9" data-testid="parents-search" />
        </div>
        <Select value={cls} onValueChange={(v) => { setCls(v); setPage(1); }}>
          <SelectTrigger className="w-48" data-testid="parents-class-filter"><SelectValue placeholder="All classes" /></SelectTrigger>
          <SelectContent><SelectItem value="all">All classes</SelectItem>{classOpts.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
          <SelectTrigger className="w-44" data-testid="parents-status-filter"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any status</SelectItem><SelectItem value="linked">Linked</SelectItem>
            <SelectItem value="invited">Invited</SelectItem><SelectItem value="not_invited">Not invited</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="parents-table">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-5 py-3">Parent</th><th className="px-5 py-3">Contact</th><th className="px-5 py-3">Children</th><th className="px-5 py-3">Onboarding</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {!d && <tr><td colSpan={4} className="px-5 py-10 text-center text-slate-400">Loading…</td></tr>}
              {d?.items.length === 0 && <tr><td colSpan={4} className="px-5 py-12 text-center text-slate-400"><Users2 className="mx-auto mb-2" />No parents match.</td></tr>}
              {d?.items.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40" data-testid={`parent-row-${p.id}`}>
                  <td className="px-5 py-3 font-medium text-slate-800 dark:text-slate-100">
                    {p.type === "parent" ? <Link to={`${base}/parents/${p.id}`} className="text-indigo-700 dark:text-indigo-400 hover:underline" data-testid={`parent-link-${p.id}`}>{p.name}</Link> : <span>{p.name} <span className="text-xs text-slate-400 font-normal">(no account)</span></span>}
                    {p.relation && <span className="ml-1.5 text-xs text-slate-400 capitalize">{p.relation}</span>}
                  </td>
                  <td className="px-5 py-3 text-slate-600 dark:text-slate-300">
                    {p.phone && <p className="flex items-center gap-1"><Phone size={12} className="text-slate-400" />{p.phone}</p>}
                    {p.email && <p className="flex items-center gap-1 text-xs"><Mail size={12} className="text-slate-400" />{p.email}</p>}
                    {!p.phone && !p.email && <span className="text-slate-400">—</span>}
                  </td>
                  <td className="px-5 py-3">
                    {p.children.map((c) => (
                      <Link key={c.id} to={base === "/app" ? `/app/students/${c.id}` : `${base}/students`} className="block text-slate-700 dark:text-slate-200 hover:text-indigo-600" data-testid={`parent-child-link-${c.id}`}>
                        {c.name} <span className="text-xs text-slate-400">{c.class_name}{c.section ? ` ${c.section}` : ""}</span>
                      </Link>
                    ))}
                  </td>
                  <td className="px-5 py-3"><StatusPill s={p.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {d && d.pages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-200 dark:border-slate-800 text-sm text-slate-500">
            <span data-testid="parents-total">{d.total} total</span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="parents-prev"><ChevronLeft size={14} /></Button>
              <span data-testid="parents-page-num">{d.page} / {d.pages}</span>
              <Button size="sm" variant="outline" disabled={page >= d.pages} onClick={() => setPage(page + 1)} data-testid="parents-next"><ChevronRight size={14} /></Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
