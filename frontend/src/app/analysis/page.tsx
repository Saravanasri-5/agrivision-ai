
"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2, Play, Satellite } from "lucide-react";
import * as api from "@/lib/api";
import { MIN_AREA_KM2, PRESETS, areaKm2 } from "@/lib/geo";
import {
  CHANGE_COLORS,
  CROPS,
  CROP_COLORS,
  ParcelDetail,
  Stats,
  YEARS,
} from "@/lib/types";
import Charts from "@/components/Charts";
import {
  ChatPanel,
  ComparePanel,
  ParcelCard,
  Spinner,
  StatsGrid,
} from "@/components/Panels";

const MapView = dynamic(
  () => import("@/components/MapView"),
  {
    ssr: false,
    loading: () => (
      <div className="p-6">
        <Spinner text="Loading map..." />
      </div>
    ),
  }
);

const PNG_PREFIX = "data:image/png;base64,";

export default function AnalysisPage() {
  const [aoi, setAoi] = useState<any>(null);
  const [areaName, setAreaName] = useState("Custom study area");
  const [clearSignal, setClearSignal] = useState(0);
  const [year, setYear] = useState(2026);
  const [minConf, setMinConf] = useState(0);

  const [job, setJob] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const [parcels, setParcels] = useState<any>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ParcelDetail | null>(null);

  const [tab, setTab] = useState<"stats" | "compare" | "assistant">("stats");
  const [a, setA] = useState(2025);
  const [b, setB] = useState(2026);
  const [mode, setMode] = useState<"crops" | "changes">("crops");
  const [changes, setChanges] = useState<any>(null);
  const [highlight, setHighlight] = useState<string[]>([]);

  const [showParcels, setShowParcels] = useState(true);
  const [satellite, setSatellite] = useState(false);
  const [reporting, setReporting] = useState(false);

  // Real Sentinel-2 NDVI overlay and metadata.
  const [ndviOverlay, setNdviOverlay] = useState<string | null>(null);
  const [ndviBounds, setNdviBounds] = useState<number[][] | null>(null);
  const [showNdvi, setShowNdvi] = useState(false);
  const [loadingNdvi, setLoadingNdvi] = useState(false);
  const [ndviStats, setNdviStats] = useState<any>(null);
  const [ndviScene, setNdviScene] = useState<any>(null);
  const [ndviLegend, setNdviLegend] = useState<any[]>([]);

  const pollRef = useRef<any>(null);

  const ring = aoi?.coordinates?.[0];
  const area = ring ? areaKm2(ring) : 0;
  const tooSmall = !!aoi && area < MIN_AREA_KM2;

  const clearNdvi = () => {
    setNdviOverlay(null);
    setNdviBounds(null);
    setShowNdvi(false);
    setNdviStats(null);
    setNdviScene(null);
    setNdviLegend([]);
  };

  const onAoi = useCallback((g: any) => {
    setAoi(g);
    setAreaName("Custom study area");
    setError("");
    clearNdvi();
  }, []);

  const choosePreset = (key: string) => {
    if (!key) return;

    const p = PRESETS[key];

    setClearSignal((n) => n + 1);
    setAoi({ type: "Polygon", coordinates: [p.ring] });
    setAreaName(p.name);
    setError("");
    clearNdvi();
  };

  // Fetch observed NDVI from the real Sentinel-2 backend.
  const fetchNdvi = async () => {
    if (!aoi || tooSmall || loadingNdvi) return;

    setLoadingNdvi(true);
    setError("");

    try {
      const result: any = await api.getSatelliteNdvi(aoi, 90, 80);

      const imageUrl = result?.overlay?.png_data_url;
      const bounds = result?.overlay?.bounds;

      if (
        typeof imageUrl !== "string" ||
        !imageUrl.startsWith(PNG_PREFIX)
      ) {
        throw new Error(
          "The backend response did not contain a valid NDVI PNG image."
        );
      }

      if (
        !Array.isArray(bounds) ||
        bounds.length !== 2 ||
        !bounds.every(
          (point: any) =>
            Array.isArray(point) &&
            point.length === 2 &&
            point.every(
              (coordinate: any) =>
                typeof coordinate === "number" &&
                Number.isFinite(coordinate)
            )
        )
      ) {
        throw new Error(
          "The backend response did not contain valid image bounds."
        );
      }

      // MapView expects the base64 portion, not the full data URL.
      setNdviOverlay(imageUrl.slice(PNG_PREFIX.length));
      setNdviBounds(bounds);
      setNdviStats(result.ndvi ?? null);
      setNdviScene(result.scene ?? null);
      setNdviLegend(result.overlay.legend ?? []);
      setShowNdvi(true);
    } catch (e: any) {
      setError(
        e?.message ||
          "Could not load satellite NDVI. Check the backend and try again."
      );
    } finally {
      setLoadingNdvi(false);
    }
  };

  const analyze = async () => {
    if (!aoi || tooSmall) return;

    setError("");
    setRunning(true);
    setProgress(0);
    setParcels(null);
    setStats(null);
    setJob(null);
    setChanges(null);
    setMode("crops");
    setSelected(null);
    setHighlight([]);

    try {
      const r = await api.startAnalysis(areaName, aoi);

      pollRef.current = setInterval(async () => {
        try {
          const s = await api.jobStatus(r.job_id);

          setProgress(s.progress);

          if (s.status === "done") {
            clearInterval(pollRef.current);
            setRunning(false);
            setJob(r.job_id);
          }

          if (s.status === "failed") {
            clearInterval(pollRef.current);
            setRunning(false);
            setError(s.error || "Analysis failed");
          }
        } catch (e: any) {
          clearInterval(pollRef.current);
          setRunning(false);
          setError(e.message);
        }
      }, 700);
    } catch (e: any) {
      setRunning(false);
      setError(e.message);
    }
  };

  useEffect(() => {
    return () => clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    if (!job) return;

    let live = true;
    setLoadingData(true);

    Promise.all([
      api.getParcels(job, year, minConf / 100),
      api.getStats(job, year, minConf / 100),
    ])
      .then(([p, s]) => {
        if (live) {
          setParcels(p);
          setStats(s);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoadingData(false);
      });

    return () => {
      live = false;
    };
  }, [job, year, minConf]);

  useEffect(() => {
    if (!job || !selected) {
      setDetail(null);
      return;
    }

    api
      .getParcel(job, selected, year)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [job, selected, year]);

  const download = (fmt: string) => {
    if (job) {
      window.open(
        api.exportUrl(job, fmt, year, a, b, minConf / 100),
        "_blank"
      );
    }
  };

  const makeReport = async () => {
    if (!job) return;

    setReporting(true);

    try {
      const r = await fetch(api.API + "/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job,
          year,
          period_a: a,
          period_b: b,
        }),
      });

      if (!r.ok) {
        const body = await r.json();
        throw new Error(body.detail || "Report failed");
      }

      const j = await r.json();
      window.open(api.API + j.download_url, "_blank");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setReporting(false);
    }
  };

  const tabBtn = (id: typeof tab, label: string) => (
    <button
      onClick={() => setTab(id)}
      className={`flex-1 border-b-2 px-2 py-2 text-sm font-semibold ${
        tab === id
          ? "border-brand-600 text-brand-600"
          : "border-transparent text-slate-500"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex h-full flex-col lg:flex-row">
      {/* LEFT PANEL */}
      <aside className="w-full shrink-0 space-y-4 overflow-auto border-b border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 lg:w-72 lg:border-b-0 lg:border-r">
        <div>
          <label className="label">Study area</label>

          <select
            className="input"
            onChange={(e) => choosePreset(e.target.value)}
            value=""
          >
            <option value="">Select a taluk preset...</option>
            {Object.entries(PRESETS).map(([k, p]) => (
              <option key={k} value={k}>
                {p.name}
              </option>
            ))}
          </select>

          <p className="mt-1 text-xs text-slate-500">
            Or draw a polygon / rectangle with the map tools (top right).
          </p>

          <div
            className={`mt-2 rounded-lg border px-3 py-2 text-sm ${
              !aoi
                ? "border-slate-300 text-slate-500 dark:border-slate-700"
                : tooSmall
                  ? "border-red-400 bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
                  : "border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-50"
            }`}
          >
            {!aoi ? (
              "No area selected"
            ) : (
              <>
                Selected: <b>{area.toFixed(1)} km²</b> · {areaName}
              </>
            )}

            {tooSmall && (
              <div className="mt-1 font-semibold">
                Please select an area of at least {MIN_AREA_KM2} km²
              </div>
            )}
          </div>
        </div>

        <div>
          <label className="label">Date range (observation season)</label>
          <select
            className="input"
            value={year}
            onChange={(e) => setYear(+e.target.value)}
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>
                Jan – Sep {y}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="label">
            Minimum confidence: {minConf}%
          </label>
          <input
            type="range"
            min={0}
            max={95}
            step={5}
            value={minConf}
            onChange={(e) => setMinConf(+e.target.value)}
            className="w-full accent-green-600"
          />
        </div>

        <button
          className="btn btn-primary w-full"
          disabled={!aoi || tooSmall || running}
          onClick={analyze}
        >
          {running ? (
            <Loader2 className="animate-spin" size={16} />
          ) : (
            <Play size={16} />
          )}
          {running ? `Analyzing ${progress}%` : "Analyze"}
        </button>

        {running && (
          <div className="h-1.5 overflow-hidden rounded bg-slate-200 dark:bg-slate-700">
            <div
              className="h-full bg-brand-600 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-400 bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}

        {/* MAP LAYERS */}
        <div className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-800">
          <div className="label">Map layers</div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showParcels}
              onChange={(e) => setShowParcels(e.target.checked)}
            />
            Classified parcels
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={satellite}
              onChange={(e) => setSatellite(e.target.checked)}
            />
            Satellite basemap
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={mode === "changes"}
              disabled={!changes}
              onChange={(e) =>
                setMode(e.target.checked ? "changes" : "crops")
              }
            />
            Change detection layer
          </label>

          <div className="border-t border-slate-200 pt-3 dark:border-slate-700">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Satellite size={16} />
              Real Satellite NDVI
            </div>

            <p className="mb-2 text-xs text-slate-500">
              Fetch observed Sentinel-2 NDVI for the selected area.
              This is separate from the simulated crop classifications.
            </p>

            <button
              className="btn btn-primary w-full"
              disabled={!aoi || tooSmall || loadingNdvi}
              onClick={fetchNdvi}
            >
              {loadingNdvi ? (
                <Loader2 className="animate-spin" size={16} />
              ) : (
                <Satellite size={16} />
              )}
              {loadingNdvi ? "Fetching satellite data..." : "Fetch Real NDVI"}
            </button>

            {ndviOverlay && (
              <>
                <label className="mt-3 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={showNdvi}
                    onChange={(e) => setShowNdvi(e.target.checked)}
                  />
                  Show NDVI overlay
                </label>

                {ndviStats && (
                  <div className="mt-3 space-y-1 rounded-lg border border-slate-200 p-3 text-xs dark:border-slate-700">
                    <div className="mb-2 font-semibold">
                      Observed NDVI statistics
                    </div>

                    <div className="flex justify-between gap-2">
                      <span>Mean NDVI</span>
                      <b>{Number(ndviStats.mean).toFixed(3)}</b>
                    </div>

                    <div className="flex justify-between gap-2">
                      <span>Minimum</span>
                      <b>{Number(ndviStats.min).toFixed(3)}</b>
                    </div>

                    <div className="flex justify-between gap-2">
                      <span>Maximum</span>
                      <b>{Number(ndviStats.max).toFixed(3)}</b>
                    </div>

                    {ndviScene?.datetime && (
                      <div className="mt-2 border-t border-slate-200 pt-2 dark:border-slate-700">
                        <div className="text-slate-500">
                          Sentinel-2 observation
                        </div>
                        <div>
                          {new Date(ndviScene.datetime).toLocaleDateString()}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {ndviLegend.length > 0 && (
                  <div className="mt-3 space-y-1">
                    <div className="text-xs font-semibold">
                      NDVI colour legend
                    </div>

                    {ndviLegend.map((item: any, index: number) => (
                      <div
                        key={`${item.ndvi}-${index}`}
                        className="flex items-center gap-2 text-xs"
                      >
                        <span
                          className="h-3 w-3 rounded-sm"
                          style={{ backgroundColor: item.color }}
                        />
                        NDVI {item.ndvi}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* EXISTING LEGEND */}
        <div className="border-t border-slate-200 pt-3 dark:border-slate-800">
          <div className="label">Legend</div>

          {mode === "crops"
            ? CROPS.map((c) => (
                <div
                  key={c}
                  className="flex items-center gap-2 text-xs"
                >
                  <span
                    className="h-3 w-3 rounded"
                    style={{ background: CROP_COLORS[c] }}
                  />
                  {c}
                </div>
              ))
            : Object.entries(CHANGE_COLORS).map(([k, c]) => (
                <div
                  key={k}
                  className="flex items-center gap-2 text-xs"
                >
                  <span
                    className="h-3 w-3 rounded"
                    style={{ background: c }}
                  />
                  {k}
                </div>
              ))}
        </div>

        {/* EXISTING REPORTS & EXPORT */}
        <div className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-800">
          <div className="label">Reports &amp; export</div>

          <button
            className="btn btn-ghost w-full !py-1.5"
            disabled={!job || reporting}
            onClick={makeReport}
          >
            {reporting ? (
              <Loader2 className="animate-spin" size={14} />
            ) : (
              <Download size={14} />
            )}
            PDF report
          </button>

          <div className="flex gap-2">
            <button
              className="btn btn-ghost flex-1 !py-1.5"
              disabled={!job}
              onClick={() => download("csv")}
            >
              CSV
            </button>

            <button
              className="btn btn-ghost flex-1 !py-1.5"
              disabled={!job}
              onClick={() => download("geojson")}
            >
              GeoJSON
            </button>
          </div>
        </div>
      </aside>

      {/* MAP */}
      <section className="relative min-h-[420px] flex-1">
        <MapView
          aoi={aoi}
          parcels={parcels}
          changes={changes}
          mode={mode}
          showParcels={showParcels}
          satellite={satellite}
          highlightIds={highlight}
          selectedId={selected}
          dataKey={`${job}|${year}|${minConf}|${a}|${b}`}
          clearSignal={clearSignal}
          onSelect={setSelected}
          onAoi={onAoi}
          ndviOverlay={ndviOverlay}
          ndviBounds={ndviBounds}
          showNdvi={showNdvi}
        />

        {(running || loadingData) && (
          <div className="absolute inset-0 z-[1000] flex items-center justify-center bg-black/30">
            <div className="card">
              <Spinner
                text={
                  running ? "Running analysis..." : "Loading results..."
                }
              />
            </div>
          </div>
        )}

        {!job && !running && (
          <div className="pointer-events-none absolute left-1/2 top-4 z-[500] -translate-x-1/2 rounded-lg bg-white/95 px-4 py-2 text-sm shadow dark:bg-slate-900/95">
            Select a taluk preset or draw an area of at least{" "}
            {MIN_AREA_KM2} km², then press <b>Analyze</b>.
          </div>
        )}
      </section>

      {/* RIGHT PANEL */}
      <aside className="flex w-full shrink-0 flex-col border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 lg:w-96 lg:border-l lg:border-t-0">
        <div className="flex border-b border-slate-200 dark:border-slate-800">
          {tabBtn("stats", "Statistics")}
          {tabBtn("compare", "Compare")}
          {tabBtn("assistant", "Assistant")}
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {!job ? (
            <p className="text-sm text-slate-500">
              Run an analysis to see statistics, historical comparison,
              change detection and the AI assistant.
            </p>
          ) : (
            <>
              {detail && (
                <div className="mb-3">
                  <ParcelCard
                    p={detail}
                    onClose={() => setSelected(null)}
                  />
                </div>
              )}

              {tab === "stats" &&
                (stats ? (
                  <div className="space-y-3">
                    <StatsGrid s={stats} />
                    <Charts stats={stats} />
                  </div>
                ) : (
                  <Spinner />
                ))}

              {tab === "compare" && (
                <ComparePanel
                  job={job}
                  a={a}
                  b={b}
                  setA={setA}
                  setB={setB}
                  mode={mode}
                  setMode={setMode}
                  onChanges={setChanges}
                  onSelect={setSelected}
                />
              )}

              {tab === "assistant" && (
                <ChatPanel
                  job={job}
                  a={a}
                  b={b}
                  onHighlight={setHighlight}
                />
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}