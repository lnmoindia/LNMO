// Chat thread: live over WebSocket (fallback 10s polling), typing indicator, seen ticks, image/PDF attachments.
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { setActiveThread } from "@/src/push/push";
import { Image } from "expo-image";
import { Feather } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth, useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useQuickReplies, useThread } from "@/src/lib/queries";
import { DocumentScanner } from "@/src/scan/DocumentScanner";
import { todayISO } from "@/src/lib/format";
import { sendChat, useChatSocket } from "@/src/lib/chat";
import { API, api, authHeaders } from "@/src/lib/api";
import { MAX_BYTES, appendFile, openAuthedFile, pickImage, pickPdf, type Picked } from "@/src/lib/files";
import { StackScreen } from "@/src/ui/Screen";
import { Sheet } from "@/src/ui/brandbits";
import { C, ErrorState, ListRow, SkeletonList, k } from "@/src/ui/kit";
import { LiveBadge } from "@/src/parent/LiveBadge";
import { fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";

const MAX = 2000;

export default function ThreadScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  useEffect(() => { setActiveThread(id || null); return () => setActiveThread(null); }, [id]);
  const qc = useQueryClient();
  const [typing, setTyping] = useState<string | null>(null);
  const typingT = useRef<any>(null);
  const onEv = useCallback((ev: any) => {
    if (ev.thread_id !== id) return;
    if (ev.type === "typing") {
      setTyping(ev.name || "Someone");
      clearTimeout(typingT.current);
      typingT.current = setTimeout(() => setTyping(null), 4000);
    } else if (["message", "read", "status"].includes(ev.type)) {
      if (ev.type === "message") setTyping(null);
      qc.invalidateQueries({ queryKey: ["thread", id] });
      qc.invalidateQueries({ queryKey: ["threads"] });
      qc.invalidateQueries({ queryKey: ["unread"] });
    }
  }, [id, qc]);
  const live = useChatSocket(onEv);
  const q = useThread(id, live !== "live");
  useEffect(() => { if (q.data) { qc.invalidateQueries({ queryKey: ["unread"] }); qc.invalidateQueries({ queryKey: ["threads"] }); } }, [q.dataUpdatedAt]); // eslint-disable-line react-hooks/exhaustive-deps
  const t = q.data?.thread;
  const { user } = useAuth();
  const staff = user?.role !== "parent";
  const toast = useToast();
  const title = t ? (staff ? t.parent_name || "Parent" : `${t.target === "office" ? "School office" : "Class teacher"}`) : "Conversation";
  const setStatus = async () => {
    try { await api.post(`/chat/threads/${id}/status`, { status: t.status === "closed" ? "open" : "closed" }); q.refetch(); qc.invalidateQueries({ queryKey: ["threads"] }); }
    catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <StackScreen title={title} testID="thread-screen" scroll={false} keyboard right={<View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}><LiveBadge status={live} testID="thread-live-status" />
        {staff && t && <Pressable onPress={setStatus} hitSlop={8} style={s.iconBtn} testID="chat-status-toggle"><Feather name={t.status === "closed" ? "unlock" : "lock"} size={18} color={C.onSurfaceTertiary} /></Pressable>}</View>}
      footer={t && (t.status === "closed"
        ? <Text style={s.closed} testID="chat-closed-note">This conversation is closed. Start a new message from Messages if you need to.</Text>
        : <Composer threadId={id} staff={staff} />)}>
      {q.isLoading ? <View style={{ padding: 20 }}><SkeletonList n={4} height={60} /></View>
        : q.isError ? <View style={{ padding: 20 }}><ErrorState error={q.error} onRetry={q.refetch} /></View>
        : <MessageList d={q.data} typing={typing} />}
    </StackScreen>
  );
}

function MessageList({ d, typing }: { d: any; typing: string | null }) {
  const ref = useRef<FlatList>(null);
  const t = d.thread;
  return (
    <FlatList ref={ref} data={d.messages} keyExtractor={(m) => m.id} testID="chat-messages"
      contentContainerStyle={s.list}
      onContentSizeChange={() => { ref.current?.scrollToEnd({ animated: false }); setTimeout(() => ref.current?.scrollToEnd({ animated: true }), 120); }}
      onLayout={() => ref.current?.scrollToEnd({ animated: false })}
      ListHeaderComponent={<Text style={s.threadHead} testID="chat-thread-title">{t.student_name} · {t.class_name}{t.section ? ` ${t.section}` : ""}{t.subject ? `\n${t.subject}` : ""}</Text>}
      ListEmptyComponent={<Text style={[k.small, { textAlign: "center", paddingVertical: 30 }]}>No messages yet — say hello.</Text>}
      ListFooterComponent={typing ? <Text style={s.typing} testID="chat-typing">{typing} is typing…</Text> : null}
      renderItem={({ item }) => <Bubble m={item} />} />
  );
}

function Bubble({ m }: { m: any }) {
  const b = useBrand();
  const mine = m.mine;
  return (
    <View style={[s.bRow, { justifyContent: mine ? "flex-end" : "flex-start" }]} testID={`chat-msg-${m.id}`}>
      <View style={[s.bubble, mine ? [s.mine, { backgroundColor: b.ink }] : s.theirs, m.hidden && { opacity: 0.6 }]}>
        {!mine && <Text style={s.sender}>{m.sender_name} · {m.sender_title}</Text>}
        {m.hidden && <Text style={[s.sender, mine && { color: "#fff" }]}>Hidden{m.hidden_by ? ` by ${m.hidden_by}` : ""}</Text>}
        {m.body ? <Text style={[s.body, mine && { color: "#fff" }]}>{m.body}</Text> : null}
        {m.attachment && <Attachment m={m} mine={mine} />}
        <View style={s.meta}>
          <Text style={[s.time, mine && { color: "rgba(255,255,255,0.75)" }]}>{fmtDateTime(m.created_at)}</Text>
          {mine && (m.seen
            ? <View style={s.seen} testID={`chat-seen-${m.id}`}><Feather name="check-circle" size={12} color="rgba(255,255,255,0.9)" /><Text style={[s.time, { color: "rgba(255,255,255,0.9)" }]}>Seen</Text></View>
            : <Feather name="check" size={12} color="rgba(255,255,255,0.75)" />)}
        </View>
      </View>
    </View>
  );
}

function Attachment({ m, mine }: { m: any; mine: boolean }) {
  const toast = useToast();
  const a = m.attachment;
  const open = async () => {
    try { await openAuthedFile(`/chat/messages/${m.id}/attachment`, a.name || "attachment", a.content_type); } catch (e: any) { toast(e.message, "error"); }
  };
  if (a.content_type?.startsWith("image/")) {
    return (
      <Pressable onPress={open} testID={`chat-attachment-img-${m.id}`}>
        <Image source={{ uri: `${API}/chat/messages/${m.id}/attachment`, headers: authHeaders() }} style={s.img} contentFit="cover" />
      </Pressable>
    );
  }
  return (
    <Pressable onPress={open} style={[s.file, mine && { backgroundColor: "rgba(255,255,255,0.15)" }]} testID={`chat-attachment-file-${m.id}`}>
      <Feather name="file-text" size={18} color={mine ? "#fff" : C.onSurface} />
      <Text style={[s.fileText, mine && { color: "#fff" }]} numberOfLines={1}>{a.name} · {Math.ceil((a.size || 0) / 1024)} KB</Text>
    </Pressable>
  );
}

function Composer({ threadId, staff }: { threadId: string; staff: boolean }) {
  const qr = useQuickReplies(staff);
  const [qrOpen, setQrOpen] = useState(false);
  const [scan, setScan] = useState(false);
  const applyReply = async (r: any) => {
    setQrOpen(false);
    let ph: any = {};
    try { ph = await api.get(`/chat/threads/${threadId}/placeholders`); } catch { /* fill what we can */ }
    setText(String(r.text).replace(/\{(\w+)\}/g, (m0: string, key: string) => (ph[key] != null ? String(ph[key]) : m0)));
  };
  const b = useBrand();
  const toast = useToast();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [file, setFile] = useState<Picked | null>(null);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState(false);
  const lastTyping = useRef(0);
  const onType = (v: string) => {
    if (staff && v === "/") { setQrOpen(true); setText(""); return; }
    setText(v);
    if (Date.now() - lastTyping.current > 2500 && v.trim()) { lastTyping.current = Date.now(); sendChat({ type: "typing", thread_id: threadId }); }
  };
  const attach = async (kind: "library" | "camera" | "pdf") => {
    setSheet(false);
    try {
      const f = kind === "pdf" ? await pickPdf() : await pickImage(kind);
      if (!f) return;
      if (f.size && f.size > MAX_BYTES) return toast("Attachments can be at most 5 MB", "error");
      if (!/^(image\/(jpeg|png|webp)|application\/pdf)$/.test(f.type)) return toast("Attach a JPG, PNG, WEBP image or a PDF", "error");
      setFile(f);
    } catch (e: any) { toast(e.message, "error"); }
  };
  const send = async () => {
    if (!text.trim() && !file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("body", text);
      if (file) await appendFile(fd, "file", file);
      await api.postForm(`/chat/threads/${threadId}/messages`, fd);
      setText(""); setFile(null);
      qc.invalidateQueries({ queryKey: ["thread", threadId] });
      qc.invalidateQueries({ queryKey: ["threads"] });
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <View style={s.composer}>
      {file && (
        <View style={[s.chip, { backgroundColor: b.soft }]} testID="chat-file-chip">
          <Feather name="paperclip" size={14} color={b.ink} />
          <Text style={[s.chipText, { color: b.ink }]} numberOfLines={1}>{file.name}</Text>
          <Pressable onPress={() => setFile(null)} hitSlop={10} testID="chat-file-remove"><Feather name="x" size={16} color={b.ink} /></Pressable>
        </View>
      )}
      <View style={s.inputRow}>
        <Pressable onPress={() => setSheet(true)} style={s.iconBtn} testID="chat-attach-btn" accessibilityLabel="Attach image or PDF">
          <Feather name="paperclip" size={22} color={C.onSurfaceTertiary} />
        </Pressable>
        {staff && <Pressable onPress={() => setQrOpen(true)} style={s.iconBtn} testID="chat-quick-replies-btn" accessibilityLabel="Quick replies"><Feather name="zap" size={21} color={C.onSurfaceTertiary} /></Pressable>}
        <TextInput value={text} onChangeText={onType} placeholder="Write a message…" placeholderTextColor={C.muted} multiline maxLength={MAX}
          style={s.input} testID="chat-input" />
        <Pressable onPress={send} disabled={busy || (!text.trim() && !file)} testID="chat-send-btn"
          style={[s.send, { backgroundColor: b.color }, (busy || (!text.trim() && !file)) && { opacity: 0.45 }]}>
          {busy ? <ActivityIndicator color={b.onColor} /> : <Feather name="send" size={20} color={b.onColor} />}
        </Pressable>
      </View>
      <Sheet open={sheet} onClose={() => setSheet(false)} title="Attach" testID="chat-attach-sheet">
        <ListRow icon="image" title="Photo from gallery" onPress={() => attach("library")} testID="chat-attach-gallery" />
        <ListRow icon="camera" title="Take a photo" onPress={() => attach("camera")} testID="chat-attach-camera" />
        <ListRow icon="file-text" title="PDF document" sub="Max 5 MB" onPress={() => attach("pdf")} testID="chat-attach-pdf" />
        <ListRow icon="maximize" title="Scan document" sub="Straighten pages into one PDF" onPress={() => { setSheet(false); setScan(true); }} testID="chat-attach-scan" />
      </Sheet>
      <DocumentScanner open={scan} onClose={() => setScan(false)} name={`Scan_${todayISO()}.pdf`} onDone={(fs) => fs[0] && setFile(fs[0])} />
      {staff && (
        <Sheet open={qrOpen} onClose={() => setQrOpen(false)} title="Quick replies" testID="chat-quick-replies-sheet">
          <ScrollView style={{ maxHeight: 420 }}>
            {(qr.data || []).map((r: any) => <ListRow key={r.id} icon="zap" title={r.title} sub={r.text} onPress={() => applyReply(r)} testID={`chat-qr-${r.id}`} />)}
            {!qr.data?.length && <Text style={[k.small, { padding: 16 }]}>No quick replies yet — add them on the web.</Text>}
          </ScrollView>
        </Sheet>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  list: { padding: 16, gap: 10, paddingBottom: 20 },
  threadHead: { fontFamily: fonts.bodySemi, fontSize: 13, color: C.muted, textAlign: "center", marginBottom: 8, lineHeight: 19 },
  bRow: { flexDirection: "row" },
  bubble: { maxWidth: "84%", borderRadius: 20, paddingHorizontal: 14, paddingVertical: 10, gap: 4 },
  mine: { borderBottomRightRadius: 6 },
  theirs: { backgroundColor: "#fff", borderWidth: 1, borderColor: C.border, borderBottomLeftRadius: 6 },
  sender: { fontFamily: fonts.bodyBold, fontSize: 12, color: C.muted },
  body: { fontFamily: fonts.body, fontSize: 16, color: C.onSurface, lineHeight: 22 },
  meta: { flexDirection: "row", alignItems: "center", gap: 6, justifyContent: "flex-end" },
  time: { fontFamily: fonts.body, fontSize: 11, color: C.muted },
  seen: { flexDirection: "row", alignItems: "center", gap: 3 },
  img: { width: 220, height: 180, borderRadius: 14, marginTop: 4, backgroundColor: C.surfaceTertiary },
  file: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: 12, backgroundColor: C.surfaceTertiary, marginTop: 4, minHeight: 44 },
  fileText: { flexShrink: 1, fontFamily: fonts.bodySemi, fontSize: 13, color: C.onSurface },
  typing: { fontFamily: fonts.bodyMedium, fontStyle: "italic", fontSize: 13, color: C.muted, paddingTop: 4 },
  closed: { fontFamily: fonts.bodyMedium, fontSize: 14, color: C.muted, padding: 16, backgroundColor: "#fff", borderTopWidth: 1, borderTopColor: C.border },
  composer: { backgroundColor: "#fff", borderTopWidth: 1, borderTopColor: C.border, paddingHorizontal: 10, paddingVertical: 8, gap: 8 },
  chip: { flexDirection: "row", alignItems: "center", gap: 8, alignSelf: "flex-start", paddingHorizontal: 12, minHeight: 36, borderRadius: 999, maxWidth: "90%" },
  chipText: { fontFamily: fonts.bodySemi, fontSize: 13, flexShrink: 1 },
  inputRow: { flexDirection: "row", alignItems: "flex-end", gap: 6 },
  iconBtn: { width: 44, height: 48, alignItems: "center", justifyContent: "center" },
  input: { flex: 1, minHeight: 48, maxHeight: 130, borderRadius: 22, backgroundColor: C.surfaceTertiary, paddingHorizontal: 16, paddingTop: 13, paddingBottom: 12, fontFamily: fonts.body, fontSize: 16, color: C.onSurface },
  send: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
});
