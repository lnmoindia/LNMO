import { useState } from "react";
import { View } from "react-native";
import { Image } from "expo-image";
import { useQueryClient } from "@tanstack/react-query";
import { useMe } from "@/src/lib/queries";
import { useToast } from "@/src/state/toast";
import { API, api, authHeaders } from "@/src/lib/api";
import { appendFile, pickImage } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Card, ErrorState, Field, SkeletonList } from "@/src/ui/kit";
import { Avatar } from "@/src/ui/brandbits";
import { fmtDate, fullName } from "@/src/lib/format";

export default function StudentProfile() {
  const q = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const [v, setV] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const s = q.data?.student;
  const change = async () => {
    try {
      const f = await pickImage("library");
      if (!f) return;
      if (!/^image\/(png|jpeg|webp)$/.test(f.type)) return toast("Use a JPG, PNG or WEBP photo", "error");
      setBusy(true);
      const fd = new FormData();
      await appendFile(fd, "file", f);
      await api.postForm(`/students/${s.id}/photo`, fd);
      toast("Photo updated!"); setV(Date.now());
      qc.invalidateQueries({ queryKey: ["s-me"] });
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const leader = q.data?.leader_role === "class_leader" ? "Class Leader" : q.data?.leader_role === "second_leader" ? "Second Leader" : "";
  return (
    <StackScreen title="Profile" testID="student-profile-screen">
      {q.isLoading ? <SkeletonList n={2} height={160} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <Card testID="student-profile-card">
          <View style={{ flexDirection: "row", alignItems: "center", gap: 16, marginBottom: 8 }}>
            {s.photo_path
              ? <Image source={{ uri: `${API}/students/${s.id}/photo?v=${v}`, headers: authHeaders() }} style={{ width: 72, height: 72, borderRadius: 22 }} testID="student-profile-photo" />
              : <Avatar name={s.first_name} size={72} />}
            <Button small variant="outline" icon="camera" label="Change photo" onPress={change} loading={busy} testID="student-change-photo-btn" />
          </View>
          <Field label="Full name" value={fullName(s)} testID="student-profile-name" />
          <Field label="Admission no." value={s.admission_no} testID="student-profile-admission" />
          <Field label="Class & section" value={`${s.class_name || "—"}${s.section ? ` · ${s.section}` : ""}`} />
          <Field label="Academic year" value={s.academic_year} />
          <Field label="Date of birth" value={s.date_of_birth || s.dob ? fmtDate(s.date_of_birth || s.dob) : ""} />
          <Field label="Gender" value={s.gender && s.gender[0].toUpperCase() + s.gender.slice(1)} />
          <Field label="Guardian" value={s.guardian_name} />
          <Field label="Guardian phone" value={s.guardian_phone} />
          {leader ? <Field label="Leadership" value={leader} /> : null}
        </Card>
      )}
    </StackScreen>
  );
}
