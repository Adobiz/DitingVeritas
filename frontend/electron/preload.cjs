const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("electronAPI", {
  expandControl: () => ipcRenderer.invoke("expand-control"),
  collapseControl: () => ipcRenderer.invoke("collapse-control"),
  setHeight: (h) => ipcRenderer.invoke("set-height", h),
  setTrayActive: (active) => ipcRenderer.invoke("set-tray-active", active),
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
  close: () => ipcRenderer.invoke("close-window"),
});
