// Support / Report an issue → POST /support/issues (same fields as the web dialog).
import { useState } from "react";
import { Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { appendFile, type Picked } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Chip, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { PhotoPicker } from "@/src/ui/PhotoPicker";

const CATS: [string, string][] = [["bug", "Something is broken"], ["question", "I need help"], ["suggestion", "An idea"]];

export default function Support() {
  const toast = useToast();
  const pre = useLocalSearchParams<{ title?: string; desc?: string }>(); // prefilled e.g. from an offline sync rejection
  const [category, setCategory] = useState("question");
  const [title, setTitle] = useState(pre.title || "");
  const [desc, setDesc] = useState(pre.desc || "");
  const [file, setFile] = useState<Picked | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("title", title.trim()); fd.append("description", desc.trim()); fd.append("category", category);
      fd.append("page_url", "lnmo-mobile://parent/support"); fd.append("route", "/more/support");
      if (file) await appendFile(fd, "screenshot", file);
      const d = await api.postForm("/support/issues", fd);
      toast(`Thanks! Ticket #${String(d.id).slice(0, 8)} created`);
      router.back();
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <StackScreen title="Support" testID="support-screen" keyboard>
      <Card><Text style={k.body}>{"Something not working, or a question about fees, attendance or results? Send it to the school and they'll get back to you."}</Text></Card>
      <View style={{ gap: 8 }}>
        <Text style={k.label}>Category</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {CATS.map(([v, l]) => <Chip key={v} label={l} active={category === v} onPress={() => setCategory(v)} testID={`support-category-${v}`} />)}
        </View>
      </View>
      <TextField label="Title" value={title} onChangeText={setTitle} placeholder="Short summary" testID="support-title-input" />
      <TextField label="What happened?" multiline value={desc} onChangeText={setDesc} placeholder="Steps, what you expected, what you saw…" testID="support-description-input" />
      <PhotoPicker file={file} setFile={setFile} testID="support-screenshot" label="Screenshot (optional)" />
      <Button label={busy ? "Sending…" : "Report an issue"} icon="send" onPress={submit} loading={busy} disabled={!title.trim()} testID="support-submit-btn" />
    </StackScreen>
  );
}
