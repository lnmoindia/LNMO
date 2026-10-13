import { useCallback, useEffect, useRef, useState } from "react";
import { User, Mail, School, BookOpen, GraduationCap, Crown, ClipboardList, Upload, Trash2, PenLine, ImageOff, Phone, ShieldCheck, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { errText } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

const API = process.env.REACT_APP_BACKEND_URL;

function DeliveryEmailDialog({ loginEmail, current, onClose, onSubmit }) {
  const [email, setEmail] = useState(current || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    setBusy(true); setErr("");
    try {
      const res = await onSubmit(email.trim().toLowerCase());
      if (res === null) setErr("Something went wrong — try again.");
      else if (res.sent === false) setErr(res.message || "Couldn't send a code to that address.");
    } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" data-testid="delivery-email-dialog">
      <div className="w-full max-w-md rounded-3xl bg-white dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-xl font-bold text-slate-900 dark:text-white">Where should we send your code?</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="delivery-email-close"><X size={18} /></button>
        </div>
        <p className="text-sm text-slate-500">Your login is <span className="font-medium">{loginEmail}</span>, which may not receive mail. Enter a personal email (e.g. you@gmail.com) to get your code there.</p>
        <Input type="email" value={email} onChange={(e) => { setEmail(e.target.value); setErr(""); }} placeholder="you@gmail.com" data-testid="delivery-email-input" />
        {err && <p className="text-sm text-red-600 dark:text-red-400" data-testid="delivery-email-error">{err}</p>}
        <Button className="w-full" disabled={busy || !email.includes("@")} onClick={submit} data-testid="delivery-email-submit">
          {busy ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={15} /> Sending…</span> : "Send code here"}
        </Button>
      </div>
    </div>
  );
}

function PhoneCard({ user, refresh }) {
  const [phone, setPhone] = useState(user?.phone || "");
  const [verified, setVerified] = useState(!!user?.phone_verified);
  const [stage, setStage] = useState("idle"); // idle | code
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sentTo, setSentTo] = useState("");
  const [showDelivery, setShowDelivery] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  useEffect(() => { setPhone(user?.phone || ""); setVerified(!!user?.phone_verified); }, [user]);
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setInterval(() => setCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  const doRequest = async (deliveryEmail) => {
    await api.post("/profile/phone", { phone });
    const body = { purpose: "phone_verify" };
    if (deliveryEmail) body.delivery_email = deliveryEmail;
    const r = await api.post("/verify/request", body);
    if (r.data.sent !== false) {
      setVerified(false); setStage("code"); setSentTo(r.data.sent_to || ""); setShowDelivery(false);
      setCode(""); setCooldown(60); refresh?.();
      toast.success(r.data.message);
    }
    return r.data;
  };
  const sendFlow = async (deliveryEmail) => {
    setBusy(true);
    try { const d = await doRequest(deliveryEmail); if (d.sent === false) toast.error(d.message); return d; }
    catch (err) { toast.error(errText(err)); return null; } finally { setBusy(false); }
  };
  const onVerifyClick = () => {
    if (!user?.personal_email) { setShowDelivery(true); return; }
    sendFlow();
  };
  const resend = () => { if (cooldown > 0 || busy) return; sendFlow(); };
  const confirmCode = useCallback(async (val) => {
    const c = (val ?? "").toString();
    setConfirming(true);
    try {
      await api.post("/verify/confirm", { purpose: "phone_verify", code: c });
      setVerified(true); setStage("idle"); setCode(""); refresh?.();
      toast.success("Phone verified");
    } catch (err) { toast.error(errText(err)); } finally { setConfirming(false); }
  }, [refresh]);
  useEffect(() => {
    if (stage === "code" && code.length === 6 && !confirming && !verified) confirmCode(code);
  }, [code, stage, confirming, verified, confirmCode]);

  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid="profile-phone-card">
      <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Phone size={15} className="text-indigo-600" /> Phone number</h2>
      <p className="text-xs text-slate-500 mt-1">We email a 6-digit code to {user?.personal_email || user?.email} to confirm your number. (SMS coming soon.)</p>
      <div className="flex flex-wrap items-center gap-2 mt-4">
        <Input value={phone} onChange={(e) => { setPhone(e.target.value); setVerified(false); setStage("idle"); }}
          placeholder="e.g. 9000000000" className="max-w-[200px]" data-testid="profile-phone-input" />
        {verified
          ? <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300" data-testid="profile-phone-verified-badge"><ShieldCheck size={13} /> Verified</span>
          : <Button type="button" size="sm" disabled={busy || !phone.trim()} onClick={onVerifyClick} data-testid="profile-phone-verify-btn">
              {busy ? <span className="inline-flex items-center gap-1.5"><Loader2 className="animate-spin" size={14} /> Sending…</span> : "Verify"}
            </Button>}
      </div>
      {stage === "code" && !verified && (
        <div className="mt-3" data-testid="profile-phone-code-row">
          <p className="text-xs text-slate-500 mb-2">Enter the 6-digit code sent to <span className="font-medium">{sentTo}</span>.</p>
          <div className="flex flex-wrap items-center gap-2">
            <Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="Enter code" maxLength={6} inputMode="numeric" className="max-w-[140px]" data-testid="profile-phone-code-input" />
            <Button type="button" size="sm" disabled={confirming || code.length < 4} onClick={() => confirmCode(code)} data-testid="profile-phone-code-submit">
              {confirming ? <span className="inline-flex items-center gap-1.5"><Loader2 className="animate-spin" size={14} /> Verifying…</span> : "Confirm"}
            </Button>
            <button type="button" className="text-xs text-indigo-600 underline disabled:text-slate-400 disabled:no-underline" disabled={cooldown > 0 || busy} onClick={resend} data-testid="profile-phone-resend">
              {cooldown > 0 ? `Resend in ${cooldown}s` : (busy ? "Sending…" : "Resend code")}
            </button>
            <button type="button" className="text-xs text-indigo-600 underline" disabled={busy} onClick={() => setShowDelivery(true)} data-testid="profile-phone-change-email">Use a different email</button>
          </div>
        </div>
      )}
      {!verified && stage === "idle" && (
        <button type="button" className="text-xs text-indigo-600 underline mt-2" onClick={() => setShowDelivery(true)} data-testid="profile-phone-use-other-email">Send code to a different email</button>
      )}
      {showDelivery && (
        <DeliveryEmailDialog loginEmail={user?.email} current={user?.personal_email || user?.email}
          onClose={() => setShowDelivery(false)}
          onSubmit={async (em) => await sendFlow(em)} />
      )}
    </div>
  );
}

function PersonalEmailCard({ user, refresh }) {
  const [email, setEmail] = useState(user?.personal_email || "");
  const [busy, setBusy] = useState(false);
  const verified = !!user?.personal_email_verified;
  useEffect(() => { setEmail(user?.personal_email || ""); }, [user]);
  const save = async () => {
    setBusy(true);
    try {
      await api.post("/profile/personal-email", { personal_email: email.trim().toLowerCase() });
      refresh?.();
      toast.success("Personal email saved — verify a phone to confirm it, or use it for OTP codes");
    } catch (err) { toast.error(errText(err)); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid="profile-personal-email-card">
      <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Mail size={15} className="text-indigo-600" /> Email addresses</h2>
      <div className="mt-4 space-y-3">
        <div>
          <label className="text-xs font-medium text-slate-400">Login email (read-only)</label>
          <Input value={user?.email || ""} disabled className="mt-1 bg-slate-50 dark:bg-slate-800/60" data-testid="profile-login-email" />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-400 flex items-center gap-2">Personal email
            {verified && <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-semibold" data-testid="personal-email-verified"><ShieldCheck size={12} /> Verified</span>}
          </label>
          <div className="flex flex-wrap items-center gap-2 mt-1">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@gmail.com" className="max-w-[240px]" data-testid="profile-personal-email-input" />
            <Button type="button" size="sm" variant="outline" disabled={busy || !email.includes("@") || email === user?.personal_email} onClick={save} data-testid="profile-personal-email-save">Save</Button>
          </div>
          <p className="text-xs text-slate-500 mt-1.5">OTP codes go here when set. Confirming any code sent to this address verifies it.</p>
        </div>
      </div>
    </div>
  );
}

function MediaCard({ title, desc, kind, uploadUrl, getUrl, has, onChange, accept = "image/png,image/jpeg,image/webp", contain }) {
  const fileRef = useRef(null);
  const [bust, setBust] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      await api.post(uploadUrl, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setBust(Date.now()); onChange(true); toast.success(`${title} updated`);
    } catch (err) { toast.error(errText(err)); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete(uploadUrl); onChange(false); toast.success(`${title} removed`); }
    catch (err) { toast.error(errText(err)); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5" data-testid={`profile-${kind}-card`}>
      <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2">{kind === "signature" ? <PenLine size={15} className="text-indigo-600" /> : <User size={15} className="text-indigo-600" />} {title}</h2>
      <p className="text-xs text-slate-500 mt-1">{desc}</p>
      <div className="flex items-center gap-4 mt-4">
        <div className={`h-20 w-20 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex items-center justify-center overflow-hidden shrink-0 ${kind === "photo" ? "rounded-full" : ""}`}>
          {has
            ? <img src={`${API}${getUrl}?t=${bust}`} alt={kind} className={`h-full w-full ${contain ? "object-contain" : "object-cover"}`} data-testid={`profile-${kind}-preview`} />
            : <ImageOff size={22} className="text-slate-300 dark:text-slate-600" />}
        </div>
        <div className="flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept={accept} className="hidden" onChange={upload} data-testid={`profile-${kind}-input`} />
          <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => fileRef.current?.click()} data-testid={`profile-${kind}-upload-btn`}>
            <Upload size={14} className="mr-1.5" /> {has ? "Replace" : "Upload"}
          </Button>
          {has && (
            <Button type="button" variant="outline" size="sm" disabled={busy} onClick={remove} className="text-red-600 hover:text-red-700" data-testid={`profile-${kind}-remove-btn`}>
              <Trash2 size={14} className="mr-1.5" /> Remove
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TeacherProfile() {
  const { user, refresh } = useAuth();
  const [data, setData] = useState(null);
  const [hasPhoto, setHasPhoto] = useState(false);
  const [hasSig, setHasSig] = useState(false);

  useEffect(() => {
    api.get("/teacher/profile").then((r) => setData(r.data)).catch(() => setData(null));
  }, []);
  useEffect(() => { setHasPhoto(!!user?.has_photo); setHasSig(!!user?.has_signature); }, [user]);

  if (!data) return <p className="text-sm text-slate-400 py-10 text-center">Loading…</p>;
  const u = data.user || {};
  const syncPhoto = (v) => { setHasPhoto(v); refresh?.(); };

  return (
    <div className="space-y-6" data-testid="teacher-profile">
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 flex items-center gap-5">
        <div className="h-16 w-16 rounded-full bg-indigo-600 flex items-center justify-center text-white shrink-0 overflow-hidden">
          {hasPhoto ? <img src={`${API}/api/users/${user.id}/photo`} alt="" className="h-full w-full object-cover" /> : <User size={28} />}
        </div>
        <div>
          <h1 className="font-heading text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-50" data-testid="teacher-profile-name">{u.name}</h1>
          <p className="text-sm text-slate-500 mt-0.5 flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center gap-1"><Mail size={13} /> {u.email}</span>
            <span className="inline-flex items-center gap-1"><School size={13} /> {data.institution_name}</span>
            {u.created_at && <span>· Joined {(u.created_at || "").slice(0, 10)}</span>}
          </p>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <MediaCard title="Profile photo" kind="photo" desc="JPG, PNG or WebP up to 4 MB. Shown across the app."
          uploadUrl="/profile/photo" getUrl={`/api/users/${user.id}/photo`} has={hasPhoto} onChange={syncPhoto} />
        <MediaCard title="Digital signature" kind="signature" desc="Used on report cards & certificates. Stored privately (vault) — never shown publicly. Up to 2 MB."
          uploadUrl="/profile/signature" getUrl="/api/profile/signature" has={hasSig} onChange={(v) => { setHasSig(v); refresh?.(); }} contain />
      </div>

      <PhoneCard user={user} refresh={refresh} />
      <PersonalEmailCard user={user} refresh={refresh} />

      <div className="grid sm:grid-cols-3 gap-4" data-testid="teacher-profile-stats">
        <Stat icon={ClipboardList} label="Teaching assignments" value={data.assignments.length} />
        <Stat icon={BookOpen} label="Subjects" value={data.subjects.length ? data.subjects.join(", ") : "—"} small />
        <Stat icon={GraduationCap} label="Students under me" value={data.total_students} />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid="teacher-profile-assignments">
          <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
            <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><BookOpen size={15} className="text-indigo-600" /> Teaching load</h2>
          </div>
          {data.assignments.length === 0 ? (
            <p className="px-5 py-6 text-sm text-slate-400">No teaching assignments yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {data.assignments.map((a) => (
                <li key={a.id} className="px-5 py-3 flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-700 dark:text-slate-200">{a.subject || "General"}</span>
                  <span className="text-slate-500">{a.class_name}{a.section ? ` · ${a.section}` : " · all sections"}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden" data-testid="teacher-profile-homerooms">
          <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
            <h2 className="font-heading text-base font-semibold text-slate-900 dark:text-slate-50 flex items-center gap-2"><Crown size={15} className="text-amber-500" /> Class teacher of</h2>
          </div>
          {data.homerooms.length === 0 ? (
            <p className="px-5 py-6 text-sm text-slate-400">You are not a class teacher of any section.</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {data.homerooms.map((h) => (
                <li key={h.id} className="px-5 py-3 flex items-center justify-between text-sm">
                  <span className="font-medium text-slate-700 dark:text-slate-200">{h.class_name} · Section {h.name}</span>
                  <span className="text-slate-500">{h.class_leader ? `Leader: ${h.class_leader}` : "No leader set"}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

const Stat = ({ icon: Icon, label, value, small }) => (
  <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
    <div className="flex items-center gap-2 text-slate-400 text-xs font-medium uppercase tracking-wide"><Icon size={13} /> {label}</div>
    <p className={`mt-2 font-heading font-bold text-slate-900 dark:text-slate-50 ${small ? "text-base" : "text-2xl"}`}>{value}</p>
  </div>
);
