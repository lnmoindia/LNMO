import { Checkbox } from "../ui/checkbox";

export const CHANNELS = [["whatsapp", "WhatsApp"], ["sms", "SMS"], ["email", "Email"]];

// "All channels" + one checkbox per channel; value is an array, at least one required.
export function ChannelPicker({ value, onChange, prefix = "invite", note }) {
  const all = CHANNELS.every(([k]) => value.includes(k));
  const toggle = (k) => onChange(value.includes(k) ? value.filter((x) => x !== k) : [...value, k]);
  return (
    <div className="space-y-1.5" data-testid={`${prefix}-channel-picker`}>
      <div className="flex items-center gap-x-4 gap-y-2 flex-wrap text-sm">
        <span className="font-medium text-slate-700 dark:text-slate-200">Send via</span>
        <label className="flex items-center gap-1.5 cursor-pointer font-medium">
          <Checkbox checked={all} onCheckedChange={(v) => onChange(v ? CHANNELS.map(([k]) => k) : ["whatsapp"])} data-testid={`${prefix}-channel-all`} /> All channels
        </label>
        {CHANNELS.map(([k, l]) => (
          <label key={k} className="flex items-center gap-1.5 cursor-pointer">
            <Checkbox checked={value.includes(k)} onCheckedChange={() => toggle(k)} data-testid={`${prefix}-channel-${k}`} /> {l}
          </label>
        ))}
      </div>
      {value.length === 0 && <p className="text-xs text-rose-600" data-testid={`${prefix}-channel-error`}>Pick at least one channel.</p>}
      <p className="text-[11px] text-slate-500">{note || "Parents without an email or phone are skipped for that channel and listed in the results. WhatsApp/SMS use your message quota; email doesn't."}</p>
    </div>
  );
}

const LABEL = { sent: "sent", failed: "failed", skipped_no_email: "no email", skipped_no_phone: "no phone", quota_exceeded: "quota" };
export const ChannelResults = ({ channels, testid }) => !channels ? null : (
  <span className="inline-flex flex-wrap gap-1 ml-1" data-testid={testid}>
    {CHANNELS.filter(([k]) => channels[k]).map(([k, l]) => (
      <span key={k} className={`rounded px-1.5 py-px text-[10px] font-semibold ${channels[k] === "sent" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" : channels[k] === "failed" ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}
        title={k === "email" && channels.email_message_id ? `Resend id ${channels.email_message_id}` : undefined}>
        {l}: {LABEL[channels[k]] || channels[k]}
      </span>
    ))}
  </span>
);
