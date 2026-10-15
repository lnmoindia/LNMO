// Start a new conversation with the class teacher or the school office (POST /chat/threads).
import { useState } from "react";
import { Text, View } from "react-native";
import { router } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useChild } from "@/src/state/child";
import { useToast } from "@/src/state/toast";
import { api } from "@/src/lib/api";
import { StackScreen } from "@/src/ui/Screen";
import { Button, Chip, k } from "@/src/ui/kit";
import { TextField } from "@/src/ui/inputs";
import { fullName } from "@/src/lib/format";

export default function NewMessage() {
  const { children, childId } = useChild();
  const qc = useQueryClient();
  const toast = useToast();
  const [child, setChild] = useState(childId);
  const [target, setTarget] = useState<"class_teacher" | "office">("class_teacher");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("student_id", child); fd.append("target", target); fd.append("body", text);
      const d = await api.postForm("/chat/threads", fd);
      toast("Message sent");
      qc.invalidateQueries({ queryKey: ["threads"] });
      router.replace(`/thread/${d.thread.id}`);
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  return (
    <StackScreen title="New message" testID="new-message-screen" keyboard>
      {(children?.length || 0) > 1 && (
        <View style={{ gap: 8 }}>
          <Text style={k.label}>About</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {children!.map((c: any) => <Chip key={c.id} label={fullName(c)} active={child === c.id} onPress={() => setChild(c.id)} testID={`new-message-child-${c.id}`} />)}
          </View>
        </View>
      )}
      <View style={{ gap: 8 }}>
        <Text style={k.label}>To</Text>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Chip label="Class teacher" active={target === "class_teacher"} onPress={() => setTarget("class_teacher")} testID="new-message-target-teacher" />
          <Chip label="School office" active={target === "office"} onPress={() => setTarget("office")} testID="new-message-target-office" />
        </View>
      </View>
      <TextField label="Message" multiline maxLength={2000} value={text} onChangeText={setText} placeholder="Write your message…" testID="new-message-body-input" />
      <Button label="Send" icon="send" onPress={send} loading={busy} disabled={!text.trim() || !child} testID="new-message-send-btn" />
    </StackScreen>
  );
}
