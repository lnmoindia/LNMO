// Students in my divisions: search by name or admission no (GET /students/filter is principal-scoped).
import { useEffect, useState } from "react";
import { Text } from "react-native";
import { router } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Card, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { fullName } from "@/src/lib/format";

export default function PStudents() {
  const [text, setText] = useState(""); const [q, setQ] = useState("");
  useEffect(() => { const t = setTimeout(() => setQ(text.trim()), 350); return () => clearTimeout(t); }, [text]);
  const r = useQuery({ queryKey: ["p-students", q], queryFn: () => api.get(`/students/filter?limit=50&search=${encodeURIComponent(q)}`) });
  const items = r.data?.items || [];
  return (
    <StackScreen title="Students" testID="principal-students-screen" keyboard>
      <TextField label="Search" placeholder="Name or admission no (e.g. SPS-001)" value={text} onChangeText={setText} autoCapitalize="none" testID="pstudents-search" />
      {r.isLoading ? <SkeletonList n={3} height={64} /> : r.isError ? <ErrorState error={r.error} onRetry={r.refetch} /> : !items.length ? <Card><Empty icon="search" text="No students found." /></Card>
        : items.map((s: any) => (
          <Card key={s.id} onPress={() => router.push(`/principal/student/${s.id}`)} style={{ gap: 2 }} testID={`pstudent-${s.admission_no || s.id}`}>
            <Text style={k.label}>{fullName(s)}</Text><Text style={k.small}>{s.admission_no} · {s.class_name} {s.section}</Text>
          </Card>
        ))}
      {r.data && <Text style={k.small}>{r.data.total} in your divisions</Text>}
    </StackScreen>
  );
}
