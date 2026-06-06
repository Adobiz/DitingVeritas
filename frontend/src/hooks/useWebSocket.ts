import { useEffect, useRef, useState, useCallback } from "react";

export interface TranslationMessage {
  type: string;
  payload: Record<string, any>;
  timestamp: number;
}

interface Options {
  url?: string;
  onMessage?: (msg: TranslationMessage) => void;
}

export function useWebSocket({ url = "ws://127.0.0.1:8765/ws/translate", onMessage }: Options = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState("idle");
  const onMsgRef = useRef(onMessage);
  onMsgRef.current = onMessage;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    console.log("[WS] 连接中…", url);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => { setConnected(true); console.log("[WS] 已连接"); };
    ws.onmessage = (e) => {
      try {
        const msg: TranslationMessage = JSON.parse(e.data);
        if (msg.type === "status") setStatus(msg.payload?.status || "");
        onMsgRef.current?.(msg);
      } catch { /* ignore */ }
    };
    ws.onclose = () => { setConnected(false); wsRef.current = null; console.log("[WS] 断开"); };
    ws.onerror = () => console.log("[WS] 连接失败");
  }, [url]);

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
      console.log("[WS] 发送:", data);
    } else {
      console.log("[WS] 未连接，无法发送");
    }
  }, []);

  useEffect(() => { connect(); return () => wsRef.current?.close(); }, [connect]);

  return { connected, status, connect, send };
}
