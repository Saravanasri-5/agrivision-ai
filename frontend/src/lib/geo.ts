export type Ring = number[][];
/** Approximate geodesic polygon area in km² (local equirectangular projection). */
export function areaKm2(ring: Ring): number {
  if (!ring || ring.length < 4) return 0;
  const lat0 = ring.reduce((s, p) => s + p[1], 0) / ring.length;
  const lon0 = ring.reduce((s, p) => s + p[0], 0) / ring.length;
  const kx = 111320 * Math.cos((lat0 * Math.PI) / 180), ky = 110574;
  const pts = ring.map(([lon, lat]) => [(lon - lon0) * kx, (lat - lat0) * ky]);
  let a = 0;
  for (let i = 0; i < pts.length - 1; i++) a += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1];
  return Math.abs(a / 2) / 1e6;
}
export const MIN_AREA_KM2 = 20;
export const PRESETS: Record<string, { name: string; ring: Ring }> = {
  ambasamudram: { name: "Ambasamudram Taluk", ring: [[77.45, 8.68], [77.52, 8.68], [77.52, 8.73], [77.45, 8.73], [77.45, 8.68]] },
  cheranmahadevi: { name: "Cheranmahadevi Taluk", ring: [[77.5, 8.66], [77.58, 8.66], [77.58, 8.72], [77.5, 8.72], [77.5, 8.66]] },
};
