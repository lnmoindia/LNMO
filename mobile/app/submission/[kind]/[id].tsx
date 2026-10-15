// Submission detail (GET /submissions/{kind}/{id}): attachments (images inline + zoom, PDFs open/share),
// status, feedback, previous attempts (read-only). Reviewers: "Mark reviewed" (+ marks) and "Request redo".
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Feather } from "@expo/vector-icons";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Avatar } from "@/src/ui/brandbits";
import { Button, C, Card, Chip, ErrorState, SectionTitle, SkeletonList, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { Attempt, StateChip, apiKind } from "@/src/work/SubmissionBits";
import { addDaysISO, fmtDate, fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export default function SubmissionDetail() {
  const { kind, id } = useLocalSearchParams<{ kind: string; id: string }>();
  const base = apiKind(kind);
  const q = useQuery({ queryKey: ["submission", base, id], queryFn: () => api.get(`/submissions/${base}/${id}`) });
  const d = q.data;
  return (
    <StackScreen title="Submission" testID="submission-screen" keyboard>
      {q.isLoading ? <SkeletonList n={3} height={120} /> : q.isError ? <ErrorState error={q.error} onRetry={q.refetch} /> : (
        <>
          <Card style={{ flexDirection: "row", alignItems: "center", gap: 14 }} testID="submission-student">
            <Avatar name={d.student.name} uri={d.student.thumb_url} size={52} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={s.name}>{d.student.name}</Text>
              <Text style={k.small}>{d.student.class_name} {d.student.section} · {d.student.admission_no}</Text>
            </View>
          </Card>
          <Card style={{ gap: 4 }} testID="submission-item">
            <Text style={k.small}>{d.item.subject} · due {fmtDate(d.item.due_date)}{d.item.max_marks ? ` · ${d.item.max_marks} marks` : ""}</Text>
            <Text style={k.h2}>{d.item.title}</Text>
          </Card>
          <Attempt sub={d.submission} max={d.item.max_marks} current testID="submission-current" />
          {d.can_review && <ReviewBox d={d} base={base} id={id} onDone={() => q.refetch()} />}
          {d.previous_attempts?.length ? <SectionTitle title={`Previous attempts · ${d.previous_attempts.length}`} /> : null}
          {(d.previous_attempts || []).map((a: any) => <PrevAttempt key={a.attempt} a={a} max={d.item.max_marks} />)}
        </>
      )}
    </StackScreen>
  );
}

function PrevAttempt({ a, max }: { a: any; max?: number }) {
  const [open, setOpen] = useState(false);
  return (
    <View style={{ gap: 8 }}>
      <Pressable onPress={() => setOpen(!open)} style={s.prev} testID={`prev-attempt-${a.attempt}`}>
        <Feather name={open ? "chevron-down" : "chevron-right"} size={18} color={C.muted} />
        <Text style={[k.label, { flex: 1 }]}>Attempt {a.attempt} · {fmtDateTime(a.submitted_at)}</Text>
        <StateChip state={a.state} />
      </Pressable>
      {open && <Attempt sub={a} max={max} testID={`prev-attempt-body-${a.attempt}`} />}
    </View>
  );
}

function ReviewBox({ d, base, id, onDone }: { d: any; base: string; id: string; onDone: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const sub = d.submission;
  const [fb, setFb] = useState(sub.state === "reviewed" ? sub.feedback || "" : "");
  const [score, setScore] = useState(sub.score != null ? String(sub.score) : "");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState<"" | "review" | "redo">("");
  const done = (msg: string) => { toast(msg); onDone(); qc.invalidateQueries({ queryKey: ["board"] }); qc.invalidateQueries({ queryKey: ["t-subs-of"] }); };
  const review = async () => {
    setBusy("review");
    try { await api.post(`/submissions/${base}/${id}/review`, { feedback: fb.trim(), score: d.supports_marks && score.trim() ? Number(score) : null }); done("Marked reviewed ✓"); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  const redo = async () => {
    if (!fb.trim()) return toast("Tell the student what to fix — feedback is required for a redo", "error");
    setBusy("redo");
    try { await api.post(`/submissions/${base}/${id}/redo`, { feedback: fb.trim(), due_date: due || null }); done("Redo requested"); }
    catch (e: any) { toast(e.message, "error"); } finally { setBusy(""); }
  };
  return (
    <Card style={{ gap: 12 }} testID="review-box">
      <Text style={s.title}>Review</Text>
      <TextField label="Feedback" multiline value={fb} onChangeText={setFb} placeholder="What went well / what to fix…" testID="review-feedback" />
      {d.supports_marks && <TextField label={`Marks${d.item.max_marks ? ` (out of ${d.item.max_marks})` : ""}`} value={score} onChangeText={setScore} keyboardType="decimal-pad" placeholder="Optional" testID="review-score" />}
      <Button icon="check" variant="success" label="Mark reviewed" onPress={review} loading={busy === "review"} testID="review-submit" />
      <Text style={k.label}>New due date for the redo (optional)</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {[["", "Keep"], [addDaysISO(1), "Tomorrow"], [addDaysISO(2), "In 2 days"], [addDaysISO(7), "In a week"]].map(([v, l]) => (
          <Chip key={l} label={v ? `${l} · ${fmtDate(v)}` : l} active={due === v} onPress={() => setDue(v)} testID={`redo-due-${l.replace(/\s+/g, "-").toLowerCase()}`} />
        ))}
      </View>
      <Button icon="rotate-ccw" variant="outline" label="Request redo" onPress={redo} loading={busy === "redo"} testID="review-redo" />
    </Card>
  );
}

const s = StyleSheet.create({
  name: { fontFamily: fonts.bodyBold, fontSize: 17, color: C.onSurface },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  title: { fontFamily: fonts.headingSemi, fontSize: 17, color: C.onSurface },
  prev: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 48, paddingHorizontal: 12, borderRadius: 12, backgroundColor: "#fff", borderWidth: 1, borderColor: C.border },
});
