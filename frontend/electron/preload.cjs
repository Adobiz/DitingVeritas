const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("electronAPI", {
  expandControl: () => ipcRenderer.invoke("expand-control"),
  collapseControl: () => ipcRenderer.invoke("collapse-control"),
  showSubtitle: () => ipcRenderer.invoke("show-subtitle"),
  hideSubtitle: () => ipcRenderer.invoke("hide-subtitle"),
  close: () => ipcRenderer.invoke("close-window"),
});
