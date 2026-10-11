export type Crop = "Paddy" | "Banana" | "Other Vegetation" | "Non-Agricultural";
export const CROPS: Crop[] = ["Paddy", "Banana", "Other Vegetation", "Non-Agricultural"];
export const YEARS = [2024, 2025, 2026];
export const CROP_COLORS: Record<Crop, string> = {
  Paddy: "#16a34a", Banana: "#eab308", "Other Vegetation": "#a7f3a0", "Non-Agricultural": "#9ca3af",
};
export const LEVEL_COLORS: Record<string, string> = { High: "#16a34a", Medium: "#f59e0b", Low: "#ef4444" };
export const CHANGE_COLORS: Record<string, string> = {
  "Paddy → Banana": "#f97316", "Banana → Paddy": "#3b82f6", "New Cultivation": "#a855f7",
  "Non-Crop Conversion": "#ef4444", "Other Vegetation Shift": "#64748b",
};
export interface Stats {
  total_parcels: number; total_area_ha: number; agricultural_area_ha: number; avg_confidence: number;
  crop_area_ha: Record<string, number>; crop_count: Record<string, number>; crop_pct: Record<string, number>;
  confidence_levels: Record<string, number>; size_distribution: { bucket: string; count: number }[];
}
export interface ParcelDetail {
  parcel_id: string; area_ha: number; crop_type: Crop; confidence: number; confidence_level: string; year: number;
  explanation: string[]; probabilities: Record<string, number>; features: Record<string, number>; model_version: string;
  history: { year: number; crop_type: Crop; confidence: number }[];
}
export interface ChangeResult {
  total_changed: number; total_parcels: number;
  summary: Record<string, { count: number; area_ha: number }>;
  changes: { parcel_id: string; from_crop: string; to_crop: string; category: string; area_ha: number; message: string }[];
  geojson: any;
}
export interface HistoryResult {
  period_a: { year: number; stats: Stats }; period_b: { year: number; stats: Stats };
  delta: Record<string, { area_ha: number; pct_points: number; parcels: number }>;
  timeline: any[];
}
