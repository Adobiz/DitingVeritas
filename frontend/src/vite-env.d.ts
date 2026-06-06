/// <reference types="vite/client" />

interface ElectronAPI {
  expandControl: () => Promise<void>;
  collapseControl: () => Promise<void>;
  showSubtitle: () => Promise<void>;
  hideSubtitle: () => Promise<void>;
  close: () => Promise<void>;
}
declare global { interface Window { electronAPI?: ElectronAPI } }
export {};
