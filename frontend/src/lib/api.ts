
const API =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export { API };

async function req<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const data = await response.json();
      message = data.detail || data.message || message;
    } catch {
      // Keep the default error message if the response isn't JSON.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function query(params: Record<string, string | number>) {
  return new URLSearchParams(
    Object.entries(params).map(([key, value]) => [key, String(value)])
  ).toString();
}

/** Start an analysis for the selected study area. */
export function startAnalysis(name: string, aoi: any) {
  if (!aoi || aoi.type !== "Polygon" || !Array.isArray(aoi.coordinates)) {
    throw new Error("Please draw a polygon on the map before starting analysis.");
  }

  return req<{
    job_id: string;
    status: string;
    area_km2?: number;
    message?: string;
  }>("/analysis", {
    method: "POST",
    body: JSON.stringify({ name, aoi }),
  });
}

/** Check the progress of an analysis job. */
export function jobStatus(jobId: string) {
  return req<any>(`/analysis/${encodeURIComponent(jobId)}`);
}

/** Load parcel GeoJSON for a job and year. */
export function getParcels(
  jobId: string,
  year = 2026,
  minConfidence = 0
) {
  return req<any>(
    `/parcels?${query({
      job_id: jobId,
      year,
      min_confidence: minConfidence,
    })}`
  );
}

/** Load statistics for a job and year. */
export async function getStats(
  jobId: string,
  year = 2026,
  minConfidence = 0
) {
  const result = await req<any>(
    `/statistics?${query({
      job_id: jobId,
      year,
      min_confidence: minConfidence,
    })}`
  );

  return result.stats ?? result;
}

/** Build a download URL for CSV, GeoJSON, or PDF exports. */
export function exportUrl(
  jobId: string,
  format: string,
  year = 2026,
  periodA = 2025,
  periodB = 2026,
  minConfidence = 0
) {
  return `${API}/export?${query({
    job_id: jobId,
    format,
    year,
    period_a: periodA,
    period_b: periodB,
    min_confidence: minConfidence,
  })}`;
}

/** Fetch observed Sentinel-2 NDVI for the selected polygon. */
export function getSatelliteNdvi(
  aoi: any,
  daysBack = 90,
  maxSceneCloud = 80
) {
  if (
    !aoi ||
    aoi.type !== "Polygon" ||
    !Array.isArray(aoi.coordinates) ||
    !Array.isArray(aoi.coordinates[0]) ||
    aoi.coordinates[0].length < 4
  ) {
    throw new Error(
      "Please draw a polygon on the map before fetching satellite NDVI."
    );
  }

  return req<any>("/satellite/ndvi", {
    method: "POST",
    body: JSON.stringify({
      aoi,
      days_back: daysBack,
      max_scene_cloud: maxSceneCloud,
    }),
  });
}