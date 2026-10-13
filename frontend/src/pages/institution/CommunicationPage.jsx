import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Plus, AlertTriangle, Loader2, Link2, X, History, Send, Paperclip, ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import ComposeDialog from "../../components/comm/ComposeDialog";

const STATUS_CHIP = {
  delivered: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  sent: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  queued: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
  rejected: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  not_configured: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
};

export default function CommunicationPage() {
  const [status, setStatus] = useState(null);
  const [hist, setHist] = useState([]);
  const [showReq, setShowReq] = useState(false);
  const [showCompose, setShowCompose] = useState(false);

  const load = useCallback(() => {
    api.get("/comm/status").then((r) => setStatus(r.data)).catch((e) => toast.error(errText(e)));
    api.get("/comm/history").then((r) => setHist(r.data.messages)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const [dir, setDir] = useState("all");
  const [detail, setDetail] = useState(null);
  useEffect(() => {
    const q = dir === "all" ? "" : `?direction=${dir}`;
    api.get(`/comm/history${q}`).then((r) => setHist(r.data.messages)).catch(() => {});
  }, [dir]);

  const warn = status && (status.whatsapp.warn || status.sms.warn);

  return (
    <div className="space-y-6" data-testid="comm-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50 flex items-center gap-2"><MessageSquare className="text-emerald-600" size={24} /> Communication</h1>
          <p className="text-sm text-slate-500 mt-1">Your WhatsApp &amp; SMS connection, monthly message allowance and send history.</p>
        </div>
        <div className="flex items-center gap-2">
        <Button onClick={() => setShowReq(true)} variant="outline" data-testid="request-credit-btn"><Plus size={16} className="mr-1.5" /> Request more messages</Button>
        <Button onClick={() => setShowCompose(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="compose-open-btn"><Send size={16} className="mr-1.5" /> Send message</Button>
        </div>
      </div>

      {warn && (
        <div className="rounded-2xl border-2 border-amber-300 bg-amber-50 dark:bg-amber-500/10 dark:border-amber-500/40 px-4 py-3 flex items-center gap-2 text-sm text-amber-800 dark:text-amber-300" data-testid="comm-warning">
          <AlertTriangle size={16} /> You've used 80% or more of a monthly message allowance. Request more to avoid interruptions.
        </div>
      )}

      {status && (
        <>
          <div className="rounded-3xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-md" data-testid="comm-status-card">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${status.connection.connected ? "bg-emerald-500" : "bg-rose-500"}`} />
              <p className="font-heading font-semibold text-slate-900 dark:text-slate-50" data-testid="comm-connection-label">{status.connection.label}</p>
            </div>
            <div className="grid sm:grid-cols-2 gap-4 mt-4">
              <QuotaBar label="WhatsApp" data={status.whatsapp} disabled={!status.channels?.whatsapp_enabled} testid="quota-whatsapp" />
              <QuotaBar label="SMS" data={status.sms} disabled={!status.channels?.sms_enabled} testid="quota-sms" />
            </div>
            <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-3 flex items-center gap-1.5" data-testid="whatsapp-recommended-hint">
              <MessageSquare size={13} /> WhatsApp recommended — it's far cheaper to send than SMS, so your allowance goes much further.
            </p>
          </div>

          <div className="rounded-3xl border-2 border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-md overflow-hidden" data-testid="comm-history-card">
            <div className="px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
              <History size={16} className="text-emerald-600" />
              <h2 className="font-heading text-base font-bold text-slate-900 dark:text-slate-50">Message history</h2>
              <div className="ml-auto flex items-center gap-1" data-testid="history-direction-filter">
                {["all", "outbound", "inbound"].map((d) => (
                  <button key={d} onClick={() => setDir(d)} data-testid={`history-filter-${d}`}
                    className={`text-xs font-medium rounded-full px-2.5 py-1 capitalize transition-colors ${dir === d ? "bg-emerald-600 text-white" : "text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"}`}>{d}</button>
                ))}
              </div>
            </div>
            {hist.length === 0 ? <p className="px-5 py-6 text-sm text-slate-400">No messages here yet.</p> : (
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-400"><tr>
                  <th className="px-5 py-2">Contact</th><th className="px-3 py-2">Dir</th><th className="px-3 py-2">Channel</th><th className="px-3 py-2">Module</th><th className="px-3 py-2">When</th><th className="px-3 py-2">Status</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                  {hist.map((m) => (
                    <tr key={m.id} data-testid={`comm-msg-${m.id}`} onClick={() => setDetail(m)} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40">
                      <td className="px-5 py-2.5 text-slate-800 dark:text-slate-200">
                        {m.recipient_name || m.recipient_phone || m.from_phone}
                        {m.has_media && <span className="ml-1.5 inline-flex items-center text-[9px] font-bold uppercase rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300 px-1.5 py-0.5" data-testid={`media-badge-${m.id}`}><Paperclip size={9} className="mr-0.5" />media</span>}
                      </td>
                      <td className="px-3 py-2.5">{m.direction === "inbound" ? <ArrowDownLeft size={14} className="text-sky-500" /> : <ArrowUpRight size={14} className="text-emerald-500" />}</td>
                      <td className="px-3 py-2.5 capitalize">{m.channel}</td>
                      <td className="px-3 py-2.5 text-slate-500">{m.module}</td>
                      <td className="px-3 py-2.5 text-slate-400 text-xs">{String(m.created_at).slice(0, 16).replace("T", " ")}</td>
                      <td className="px-3 py-2.5"><span className={`text-[10px] font-bold uppercase rounded-full px-2 py-0.5 ${STATUS_CHIP[m.status] || STATUS_CHIP.queued}`}>{m.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {showReq && <RequestDialog onClose={() => setShowReq(false)} onDone={() => { setShowReq(false); load(); }} />}
      {showCompose && <ComposeDialog module="announcement" title="Send a message to parents" defaultCategory={null} onClose={() => setShowCompose(false)} onSent={load} />}
      {detail && <MessageDetail m={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function MessageDetail({ m, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="message-detail" onClick={onClose}>
      <div className="w-full max-w-md rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-lg font-bold text-slate-900 dark:text-white">Message detail</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="message-detail-close"><X size={18} /></button>
        </div>
        <div className="space-y-2 text-sm">
          <Row k="Direction" v={m.direction || "outbound"} />
          <Row k="Contact" v={m.recipient_name || m.recipient_phone || m.from_phone || "—"} />
          <Row k="Channel" v={m.channel} />
          <Row k="Module" v={m.module} />
          {m.has_media && <Row k="Media" v="attached (document)" />}
          <div>
            <p className="text-xs font-medium text-slate-400 mb-1">Body</p>
            <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2 text-slate-700 dark:text-slate-200 whitespace-pre-wrap" data-testid="message-detail-body">{m.body || "—"}</div>
          </div>
          {m.vars && Object.keys(m.vars).length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-400 mb-1">Variables</p>
              <div className="rounded-lg bg-slate-50 dark:bg-slate-800/60 px-3 py-2 text-xs font-mono text-slate-600 dark:text-slate-300 break-all">{JSON.stringify(m.vars)}</div>
            </div>
          )}
          <div>
            <p className="text-xs font-medium text-slate-400 mb-1">Status timeline</p>
            <ol className="space-y-1" data-testid="message-detail-timeline">
              {(m.status_history || []).map((h, i) => (
                <li key={i} className="flex items-center gap-2 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  <span className="font-medium capitalize text-slate-700 dark:text-slate-200">{h.status}</span>
                  <span className="text-slate-400 ml-auto">{String(h.at).slice(0, 19).replace("T", " ")}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
function Row({ k, v }) {
  return <div className="flex items-center justify-between gap-3"><span className="text-xs text-slate-400">{k}</span><span className="text-slate-700 dark:text-slate-200 capitalize">{v}</span></div>;
}

function QuotaBar({ label, data, disabled, testid }) {
  const pct = data.limit > 0 ? Math.min(100, Math.round((data.used / data.limit) * 100)) : 0;
  return (
    <div data-testid={testid}>
      <div className="flex items-center justify-between text-sm mb-1.5">
        <span className="font-medium text-slate-700 dark:text-slate-300">{label}{disabled && <span className="ml-2 text-[10px] uppercase text-amber-600">disabled</span>}</span>
        <span className="text-xs text-slate-500">{data.remaining} left · {data.used}/{data.limit}</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${data.warn ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function RequestDialog({ onClose, onDone }) {
  const [channel, setChannel] = useState("whatsapp");
  const [amount, setAmount] = useState("100");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    const n = parseInt(amount, 10);
    if (!n || n < 1) { toast.error("Enter how many extra messages you need"); return; }
    setBusy(true);
    try { await api.post("/comm/request-credit", { channel, amount: n, note }); toast.success("Request sent to LNMO"); onDone(); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="request-credit-dialog">
      <div className="w-full max-w-md rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2"><Link2 size={18} className="text-emerald-600" /> Request more messages</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        <label className="text-xs font-medium text-slate-400">Channel</label>
        <select className="w-full mt-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent px-3 py-2 text-sm" value={channel} onChange={(e) => setChannel(e.target.value)} data-testid="request-channel">
          <option value="whatsapp">WhatsApp</option><option value="sms">SMS</option>
        </select>
        <label className="text-xs font-medium text-slate-400 mt-3 block">Extra messages</label>
        <Input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} className="mt-1" data-testid="request-amount" />
        <Textarea placeholder="Reason (optional)" value={note} onChange={(e) => setNote(e.target.value)} className="mt-3" data-testid="request-note" />
        <Button className="w-full mt-4" onClick={submit} disabled={busy} data-testid="request-submit">{busy ? <Loader2 className="animate-spin" size={16} /> : "Send request"}</Button>
      </div>
    </div>
  );
}
