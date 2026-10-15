// Tiny Markdown renderer for AI Tutor answers: headings, bold/italic, inline code, code blocks,
// bullet + numbered lists, simple tables and rules. Stray "**" never shows as raw text.
import { Fragment } from "react";
import { Platform, StyleSheet, Text, View } from "react-native";
import { fonts } from "@/src/theme";
import { C } from "./kit";

const MONO = Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" });
const INLINE = /(\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+`|\*[^*\s][^*\n]*?\*|_[^_\s][^_\n]*?_)/g;

function Inline({ text, color }: { text: string; color: string }) {
  const parts = text.split(INLINE).filter((x) => x !== "");
  return (
    <>
      {parts.map((p, i) => {
        if ((p.startsWith("**") && p.endsWith("**")) || (p.startsWith("__") && p.endsWith("__"))) return <Text key={i} style={{ fontFamily: fonts.bodyBold, color }}>{p.slice(2, -2)}</Text>;
        if (p.startsWith("`") && p.endsWith("`")) return <Text key={i} style={m.codeInline}>{p.slice(1, -1)}</Text>;
        if (p.length > 2 && ((p.startsWith("*") && p.endsWith("*")) || (p.startsWith("_") && p.endsWith("_")))) return <Text key={i} style={{ fontStyle: "italic", color }}>{p.slice(1, -1)}</Text>;
        return <Fragment key={i}>{p.replace(/\*\*|__/g, "")}</Fragment>;
      })}
    </>
  );
}

type Block = { t: "p" | "h" | "li" | "ol" | "code" | "hr" | "row"; text: string; n?: string; level?: number; indent?: number };

// LaTeX the model sometimes emits ($g/cm^3$, $$\frac{a}{b}$$) → readable plain text.
const SUP: Record<string, string> = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻", "+": "⁺" };
const SYM: Record<string, string> = { times: "×", div: "÷", cdot: "·", pm: "±", approx: "≈", le: "≤", leq: "≤", ge: "≥", geq: "≥", neq: "≠", rightarrow: "→", to: "→", leftarrow: "←", degree: "°", circ: "°", pi: "π", theta: "θ", alpha: "α", beta: "β", lambda: "λ", mu: "µ", Delta: "Δ", infty: "∞", quad: " ", ",": " " };
const tex = (m: string) => {
  let t = m;
  for (let i = 0; i < 3; i++) t = t.replace(/\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}/g, "($1) / ($2)").replace(/\\(?:text|mathrm|mathbf|textbf|operatorname)\{([^{}]*)\}/g, "$1");
  t = t.replace(/\\sqrt\{([^{}]*)\}/g, "√($1)").replace(/\\([a-zA-Z]+|,)/g, (_, n) => SYM[n] ?? n);
  t = t.replace(/\^\{?([0-9+-]+)\}?/g, (_, d) => d.split("").map((c: string) => SUP[c] || c).join("")).replace(/_\{([^{}]*)\}/g, "$1");
  return t.replace(/\(([^()\s]+)\) \/ \(([^()\s]+)\)/g, "$1 / $2").replace(/[{}]/g, "").replace(/\s{2,}/g, " ").trim();
};
export const cleanMath = (src: string) =>
  src.replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => tex(m)).replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => tex(m))
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => tex(m)).replace(/\$(\S[^$\n]*?\S|\S)\$/g, (all, m) => (/[\\^_{}=]/.test(m) || /^[a-zA-Z]$/.test(m) ? tex(m) : all));

function parse(src: string): Block[] {
  const out: Block[] = [];
  const lines = cleanMath(String(src || "")).replace(/\r\n/g, "\n").split("\n");
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    if (/^\s*```/.test(raw)) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]);
      out.push({ t: "code", text: buf.join("\n") });
      continue;
    }
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) { out.push({ t: "p", text: "" }); continue; }
    let mm;
    if ((mm = line.match(/^\s*(#{1,6})\s+(.*)$/))) out.push({ t: "h", text: mm[2].replace(/#+\s*$/, ""), level: mm[1].length });
    else if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) out.push({ t: "hr", text: "" });
    else if ((mm = line.match(/^(\s*)[-*•+]\s+(.*)$/))) out.push({ t: "li", text: mm[2], indent: Math.min(3, Math.floor(mm[1].length / 2)) });
    else if ((mm = line.match(/^(\s*)(\d+)[.)]\s+(.*)$/))) out.push({ t: "ol", text: mm[3], n: mm[2], indent: Math.min(3, Math.floor(mm[1].length / 2)) });
    else if (/^\s*\|.*\|\s*$/.test(line)) {
      if (!/^\s*\|[\s:|-]+\|\s*$/.test(line)) out.push({ t: "row", text: line.trim().slice(1, -1).split("|").map((c) => c.trim()).join("   ·   ") });
    } else out.push({ t: "p", text: line.trim() });
  }
  return out;
}

export function Markdown({ text, color = C.onSurface, testID }: { text: string; color?: string; testID?: string }) {
  const blocks = parse(text);
  return (
    <View style={{ gap: 6 }} testID={testID}>
      {blocks.map((b, i) => {
        if (b.t === "p") return b.text ? <Text key={i} style={[m.p, { color }]}><Inline text={b.text} color={color} /></Text> : <View key={i} style={{ height: 2 }} />;
        if (b.t === "h") return <Text key={i} style={[m.h, { color, fontSize: b.level === 1 ? 19 : b.level === 2 ? 17 : 16 }]}><Inline text={b.text} color={color} /></Text>;
        if (b.t === "hr") return <View key={i} style={m.hr} />;
        if (b.t === "code") return <View key={i} style={m.codeBlock}><Text style={m.codeText} selectable>{b.text}</Text></View>;
        if (b.t === "row") return <Text key={i} style={[m.p, { color }]}><Inline text={b.text} color={color} /></Text>;
        return (
          <View key={i} style={[m.li, { paddingLeft: (b.indent || 0) * 16 }]}>
            <Text style={[m.bullet, { color }]}>{b.t === "ol" ? `${b.n}.` : "•"}</Text>
            <Text style={[m.p, { color, flex: 1 }]}><Inline text={b.text} color={color} /></Text>
          </View>
        );
      })}
    </View>
  );
}

const m = StyleSheet.create({
  p: { fontFamily: fonts.body, fontSize: 16, lineHeight: 23 },
  h: { fontFamily: fonts.heading, marginTop: 4 },
  li: { flexDirection: "row", gap: 8 },
  bullet: { fontFamily: fonts.bodyBold, fontSize: 16, lineHeight: 23, minWidth: 14 },
  hr: { height: 1, backgroundColor: C.border, marginVertical: 6 },
  codeInline: { fontFamily: MONO, fontSize: 14, backgroundColor: "#E9EDF2", color: "#0F172A" },
  codeBlock: { backgroundColor: "#0F172A", borderRadius: 12, padding: 12 },
  codeText: { fontFamily: MONO, fontSize: 13, color: "#E2E8F0", lineHeight: 19 },
});
