import { useEffect, useState } from "react";

// One shared chat WebSocket per tab: auto-reconnect with backoff; after 3 failed connects we report "polling"
// so callers fall back to 10s polling, while still retrying the socket in the background.
const listeners = new Set();
const statusListeners = new Set();
let ws = null;
let status = "connecting";
let failures = 0;
let timer = null;
let users = 0;

const setStatus = (s) => { status = s; statusListeners.forEach((f) => f(s)); };
const url = () => `${process.env.REACT_APP_BACKEND_URL.replace(/^http/, "ws")}/api/ws/chat`;

function connect() {
  clearTimeout(timer);
  if (ws || users === 0) return;
  let opened = false;
  if (window.localStorage?.getItem("chatForcePoll") === "1" || /[?&]chatForcePoll=1/.test(window.location.search)) { setStatus("polling"); return; }
  try { ws = new WebSocket(url()); } catch { ws = null; failures += 1; return retry(); }
  ws.onopen = () => { opened = true; failures = 0; setStatus("live"); };
  ws.onmessage = (e) => {
    let ev; try { ev = JSON.parse(e.data); } catch { return; }
    listeners.forEach((f) => f(ev));
  };
  ws.onclose = (e) => {
    ws = null;
    if (e.code === 4403 && window.location.pathname !== "/change-password") window.location.assign("/change-password");
    if (e.code === 4400 || e.code === 4401 || e.code === 4403) { setStatus("polling"); return; }
    if (!opened) failures += 1;
    retry();
  };
}

function retry() {
  if (users === 0) return;
  setStatus(failures >= 3 ? "polling" : "reconnecting");
  const wait = Math.min(30000, 1000 * 2 ** Math.min(failures, 5));
  timer = setTimeout(connect, wait);
}

export function sendChat(ev) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(ev));
}

export function useChatSocket(onEvent) {
  const [s, setS] = useState(status);
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
      if (users === 0 && ws) { ws.close(); ws = null; }
    };
  }, [onEvent]);
  return s;
}

export const LiveBadge = ({ status: s }) => (
  <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide ${s === "live" ? "text-emerald-600" : "text-amber-600"}`} data-testid="chat-live-status" data-status={s}>
    <span className={`h-1.5 w-1.5 rounded-full ${s === "live" ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
    {s === "live" ? "Live" : s === "polling" ? "Auto-refresh" : "Reconnecting…"}
  </span>
);
