// Pick a screenshot/photo from the gallery or camera, with preview + remove.
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Image } from "expo-image";
import { Feather } from "@expo/vector-icons";
import { useToast } from "@/src/state/toast";
import { MAX_BYTES, pickImage, type Picked } from "@/src/lib/files";
import { Button, C, k } from "./kit";

export function PhotoPicker({ file, setFile, testID, label = "Payment screenshot" }: { file: Picked | null; setFile: (f: Picked | null) => void; testID: string; label?: string }) {
  const toast = useToast();
  const pick = async (src: "library" | "camera") => {
    try {
      const f = await pickImage(src);
      if (!f) return;
      if (f.size && f.size > MAX_BYTES) return toast("Image must be 5 MB or smaller", "error");
      setFile(f);
    } catch (e: any) { toast(e.message, "error"); }
  };
  return (
    <View style={{ gap: 8 }}>
      <Text style={k.label}>{label}</Text>
      {file ? (
        <View style={s.preview} testID={`${testID}-preview`}>
          <Image source={{ uri: file.uri }} style={s.img} contentFit="cover" />
          <Pressable onPress={() => setFile(null)} style={s.remove} hitSlop={8} testID={`${testID}-remove`}><Feather name="x" size={18} color="#fff" /></Pressable>
        </View>
      ) : (
        <View style={{ flexDirection: "row", gap: 10 }}>
          <Button label="Gallery" icon="image" variant="outline" onPress={() => pick("library")} style={{ flex: 1 }} testID={`${testID}-gallery-btn`} />
          <Button label="Camera" icon="camera" variant="outline" onPress={() => pick("camera")} style={{ flex: 1 }} testID={`${testID}-camera-btn`} />
        </View>
      )}
      <Text style={k.small}>JPG, PNG, HEIC or WEBP · max 5 MB</Text>
    </View>
  );
}

const s = StyleSheet.create({
  preview: { borderRadius: 18, overflow: "hidden", borderWidth: 1, borderColor: C.border },
  img: { width: "100%", height: 220, backgroundColor: C.surfaceTertiary },
  remove: { position: "absolute", top: 10, right: 10, width: 36, height: 36, borderRadius: 18, backgroundColor: "rgba(15,23,42,0.7)", alignItems: "center", justifyContent: "center" },
});
