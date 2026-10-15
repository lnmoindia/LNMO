// Class teacher card (parent Home + Child profile): photo/initials, name, "Class teacher · Grade 8 A", Message.
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { api } from "@/src/lib/api";
import { useToast } from "@/src/state/toast";
import { Avatar } from "@/src/ui/brandbits";
import { Button, C, Card } from "@/src/ui/kit";
import { fonts } from "@/src/theme";

// Open the existing open thread with the class teacher for this child, else start a new message to them.
export async function messageClassTeacher(childId: string) {
  const d = await api.get("/chat/threads", { student_id: childId, status: "" });
  const t = (d?.threads || []).find((x: any) => x.target === "class_teacher" && x.status !== "closed");
  if (t) router.push(`/thread/${t.id}`);
  else router.push({ pathname: "/new-message", params: { child: childId, target: "class_teacher" } });
}

export function ClassTeacherCard({ t, cls, childId, testID = "class-teacher-card" }: { t: any; cls: string; childId: string; testID?: string }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  if (!t) return null;
  const go = async () => { setBusy(true); try { await messageClassTeacher(childId); } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); } };
  return (
    <Card style={s.card} testID={testID}>
      <Avatar name={t.name} uri={t.thumb_url || t.photo_url} size={52} testID={`${testID}-photo`} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={s.name} numberOfLines={1} testID={`${testID}-name`}>{t.name}</Text>
        <Text style={s.sub} numberOfLines={1}>Class teacher · {cls}</Text>
      </View>
      <Button small icon="message-circle" label="Message" onPress={go} loading={busy} testID={`${testID}-message-btn`} />
    </Card>
  );
}

export function SubjectTeachers({ list }: { list: any[] }) {
  if (!list?.length) return null;
  return (
    <Card style={{ gap: 12 }} testID="subject-teachers">
      {list.map((t: any) => (
        <View key={`${t.subject}-${t.id}`} style={s.row} testID={`subject-teacher-${t.id}`}>
          <Avatar name={t.name} uri={t.thumb_url} size={40} />
          <View style={{ flex: 1 }}><Text style={s.name2}>{t.name}</Text><Text style={s.sub}>{t.subject}</Text></View>
        </View>
      ))}
    </Card>
  );
}

const s = StyleSheet.create({
  card: { flexDirection: "row", alignItems: "center", gap: 14 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  name: { fontFamily: fonts.bodyBold, fontSize: 16, color: C.onSurface },
  name2: { fontFamily: fonts.bodySemi, fontSize: 15, color: C.onSurface },
  sub: { fontFamily: fonts.body, fontSize: 13, color: C.muted },
});
