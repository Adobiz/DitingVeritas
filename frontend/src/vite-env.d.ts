/// <reference types="vite/client" />

interface ElectronAPI {
  expandControl: () => Promise<void>;
  collapseControl: () => Promise<void>;
  setHeight: (h: number) => Promise<void>;
  setTrayActive: (active: boolean) => Promise<void>;
  close: () => Promise<void>;
}
declare global { interface Window { electronAPI?: ElectronAPI } }

import "react";
declare module "react" {
  interface CSSProperties { WebkitAppRegion?: string }
}

export {};
