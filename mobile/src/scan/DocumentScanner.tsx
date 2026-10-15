// Reusable document scanner (no AI, Expo Go friendly): Capture → Crop → Adjust → Pages → Attach.
// Server does the 4-point warp + filters (/api/scan/process) and the multi-page PDF (/api/scan/pdf).
import { useState } from "react";
import { ActivityIndicator, Image as RNImage, Modal, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Image } from "expo-image";
import { Feather } from "@expo/vector-icons";
import { api } from "@/src/lib/api";
import { appendFile, downloadToPicked, kb, pickImage, type Picked } from "@/src/lib/files";
import { useBrand } from "@/src/state/auth";
import { Button, C, Chip, k } from "@/src/ui/kit";
import { fonts } from "@/src/theme";
import { CropView, defaultCorners, type Pt } from "./CropView";

type Mode = "document" | "original" | "grayscale";
type Page = { key: string; src: Picked; corners: Pt[]; mode: Mode; rotation: number; out?: { id: string; preview: string; size: number } };
type Step = "capture" | "crop" | "adjust" | "pages";
const STEPS: [Step | "attach", string][] = [["capture", "Capture"], ["crop", "Crop"], ["adjust", "Adjust"], ["pages", "Pages"], ["attach", "Attach"]];
const MAX_SCAN = 15 * 1024 * 1024;

const sizeOf = (uri: string) => new Promise<[number, number]>((res, rej) => RNImage.getSize(uri, (w, h) => res([w, h]), rej));

export function DocumentScanner({ open, onClose, onDone, name }: { open: boolean; onClose: () => void; onDone: (files: Picked[]) => void; name: string }) {
  const b = useBrand();
  const win = useWindowDimensions();
  const [pages, setPages] = useState<Page[]>([]);
  const [idx, setIdx] = useState(0);
  const [step, setStep] = useState<Step>("capture");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [retaking, setRetaking] = useState(false);
  const page = pages[idx];
  const reset = () => { setPages([]); setIdx(0); setStep("capture"); setErr(""); setBusy(""); setRetaking(false); };
  const close = () => { reset(); onClose(); };
  const patch = (p: Partial<Page>) => setPages((ps) => ps.map((x, i) => (i === idx ? { ...x, ...p } : x)));

  const capture = async (src: "camera" | "library") => {
    setErr("");
    try {
      const f = await pickImage(src, 0.9);
      if (!f) return;
      if (f.size && f.size > MAX_SCAN) { setErr("That photo is larger than 15 MB — try again with a smaller photo."); return; }
      const [w, h] = f.width && f.height ? [f.width, f.height] : await sizeOf(f.uri);
      const np: Page = { key: `${Date.now()}`, src: { ...f, width: w, height: h }, corners: defaultCorners(w, h), mode: "document", rotation: 0 };
      if (page && (retaking || !page.out)) setPages((ps) => ps.map((x, i) => (i === idx ? np : x)));
      else { setPages((ps) => [...ps, np]); setIdx(pages.length); }
      setRetaking(false);
      setStep("crop");
    } catch (e: any) { setErr(e.message || "Couldn't open the camera or gallery"); }
  };

  const process = async (p: Page, changes: Partial<Page> = {}) => {
    const q = { ...p, ...changes };
    setBusy("Straightening and cleaning the page…"); setErr("");
    try {
      const fd = new FormData();
      await appendFile(fd, "file", q.src);
      fd.append("corners", JSON.stringify(q.corners.map(([x, y]) => [Math.round(x), Math.round(y)])));
      fd.append("img_w", String(q.src.width)); fd.append("img_h", String(q.src.height));
      fd.append("mode", q.mode); fd.append("rotation", String(q.rotation));
      const d = await api.postForm("/scan/process", fd);
      patch({ ...changes, out: { id: d.id, preview: d.preview, size: d.size } });
      setStep("adjust");
    } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  const finish = async (asImages: boolean) => {
    setBusy(asImages ? "Preparing images…" : "Making your PDF…"); setErr("");
    try {
      const ready = pages.filter((p) => p.out);
      if (asImages) {
        const files = await Promise.all(ready.map((p, i) => downloadToPicked(`/scan/pages/${p.out!.id}.jpg`, name.replace(/\.pdf$/i, `_p${i + 1}.jpg`), "image/jpeg")));
        onDone(files);
      } else {
        const d = await api.post("/scan/pdf", { page_ids: ready.map((p) => p.out!.id), name });
        const f = await downloadToPicked(`/scan/files/${d.id}.pdf`, d.name, "application/pdf");
        onDone([{ ...f, size: f.size || d.size, scanId: d.id, note: `PDF · ${d.pages} page${d.pages > 1 ? "s" : ""} · ${kb(f.size || d.size)}` }]);
      }
      reset(); onClose();
    } catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  const move = (i: number, d: number) => setPages((ps) => { const a = [...ps]; const j = i + d; if (j < 0 || j >= a.length) return ps; [a[i], a[j]] = [a[j], a[i]]; return a; });
  const cur = STEPS.findIndex(([st]) => st === step);
  const boxW = Math.min(win.width - 32, 560);
  const boxH = Math.max(260, win.height - 300);

  return (
    <Modal visible={open} animationType="slide" onRequestClose={close}>
      <SafeAreaView style={s.root} testID="scanner-modal">
        <View style={s.top}>
          <Pressable onPress={close} style={s.icon} testID="scanner-close"><Feather name="x" size={24} color={C.onSurface} /></Pressable>
          <Text style={s.title}>Scan document</Text>
          <View style={s.icon} />
        </View>
        <View style={s.steps} testID="scanner-steps">
          {STEPS.map(([st, l], i) => (
            <View key={st} style={s.stepItem}>
              <View style={[s.stepDot, { backgroundColor: i <= cur ? b.color : C.border }]} />
              <Text style={[s.stepText, i === cur && { color: C.onSurface, fontFamily: fonts.bodyBold }]}>{l}</Text>
            </View>
          ))}
        </View>
        {err ? <View style={s.err} testID="scanner-error"><Feather name="alert-circle" size={16} color={C.error} /><Text style={s.errText}>{err}</Text></View> : null}
        <View style={{ flex: 1 }}>
          {step === "capture" && (
            <View style={s.center} testID="scanner-capture">
              <Feather name="file-text" size={44} color={b.ink} />
              <Text style={[k.h2, { textAlign: "center" }]}>{pages.length ? `Page ${retaking ? idx + 1 : pages.length + 1}` : "Photograph your page"}</Text>
              <Text style={[k.body, { textAlign: "center" }]}>Lay the page flat in good light. You'll adjust the corners next.</Text>
              <Button label="Take photo" icon="camera" onPress={() => capture("camera")} style={s.wide} testID="scanner-camera-btn" />
              <Button label="Choose from gallery" icon="image" variant="outline" onPress={() => capture("library")} style={s.wide} testID="scanner-gallery-btn" />
              {pages.some((p) => p.out) && <Button label="Back to pages" variant="ghost" onPress={() => { setRetaking(false); setStep("pages"); }} testID="scanner-back-to-pages" />}
            </View>
          )}
          {step === "crop" && page && (
            <View style={{ flex: 1, alignItems: "center", gap: 12, paddingTop: 8 }}>
              <Text style={k.small}>Drag the 4 corners onto the page edges</Text>
              <CropView uri={page.src.uri} w={page.src.width!} h={page.src.height!} maxW={boxW} maxH={boxH} corners={page.corners}
                setCorners={(fn) => setPages((ps) => ps.map((x, i) => (i === idx ? { ...x, corners: fn(x.corners) } : x)))} color={b.color} />
              <View style={s.row}>
                <Button small variant="outline" icon="rotate-ccw" label="Reset" onPress={() => patch({ corners: defaultCorners(page.src.width!, page.src.height!) })} testID="scanner-reset-corners" />
                <Button small variant="outline" icon="maximize" label="Full image" onPress={() => patch({ corners: defaultCorners(page.src.width!, page.src.height!, 0) })} testID="scanner-full-image" />
                <Button small icon="check" label="Next" onPress={() => process(page)} testID="scanner-crop-next" />
              </View>
            </View>
          )}
          {step === "adjust" && page?.out && (
            <ScrollView contentContainerStyle={{ alignItems: "center", gap: 12, padding: 16 }}>
              <Image source={{ uri: page.out.preview }} style={{ width: boxW, height: Math.max(220, boxH - 120) }} contentFit="contain" testID="scanner-preview" />
              <View style={s.row}>
                {(["document", "original", "grayscale"] as Mode[]).map((m) => (
                  <Chip key={m} label={m === "document" ? "Document" : m === "original" ? "Original" : "Grayscale"} active={page.mode === m} onPress={() => process(page, { mode: m })} testID={`scanner-filter-${m}`} />
                ))}
              </View>
              <View style={s.row}>
                <Button small variant="outline" icon="rotate-ccw" label="Left" onPress={() => process(page, { rotation: (page.rotation + 270) % 360 })} testID="scanner-rotate-left" />
                <Button small variant="outline" icon="rotate-cw" label="Right" onPress={() => process(page, { rotation: (page.rotation + 90) % 360 })} testID="scanner-rotate-right" />
                <Button small variant="outline" icon="crop" label="Re-crop" onPress={() => setStep("crop")} testID="scanner-recrop" />
                <Button small variant="outline" icon="camera" label="Retake" onPress={() => { setRetaking(true); setStep("capture"); }} testID="scanner-retake" />
              </View>
              <Button label="Save page" icon="check" onPress={() => setStep("pages")} style={s.wide} testID="scanner-save-page" />
            </ScrollView>
          )}
          {step === "pages" && (
            <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }} testID="scanner-pages">
              <Text style={k.h2}>{pages.filter((p) => p.out).length} page{pages.length > 1 ? "s" : ""}</Text>
              {pages.map((p, i) => p.out && (
                <View key={p.key} style={s.thumbRow} testID={`scanner-page-${i}`}>
                  <Pressable onPress={() => { setIdx(i); setStep("adjust"); }}><Image source={{ uri: p.out.preview }} style={s.thumb} contentFit="cover" /></Pressable>
                  <View style={{ flex: 1 }}><Text style={k.label}>Page {i + 1}</Text><Text style={k.small}>{p.mode} · {kb(p.out.size)}</Text></View>
                  <Pressable onPress={() => move(i, -1)} style={s.icon} testID={`scanner-page-up-${i}`}><Feather name="arrow-up" size={20} color={C.onSurface} /></Pressable>
                  <Pressable onPress={() => move(i, 1)} style={s.icon} testID={`scanner-page-down-${i}`}><Feather name="arrow-down" size={20} color={C.onSurface} /></Pressable>
                  <Pressable onPress={() => { setPages((ps) => ps.filter((_, j) => j !== i)); setIdx(0); }} style={s.icon} testID={`scanner-page-delete-${i}`}><Feather name="trash-2" size={20} color={C.error} /></Pressable>
                </View>
              ))}
              <Button label="Add page" icon="plus" variant="outline" onPress={() => { setRetaking(false); setStep("capture"); }} testID="scanner-add-page" />
              <Button label="Done — attach as one PDF" icon="file-text" variant="success" disabled={!pages.some((p) => p.out)} onPress={() => finish(false)} testID="scanner-done-pdf" />
              <Button label="Attach as separate images" variant="ghost" disabled={!pages.some((p) => p.out)} onPress={() => finish(true)} testID="scanner-done-images" />
            </ScrollView>
          )}
          {busy ? (
            <View style={s.busy} testID="scanner-busy"><ActivityIndicator size="large" color="#fff" /><Text style={s.busyText}>{busy}</Text></View>
          ) : null}
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 8, minHeight: 52 },
  title: { fontFamily: fonts.heading, fontSize: 19, color: C.onSurface },
  icon: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  steps: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 20, paddingBottom: 8 },
  stepItem: { alignItems: "center", gap: 4, flex: 1 },
  stepDot: { height: 4, alignSelf: "stretch", marginHorizontal: 3, borderRadius: 2 },
  stepText: { fontFamily: fonts.bodySemi, fontSize: 11, color: C.muted },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 14, padding: 24 },
  wide: { alignSelf: "stretch", maxWidth: 420, width: "100%" },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "center" },
  err: { flexDirection: "row", gap: 8, alignItems: "center", marginHorizontal: 16, padding: 12, borderRadius: 12, backgroundColor: C.errorSoft },
  errText: { flex: 1, fontFamily: fonts.bodySemi, fontSize: 13, color: C.error },
  thumbRow: { flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: 16, backgroundColor: "#fff", borderWidth: 1, borderColor: C.border },
  thumb: { width: 56, height: 72, borderRadius: 8, backgroundColor: C.surfaceTertiary },
  busy: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: "rgba(15,23,42,0.6)", alignItems: "center", justifyContent: "center", gap: 12 },
  busyText: { fontFamily: fonts.bodySemi, fontSize: 15, color: "#fff" },
});
