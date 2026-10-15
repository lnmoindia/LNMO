// Crop step: the photo with 4 draggable corner handles (image-pixel coords), edge lines, and a magnifier loupe.
import { useMemo, useRef, useState } from "react";
import { PanResponder, StyleSheet, View } from "react-native";
import { Image } from "expo-image";

export type Pt = [number, number];
export const defaultCorners = (w: number, h: number, inset = 0.08): Pt[] => [
  [w * inset, h * inset], [w * (1 - inset), h * inset], [w * (1 - inset), h * (1 - inset)], [w * inset, h * (1 - inset)],
];

const HANDLE = 44;
const LOUPE = 110;
const ZOOM = 2.2;

function Edge({ a, b, color }: { a: Pt; b: Pt; color: string }) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.sqrt(dx * dx + dy * dy);
  return (
    <View pointerEvents="none" style={{
      position: "absolute", left: (a[0] + b[0]) / 2 - len / 2, top: (a[1] + b[1]) / 2 - 1, width: len, height: 2.5,
      backgroundColor: color, transform: [{ rotate: `${Math.atan2(dy, dx)}rad` }],
    }} />
  );
}

function Handle({ p, scale, w, h, color, onMove, onActive, testID }: {
  p: Pt; scale: number; w: number; h: number; color: string; onMove: (p: Pt) => void; onActive: (on: boolean) => void; testID: string;
}) {
  const start = useRef<Pt>(p);
  const cur = useRef<Pt>(p);
  const cfg = useRef({ scale, w, h, onMove, onActive });
  cur.current = p;
  cfg.current = { scale, w, h, onMove, onActive };
  const pan = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: () => { start.current = cur.current; cfg.current.onActive(true); },
    onPanResponderMove: (_, g) => {
      const c = cfg.current;
      c.onMove([Math.min(c.w - 1, Math.max(0, start.current[0] + g.dx / c.scale)), Math.min(c.h - 1, Math.max(0, start.current[1] + g.dy / c.scale))]);
    },
    onPanResponderRelease: () => cfg.current.onActive(false),
    onPanResponderTerminate: () => cfg.current.onActive(false),
  }), []);
  return (
    <View {...pan.panHandlers} testID={testID} style={[s.handle, { left: p[0] * scale - HANDLE / 2, top: p[1] * scale - HANDLE / 2 }]}>
      <View style={[s.dot, { borderColor: color }]} />
    </View>
  );
}

export function CropView({ uri, w, h, maxW, maxH, corners, setCorners, color }: {
  uri: string; w: number; h: number; maxW: number; maxH: number; corners: Pt[]; setCorners: (fn: (c: Pt[]) => Pt[]) => void; color: string;
}) {
  const scale = Math.min(maxW / w, maxH / h);
  const dw = w * scale;
  const dh = h * scale;
  const [active, setActive] = useState<number | null>(null);
  const disp = corners.map(([x, y]) => [x * scale, y * scale] as Pt);
  const ap = active != null ? disp[active] : null;
  const loupeLeft = ap && ap[0] < dw / 2 ? dw - LOUPE - 8 : 8;
  return (
    <View style={{ width: dw, height: dh }} testID="scan-crop-view">
      <Image source={{ uri }} style={{ width: dw, height: dh }} contentFit="fill" />
      {disp.map((a, i) => <Edge key={i} a={a} b={disp[(i + 1) % 4]} color={color} />)}
      {corners.map((p, i) => (
        <Handle key={i} p={p} scale={scale} w={w} h={h} color={color} testID={`scan-corner-${i}`}
          onActive={(on) => setActive(on ? i : null)}
          onMove={(np) => setCorners((cs) => cs.map((c, j) => (j === i ? np : c)))} />
      ))}
      {ap && (
        <View pointerEvents="none" style={[s.loupe, { left: loupeLeft, borderColor: color }]} testID="scan-loupe">
          <Image source={{ uri }} contentFit="fill"
            style={{ position: "absolute", width: dw * ZOOM, height: dh * ZOOM, left: LOUPE / 2 - ap[0] * ZOOM, top: LOUPE / 2 - ap[1] * ZOOM }} />
          <View style={[s.crossH, { backgroundColor: color }]} /><View style={[s.crossV, { backgroundColor: color }]} />
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  handle: { position: "absolute", width: HANDLE, height: HANDLE, alignItems: "center", justifyContent: "center" },
  dot: { width: 24, height: 24, borderRadius: 12, borderWidth: 3, backgroundColor: "rgba(255,255,255,0.85)" },
  loupe: { position: "absolute", top: 8, width: LOUPE, height: LOUPE, borderRadius: LOUPE / 2, borderWidth: 3, overflow: "hidden", backgroundColor: "#000" },
  crossH: { position: "absolute", left: LOUPE / 2 - 10, top: LOUPE / 2 - 1, width: 20, height: 2 },
  crossV: { position: "absolute", left: LOUPE / 2 - 1, top: LOUPE / 2 - 10, width: 2, height: 20 },
});
