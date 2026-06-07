/** hex → [r,g,b] */
function hexToRgb(hex: string): [number, number, number] {
  const c = hex.replace("#", "");
  return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
}

/** rgb → [h,s,l] — h: 0~360, s/l: 0~1 */
function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  const nr = r / 255, ng = g / 255, nb = b / 255;
  const max = Math.max(nr, ng, nb), min = Math.min(nr, ng, nb);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  switch (max) {
    case nr: h = ((ng - nb) / d + (ng < nb ? 6 : 0)) / 6; break;
    case ng: h = ((nb - nr) / d + 2) / 6; break;
    case nb: h = ((nr - ng) / d + 4) / 6; break;
  }
  return [Math.round(h * 360), s, l];
}

/** hsl → [r,g,b] */
function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const nh = h / 360;
  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [
    Math.round(hue2rgb(p, q, nh + 1 / 3) * 255),
    Math.round(hue2rgb(p, q, nh) * 255),
    Math.round(hue2rgb(p, q, nh - 1 / 3) * 255),
  ];
}

/** 保色相，压饱和/亮度 → 极暗主题背景 */
export function toBgColor(hex: string, opacity: number, brightness: number = 1.0): string {
  const [r, g, b] = hexToRgb(hex);
  const [h, s, l] = rgbToHsl(r, g, b);
  // 保色相，压低饱和度和亮度
  const ns = Math.min(s, 0.2);
  const nl = Math.min(0.15, Math.max(0.03, l * 0.12 * brightness));
  const [nr, ng, nb] = hslToRgb(h, ns, nl);
  return `rgba(${nr},${ng},${nb},${opacity.toFixed(2)})`;
}

/** 基于主题色的微亮面板颜色 */
export function panelBg(hex: string): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},0.06)`;
}
