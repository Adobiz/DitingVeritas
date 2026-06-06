const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("electronAPI", {
  expandControl: () => ipcRenderer.invoke("expand-control"),
  collapseControl: () => ipcRenderer.invoke("collapse-control"),
  setHeight: (h) => ipcRenderer.invoke("set-height", h),
  close: () => ipcRenderer.invoke("close-window"),
});
