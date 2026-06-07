const { app, BrowserWindow, Tray, Menu, screen, ipcMain, nativeImage } = require("electron");
const path = require("path");

let ctrlWin = null, tray = null, isQuitting = false;
let pipelineActive = false;
const BALL = 48, BAR_W = 360, BAR_H = 200;

let iconIdle = null, iconActive = null;
const fs = require("fs");

function loadPNG(name) {
  const p = path.join(__dirname, "../assets", name);
  try { if (fs.existsSync(p)) return nativeImage.createFromPath(p); } catch {}
  return null;
}

function makeIcon(r, g, b) {
  const size = 16, buf = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const d = Math.sqrt((x - 7.5) ** 2 + (y - 7.5) ** 2);
      if (d <= 5.5) { buf[i] = r; buf[i + 1] = g; buf[i + 2] = b; buf[i + 3] = 255; }
    }
  return nativeImage.createFromBuffer(buf, { width: size, height: size, scaleFactor: 1.0 });
}

function buildTrayMenu() {
  return Menu.buildFromTemplate([
    { label: "显示/隐藏", click: () => ctrlWin?.isVisible() ? ctrlWin.hide() : ctrlWin?.show() },
    { type: "separator" },
    {
      label: pipelineActive ? "■ 停止翻译" : "▶ 开始翻译",
      click: () => { ctrlWin?.webContents.send("tray-command", pipelineActive ? "stop" : "start"); }
    },
    { type: "separator" },
    { label: "退出", click: () => { isQuitting = true; app.quit(); } },
  ]);
}

function createTray() {
  iconIdle = loadPNG("icon-idle.png") || makeIcon(107, 114, 128);
  iconActive = loadPNG("icon-active.png") || makeIcon(59, 130, 246);
  tray = new Tray(iconIdle);
  tray.setToolTip("谛听·译真");
  tray.setContextMenu(buildTrayMenu());
  tray.on("double-click", () => ctrlWin?.isVisible() ? ctrlWin.hide() : ctrlWin?.show());
}

function createWindow() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  ctrlWin = new BrowserWindow({
    icon: loadPNG("icon.png") || makeIcon(59, 130, 246),
    width: BALL, height: BALL,
    x: sw - BALL - 16, y: Math.round(sh * 0.35),
    frame: false, transparent: true, alwaysOnTop: true,
    resizable: false, hasShadow: false, skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false, contextIsolation: true, webSecurity: false,
    },
  });
  const url = app.isPackaged
    ? `file://${path.join(__dirname, "../dist/index.html")}`
    : "http://localhost:3000";
  ctrlWin.loadURL(url);
  ctrlWin.on("close", (e) => { if (!isQuitting) { e.preventDefault(); ctrlWin.hide(); } });
}

ipcMain.handle("expand-control", () => {
  const [x, y] = ctrlWin.getPosition();
  ctrlWin.setBounds({ x: x - (BAR_W - BALL), y, width: BAR_W, height: BAR_H }, true);
});
ipcMain.handle("collapse-control", () => {
  const [x, y] = ctrlWin.getPosition();
  ctrlWin.setBounds({ x: x + (BAR_W - BALL), y, width: BALL, height: BALL }, true);
});
ipcMain.handle("set-height", (_e, h) => {
  const [x, y] = ctrlWin.getPosition();
  ctrlWin.setBounds({ x, y, width: BAR_W, height: h }, true);
});
ipcMain.handle("set-tray-active", (_e, active) => {
  pipelineActive = active;
  tray?.setImage(active ? iconActive : iconIdle);
  tray?.setContextMenu(buildTrayMenu());
});
ipcMain.handle("open-external", (_e, url) => { require("electron").shell.openExternal(url); });
ipcMain.handle("close-window", () => ctrlWin?.hide());

app.whenReady().then(() => { createWindow(); createTray(); });
app.on("window-all-closed", () => { });
app.on("before-quit", () => { isQuitting = true; });
