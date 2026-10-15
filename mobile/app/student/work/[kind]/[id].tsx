// Homework / assignment detail + submission (note and/or up to 5 photos/PDFs).
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Image } from "expo-image";
import { Feather } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useMyAssignments, useMyHomework } from "@/src/lib/queries";
import { api } from "@/src/lib/api";
import { MAX_BYTES, appendFile, kb, openAuthedFile, pickImage, pickPdf, type Picked } from "@/src/lib/files";
import { DocumentScanner } from "@/src/scan/DocumentScanner";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, SkeletonList, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { dueOf, isPending, workBadge } from "@/src/student/work";
import { fmtDate, fmtDateTime, todayISO } from "@/src/lib/format";
import { fonts } from "@/src/theme";

function FileLink({ name, onPress, testID }: { name: string; onPress: () => void; testID: string }) {
  const b = useBrand();
  return (
    <Pressable onPress={onPress} style={s.file} testID={testID}>
      <Feather name="paperclip" size={15} color={b.ink} /><Text style={[s.fileText, { color: b.ink }]} numberOfLines={1}>{name}</Text><Feather name="download" size={15} color={b.ink} />
    </Pressable>
  );
}

export default function WorkDetail() {
  const { kind, id } = useLocalSearchParams<{ kind: "homework" | "assignment"; id: string }>();
  const hw = useMyHomework();
  const asg = useMyAssignments();
  const q = kind === "assignment" ? asg : hw;
  const x = (q.data || []).find((i: any) => i.id === id);
  const toast = useToast();
  const base = kind === "assignment" ? "/assignments/attachment" : "/homework/attachment";
  const open = (path: string, a: any) => openAuthedFile(path, a.name || "attachment", a.content_type || "application/octet-stream").catch((e) => toast(e.message, "error"));
  if (q.isLoading) return <StackScreen title="Homework" testID="work-detail-screen"><SkeletonList n={2} height={140} /></StackScreen>;
  if (!x) return <StackScreen title="Homework" testID="work-detail-screen"><Card><Empty icon="file" text="This item isn't available any more." /></Card></StackScreen>;
  const sub = x.my_submission;
  const [label, bg, fg] = workBadge(x);
  const overdue = isPending(x) && dueOf(x) && dueOf(x) < todayISO();
  return (
    <StackScreen title={kind === "assignment" ? "Assignment" : "Homework"} testID="work-detail-screen" keyboard>
      <Card style={{ gap: 8 }} testID="work-detail-card">
        <View style={s.row}><Text style={s.subject}>{x.subject}</Text><View style={[s.badge, { backgroundColor: bg }]}><Text style={[s.badgeText, { color: fg }]} testID="work-status">{label}</Text></View></View>
        <Text style={k.h2} testID="work-title">{x.title}</Text>
        <Text style={[k.small, overdue && { color: C.error, fontFamily: fonts.bodySemi }]}>Due {fmtDate(x.due_date, { weekday: true })}{x.max_marks ? ` · ${x.max_marks} marks` : ""}{x.status === "closed" ? " · closed" : ""}</Text>
        {x.teacher_name ? <Text style={k.small}>Set by {x.teacher_name}</Text> : null}
        {x.instructions ? <Text style={[k.body, { marginTop: 4 }]} testID="work-instructions">{x.instructions}</Text> : null}
        {(x.attachments || []).map((a: any, i: number) => <FileLink key={i} name={a.name} onPress={() => open(`${base}/${x.id}/${i}?kind=${kind}`, a)} testID={`work-file-${i}`} />)}
      </Card>
      {sub && (
        <Card style={{ gap: 6 }} testID="work-my-submission">
          <Text style={s.cardTitle}>Your submission</Text>
          <Text style={k.small}>{sub.submitted_at ? `Sent ${fmtDateTime(sub.submitted_at)}` : "Submitted"}{sub.late ? " · late" : ""}</Text>
          {sub.note ? <Text style={k.body}>{sub.note}</Text> : null}
          {sub.marks != null ? <Text style={k.label}>Marks: {sub.marks}{x.max_marks ? ` / ${x.max_marks}` : ""}</Text> : null}
          {sub.feedback ? <Text style={[k.body, { color: C.warning }]} testID="work-feedback">Teacher: {sub.feedback}</Text> : null}
          {(sub.attachments || []).map((a: any, i: number) => <FileLink key={i} name={a.name} onPress={() => open(`${base}/${sub.id}/${i}?kind=submission`, a)} testID={`work-sub-file-${i}`} />)}
        </Card>
      )}
      {isPending(x) && <SubmitForm kind={kind} id={x.id} redo={sub?.status === "redo"} subject={x.subject} />}
    </StackScreen>
  );
}

function SubmitForm({ kind, id, redo, subject }: { kind: string; id: string; redo: boolean; subject: string }) {
  const [scan, setScan] = useState(false);
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<Picked[]>([]);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const qc = useQueryClient();
  const add = async (src: "library" | "camera" | "pdf") => {
    try {
      const f = src === "pdf" ? await pickPdf() : await pickImage(src);
      if (!f) return;
      if (f.size && f.size > MAX_BYTES) return toast("Each file must be 5 MB or smaller", "error");
      setFiles((v) => [...v, f].slice(0, 5));
    } catch (e: any) { toast(e.message, "error"); }
  };
  const submit = async () => {
    if (!files.length && !note.trim()) return toast("Attach a file or add a note", "error");
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("note", note);
      for (const f of files) await appendFile(fd, "files", f);
      const d = await api.postForm(`/${kind === "assignment" ? "assignments" : "homework"}/${id}/submit`, fd);
      toast(d?.message || "Submitted!");
      files.forEach((f) => { if (f.scanId) api.del(`/scan/files/${f.scanId}`).catch(() => {}); });
      setNote(""); setFiles([]);
      await qc.invalidateQueries({ queryKey: [kind === "assignment" ? "s-asg" : "s-hw"] });
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <Card style={{ gap: 12 }} testID="work-submit-form">
      <Text style={s.cardTitle}>{redo ? "Submit again" : "Hand it in"}</Text>
      <TextField label="Note (optional)" multiline value={note} onChangeText={setNote} placeholder="Anything to tell your teacher…" testID="work-note-input" />
      <Button icon="maximize" label="Scan document" onPress={() => setScan(true)} testID="work-scan-btn" />
      <DocumentScanner open={scan} onClose={() => setScan(false)} name={`Scan_${(subject || "work").replace(/\s+/g, "_")}_${todayISO()}.pdf`}
        onDone={(fs) => {
          const ok = fs.filter((f) => !f.size || f.size <= MAX_BYTES * 2);
          if (ok.length < fs.length) toast("The scan is larger than 10 MB — remove a page or use the Original filter less", "error");
          setFiles((v) => [...v, ...ok].slice(0, 5));
        }} />
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Button small variant="outline" icon="image" label="Photo" onPress={() => add("library")} style={{ flex: 1 }} testID="work-add-photo" />
        <Button small variant="outline" icon="camera" label="Camera" onPress={() => add("camera")} style={{ flex: 1 }} testID="work-add-camera" />
        <Button small variant="outline" icon="file-text" label="PDF" onPress={() => add("pdf")} style={{ flex: 1 }} testID="work-add-pdf" />
      </View>
      {files.map((f, i) => (
        <View key={i} style={s.picked} testID={`work-picked-${i}`}>
          {f.type.startsWith("image/") ? <Image source={{ uri: f.uri }} style={s.thumb} /> : <Feather name="file-text" size={22} color={C.muted} />}
          <View style={{ flex: 1 }}><Text style={k.label} numberOfLines={1}>{f.name}</Text><Text style={k.small}>{f.note || kb(f.size)}</Text></View>
          <Pressable onPress={() => setFiles((v) => v.filter((_, j) => j !== i))} hitSlop={10} testID={`work-remove-${i}`}><Feather name="x" size={18} color={C.muted} /></Pressable>
        </View>
      ))}
      <Text style={k.small}>Up to 5 files · images or PDF · max 5 MB each</Text>
      <Button label={busy ? "Submitting…" : "Submit"} icon="check" variant="success" onPress={submit} loading={busy} disabled={!files.length && !note.trim()} testID="work-submit-btn" />
    </Card>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  subject: { flex: 1, fontFamily: fonts.bodyBold, fontSize: 12, color: C.muted, textTransform: "uppercase", letterSpacing: 0.6 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  badgeText: { fontFamily: fonts.bodyBold, fontSize: 12 },
  cardTitle: { fontFamily: fonts.headingSemi, fontSize: 17, color: C.onSurface },
  file: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 44, paddingHorizontal: 12, borderRadius: 12, backgroundColor: C.surfaceTertiary },
  fileText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14 },
  picked: { flexDirection: "row", alignItems: "center", gap: 10, padding: 8, borderRadius: 12, borderWidth: 1, borderColor: C.border },
  thumb: { width: 40, height: 40, borderRadius: 8, backgroundColor: C.surfaceTertiary },
});
