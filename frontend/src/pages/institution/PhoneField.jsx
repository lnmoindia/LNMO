import { useEffect, useState } from "react";
import { Input } from "../../components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../../components/ui/select";

const COUNTRIES = [
  { d: "+91", f: "🇮🇳", n: "India" },
  { d: "+1", f: "🇺🇸", n: "United States" },
  { d: "+44", f: "🇬🇧", n: "United Kingdom" },
  { d: "+971", f: "🇦🇪", n: "UAE" },
  { d: "+61", f: "🇦🇺", n: "Australia" },
  { d: "+65", f: "🇸🇬", n: "Singapore" },
  { d: "+60", f: "🇲🇾", n: "Malaysia" },
  { d: "+966", f: "🇸🇦", n: "Saudi Arabia" },
  { d: "+974", f: "🇶🇦", n: "Qatar" },
  { d: "+973", f: "🇧🇭", n: "Bahrain" },
  { d: "+968", f: "🇴🇲", n: "Oman" },
  { d: "+965", f: "🇰🇼", n: "Kuwait" },
  { d: "+92", f: "🇵🇰", n: "Pakistan" },
  { d: "+880", f: "🇧🇩", n: "Bangladesh" },
  { d: "+94", f: "🇱🇰", n: "Sri Lanka" },
  { d: "+977", f: "🇳🇵", n: "Nepal" },
  { d: "+64", f: "🇳🇿", n: "New Zealand" },
  { d: "+49", f: "🇩🇪", n: "Germany" },
  { d: "+33", f: "🇫🇷", n: "France" },
  { d: "+27", f: "🇿🇦", n: "South Africa" },
  { d: "+254", f: "🇰🇪", n: "Kenya" },
  { d: "+234", f: "🇳🇬", n: "Nigeria" },
];

export default function PhoneField({ value = "", onChange, testid }) {
  const [dial, setDial] = useState("+91");
  const [num, setNum] = useState("");

  useEffect(() => {
    const combined = num ? `${dial} ${num}`.trim() : "";
    if ((value || "") === combined) return;
    if (value && value.startsWith("+")) {
      const parts = value.split(" ");
      setDial(parts[0]); setNum(parts.slice(1).join(" "));
    } else { setNum(value || ""); }
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (d, n) => {
    setDial(d); setNum(n);
    onChange(n ? `${d} ${n}`.trim() : "");
  };

  return (
    <div className="flex gap-2">
      <Select value={dial} onValueChange={(v) => update(v, num)}>
        <SelectTrigger className="w-[110px] shrink-0" data-testid={`${testid}-code`}><SelectValue /></SelectTrigger>
        <SelectContent className="max-h-64">
          {COUNTRIES.map((c, i) => (
            <SelectItem key={`${c.d}-${i}`} value={c.d}>{c.f} {c.d}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        inputMode="numeric"
        value={num}
        onChange={(e) => update(dial, e.target.value.replace(/[^0-9]/g, ""))}
        placeholder="Phone number"
        data-testid={testid}
      />
    </div>
  );
}
