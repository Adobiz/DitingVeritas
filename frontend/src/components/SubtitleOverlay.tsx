interface Props {
  sourceText: string;
  translation: string;
  status: string;
  connected: boolean;
}

export function SubtitleOverlay({ sourceText, translation, status, connected }: Props) {
  const isRunning = status === "running";
  const showTrans = translation && translation !== sourceText;
  const showSource = sourceText && !showTrans;

  let label = "○ 休息中";
  if (!connected) label = "○ 未连接";
  else if (status === "starting") label = "◉ 启动中…";
  else if (isRunning && showTrans) label = "◉ 翻译ing";
  else if (isRunning) label = "◉ 聆听中…";

  return (
    <div style={{
      position: "fixed", bottom: 80, left: "50%", transform: "translateX(-50%)",
      minWidth: 320, maxWidth: 700, padding: "16px 24px",
      background: "rgba(0,0,0,0.72)", backdropFilter: "blur(12px)",
      borderRadius: 10, color: "#fff", textAlign: "center", zIndex: 9999,
    }}>
      <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", marginBottom: 6 }}>
        {label} | EN → 中文
      </div>
      {showSource && (
        <div style={{ fontSize: 14, color: "rgba(255,255,255,0.55)", marginBottom: 4 }}>
          {sourceText}
        </div>
      )}
      {showTrans && (
        <div style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.4 }}>
          {translation}
        </div>
      )}
      {!sourceText && !translation && (
        <div style={{ fontSize: 15, color: "rgba(255,255,255,0.35)" }}>
          {!connected ? "请先启动后端 python main.py" : isRunning ? "等待语音输入…" : "发送 {\"type\":\"start\"} 开始"}
        </div>
      )}
    </div>
  );
}
