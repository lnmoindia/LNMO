// Picking images/PDFs, building multipart parts, and opening authed PDFs/files.
import { Platform, Linking } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { API, ApiError, authHeaders } from "./api";

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

// Append a picked file to FormData — RN wants {uri,name,type}; the web wants a Blob/File.
export async function appendFile(fd: FormData, field: string, f: Picked) {
  if (Platform.OS === "web") {
    const blob = f.file || (await (await fetch(f.uri)).blob());
    fd.append(field, blob, f.name);
  } else {
    fd.append(field, { uri: f.uri, name: f.name, type: f.type } as any);
  }
}

const safe = (s: string) => s.replace(/[^a-zA-Z0-9._-]+/g, "-");

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
