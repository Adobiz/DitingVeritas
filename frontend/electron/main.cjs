const { app, BrowserWindow, screen, ipcMain } = require("electron");
const path = require("path");

let ctrlWin = null, subWin = null;
const BALL = 48;
const BAR_W = 230;
const BAR_H = 52;
const SUB_W = 520;
const SUB_H = 80;

function createCtrl() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  ctrlWin = new BrowserWindow({
    width: BALL, height: BALL,
    x: sw - BALL - 16, y: Math.round(sh * 0.35),
    frame: false, transparent: true, alwaysOnTop: true,
    resizable: false, hasShadow: false, skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false, contextIsolation: true,
    },
  });
  if (!app.isPackaged) {
    ctrlWin.loadURL("http://localhost:3000?role=control");
  } else {
    ctrlWin.loadFile(path.join(__dirname, "../dist/index.html"), { query: { role: "control" } });
  }
}

function createSub() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  subWin = new BrowserWindow({
    width: SUB_W, height: SUB_H,
    x: Math.round((sw - SUB_W) / 2), y: sh - SUB_H - 80,
    frame: false, transparent: true, alwaysOnTop: true,
    resizable: false, hasShadow: false, skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false, contextIsolation: true,
    },
  });
  if (!app.isPackaged) {
    subWin.loadURL("http://localhost:3000?role=subtitle");
  } else {
    subWin.loadFile(path.join(__dirname, "../dist/index.html"), { query: { role: "subtitle" } });
  }
}

// 控制窗口：展开/收起
ipcMain.handle("expand-control", () => {
  const [x, y] = ctrlWin.getPosition();
  ctrlWin.setBounds({ x: x - (BAR_W - BALL), y, width: BAR_W, height: BAR_H }, true);
});
ipcMain.handle("collapse-control", () => {
  const [x, y] = ctrlWin.getPosition();
  ctrlWin.setBounds({ x: x + (BAR_W - BALL), y, width: BALL, height: BALL }, true);
});

// 字幕窗口：显示/隐藏
ipcMain.handle("show-subtitle", () => subWin?.show());
ipcMain.handle("hide-subtitle", () => subWin?.hide());

ipcMain.handle("close-window", () => { ctrlWin?.close(); subWin?.close(); });

app.whenReady().then(() => { createCtrl(); createSub(); });
app.on("window-all-closed", () => app.quit());
