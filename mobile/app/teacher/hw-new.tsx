// Create homework / assignment for one of MY class-subject assignments, with photo / PDF / scanned attachments.
import { useState } from "react";
import { Text, View } from "react-native";
import { router } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useTeachingOptions } from "@/src/lib/queries";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { appendFile, kb, pickImage, pickPdf, type Picked } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Chip, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { DocumentScanner } from "@/src/scan/DocumentScanner";
import { addDaysISO, todayISO } from "@/src/lib/format";

export default function NewWork() {
  const opts = useTeachingOptions();
  const [kind, setKind] = useState<"homework" | "assignment">("homework");
  const [oi, setOi] = useState(0);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [due, setDue] = useState(addDaysISO(1));
  const [max, setMax] = useState("20");
  const [files, setFiles] = useState<Picked[]>([]);
  const [scan, setScan] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const qc = useQueryClient();
  const opt = opts.data?.[oi];
  const add = async (src: "library" | "camera" | "pdf") => {
    try { const f = src === "pdf" ? await pickPdf() : await pickImage(src); if (f) setFiles((v) => [...v, f].slice(0, 5)); } catch (e: any) { toast(e.message, "error"); }
  };
  const save = async () => {
    if (!opt || !title.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(due)) return toast("Pick a class, a title and a due date", "error");
    setBusy(true);
    try {
      const base = { class_name: opt.class_name, section: opt.section, subject: opt.subject, title: title.trim(), instructions: text, due_date: due };
      const d = kind === "homework" ? await api.post("/homework", base) : await api.post("/assignments", { ...base, max_marks: Number(max) || 20, counts_toward_report: false });
      const id = (d.homework || d.assignment || d).id;
      if (files.length) {
        const fd = new FormData();
        for (const f of files) await appendFile(fd, "files", f);
        await api.postForm(`/${kind === "homework" ? "homework" : "assignments"}/${id}/attachments`, fd);
        files.forEach((f) => { if (f.scanId) api.del(`/scan/files/${f.scanId}`).catch(() => {}); });
      }
      toast("Published to students"); qc.invalidateQueries({ queryKey: ["t-work"] });
      router.replace(`/teacher/hw/${kind}/${id}`);
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <StackScreen title="New homework" testID="thw-new-screen" keyboard>
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Chip label="Homework" active={kind === "homework"} onPress={() => setKind("homework")} testID="thw-kind-homework" />
        <Chip label="Assignment (marks)" active={kind === "assignment"} onPress={() => setKind("assignment")} testID="thw-kind-assignment" />
      </View>
      <Text style={k.label}>Class & subject (your assignments)</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {(opts.data || []).map((o: any, i: number) => <Chip key={i} label={`${o.class_name} ${o.section} · ${o.subject}`} active={oi === i} onPress={() => setOi(i)} testID={`thw-opt-${i}`} />)}
      </View>
      <TextField label="Title" value={title} onChangeText={setTitle} placeholder="e.g. Exercise 7.3 Q1–10" testID="thw-title-input" />
      <TextField label="Instructions" multiline value={text} onChangeText={setText} testID="thw-instructions-input" />
      <TextField label="Due date (YYYY-MM-DD)" value={due} onChangeText={setDue} autoCapitalize="none" testID="thw-due-input" />
      <View style={{ flexDirection: "row", gap: 8 }}>
        {[["Tomorrow", 1], ["In 2 days", 2], ["Next week", 7]].map(([l, n]) => <Chip key={l} label={String(l)} active={due === addDaysISO(Number(n))} onPress={() => setDue(addDaysISO(Number(n)))} />)}
      </View>
      {kind === "assignment" && <TextField label="Max marks" keyboardType="number-pad" value={max} onChangeText={setMax} testID="thw-max-input" />}
      <Card style={{ gap: 10 }}>
        <Text style={k.label}>Attachments (up to 5)</Text>
        <Button icon="maximize" label="Scan document" onPress={() => setScan(true)} testID="thw-scan-btn" />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button small variant="outline" icon="image" label="Photo" onPress={() => add("library")} style={{ flex: 1 }} testID="thw-add-photo" />
          <Button small variant="outline" icon="camera" label="Camera" onPress={() => add("camera")} style={{ flex: 1 }} />
          <Button small variant="outline" icon="file-text" label="PDF" onPress={() => add("pdf")} style={{ flex: 1 }} />
        </View>
        {files.map((f, i) => (
          <View key={i} style={{ flexDirection: "row", gap: 8, alignItems: "center" }} testID={`thw-file-${i}`}>
            <Text style={[k.label, { flex: 1 }]} numberOfLines={1}>{f.name}</Text><Text style={k.small}>{f.note || kb(f.size)}</Text>
            <Button small variant="ghost" label="Remove" onPress={() => setFiles((v) => v.filter((_, j) => j !== i))} />
          </View>
        ))}
      </Card>
      <DocumentScanner open={scan} onClose={() => setScan(false)} name={`Scan_${(opt?.subject || "work").replace(/\s+/g, "_")}_${todayISO()}.pdf`} onDone={(fs) => setFiles((v) => [...v, ...fs].slice(0, 5))} />
      <Button label={busy ? "Publishing…" : "Publish"} icon="send" onPress={save} loading={busy} testID="thw-publish-btn" />
    </StackScreen>
  );
}
