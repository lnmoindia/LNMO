// Student detail for a principal: profile + linked parents with Call / SMS / Email / password help.
import { useState } from "react";
import { Linking, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, Empty, ErrorState, Field, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { ResetSheet } from "@/src/principal/ResetSheet";
import { fmtDate, fullName } from "@/src/lib/format";

export default function PStudent() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const p = useQuery({ queryKey: ["p-student", id], queryFn: () => api.get(`/students/${id}/profile`) });
  const par = useQuery({ queryKey: ["p-student-parents", id], queryFn: () => api.get(`/students/${id}/parents`) });
  const [uid, setUid] = useState<string | null>(null);
  const st = p.data?.student || p.data || {};
  const parents: any[] = par.data?.parents || (Array.isArray(par.data) ? par.data : []);
  return (
    <StackScreen title="Student" testID="principal-student-screen">
      {p.isLoading ? <SkeletonList n={2} /> : p.isError ? <ErrorState error={p.error} onRetry={p.refetch} /> : (
        <Card style={{ gap: 8 }} testID="pstudent-card">
          <Text style={k.h2} testID="pstudent-name">{fullName(st)}</Text>
          <Field label="Admission no" value={st.admission_no} /><Field label="Class" value={`${st.class_name || ""} ${st.section || ""}`} />
          <Field label="Date of birth" value={st.date_of_birth ? fmtDate(st.date_of_birth, { year: true }) : "—"} /><Field label="Guardian" value={`${st.guardian_name || "—"} ${st.guardian_phone || ""}`} />
        </Card>
      )}
      <SectionTitle title="Parents" />
      {par.isLoading ? <SkeletonList n={1} /> : !parents.length ? <Card><Empty icon="users" text="No parent account linked yet." /></Card> : parents.map((u: any) => (
        <Card key={u.id} style={{ gap: 8 }} testID={`pparent-${u.id}`}>
          <Text style={k.label}>{u.name}</Text><Text style={k.small}>{[u.phone, u.email].filter(Boolean).join(" · ")}</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {u.phone ? <Button small icon="phone" label="Call" onPress={() => Linking.openURL(`tel:${u.phone}`)} testID={`pparent-call-${u.id}`} /> : null}
            {u.phone ? <Button small variant="outline" icon="message-square" label="SMS" onPress={() => Linking.openURL(`sms:${u.phone}`)} testID={`pparent-sms-${u.id}`} /> : null}
            {u.email ? <Button small variant="outline" icon="mail" label="Email" onPress={() => Linking.openURL(`mailto:${u.email}`)} testID={`pparent-email-${u.id}`} /> : null}
            <Button small variant="ghost" icon="key" label="Password" onPress={() => setUid(u.id)} testID={`pparent-reset-${u.id}`} />
          </View>
        </Card>
      ))}
      {st.user_id ? <Button variant="ghost" icon="key" label="Student password help" onPress={() => setUid(st.user_id)} testID="pstudent-reset" /> : null}
      <ResetSheet uid={uid} onClose={() => setUid(null)} />
    </StackScreen>
  );
}
