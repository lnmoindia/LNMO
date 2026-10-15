// Teacher / principal: one homework or assignment → the Submissions board (filter chips with counts) → tap a row for the detail.
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Feather } from "@expo/vector-icons";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { openAuthedFile } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Avatar } from "@/src/ui/brandbits";
import { Button, C, Card, Chip, Empty, ErrorState, SkeletonList, k } from "@/src/ui/kit";
import { STATE, StateChip, apiKind, type SubStateKey } from "@/src/work/SubmissionBits";
import { fmtDate, fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const FILTERS: ("" | SubStateKey)[] = ["", "submitted", "late", "redo_requested", "reviewed", "not_submitted"];

export default function SubmissionBoard() {
  const { kind, id } = useLocalSearchParams<{ kind: string; id: string }>();
  const base = apiKind(kind);
  const [filter, setFilter] = useState<"" | SubStateKey>("");
  const item = useQuery({ queryKey: ["t-subs-of", id], queryFn: () => api.get(`/${base}/${id}/submissions`) });
  const board = useQuery({ queryKey: ["board", base, id, filter], queryFn: () => api.get(`/${base}/${id}/submission-board`, filter ? { filter } : undefined) });
  const qc = useQueryClient();
  const toast = useToast();
  const w = item.data?.[base === "assignments" ? "assignment" : "homework"];
  const counts = board.data?.counts || {};
  const toggle = async () => {
    try { await api.post(`/${base}/${id}/${w.status === "closed" ? "reopen" : "close"}`); item.refetch(); qc.invalidateQueries({ queryKey: ["t-work"] }); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <StackScreen title="Submissions" testID="thw-submissions-screen">
      {!w ? <SkeletonList n={1} height={120} /> : (
        <Card style={{ gap: 4 }} testID="thw-detail">
          <Text style={k.small}>{w.class_name} {w.section} · {w.subject} · due {fmtDate(w.due_date)}{w.max_marks ? ` · ${w.max_marks} marks` : ""}</Text>
          <Text style={k.h2}>{w.title}</Text>
          {w.instructions ? <Text style={k.body}>{w.instructions}</Text> : null}
          {(w.attachments || []).map((a: any, i: number) => (
            <Pressable key={i} onPress={() => openAuthedFile(`/${base}/attachment/${w.id}/${i}?kind=${base === "assignments" ? "assignment" : "homework"}`, a.name || "file", a.type || "application/octet-stream").catch((e) => toast(e.message, "error"))}
              style={s.attach} testID={`thw-attachment-${i}`}>
              <Feather name="paperclip" size={14} color={C.info} /><Text style={[k.label, { color: C.info }]}>{a.name}</Text>
            </Pressable>
          ))}
          <Button small variant="outline" label={w.status === "closed" ? "Reopen" : "Close submissions"} onPress={toggle} style={{ marginTop: 8 }} testID="thw-close-toggle" />
        </Card>
      )}
      <View style={s.chips} testID="board-filters">
        {FILTERS.map((f) => (
          <Chip key={f || "all"} label={`${f ? STATE[f][0] : "All"} · ${counts[f || "all"] ?? 0}`} active={filter === f} onPress={() => setFilter(f)} testID={`board-filter-${f || "all"}`} />
        ))}
      </View>
      {board.isLoading ? <SkeletonList n={4} height={64} /> : board.isError ? <ErrorState error={board.error} onRetry={board.refetch} /> : !board.data.rows.length
        ? <Card><Empty icon="inbox" text="Nobody in this group." testID="board-empty" /></Card>
        : <Card style={{ padding: 0 }} testID="board-rows">{board.data.rows.map((r: any, i: number) => <Row key={r.student_id} r={r} base={base} first={i === 0} />)}</Card>}
    </StackScreen>
  );
}

function Row({ r, base, first }: { r: any; base: string; first: boolean }) {
  const open = r.submission_id ? () => router.push(`/submission/${base}/${r.submission_id}`) : undefined;
  return (
    <Pressable onPress={open} disabled={!open} style={({ pressed }) => [s.row, !first && s.line, pressed && open && { backgroundColor: C.surfaceTertiary }]} testID={`board-row-${r.student_id}`}>
      <Avatar name={r.student_name} uri={r.thumb_url} size={40} />
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={s.name} numberOfLines={1}>{r.student_name}</Text>
        <Text style={k.small} numberOfLines={1}>
          {r.submitted_at ? fmtDateTime(r.submitted_at) : r.admission_no}{r.attempt > 1 ? ` · attempt ${r.attempt}` : ""}{r.score != null ? ` · ${r.score} marks` : ""}
        </Text>
      </View>
      <StateChip state={r.state} late={r.late} testID={`board-state-${r.student_id}`} />
      {open && <Feather name="chevron-right" size={18} color={C.muted} />}
    </Pressable>
  );
}

const s = StyleSheet.create({
  attach: { flexDirection: "row", gap: 6, minHeight: 36, alignItems: "center" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingVertical: 12, minHeight: 64 },
  line: { borderTopWidth: 1, borderTopColor: C.divider },
  name: { fontFamily: fonts.bodySemi, fontSize: 15, color: C.onSurface },
});
