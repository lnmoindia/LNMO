// AI Tutor chat for one subject: history sheet, New chat, typing bubble + reveal, Markdown answers, copy.
import { useEffect, useRef, useState } from "react";
import { Animated, FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import * as Clipboard from "expo-clipboard";
import { Feather } from "@expo/vector-icons";
import { useQueryClient } from "@tanstack/react-query";
import { useBrand } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { useTutorChats } from "@/src/lib/queries";
import { ApiError, api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Sheet } from "@/src/ui/brandbits";
import { C, Divider, ListRow, k } from "@/src/ui/kit";
import { Markdown } from "@/src/ui/Markdown";
import { fmtDateTime } from "@/src/lib/format";
import { fonts } from "@/src/theme";

type Msg = { role: "user" | "assistant" | "error"; content: string; grounded?: boolean; used_item_titles?: any[]; reveal?: boolean };

const friendly = (e: any) => {
  if (e instanceof ApiError && e.status === 429) return e.message || "You've reached today's AI Tutor limit. Please come back tomorrow!";
  if (e instanceof ApiError && e.status === 403) return e.message || "The AI Tutor isn't available for this subject right now.";
  if (e instanceof ApiError && e.status === 0) return "You're offline — your question wasn't sent. Try again when you're connected.";
  return "The tutor couldn't answer just now. Please try again in a moment.";
};

export default function TutorChat() {
  const { subject } = useLocalSearchParams<{ subject: string }>();
  const chats = useTutorChats(subject);
  const qc = useQueryClient();
  const [chatId, setChatId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [sending, setSending] = useState(false);
  const [hist, setHist] = useState(false);
  const toast = useToast();

  const openChat = async (id: string) => {
    setHist(false);
    try { const d = await api.get(`/ai/tutor/chat/${id}`); setChatId(id); setMsgs(d.messages || []); } catch (e: any) { toast(e.message, "error"); }
  };
  const newChat = () => { setChatId(null); setMsgs([]); };
  const send = async (text: string) => {
    setMsgs((m) => [...m.filter((x) => x.role !== "error"), { role: "user", content: text }]);
    setSending(true);
    try {
      const d = await api.post("/ai/tutor/chat", { subject, message: text, chat_id: chatId });
      setChatId(d.chat_id);
      setMsgs((m) => [...m, { role: "assistant", content: d.answer, grounded: d.grounded, used_item_titles: d.used_item_titles, reveal: true }]);
      qc.invalidateQueries({ queryKey: ["tutor-chats", subject] });
      return true;
    } catch (e) {
      setMsgs((m) => [...m, { role: "error", content: friendly(e) }]);
      return false;
    } finally { setSending(false); }
  };
  const right = (
    <View style={{ flexDirection: "row", gap: 4 }}>
      <Pressable onPress={() => setHist(true)} style={s.hBtn} testID="tutor-history-btn" accessibilityLabel="Previous chats"><Feather name="clock" size={20} color={C.onSurface} /></Pressable>
      <Pressable onPress={newChat} style={s.hBtn} testID="tutor-new-chat-btn" accessibilityLabel="New chat"><Feather name="plus" size={22} color={C.onSurface} /></Pressable>
    </View>
  );
  return (
    <StackScreen title={subject} testID="tutor-chat-screen" scroll={false} keyboard right={right} footer={<Composer subject={subject} sending={sending} onSend={send} />}>
      <Messages msgs={msgs} sending={sending} subject={subject} />
      <Sheet open={hist} onClose={() => setHist(false)} title={`${subject} chats`} testID="tutor-history-sheet">
        <ListRow icon="plus" title="New chat" onPress={() => { newChat(); setHist(false); }} testID="tutor-history-new" />
        {(chats.data || []).map((c: any) => (
          <View key={c.chat_id}><Divider />
            <ListRow icon="message-square" title={c.preview || "Chat"} sub={fmtDateTime(c.last_at || c.started_at)} onPress={() => openChat(c.chat_id)} testID={`tutor-history-${c.chat_id}`} />
          </View>
        ))}
        {!chats.data?.length && <Text style={[k.small, { padding: 16 }]}>No earlier chats for {subject}.</Text>}
      </Sheet>
    </StackScreen>
  );
}

function Messages({ msgs, sending, subject }: { msgs: Msg[]; sending: boolean; subject: string }) {
  const ref = useRef<FlatList>(null);
  const end = () => setTimeout(() => ref.current?.scrollToEnd({ animated: true }), 60);
  return (
    <FlatList ref={ref} data={msgs} keyExtractor={(_, i) => String(i)} contentContainerStyle={s.list} testID="tutor-messages"
      onContentSizeChange={end} keyboardShouldPersistTaps="handled"
      ListEmptyComponent={<View style={s.empty}><Feather name="zap" size={30} color={C.muted} /><Text style={[k.body, { textAlign: "center" }]}>Ask me anything about {subject}. I'll use your school's approved materials first.</Text></View>}
      ListFooterComponent={<>{sending && <Thinking />}<Text style={s.disclaimer}>AI Tutor can make mistakes. Check important facts with your teacher.</Text></>}
      renderItem={({ item, index }) => <Bubble m={item} i={index} onGrow={end} />} />
  );
}

function Bubble({ m, i, onGrow }: { m: Msg; i: number; onGrow: () => void }) {
  const b = useBrand();
  const toast = useToast();
  const [shown, setShown] = useState(m.reveal ? 0 : m.content.length);
  useEffect(() => {
    if (shown >= m.content.length) return undefined;
    const step = Math.max(8, Math.ceil(m.content.length / 45));
    const t = setTimeout(() => { setShown((v) => Math.min(m.content.length, v + step)); onGrow(); }, 22);
    return () => clearTimeout(t);
  }, [shown, m.content.length, onGrow]);
  if (m.role === "user") {
    return <View style={[s.user, { backgroundColor: b.ink }]} testID={`tutor-msg-user-${i}`}><Text style={s.userText}>{m.content}</Text></View>;
  }
  if (m.role === "error") {
    return <View style={s.err} testID={`tutor-msg-error-${i}`}><Feather name="info" size={16} color={C.warning} /><Text style={s.errText}>{m.content}</Text></View>;
  }
  const done = shown >= m.content.length;
  return (
    <View style={s.ai} testID={`tutor-msg-assistant-${i}`}>
      <Markdown text={done ? m.content : m.content.slice(0, shown)} testID={`tutor-answer-${i}`} />
      {done && m.grounded && m.used_item_titles?.length ? (
        <View style={s.chips}>{m.used_item_titles.map((t: any, j: number) => (
          <View key={j} style={[s.src, { backgroundColor: b.soft }]}><Feather name="book" size={11} color={b.ink} /><Text style={[s.srcText, { color: b.ink }]} numberOfLines={1}>Based on: {t.title}</Text></View>
        ))}</View>
      ) : null}
      {done && m.grounded === false && <Text style={s.general} testID={`tutor-general-${i}`}>General explanation — not from your school's materials</Text>}
      {done && (
        <Pressable onPress={async () => { await Clipboard.setStringAsync(m.content); toast("Answer copied"); }} style={s.copy} hitSlop={8} testID={`tutor-copy-${i}`}>
          <Feather name="copy" size={14} color={C.muted} /><Text style={s.copyText}>Copy</Text>
        </Pressable>
      )}
    </View>
  );
}

function Thinking() {
  const a = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.timing(a, { toValue: 1, duration: 1100, useNativeDriver: true }));
    loop.start();
    return () => loop.stop();
  }, [a]);
  return (
    <View style={[s.ai, s.thinking]} testID="tutor-thinking">
      {[0, 1, 2].map((i) => (
        <Animated.View key={i} style={[s.dot, { opacity: a.interpolate({ inputRange: [0, (i + 1) / 4, 1], outputRange: [0.3, 1, 0.3] }) }]} />
      ))}
      <Text style={k.small}>Thinking…</Text>
    </View>
  );
}

function Composer({ subject, sending, onSend }: { subject: string; sending: boolean; onSend: (t: string) => Promise<boolean> }) {
  const b = useBrand();
  const [text, setText] = useState("");
  const go = async () => {
    const t = text.trim();
    if (!t || sending) return;
    setText("");
    const ok = await onSend(t);
    if (!ok) setText(t);
  };
  return (
    <View style={s.composer}>
      <TextInput value={text} onChangeText={setText} placeholder={`Ask about ${subject}…`} placeholderTextColor={C.muted} multiline maxLength={2000} style={s.input} testID="tutor-input" />
      <Pressable onPress={go} disabled={sending || !text.trim()} testID="tutor-send-btn" accessibilityLabel="Send question"
        style={[s.send, { backgroundColor: b.color }, (sending || !text.trim()) && { opacity: 0.45 }]}>
        <Feather name="send" size={20} color={b.onColor} />
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  hBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center", borderRadius: 14 },
  list: { padding: 16, gap: 12, paddingBottom: 12 },
  empty: { alignItems: "center", gap: 10, paddingVertical: 48, paddingHorizontal: 24 },
  user: { alignSelf: "flex-end", maxWidth: "85%", borderRadius: 20, borderBottomRightRadius: 6, paddingHorizontal: 14, paddingVertical: 10 },
  userText: { fontFamily: fonts.body, fontSize: 16, color: "#fff", lineHeight: 22 },
  ai: { alignSelf: "flex-start", maxWidth: "94%", backgroundColor: "#fff", borderWidth: 1, borderColor: C.border, borderRadius: 20, borderBottomLeftRadius: 6, padding: 14, gap: 8 },
  thinking: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.muted },
  err: { flexDirection: "row", gap: 8, alignItems: "flex-start", padding: 12, borderRadius: 14, backgroundColor: C.warningSoft },
  errText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 14, color: "#7C3E06", lineHeight: 20 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  src: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, maxWidth: "100%" },
  srcText: { fontFamily: fonts.bodySemi, fontSize: 11 },
  general: { fontFamily: fonts.bodySemi, fontSize: 12, color: C.warning },
  copy: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", minHeight: 28 },
  copyText: { fontFamily: fonts.bodySemi, fontSize: 12, color: C.muted },
  disclaimer: { fontFamily: fonts.body, fontSize: 12, color: C.muted, textAlign: "center", marginTop: 8 },
  composer: { flexDirection: "row", alignItems: "flex-end", gap: 8, padding: 10, backgroundColor: "#fff", borderTopWidth: 1, borderTopColor: C.border },
  input: { flex: 1, minHeight: 48, maxHeight: 130, borderRadius: 22, backgroundColor: C.surfaceTertiary, paddingHorizontal: 16, paddingTop: 13, paddingBottom: 12, fontFamily: fonts.body, fontSize: 16, color: C.onSurface },
  send: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
});
