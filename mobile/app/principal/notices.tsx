// Notices: list + create (audience: my divisions / one or more classes in scope) with a photo / PDF / scanned attachment.
import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { useToast } from "@/src/state/toast";
import { useAuth } from "@/src/state/auth";
import { usePSections } from "@/src/principal/hooks";
import { appendFile, pickImage, pickPdf, type Picked } from "@/src/lib/files";
import { DocumentScanner } from "@/src/scan/DocumentScanner";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Chip, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { Sheet, confirm } from "@/src/ui/brandbits";
import { TextField } from "@/src/ui/inputs";
import { fmtDateTime } from "@/src/lib/format";

function Compose({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const sec = usePSections();
  const [title, setTitle] = useState(""); const [body, setBody] = useState(""); const [cls, setCls] = useState<string[]>([]);
  const [file, setFile] = useState<Picked | null>(null); const [scan, setScan] = useState(false); const [busy, setBusy] = useState(false);
  const dirty = Boolean(title || body || file);
  const close = async () => { if (!dirty || (await confirm("Discard notice?", "Your draft will be lost.", "Discard"))) { setTitle(""); setBody(""); setCls([]); setFile(null); onClose(); } };
  const post = async () => {
    setBusy(true);
    try {
      const target = cls.length ? { scope: "classes", classes: cls.map((x) => { const [c, s] = x.split("|"); return { class_name: c, section: s }; }) } : { scope: "school" };
      const r = await api.post("/notices", { title: title.trim(), body: body.trim(), target, status: "published" });
      const nid = (r.notice || r).id;
      if (file && nid) { const fd = new FormData(); await appendFile(fd, "file", file); await api.postForm(`/notices/${nid}/attachments`, fd); }
      toast("Notice published"); setTitle(""); setBody(""); setCls([]); setFile(null); onDone(); onClose();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <Sheet open={open} onClose={close} title="New notice" testID="pnotice-compose">
      <ScrollView style={{ maxHeight: 600 }} contentContainerStyle={{ gap: 10 }} keyboardShouldPersistTaps="handled">
        <TextField label="Title" value={title} onChangeText={setTitle} testID="pnotice-title" />
        <TextField label="Message" value={body} onChangeText={setBody} multiline testID="pnotice-body" />
        <Text style={k.label}>Audience</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          <Chip label="All my divisions" active={!cls.length} onPress={() => setCls([])} testID="pnotice-aud-all" />
          {(sec.data || []).map(([c, s]) => { const v = `${c}|${s}`; return <Chip key={v} label={`${c} ${s}`} active={cls.includes(v)} onPress={() => setCls((a) => (a.includes(v) ? a.filter((x) => x !== v) : [...a, v]))} testID={`pnotice-aud-${c}-${s}`.replace(/\s/g, "")} />; })}
        </View>
        <Text style={k.small}>Students and parents of the chosen classes see it (plus staff).</Text>
        {file ? <Button variant="outline" icon="paperclip" label={`${file.name} — remove`} onPress={() => setFile(null)} testID="pnotice-file" /> : (
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Button small variant="outline" icon="image" label="Photo" onPress={async () => setFile(await pickImage("library"))} style={{ flex: 1 }} testID="pnotice-photo" />
            <Button small variant="outline" icon="file" label="PDF" onPress={async () => setFile(await pickPdf())} style={{ flex: 1 }} testID="pnotice-pdf" />
            <Button small variant="outline" icon="camera" label="Scan" onPress={() => setScan(true)} style={{ flex: 1 }} testID="pnotice-scan" />
          </View>
        )}
        <Button icon="send" label="Publish" loading={busy} disabled={!title.trim()} onPress={post} testID="pnotice-publish" />
      </ScrollView>
      {scan && <DocumentScanner open={scan} name="notice" onClose={() => setScan(false)} onDone={(files: Picked[]) => { if (files[0]) setFile(files[0]); setScan(false); }} />}
    </Sheet>
  );
}

export default function PNotices() {
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["p-notices"], queryFn: async () => (await api.get("/notices")).notices || [] });
  const [open, setOpen] = useState(false);
  const del = async (n: any) => {
    if (!(await confirm("Delete notice?", `“${n.title}” is removed for everyone.`, "Delete"))) return;
    try { await api.del(`/notices/${n.id}`); toast("Notice deleted"); qc.invalidateQueries({ queryKey: ["p-notices"] }); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <StackScreen title="Notices" testID="principal-notices-screen">
      <Button icon="plus" label="New notice" onPress={() => setOpen(true)} testID="pnotice-new-btn" />
      {q.isLoading ? <SkeletonList n={3} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : !q.data.length ? <Card><Empty icon="bell" text="No notices yet." /></Card> : q.data.map((n: any) => (
        <Card key={n.id} style={{ gap: 6 }} testID={`pnotice-${n.id}`}>
          <Text style={k.label}>{n.title}</Text>
          {n.body ? <Text style={k.small} numberOfLines={3}>{n.body}</Text> : null}
          <Text style={k.small}>{n.author_name} · {fmtDateTime(n.created_at)} · {n.target?.scope === "classes" ? (n.target.classes || []).map((c: any) => `${c.class_name} ${c.section || ""}`).join(", ") : "All"}{n.attachment_count ? ` · ${n.attachment_count} file` : ""}</Text>
          {n.author_id === user?.id ? <Button small variant="ghost" icon="trash-2" label="Delete" onPress={() => del(n)} testID={`pnotice-delete-${n.id}`} /> : null}
        </Card>
      ))}
      <Compose open={open} onClose={() => setOpen(false)} onDone={() => qc.invalidateQueries({ queryKey: ["p-notices"] })} />
    </StackScreen>
  );
}
