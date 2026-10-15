// Submissions for one homework/assignment: open files, verify / redo (+ score for assignments), close/reopen.
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Feather } from "@expo/vector-icons";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { openAuthedFile } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Button, C, Card, Empty, SectionTitle, SkeletonList, StatusChip, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { fmtDate, fmtDateTime } from "@/src/lib/format";

export default function Submissions() {
  const { kind, id } = useLocalSearchParams<{ kind: string; id: string }>();
  const base = kind === "assignment" ? "assignments" : "homework";
  const q = useQuery({ queryKey: ["t-subs-of", id], queryFn: () => api.get(`/${base}/${id}/submissions`) });
  const qc = useQueryClient();
  const toast = useToast();
  const w = q.data?.[kind === "assignment" ? "assignment" : "homework"];
  const open = (path: string, a: any) => openAuthedFile(path, a.name || "file", a.type || a.content_type || "application/octet-stream").catch((e) => toast(e.message, "error"));
  const toggle = async () => {
    try { await api.post(`/${base}/${id}/${w.status === "closed" ? "reopen" : "close"}`); q.refetch(); qc.invalidateQueries({ queryKey: ["t-work"] }); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <StackScreen title="Submissions" testID="thw-submissions-screen">
      {q.isLoading || !w ? <SkeletonList n={3} /> : (
        <>
          <Card style={{ gap: 4 }} testID="thw-detail">
            <Text style={k.small}>{w.class_name} {w.section} · {w.subject} · due {fmtDate(w.due_date)}</Text>
            <Text style={k.h2}>{w.title}</Text>
            {w.instructions ? <Text style={k.body}>{w.instructions}</Text> : null}
            {(w.attachments || []).map((a: any, i: number) => (
              <Pressable key={i} onPress={() => open(`/${base}/attachment/${w.id}/${i}?kind=${kind}`, a)} style={{ flexDirection: "row", gap: 6, minHeight: 36, alignItems: "center" }} testID={`thw-attachment-${i}`}>
                <Feather name="paperclip" size={14} color={C.info} /><Text style={[k.label, { color: C.info }]}>{a.name}</Text>
              </Pressable>
            ))}
            <Button small variant="outline" label={w.status === "closed" ? "Reopen" : "Close submissions"} onPress={toggle} style={{ marginTop: 8 }} testID="thw-close-toggle" />
          </Card>
          <SectionTitle title={`Submitted (${q.data.submissions.length})`} />
          {!q.data.submissions.length ? <Card><Empty icon="inbox" text="No submissions yet." /></Card> : q.data.submissions.map((sb: any) => (
            <SubCard key={sb.id} sb={sb} kind={kind} base={base} max={w.max_marks} onDone={() => q.refetch()} open={open} />
          ))}
          <SectionTitle title={`Not submitted (${q.data.pending.length})`} />
          <Card testID="thw-pending">{q.data.pending.map((p: any) => <Text key={p.student_id} style={[k.body, { paddingVertical: 4 }]}>{p.student_name}</Text>)}{!q.data.pending.length && <Text style={k.small}>Everyone has submitted.</Text>}</Card>
        </>
      )}
    </StackScreen>
  );
}

function SubCard({ sb, kind, base, max, onDone, open }: any) {
  const [fb, setFb] = useState(sb.feedback || "");
  const [score, setScore] = useState(sb.score != null ? String(sb.score) : "");
  const toast = useToast();
  const verify = async (verdict: string) => {
    try {
      const url = kind === "assignment" ? `/assignment-submissions/${sb.id}/verify` : `/submissions/${sb.id}/verify`;
      await api.post(url, { verdict, feedback: fb.trim(), ...(kind === "assignment" && verdict === "verified" ? { score: Number(score) } : {}) });
      toast(verdict === "redo" ? "Sent back for redo" : "Saved"); onDone();
    } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Card style={{ gap: 6 }} testID={`thw-sub-${sb.id}`}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Text style={k.label}>{sb.student_name}</Text><StatusChip status={sb.status === "submitted" ? "pending" : sb.status} /></View>
      <Text style={k.small}>{fmtDateTime(sb.submitted_at)}{sb.late ? " · late" : ""}</Text>
      {sb.note ? <Text style={k.body}>{sb.note}</Text> : null}
      {(sb.attachments || []).map((a: any, i: number) => (
        <Pressable key={i} onPress={() => open(`/${base}/attachment/${sb.id}/${i}?kind=submission`, a)} style={{ flexDirection: "row", gap: 6, minHeight: 36, alignItems: "center" }} testID={`thw-sub-file-${sb.id}-${i}`}>
          <Feather name="paperclip" size={14} color={C.info} /><Text style={[k.label, { color: C.info }]}>{a.name}</Text>
        </Pressable>
      ))}
      <TextField value={fb} onChangeText={setFb} placeholder="Feedback for the student…" testID={`thw-feedback-${sb.id}`} />
      {kind === "assignment" && <TextField value={score} onChangeText={setScore} keyboardType="number-pad" placeholder={`Score out of ${max}`} testID={`thw-score-${sb.id}`} />}
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Button small variant="success" icon="check" label={kind === "assignment" ? "Grade" : "Verify"} onPress={() => verify("verified")} style={{ flex: 1 }} testID={`thw-verify-${sb.id}`} />
        <Button small variant="outline" icon="rotate-ccw" label="Redo" onPress={() => verify("redo")} style={{ flex: 1 }} testID={`thw-redo-${sb.id}`} />
      </View>
    </Card>
  );
}
