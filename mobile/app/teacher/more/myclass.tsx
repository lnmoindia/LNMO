// My class (class teacher): student list → detail with parents + Call / Message / Email.
import { useState } from "react";
import { Linking, Text, View } from "react-native";
import { router } from "expo-router";
import { useMyClass, useSection } from "@/src/lib/queries";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Divider, Empty, Field, ListRow, SkeletonList, k } from "@/src/ui/kit";
import { Sheet } from "@/src/ui/brandbits";
import { TextField } from "@/src/ui/inputs";
import { fmtDate, fullName } from "@/src/lib/format";

export default function MyClass() {
  const homes = useMyClass();
  const h = homes.data?.[0];
  const q = useSection(h?.id || "");
  const [st, setSt] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const startChat = async () => {
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("student_id", st.id); fd.append("body", msg); fd.append("target", "class_teacher");
      const d = await api.postForm("/chat/threads", fd);
      setSt(null); setMsg(""); router.push(`/thread/${d.thread.id}`);
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  if (!homes.isLoading && !h) return <StackScreen title="My class" testID="teacher-myclass-screen"><Card><Empty icon="users" text="You're not a class teacher this year." /></Card></StackScreen>;
  return (
    <StackScreen title={h ? `My class · ${h.class_name} ${h.name}` : "My class"} testID="teacher-myclass-screen">
      {q.isLoading || !h ? <SkeletonList n={4} height={60} /> : (
        <>
          <Text style={k.small}>{q.data.students.length} students{h.room ? ` · Room ${h.room}` : ""}{h.class_leader ? ` · Leader ${h.class_leader}` : ""}</Text>
          <Card style={{ padding: 0 }}>
            {q.data.students.map((s: any, i: number) => (
              <View key={s.id}>{i > 0 && <Divider />}<ListRow icon="user" title={fullName(s)} sub={`${s.admission_no} · ${s.guardian_name || "Guardian"}`} onPress={() => setSt(s)} testID={`myclass-student-${s.id}`} /></View>
            ))}
          </Card>
        </>
      )}
      <Sheet open={Boolean(st)} onClose={() => setSt(null)} title={st ? fullName(st) : ""} testID="myclass-student-sheet">
        {st && (
          <View style={{ gap: 8 }}>
            <Field label="Admission no." value={st.admission_no} />
            <Field label="Guardian" value={st.guardian_name} />
            <Field label="Guardian phone" value={st.guardian_phone} />
            <Field label="Date of birth" value={st.date_of_birth ? fmtDate(st.date_of_birth) : ""} />
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button small icon="phone" label="Call" variant="outline" disabled={!st.guardian_phone} onPress={() => Linking.openURL(`tel:${st.guardian_phone}`)} style={{ flex: 1 }} testID="myclass-call-btn" />
              <Button small icon="mail" label="Email" variant="outline" disabled={!st.guardian_email} onPress={() => Linking.openURL(`mailto:${st.guardian_email}`)} style={{ flex: 1 }} testID="myclass-email-btn" />
            </View>
            <TextField value={msg} onChangeText={setMsg} placeholder="Message to the parent…" multiline testID="myclass-message-input" />
            <Button icon="message-circle" label="Send message" onPress={startChat} loading={busy} disabled={!msg.trim()} testID="myclass-message-btn" />
          </View>
        )}
      </Sheet>
    </StackScreen>
  );
}
