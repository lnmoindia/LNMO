// Own profile photo (More → Profile): camera/gallery → square crop + resize → POST /photos/me (field "file"); DELETE removes.
// StudentPhotoButton: staff set a student's photo (POST /photos/students/{sid}); hidden after a 403.
import { useState } from "react";
import { Text, View } from "react-native";
import { useAuth } from "@/src/state/auth";
import { useToast } from "@/src/state/toast";
import { api, ApiError } from "@/src/lib/api";
import { appendFile, pickImage, prepareImage } from "@/src/lib/files";
import { Avatar, Sheet, confirm } from "./brandbits";
import { Button, Card, ListRow, k } from "./kit";

async function pickSquare(src: "camera" | "library") {
  const f = await pickImage(src, 0.9);
  return f ? prepareImage(f, 1024, "square") : null;
}
async function send(path: string, f: any) {
  const fd = new FormData();
  await appendFile(fd, "file", f, 1024);
  return api.postForm(path, fd, "Uploading photo");
}

function SourceSheet({ open, onClose, onPick, testID }: { open: boolean; onClose: () => void; onPick: (s: "camera" | "library") => void; testID: string }) {
  return (
    <Sheet open={open} onClose={onClose} title="Profile photo" testID={testID}>
      <ListRow icon="camera" title="Take a photo" onPress={() => onPick("camera")} testID={`${testID}-camera`} />
      <ListRow icon="image" title="Choose from gallery" onPress={() => onPick("library")} testID={`${testID}-gallery`} />
    </Sheet>
  );
}

export function MyPhotoCard() {
  const { user, refreshMe } = useAuth() as any;
  const toast = useToast();
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const pick = async (src: "camera" | "library") => {
    setSheet(false);
    try {
      const f = await pickSquare(src);
      if (!f) return;
      setBusy(true);
      await send("/photos/me", f);
      await refreshMe?.();
      toast("Profile photo updated");
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!(await confirm("Remove photo?", "Your initials will show instead.", "Remove"))) return;
    try { await api.del("/photos/me"); await refreshMe?.(); toast("Photo removed"); } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <Card style={{ flexDirection: "row", alignItems: "center", gap: 16 }} testID="my-photo-card">
      <Avatar name={user?.name || "?"} uri={user?.photo_url} size={80} testID="my-photo" />
      <View style={{ flex: 1, gap: 8 }}>
        <Text style={k.small}>Your photo is shown to your school on messages, timetables and class lists.</Text>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button small icon="camera" label={user?.photo_url ? "Change" : "Add photo"} onPress={() => setSheet(true)} loading={busy} testID="my-photo-change-btn" />
          {user?.photo_url ? <Button small variant="outline" icon="trash-2" label="Remove" onPress={remove} testID="my-photo-remove-btn" /> : null}
        </View>
      </View>
      <SourceSheet open={sheet} onClose={() => setSheet(false)} onPick={pick} testID="my-photo-sheet" />
    </Card>
  );
}

export function StudentPhotoButton({ sid, onDone }: { sid: string; onDone?: () => void }) {
  const toast = useToast();
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);
  if (denied) return null;
  const pick = async (src: "camera" | "library") => {
    setSheet(false);
    try {
      const f = await pickSquare(src);
      if (!f) return;
      setBusy(true);
      await send(`/photos/students/${sid}`, f);
      toast("Student photo updated"); onDone?.();
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 403) setDenied(true);
      toast(e.message, "error");
    } finally { setBusy(false); }
  };
  return (
    <>
      <Button small variant="outline" icon="camera" label="Set photo" onPress={() => setSheet(true)} loading={busy} testID="student-photo-btn" />
      <SourceSheet open={sheet} onClose={() => setSheet(false)} onPick={pick} testID="student-photo-sheet" />
    </>
  );
}
