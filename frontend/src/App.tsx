import { useState, useCallback } from "react";
import { useWebSocket, TranslationMessage } from "./hooks/useWebSocket";
import { SubtitleOverlay } from "./components/SubtitleOverlay";

const WS = "ws://127.0.0.1:8765/ws/translate";

export default function App() {
  const [source, setSource] = useState("");
  const [translation, setTranslation] = useState("");

  const onMsg = useCallback((msg: TranslationMessage) => {
    if (msg.type === "translation") {
      if (msg.payload.source_text) setSource(msg.payload.source_text);
      if (msg.payload.translation) setTranslation(msg.payload.translation);
    } else if (msg.type === "correction") {
      setTranslation(msg.payload.new_translation || "");
    }
  }, []);

  const { connected, status, connect, send } = useWebSocket({ url: WS, onMessage: onMsg });

  const handleStart = () => send({ type: "start" });
  const handleStop = () => { send({ type: "stop" }); setSource(""); setTranslation(""); };

  return (
    <div style={{ minHeight: "100vh", background: "#111", color: "#fff", padding: 40 }}>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>谛听·译真</h1>
      <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
        <button onClick={status === "running" ? handleStop : handleStart}
          disabled={!connected}
          title={!connected ? "请先启动后端 python main.py" : ""}
          style={{ padding: "8px 20px", borderRadius: 6, border: "none", cursor: connected ? "pointer" : "not-allowed",
            background: status === "running" ? "#ef4444" : "#4ade80", color: "#000", fontWeight: 600,
            opacity: connected ? 1 : 0.5 }}>
          {status === "running" ? "■ 停止" : "▶ 开始翻译"}
        </button>
        <button onClick={connect}
          style={{ padding: "8px 20px", borderRadius: 6, border: "1px solid #333", cursor: "pointer",
            background: "transparent", color: connected ? "#4ade80" : "#ef4444" }}>
          {connected ? "● 已连接" : "○ 重连"}
        </button>
      </div>
      <SubtitleOverlay
        sourceText={source}
        translation={translation}
        status={status}
        connected={connected}
      />
    </div>
  );
}
