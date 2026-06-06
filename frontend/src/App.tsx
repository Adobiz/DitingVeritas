import { useState, useCallback, useEffect, useRef } from "react";
import { useWebSocket, TranslationMessage } from "./hooks/useWebSocket";

const WS = "ws://127.0.0.1:8765/ws/translate";

export default function App() {
  return <ControlBall />;
}

function ControlBall() {
  const [expanded, setExpanded] = useState(false);
  const [settings, setSettings] = useState(false);
  const [devices, setDevices] = useState<{ id: number; name: string }[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [modelName, setModelName] = useState("");
  const [source, setSource] = useState("");
  const [translation, setTranslation] = useState("");
  const [showControls, setShowControls] = useState(true);
  const panelRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const onMsg = useCallback((msg: TranslationMessage) => {
    if (msg.type === "translation") {
      if (msg.payload.source_text) setSource(msg.payload.source_text);
      if (msg.payload.translation) setTranslation(msg.payload.translation);
    }
  }, []);
  const { connected, status, send, connect } = useWebSocket({ url: WS, onMessage: onMsg });

  const fetchDevices = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8765/api/devices");
      setDevices(await res.json());
    } catch {}
  };
  useEffect(() => { fetchDevices(); }, [connected]);

  const isRunning = status === "running";
  const toggle = () => {
    if (expanded) window.electronAPI?.collapseControl();
    else window.electronAPI?.expandControl();
    setExpanded(!expanded); setSettings(false);
  };
  const toggleSettings = () => {
    const next = !settings;
    setSettings(next);
    window.electronAPI?.setHeight(next ? 340 : 200);
  };
  const handleStart = () => send({ type: "start", device_index: deviceId ? Number(deviceId) : undefined });
  const handleStop = () => send({ type: "stop" });

  const hasTrans = translation && translation !== source;
  const q = !connected ? "#ef4444" : isRunning ? "#4ade80" : "#9ca3af";

  // 自适应窗口高度（设置打开时固定 340，否则跟随内容）
  useEffect(() => {
    if (!expanded) return;
    if (settings) { window.electronAPI?.setHeight(340); return; }
    if (!isRunning) { window.electronAPI?.setHeight(200); return; }
    const el = panelRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        const h = el.scrollHeight;
        window.electronAPI?.setHeight(Math.max(100, Math.min(h + 20, 400)));
      }, 200);
    });
    ro.observe(el);
    return () => { ro.disconnect(); clearTimeout(debounceRef.current); };
  }, [expanded, settings, isRunning]);

  if (!expanded) {
    return (
      <div style={{ userSelect: "none", WebkitAppRegion: "drag" }}>
        <div onClick={toggle} style={{
          width: 44, height: 44, borderRadius: "50%",
          background: "rgba(0,0,0,0.78)", backdropFilter: "blur(10px)",
          border: `2px solid ${q}`, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          userSelect: "none", WebkitAppRegion: "no-drag",
        }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: q }}>谛</span>
        </div>
      </div>
    );
  }

  return (
    <div ref={panelRef} style={{
      height: "auto", padding: settings ? 12 : "0 12px",
      background: "rgba(0,0,0,0.78)", backdropFilter: settings ? "blur(14px)" : "blur(12px)",
      borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)",
      fontSize: 13, color: "#fff", userSelect: "none",
      display: "flex", flexDirection: "column", WebkitAppRegion: "drag",
    }}>
      {showControls && (
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          height: 44, minHeight: 44,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: q, flexShrink: 0 }} />
          <div style={{ display: "flex", gap: 5, flex: 1, WebkitAppRegion: "no-drag" }}>
            <button onClick={isRunning ? handleStop : handleStart} disabled={!connected}
              style={btn(isRunning ? "#374151" : q)}>
              {isRunning ? "■" : "▶"}
            </button>
            <button onClick={toggleSettings} style={btn(settings ? q : "#374151")}>⚙</button>
          </div>
          <span onClick={toggle} style={{
            fontSize: 16, fontWeight: 700, color: "#9ca3af", cursor: "pointer",
            WebkitAppRegion: "no-drag",
          }}>−</span>
        </div>
      )}

      {isRunning && (
        <div onDoubleClick={() => setShowControls(!showControls)} style={{
          marginTop: settings ? 0 : 8, padding: "8px 12px", borderRadius: 8,
          background: "rgba(255,255,255,0.04)", WebkitAppRegion: "no-drag",
          cursor: "pointer",
        }}>
          {hasTrans ? (
            <>
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginBottom: 4 }}>{source}</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "#fff", lineHeight: 1.3 }}>{translation}</div>
            </>
          ) : (
            <div style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textAlign: "center" }}>等待语音…</div>
          )}
        </div>
      )}

      {settings && (
        <div style={{
          marginTop: 10, padding: 10, borderRadius: 8,
          background: "rgba(255,255,255,0.04)",
          display: "flex", flexDirection: "column", gap: 6,
          fontSize: 12, WebkitAppRegion: "no-drag",
        }}>
          <Row label="后端" value={WS} />
          <Row label="连接" value={connected ? "已连接" : "离线"} color={connected ? "#4ade80" : "#ef4444"} />
          <Row label="状态" value={isRunning ? "运行中" : "休息中"} />
          <DeviceSelect devices={devices} deviceId={deviceId} setDeviceId={setDeviceId}
            onOpen={() => {}} />
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API Key" type="password"
            style={inputStyle} />
          <input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="API Base URL"
            style={inputStyle} />
          <input value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="Model"
            style={inputStyle} />
          <button onClick={connect} style={{
            marginTop: 4, padding: "6px 0", border: "none", borderRadius: 6,
            background: "rgba(255,255,255,0.08)", color: "#fff", cursor: "pointer",
          }}>{connected ? "断开重连" : "连接"}</button>
        </div>
      )}
    </div>
  );
}

function DeviceSelect({ devices, deviceId, setDeviceId, onOpen }: {
  devices: { id: number; name: string }[];
  deviceId: string;
  setDeviceId: (v: string) => void;
  onOpen: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const toggle = () => {
    if (!open) { onOpen(true); setTimeout(() => setOpen(true), 150); }
    else { setOpen(false); onOpen(false); }
  };
  const close = () => { setOpen(false); onOpen(false); };
  const current = devices.find((d) => String(d.id) === deviceId);

  return (
    <div style={{ position: "relative", WebkitAppRegion: "no-drag" }}>
      <div onClick={toggle} style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "4px 8px", borderRadius: 6, cursor: "pointer",
        background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
        fontSize: 11, color: "rgba(255,255,255,0.7)",
      }}>
        <span style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {current?.name || "自动"}
        </span>
        <span style={{ fontSize: 8, marginLeft: 4 }}>▼</span>
      </div>
      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4,
          maxHeight: 120, overflowY: "auto",
          background: "rgba(0,0,0,0.92)", backdropFilter: "blur(14px)",
          borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)",
          padding: 4, zIndex: 99,
        }}>
          <div onClick={() => { setDeviceId(""); close(); }} style={optStyle("自动", !deviceId)}>自动</div>
          {devices.map((d) => (
            <div key={d.id} onClick={() => { setDeviceId(String(d.id)); close(); }}
              style={optStyle(d.name, String(d.id) === deviceId)}>{d.name}</div>
          ))}
        </div>
      )}
    </div>
  );
}

const optStyle = (name: string, active: boolean): React.CSSProperties => ({
  padding: "4px 8px", borderRadius: 4, cursor: "pointer",
  fontSize: 11, color: active ? "#4ade80" : "rgba(255,255,255,0.6)",
  background: active ? "rgba(255,255,255,0.06)" : "transparent",
  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
});

const Row = ({ label, value, color }: { label: string; value: string; color?: string }) => (
  <div style={{ display: "flex", justifyContent: "space-between" }}>
    <span style={{ color: "rgba(255,255,255,0.45)" }}>{label}</span>
    <span style={{ color: color || "rgba(255,255,255,0.7)" }}>{value}</span>
  </div>
);

const inputStyle: React.CSSProperties = {
  padding: "4px 8px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.1)",
  background: "rgba(255,255,255,0.05)", color: "#fff", fontSize: 11,
  outline: "none", width: "100%",
};

const btn = (bg: string): React.CSSProperties => ({
  width: 32, height: 32, border: "none", borderRadius: 8,
  background: bg, color: "#fff", fontSize: 14, cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
});
