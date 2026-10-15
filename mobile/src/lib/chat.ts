// One shared chat WebSocket (same protocol as the web: /api/ws/chat). Mobile passes the
// token as ?token= (RN/web can't always set WS headers). After 3 failed connects callers
// fall back to 10s polling while we keep retrying in the background.
import { useEffect, useState } from "react";
import { BACKEND, getToken } from "./api";

export type ChatStatus = "connecting" | "live" | "reconnecting" | "polling";
type Ev = { type: string; thread_id?: string; name?: string; [k: string]: any };

const listeners = new Set<(e: Ev) => void>();
const statusListeners = new Set<(s: ChatStatus) => void>();
let ws: WebSocket | null = null;
let status: ChatStatus = "connecting";
let failures = 0;
let timer: any = null;
let users = 0;
let ping: any = null;

const setStatus = (s: ChatStatus) => { status = s; statusListeners.forEach((f) => f(s)); };
const url = () => `${BACKEND.replace(/^http/, "ws")}/api/ws/chat?token=${encodeURIComponent(getToken() || "")}`;

function connect() {
  clearTimeout(timer);
  if (ws || users === 0 || !getToken()) return;
  let opened = false;
  try { ws = new WebSocket(url()); } catch { ws = null; failures += 1; retry(); return; }
  ws.onopen = () => {
    opened = true; failures = 0; setStatus("live");
    clearInterval(ping);
    ping = setInterval(() => sendChat({ type: "ping" }), 25000);
  };
  ws.onmessage = (e) => {
    let ev: Ev;
    try { ev = JSON.parse(String(e.data)); } catch { return; }
    listeners.forEach((f) => f(ev));
  };
  ws.onclose = (e) => {
    ws = null;
    clearInterval(ping);
    if ([4400, 4401, 4403].includes(e.code)) { setStatus("polling"); return; }
    if (!opened) failures += 1;
    retry();
  };
  ws.onerror = () => { /* onclose follows */ };
}

function retry() {
  if (users === 0) return;
  setStatus(failures >= 3 ? "polling" : "reconnecting");
  timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** Math.min(failures, 5)));
}

export function sendChat(ev: Ev) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(ev));
}

export function closeChat() {
  clearTimeout(timer);
  clearInterval(ping);
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  setStatus("connecting");
}

export function useChatSocket(onEvent: ((e: Ev) => void) | null) {
  const [s, setS] = useState<ChatStatus>(status);
  useEffect(() => {
    if (!onEvent) return undefined;
    users += 1;
    statusListeners.add(setS);
    listeners.add(onEvent);
    connect();
    setS(status);
    return () => {
      users -= 1;
      statusListeners.delete(setS);
      listeners.delete(onEvent);
      if (users === 0) closeChat();
    };
  }, [onEvent]);
  return s;
}
