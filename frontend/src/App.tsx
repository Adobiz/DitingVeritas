import { useState, useCallback, useEffect, useRef } from "react";
import { useWebSocket, TranslationMessage } from "./hooks/useWebSocket";
import { toBgColor, panelBg } from "./colors";

const WS = "ws://127.0.0.1:8765/ws/translate";

const PRESETS = ["#9ca3af","#4ade80","#60a5fa","#f59e0b","#f472b6","#a78bfa","#34d399","#fb923c"];

function loadTheme() { try { return JSON.parse(localStorage.getItem("dv_theme")||"{}"); } catch { return {}; } }

export default function App() { return <ControlBall />; }

function ControlBall() {
  const [expanded, setExpanded] = useState(false);
  const [settings, setSettings] = useState(false);
  const [showTheme, setShowTheme] = useState(false);
  const [theme, setTheme] = useState(() => ({ primaryColor: "#9ca3af", bgOpacity: 0.78, brightness: 1.0, ...loadTheme() }));
  const [devices, setDevices] = useState<{ id: number; name: string }[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [models, setModels] = useState<{ id: string; label: string; key: string; url: string; model: string }[]>(
    () => { try { return JSON.parse(localStorage.getItem("dv_models") || "[]"); } catch { return []; } }
  );
  const [selectedModel, setSelectedModel] = useState("");
  const [showAddModel, setShowAddModel] = useState(false);
  const [toast, setToast] = useState("");
  const [source, setSource] = useState("");
  const [translation, setTranslation] = useState("");
  const [showControls, setShowControls] = useState(true);
  const [pipelineMode, setPipelineMode] = useState<string>(() => localStorage.getItem("dv_mode") || "balanced");
  const modes = ["turbo", "balanced", "stable"];
  const modeLabel: Record<string, string> = { turbo: "强化", balanced: "均衡", stable: "稳定" };
  const modeColor: Record<string, string> = { turbo: "#f59e0b", balanced: "#60a5fa", stable: "#4ade80" };
  const panelRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // 持久化主题
  useEffect(() => { localStorage.setItem("dv_theme", JSON.stringify(theme)); }, [theme]);

  const pc = theme.primaryColor;
  const bg = (a: number) => toBgColor(theme.primaryColor, (theme.bgOpacity * a), theme.brightness);

  const onMsg = useCallback((msg: TranslationMessage) => {
    if (msg.type === "translation") {
      if (msg.payload.source_text) setSource(msg.payload.source_text);
      if (msg.payload.translation) setTranslation(msg.payload.translation);
    }
  }, []);
  const { connected, status, send, connect } = useWebSocket({ url: WS, onMessage: onMsg });

  const fetchDevices = async () => {
    try { const res = await fetch("http://127.0.0.1:8765/api/devices"); setDevices(await res.json()); } catch {}
  };
  useEffect(() => { fetchDevices(); }, [connected]);

  const isRunning = status === "running";
  useEffect(() => { window.electronAPI?.setTrayActive(isRunning); }, [isRunning]);
  const toggle = () => {
    if (expanded) window.electronAPI?.collapseControl();
    else window.electronAPI?.expandControl();
    setExpanded(!expanded); setSettings(false); setShowTheme(false);
  };
  const toggleSettings = () => {
    const n = !settings; setSettings(n); setShowTheme(false);
    window.electronAPI?.setHeight(n ? (showAddModel ? 560 : 460) : 200);
  };
  const toggleTheme = () => {
    const n = !showTheme; setShowTheme(n); setSettings(false);
    window.electronAPI?.setHeight(n ? 260 : 200);
  };
  const handleStart = () => {
    const m = models.find((m) => m.id === selectedModel);
    send({ type: "start", device_index: deviceId ? Number(deviceId) : undefined,
      model: m?.model, api_key: m?.key, api_base_url: m?.url, pipeline_mode: pipelineMode });
  };
  const handleStop = () => send({ type: "stop" });
  const cycleMode = () => { if (isRunning) return; const i = modes.indexOf(pipelineMode); setPipelineMode(modes[(i+1)%3]); localStorage.setItem("dv_mode", modes[(i+1)%3]); };
  const handleDeleteModel = (id: string) => {
    const next = models.filter((m) => m.id !== id); setModels(next);
    if (selectedModel === id) setSelectedModel("");
    localStorage.setItem("dv_models", JSON.stringify(next));
  };

  const hasTrans = translation && translation !== source;
  const q = !connected ? "#ef4444" : isRunning ? pc : "#9ca3af";

  useEffect(() => {
    if (!expanded) return;
    if (settings) { window.electronAPI?.setHeight(showAddModel ? 560 : 460); return; }
    if (showTheme) { window.electronAPI?.setHeight(260); return; }
    if (!isRunning && !showControls) { window.electronAPI?.setHeight(80); return; }
    if (!isRunning) { window.electronAPI?.setHeight(200); return; }
    const el = panelRef.current; if (!el) return;
    const ro = new ResizeObserver(() => { clearTimeout(debounceRef.current); debounceRef.current = setTimeout(() => { const h = el.scrollHeight; const min = showControls ? 120 : 100; window.electronAPI?.setHeight(Math.max(min, Math.min(h + 20, 400))); }, 200); });
    ro.observe(el); return () => { ro.disconnect(); clearTimeout(debounceRef.current); };
  }, [expanded, settings, showTheme, isRunning, showAddModel, showControls]);

  if (!expanded) {
    return (
      <div style={{ width: "100%", height: "100%", userSelect: "none", WebkitAppRegion: "drag" }}>
        <div onClick={toggle} style={{ width: 44, height: 44, borderRadius: "50%", background: bg(1), backdropFilter: "blur(10px)", border: `4px solid ${q}`, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", userSelect: "none", WebkitAppRegion: "no-drag", boxSizing: "border-box", transition: "border-color 0.3s, background 0.3s" }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: q, pointerEvents: "none", transition: "color 0.3s" }}>谛</span>
        </div>
      </div>
    );
  }

  return (
    <div ref={panelRef} style={{ height: "auto", minHeight: showControls ? "auto" : 80, padding: (settings||showTheme) ? 12 : "0 12px", background: bg(1), backdropFilter: (settings||showTheme) ? "blur(14px)" : "blur(12px)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)", fontSize: 13, color: "#fff", userSelect: "none", display: "flex", flexDirection: "column" }}>
      {showControls && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, height: 44, minHeight: 44 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: q, flexShrink: 0 }} />
          <div style={{ display: "flex", gap: 5, flex: 1, WebkitAppRegion: "no-drag" }}>
            <button onClick={isRunning ? handleStop : handleStart} disabled={!connected} style={btn(isRunning ? "#374151" : q)}>{isRunning ? "■" : "▶"}</button>
            <button onClick={() => { if (!isRunning) return; setShowControls(!showControls); setSettings(false); }} disabled={!isRunning} title={isRunning ? "字幕模式" : "启动后可切换"} style={{ ...btn(!showControls && isRunning ? q : "#374151"), opacity: isRunning ? 1 : 0.3 }}>▤</button>
            <button onClick={cycleMode} disabled={isRunning} title={`模式: ${modeLabel[pipelineMode]}`} style={{ ...btn(modeColor[pipelineMode]), opacity: isRunning ? 0.4 : 1, fontSize: 10, fontWeight: 700 }}>{modeLabel[pipelineMode][0]}</button>
            <button onClick={() => { window.electronAPI?.openExternal("https://github.com/Adobiz"); }} style={btn("#374151")} title="GitHub">🐱</button>
            <button onClick={toggleTheme} style={btn(showTheme ? pc : "#374151")}>🎨</button>
            <button onClick={toggleSettings} style={btn(settings ? pc : "#374151")}>⚙</button>
          </div>
          <span style={{ fontSize: 14, color: "rgba(255,255,255,0.25)", cursor: "grab", WebkitAppRegion: "drag", userSelect: "none", padding: "0 4px" }} title="拖拽移动">⠿</span>
          <span onClick={toggle} style={{ fontSize: 16, fontWeight: 700, color: "#9ca3af", cursor: "pointer", WebkitAppRegion: "no-drag" }}>−</span>
        </div>
      )}

      {isRunning && (
        <div onDoubleClick={() => setShowControls(!showControls)} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", padding: "12px 16px", borderRadius: 8, margin: 0, background: panelBg(theme.primaryColor), WebkitAppRegion: "no-drag", cursor: "pointer" }}>
          {hasTrans ? (<><div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginBottom: 4 }}>{source}</div><div style={{ fontSize: 16, fontWeight: 600, color: "#fff", lineHeight: 1.3 }}>{translation}</div></>) : (<div style={{ fontSize: 13, color: "rgba(255,255,255,0.3)", textAlign: "center" }}>等待语音…</div>)}
        </div>
      )}

      {settings && (
        <div style={{ marginTop: 10, padding: 10, borderRadius: 8, animation: "fadeIn 0.2s ease", background: panelBg(theme.primaryColor), display: "flex", flexDirection: "column", gap: 6, fontSize: 12, WebkitAppRegion: "no-drag" }}>
          <Row label="后端" value={WS} />
          <Row label="连接" value={connected ? "已连接" : "离线"} color={connected ? pc : "#ef4444"} />
          <Row label="状态" value={isRunning ? "运行中" : "休息中"} />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 12, flexShrink: 0 }}>音频源</span>
            <DeviceSelect devices={devices} deviceId={deviceId} setDeviceId={setDeviceId} onOpen={()=>{}} disabled={isRunning} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 12, flexShrink: 0 }}>选择模型</span>
            {models.length > 0 && <ModelSelect models={models} selected={selectedModel} onSelect={setSelectedModel} onDelete={handleDeleteModel} disabled={isRunning} />}
            <button onClick={()=>{if(isRunning)return;setShowAddModel(!showAddModel)}} disabled={isRunning} title={isRunning?"运行中不可添加":""} style={{...btn("#374151"),width:22,height:22,fontSize:16,borderRadius:4,flexShrink:0,opacity:isRunning?0.4:1}}>+</button>
          </div>
          {showAddModel && <AddModelForm onAdd={(m)=>{const next=[...models,m];setModels(next);setSelectedModel(m.id);localStorage.setItem("dv_models",JSON.stringify(next));setShowAddModel(false);setToast("已添加");setTimeout(()=>setToast(""),2000)}} />}
          {toast && <div style={{ color: pc, fontSize: 11, textAlign: "center" }}>{toast}</div>}
          <button onClick={connect} style={{ marginTop: 4, padding: "6px 0", border: "none", borderRadius: 6, background: "rgba(255,255,255,0.08)", color: "#fff", cursor: "pointer" }}>{connected ? "断开重连" : "连接"}</button>
        </div>
      )}

      {showTheme && (
        <div style={{ marginTop: 10, padding: 10, borderRadius: 8, animation: "fadeIn 0.2s ease", background: panelBg(theme.primaryColor), display: "flex", flexDirection: "column", gap: 8, fontSize: 12, WebkitAppRegion: "no-drag" }}>
          <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11 }}>🎨 外观</span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {PRESETS.map(c => (
              <div key={c} onClick={() => setTheme((t: typeof theme) => ({ ...t, primaryColor: c }))}
                style={{ width: 24, height: 24, borderRadius: 6, background: c, cursor: "pointer", border: pc === c ? "2px solid #fff" : "2px solid transparent" }} />
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11, width: 42 }}>透明度</span>
            <input type="range" min={45} max={95} value={Math.round(theme.bgOpacity * 100)} onChange={e => setTheme((t: typeof theme) => ({ ...t, bgOpacity: +e.target.value / 100 }))} style={{ flex: 1, accentColor: pc }} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11, width: 42 }}>亮度</span>
            <input type="range" min={50} max={200} value={Math.round(theme.brightness * 100)} onChange={e => setTheme((t: typeof theme) => ({ ...t, brightness: +e.target.value / 100 }))} style={{ flex: 1, accentColor: pc }} />
          </div>
        </div>
      )}
    </div>
  );
}

// ── 子组件（不变）────────────────────────────

function ModelSelect({ models, selected, onSelect, onDelete, disabled }: { models: { id: string; label: string }[]; selected: string; onSelect: (id: string) => void; onDelete: (id: string) => void; disabled?: boolean; }) {
  const [open, setOpen] = useState(false); const cur = models.find((m) => m.id === selected);
  return (<div style={{ position: "relative", WebkitAppRegion: "no-drag", flex: 1 }}>
    <div onClick={() => { if (disabled) return; setOpen(!open); }} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 6px", borderRadius: 6, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11, color: "rgba(255,255,255,0.7)", width: "100%", opacity: disabled ? 0.4 : 1, cursor: disabled ? "not-allowed" : "pointer" }}>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{cur?.label || "选择模型"}</span><span style={{ fontSize: 8, marginLeft: 4 }}>▼</span></div>
    {open && (<div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, maxHeight: 100, overflowY: "auto", scrollbarWidth: "none", background: "rgba(0,0,0,0.92)", backdropFilter: "blur(14px)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", padding: 4, zIndex: 99 }}>
      {models.map((m) => (<div key={m.id} style={{ display: "flex", alignItems: "center", ...optStyle(m.label, m.id === selected) }}><div onClick={() => { onSelect(m.id); setOpen(false); }} style={{ flex: 1 }}>{m.label}</div><span onClick={(e) => { e.stopPropagation(); onDelete(m.id); }} style={{ marginLeft: 6, cursor: "pointer", color: "rgba(255,255,255,0.3)", fontSize: 14, lineHeight: 1 }} title="删除">×</span></div>))}
    </div>)}
  </div>);
}

function DeviceSelect({ devices, deviceId, setDeviceId, onOpen, disabled }: { devices: { id: number; name: string }[]; deviceId: string; setDeviceId: (v: string) => void; onOpen: (open: boolean) => void; disabled?: boolean; }) {
  const [open, setOpen] = useState(false); const toggle = () => { if (disabled) return; if (!open) { onOpen(true); setTimeout(() => setOpen(true), 150); } else { setOpen(false); onOpen(false); } }; const close = () => { setOpen(false); onOpen(false); }; const current = devices.find((d) => String(d.id) === deviceId);
  return (<div style={{ position: "relative", WebkitAppRegion: "no-drag", flex: 1 }}>
    <div onClick={toggle} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 6px", borderRadius: 6, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", fontSize: 11, color: "rgba(255,255,255,0.7)", width: "100%", opacity: disabled ? 0.4 : 1, cursor: disabled ? "not-allowed" : "pointer" }}>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{current?.name || "自动"}</span><span style={{ fontSize: 8, marginLeft: 4 }}>▼</span></div>
    {open && (<div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, maxHeight: 100, overflowY: "auto", scrollbarWidth: "none", background: "rgba(0,0,0,0.92)", backdropFilter: "blur(14px)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)", padding: 4, zIndex: 99 }}>
      <div onClick={() => { setDeviceId(""); close(); }} style={optStyle("自动", !deviceId)}>自动</div>
      {devices.map((d) => (<div key={d.id} onClick={() => { setDeviceId(String(d.id)); close(); }} style={optStyle(d.name, String(d.id) === deviceId)}>{d.name}</div>))}
    </div>)}
  </div>);
}

const optStyle = (name: string, active: boolean): React.CSSProperties => ({ padding: "4px 8px", borderRadius: 4, cursor: "pointer", fontSize: 11, color: active ? "#4ade80" : "rgba(255,255,255,0.6)", background: active ? "rgba(255,255,255,0.06)" : "transparent", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" });
const Row = ({ label, value, color }: { label: string; value: string; color?: string }) => (<div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "rgba(255,255,255,0.45)" }}>{label}</span><span style={{ color: color || "rgba(255,255,255,0.7)" }}>{value}</span></div>);
const inputStyle: React.CSSProperties = { padding: "4px 8px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.05)", color: "#fff", fontSize: 11, outline: "none", width: "100%" };

function AddModelForm({ onAdd }: { onAdd: (m: { id: string; label: string; key: string; url: string; model: string }) => void }) {
  const [label, setLabel] = useState(""); const [key, setKey] = useState(""); const [url, setUrl] = useState(""); const [model, setModel] = useState("");
  const submit = () => { if (!label || !key) return; onAdd({ id: Date.now().toString(36), label, key, url, model }); };
  return (<div style={{ padding: 8, borderRadius: 6, background: "rgba(255,255,255,0.03)" }}>
    <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="名称 (如 DeepSeek)" style={inputStyle} />
    <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="API Key" type="password" style={inputStyle} />
    <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="API Base URL (可选)" style={inputStyle} />
    <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model (可选)" style={inputStyle} />
    <button onClick={submit} style={{ width: "100%", padding: "5px 0", border: "none", borderRadius: 6, background: "#4ade80", color: "#000", fontWeight: 600, fontSize: 12, cursor: "pointer" }}>添加</button>
  </div>);
}

const btn = (bg: string): React.CSSProperties => ({ width: 32, height: 32, border: "none", borderRadius: 8, background: bg, color: "#fff", fontSize: 14, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", transition: "background 0.2s, transform 0.15s, opacity 0.2s" });
