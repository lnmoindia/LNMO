// Picking images/PDFs, building multipart parts, and opening authed PDFs/files.
import { Platform, Linking } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import { API, ApiError, authHeaders } from "./api";

const safe = (s: string) => s.replace(/[^a-zA-Z0-9._-]+/g, "-");
export type Picked = { uri: string; name: string; type: string; size?: number; file?: any; width?: number; height?: number; note?: string; scanId?: string };
export const MAX_BYTES = 5 * 1024 * 1024;

const extType = (name: string, fallback: string) => {
  const n = name.toLowerCase();
  if (n.endsWith(".png")) return "image/png";
  if (n.endsWith(".webp")) return "image/webp";
  if (n.endsWith(".heic")) return "image/heic";
  if (n.endsWith(".pdf")) return "application/pdf";
  if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
  return fallback;
};

export async function pickImage(source: "library" | "camera", quality = 0.7): Promise<Picked | null> {
  const perm = source === "camera"
    ? await ImagePicker.requestCameraPermissionsAsync()
    : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!perm.granted && Platform.OS !== "web") throw new Error("Permission needed — allow access in Settings to attach a photo.");
  const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality, allowsEditing: false };
  const r = source === "camera" ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
  if (r.canceled || !r.assets?.length) return null;
  const a = r.assets[0];
  const name = a.fileName || `photo-${Date.now()}.jpg`;
  const type = a.mimeType || extType(name, "image/jpeg");
  return { uri: a.uri, name, type: type === "image/jpg" ? "image/jpeg" : type, size: a.fileSize || a.file?.size, file: a.file, width: a.width, height: a.height };
}

export async function pickPdf(): Promise<Picked | null> {
  const r = await DocumentPicker.getDocumentAsync({ type: ["application/pdf", "image/jpeg", "image/png", "image/webp"], copyToCacheDirectory: true });
  if (r.canceled || !r.assets?.length) return null;
  const a = r.assets[0];
  return { uri: a.uri, name: a.name, type: a.mimeType || extType(a.name, "application/pdf"), size: a.size, file: a.file };
}

const isPhoto = (t: string) => /^image\/(jpeg|jpg|png|webp|heic|heif)$/i.test(t || "");
const jpgName = (n: string) => `${(n || "photo").replace(/\.[a-z0-9]+$/i, "").replace(/[^a-zA-Z0-9._-]+/g, "-") || "photo"}.jpg`;

// Downscale (long side ≤ maxSide) + JPEG ~0.75 before upload. Small JPEGs pass through untouched.
export async function prepareImage(f: Picked, maxSide = 2000, crop?: "square"): Promise<Picked> {
  if (!isPhoto(f.type)) return f;
  const w = f.width || 0, h = f.height || 0;
  const small = w && h && Math.max(w, h) <= maxSide && (f.size || 0) > 0 && (f.size || 0) <= 1_500_000 && /jpe?g/i.test(f.type);
  if (small && !crop) return f;
  try {
    let W = w, H = h;
    if (!W || !H) { const probe = await ImageManipulator.manipulate(f.uri).renderAsync(); W = probe.width; H = probe.height; }
    const ctx = ImageManipulator.manipulate(f.uri);
    if (crop === "square") { const side = Math.min(W, H); ctx.crop({ originX: Math.floor((W - side) / 2), originY: Math.floor((H - side) / 2), width: side, height: side }); W = H = side; }
    if (Math.max(W, H) > maxSide) ctx.resize(W >= H ? { width: maxSide } : { height: maxSide });
    const img = await ctx.renderAsync();
    const out = await img.saveAsync({ compress: 0.75, format: SaveFormat.JPEG });
    let size: number | undefined;
    if (Platform.OS !== "web") { try { size = ((await FileSystem.getInfoAsync(out.uri)) as any)?.size; } catch { /* ignore */ } }
    return { ...f, uri: out.uri, width: out.width, height: out.height, type: "image/jpeg", name: jpgName(f.name), size, file: undefined };
  } catch (e) {
    console.warn("[upload] image downscale failed, sending the original", e);
    return f;
  }
}

// content:// (Android gallery/providers) → a file:// copy in the cache so multipart upload can read it.
async function fileUri(f: Picked) {
  if (Platform.OS === "web" || !f.uri.startsWith("content://")) return f.uri;
  const dest = `${FileSystem.cacheDirectory}up-${Date.now()}-${safe(f.name || "file")}`;
  await FileSystem.copyAsync({ from: f.uri, to: dest });
  return dest;
}

// Append a picked file to FormData (images are downscaled first). RN wants {uri,name,type}; the web wants a Blob/File.
export async function appendFile(fd: FormData, field: string, f0: Picked, maxSide = 2000) {
  const f = await prepareImage(f0, maxSide);
  if (Platform.OS === "web") {
    const blob = f.file || (await (await fetch(f.uri)).blob());
    fd.append(field, blob, f.name);
  } else {
    const type = f.type === "image/jpg" ? "image/jpeg" : f.type || "application/octet-stream";
    fd.append(field, { uri: await fileUri(f), name: f.name || (type === "image/jpeg" ? "x.jpg" : "file"), type } as any);
  }
}
// Images are resized before upload, so only PDFs/other files are size-checked up front.
export const tooBig = (f: Picked, max = MAX_BYTES) => !isPhoto(f.type) && Boolean(f.size && f.size > max);


// Download an authenticated file (receipt / statement PDF, attachments) and open the share sheet.
export async function openAuthedFile(path: string, filename: string, mime = "application/pdf") {
  const url = `${API}${path}`;
  if (Platform.OS === "web") {
    const res = await fetch(url, { headers: { ...authHeaders(), "X-Client": "mobile" } });
    if (!res.ok) throw new ApiError(res.status, null, "Couldn't download the file");
    const blob = await res.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href; a.download = filename; a.target = "_blank";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 4000);
    return;
  }
  const dest = `${FileSystem.cacheDirectory}${Date.now()}-${safe(filename)}`;
  const r = await FileSystem.downloadAsync(url, dest, { headers: { ...authHeaders(), "X-Client": "mobile" } });
  if (r.status >= 400) throw new ApiError(r.status, null, "Couldn't download the file");
  const type = r.headers?.["content-type"] || r.headers?.["Content-Type"] || mime;
  if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(r.uri, { mimeType: type, dialogTitle: filename, UTI: type.includes("pdf") ? "com.adobe.pdf" : undefined });
  else await Linking.openURL(r.uri);
}

// Download an authenticated server file into something appendFile() can upload (cache file / web File).
export async function downloadToPicked(path: string, name: string, type: string): Promise<Picked> {
  const url = `${API}${path}`;
  if (Platform.OS === "web") {
    const res = await fetch(url, { headers: { ...authHeaders(), "X-Client": "mobile" } });
    if (!res.ok) throw new ApiError(res.status, null, "Couldn't fetch the scanned file");
    const blob = await res.blob();
    const file = new File([blob], name, { type });
    return { uri: URL.createObjectURL(blob), name, type, size: blob.size, file };
  }
  const dest = `${FileSystem.cacheDirectory}${Date.now()}-${safe(name)}`;
  const r = await FileSystem.downloadAsync(url, dest, { headers: { ...authHeaders(), "X-Client": "mobile" } });
  if (r.status >= 400) throw new ApiError(r.status, null, "Couldn't fetch the scanned file");
  const info: any = await FileSystem.getInfoAsync(r.uri);
  return { uri: r.uri, name, type, size: info?.size };
}

export const kb = (n?: number) => (!n ? "" : n > 1024 * 1024 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
