// Teachers → timetable / call / password help (teacher account changes stay scoped server-side).
import { useState } from "react";
import { Linking, Text, View } from "react-native";
import { router } from "expo-router";
import { useTeachers } from "@/src/principal/hooks";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { ResetSheet } from "@/src/principal/ResetSheet";

export default function PTeachers() {
  const t = useTeachers();
  const [uid, setUid] = useState<string | null>(null);
  return (
    <StackScreen title="Teachers" testID="principal-teachers-screen">
      {t.isLoading ? <SkeletonList n={3} /> : t.isError ? <ErrorState error={t.error} onRetry={t.refetch} /> : (t.data || []).map((x: any) => (
        <Card key={x.id} style={{ gap: 8 }} testID={`pteacher-${x.id}`}>
          <Text style={k.label}>{x.name}</Text><Text style={k.small}>{[x.phone, x.email].filter(Boolean).join(" · ")} · {x.classes_count} classes</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            <Button small icon="calendar" label="Timetable" onPress={() => router.push(`/principal/teacher/${x.id}`)} testID={`pteacher-tt-${x.id}`} />
            {x.phone ? <Button small variant="outline" icon="phone" label="Call" onPress={() => Linking.openURL(`tel:${x.phone}`)} testID={`pteacher-call-${x.id}`} /> : null}
            <Button small variant="ghost" icon="key" label="Password" onPress={() => setUid(x.id)} testID={`pteacher-reset-${x.id}`} />
          </View>
        </Card>
      ))}
      <ResetSheet uid={uid} onClose={() => setUid(null)} />
    </StackScreen>
  );
}
