const { app, BrowserWindow, screen, ipcMain } = require("electron");
const path = require("path");

let ctrlWin = null;
const BALL = 48;
const BAR_W = 360;
const BAR_H = 200;
const BAR_H_SETTINGS = 360;

function createWindow() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  ctrlWin = new BrowserWindow({
    width: BALL, height: BALL,
    x: sw - BALL - 16, y: Math.round(sh * 0.35),
    frame: false, transparent: true, alwaysOnTop: true,
    resizable: false, hasShadow: false, skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false, contextIsolation: true,
      webSecurity: false,
    },
  });
  const url = app.isPackaged
    ? `file://${path.join(__dirname, "../dist/index.html")}`
    : "http://localhost:3000";
  ctrlWin.loadURL(url);
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
ipcMain.handle("close-window", () => ctrlWin?.close());

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
