// Submission UI shared by the teacher/principal board + detail, the student detail and the parent list.
import { useEffect, useState } from "react";
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from "react-native";
import { Image } from "expo-image";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { API, authHeaders } from "@/src/lib/api";
import { openAuthedFile } from "@/src/lib/files";
import { useToast } from "@/src/state/toast";
import { C, Card, k } from "@/src/ui/kit";
import { fmtDate, fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";

export type SubStateKey = "submitted" | "late" | "redo_requested" | "reviewed" | "not_submitted";
export const STATE: Record<SubStateKey, [string, string, string]> = {
  submitted: ["Submitted", C.infoSoft, C.info],
  late: ["Late", C.warningSoft, C.warning],
  redo_requested: ["Redo requested", C.warningSoft, C.warning],
  reviewed: ["Reviewed", C.successSoft, C.success],
  not_submitted: ["Not submitted", C.surfaceTertiary, C.onSurfaceTertiary],
};
// Legacy submission.status → board state.
export const stateOf = (sub: any): SubStateKey => (!sub ? "not_submitted" : sub.status === "redo" ? "redo_requested" : sub.status === "verified" || sub.status === "graded" ? "reviewed" : "submitted");
export const apiKind = (k?: string) => (k === "assignment" || k === "assignments" ? "assignments" : "homework");

export function StateChip({ state, late, testID }: { state: SubStateKey; late?: boolean; testID?: string }) {
  const [label, bg, fg] = STATE[state] || STATE.submitted;
  return (
    <View style={{ flexDirection: "row", gap: 6 }} testID={testID}>
      <View style={[s.chip, { backgroundColor: bg }]}><Text style={[s.chipText, { color: fg }]}>{label}</Text></View>
      {late && state !== "not_submitted" && state !== "late" ? <View style={[s.chip, { backgroundColor: C.warningSoft }]}><Text style={[s.chipText, { color: C.warning }]}>Late</Text></View> : null}
    </View>
  );
}

// Image behind the Bearer token: native sends the header; the web fetches a blob first.
export function AuthedImage({ path, style, testID }: { path: string; style: any; testID?: string }) {
  const [webUri, setWebUri] = useState<string | null>(null);
  useEffect(() => {
    if (Platform.OS !== "web") return undefined;
    let url = "", gone = false;
    fetch(`${API}${path}`, { headers: { ...authHeaders(), "X-Client": "mobile" } }).then((r) => (r.ok ? r.blob() : null))
      .then((b) => { if (b && !gone) { url = URL.createObjectURL(b); setWebUri(url); } }).catch(() => {});
    return () => { gone = true; if (url) URL.revokeObjectURL(url); };
  }, [path]);
  const source = Platform.OS === "web" ? (webUri ? { uri: webUri } : null) : { uri: `${API}${path}`, headers: authHeaders() };
  return source ? <Image source={source} style={style} contentFit="contain" testID={testID} /> : <View style={[style, { backgroundColor: C.surfaceTertiary }]} />;
}

// Full-screen viewer: pinch-zoom on iOS, tap to zoom 2.5× elsewhere.
function Viewer({ path, onClose }: { path: string | null; onClose: () => void }) {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [zoom, setZoom] = useState(1);
  useEffect(() => { setZoom(1); }, [path]);
  if (!path) return null;
  const w = width * zoom, h = (height - insets.top - 60) * zoom;
  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <View style={s.viewer} testID="image-viewer">
        <ScrollView maximumZoomScale={4} minimumZoomScale={1} centerContent contentContainerStyle={{ minWidth: width, minHeight: height }} horizontal={false}>
          <ScrollView horizontal contentContainerStyle={{ minWidth: width, alignItems: "center", justifyContent: "center" }}>
            <Pressable onPress={() => Platform.OS !== "ios" && setZoom(zoom > 1 ? 1 : 2.5)} testID="image-viewer-zoom">
              <AuthedImage path={path} style={{ width: w, height: h, marginTop: insets.top + 50 }} />
            </Pressable>
          </ScrollView>
        </ScrollView>
        <Pressable onPress={onClose} style={[s.close, { top: insets.top + 8 }]} hitSlop={10} testID="image-viewer-close"><Feather name="x" size={24} color="#fff" /></Pressable>
      </View>
    </Modal>
  );
}

// Attachments of one attempt: images inline (tap = full screen), PDFs/other files open via share/open.
export function Attachments({ files, testID }: { files: any[]; testID: string }) {
  const toast = useToast();
  const [view, setView] = useState<string | null>(null);
  const rel = (u: string) => u.replace(/^\/api/, "");
  if (!files?.length) return <Text style={s.none}>No files attached.</Text>;
  return (
    <View style={{ gap: 10 }}>
      {files.filter((f) => f.is_image).map((f) => (
        <Pressable key={`i${f.idx}`} onPress={() => setView(rel(f.url))} testID={`${testID}-img-${f.idx}`}>
          <AuthedImage path={rel(f.url)} style={s.img} />
        </Pressable>
      ))}
      {files.filter((f) => !f.is_image).map((f) => (
        <Pressable key={`f${f.idx}`} onPress={() => openAuthedFile(rel(f.url), f.name || "file.pdf", f.type || "application/pdf").catch((e) => toast(e.message, "error"))}
          style={s.file} testID={`${testID}-file-${f.idx}`}>
          <Feather name={f.is_pdf ? "file-text" : "paperclip"} size={18} color={C.info} />
          <Text style={s.fileText} numberOfLines={1}>{f.name}</Text>
          <Feather name="external-link" size={16} color={C.info} />
        </Pressable>
      ))}
      <Viewer path={view} onClose={() => setView(null)} />
    </View>
  );
}

export function Attempt({ sub, max, current, testID }: { sub: any; max?: number; current?: boolean; testID: string }) {
  return (
    <Card style={{ gap: 10 }} testID={testID}>
      <View style={s.head}>
        <Text style={s.title}>{current ? `Attempt ${sub.attempt || 1}` : `Attempt ${sub.attempt}`}</Text>
        <StateChip state={sub.state} late={sub.late} testID={`${testID}-state`} />
      </View>
      <Text style={k.small}>{sub.submitted_at ? `Sent ${fmtDateTime(sub.submitted_at)}` : ""}{sub.reviewed_by_name ? ` · reviewed by ${sub.reviewed_by_name}` : ""}</Text>
      {sub.note ? <Text style={k.body}>“{sub.note}”</Text> : null}
      {sub.score != null ? <Text style={k.label} testID={`${testID}-score`}>Marks: {sub.score}{max ? ` / ${max}` : ""}</Text> : null}
      {sub.feedback ? <Text style={[k.body, { color: sub.state === "redo_requested" ? C.warning : C.onSurface }]} testID={`${testID}-feedback`}>
        {sub.state === "redo_requested" ? "Redo requested: " : "Feedback: "}{sub.feedback}</Text> : null}
      {sub.state === "redo_requested" && sub.redo_due_date ? <Text style={k.small} testID={`${testID}-redo-due`}>New due date: {fmtDate(sub.redo_due_date, { weekday: true })}</Text> : null}
      <Attachments files={sub.attachments} testID={`${testID}-att`} />
    </Card>
  );
}


const s = StyleSheet.create({
  chip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  chipText: { fontFamily: fonts.bodyBold, fontSize: 12 },
  img: { width: "100%", height: 260, borderRadius: 14, backgroundColor: C.surfaceTertiary },
  file: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 48, paddingHorizontal: 14, borderRadius: 12, backgroundColor: C.surfaceTertiary },
  fileText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, color: C.info },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  title: { fontFamily: fonts.headingSemi, fontSize: 17, color: C.onSurface },
  none: { fontFamily: fonts.body, fontSize: 13, color: C.muted },
  viewer: { flex: 1, backgroundColor: "rgba(0,0,0,0.94)" },
  close: { position: "absolute", right: 16, width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(255,255,255,0.15)", alignItems: "center", justifyContent: "center" },
});
