
"use client";

import {
  GeoJSON,
  ImageOverlay,
  MapContainer,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet-draw";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import { useEffect, useRef } from "react";
import { CHANGE_COLORS, CROP_COLORS } from "@/lib/types";

interface Props {
  aoi: any | null;
  parcels: any | null;
  changes: any | null;
  mode: "crops" | "changes";
  showParcels: boolean;
  satellite: boolean;
  highlightIds: string[];
  selectedId: string | null;
  dataKey: string;
  clearSignal: number;
  onSelect: (id: string) => void;
  onAoi: (geom: any) => void;
  ndviOverlay: string | null;
  ndviBounds: number[][] | null;
  showNdvi: boolean;
}

function Draw({
  onAoi,
  clearSignal,
}: {
  onAoi: (g: any) => void;
  clearSignal: number;
}) {
  const map = useMap();
  const group = useRef<L.FeatureGroup | null>(null);

  useEffect(() => {
    const g = new L.FeatureGroup();
    group.current = g;
    map.addLayer(g);

    const ctrl = new (L.Control as any).Draw({
      position: "topright",
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: false,
          shapeOptions: { color: "#2563eb" },
        },
        rectangle: {
          showArea: false,
          shapeOptions: { color: "#2563eb" },
        },
        polyline: false,
        circle: false,
        marker: false,
        circlemarker: false,
      },
      edit: { featureGroup: g },
    });

    map.addControl(ctrl);

    const created = (e: any) => {
      g.clearLayers();
      g.addLayer(e.layer);
      onAoi(e.layer.toGeoJSON().geometry);
    };

    const edited = () => {
      g.eachLayer((layer: any) => {
        onAoi(layer.toGeoJSON().geometry);
      });
    };

    map.on("draw:created", created);
    map.on("draw:edited", edited);

    return () => {
      map.off("draw:created", created);
      map.off("draw:edited", edited);
      map.removeControl(ctrl);
      map.removeLayer(g);
    };
  }, [map, onAoi]);

  useEffect(() => {
    group.current?.clearLayers();
  }, [clearSignal]);

  return null;
}

function Fit({
  geom,
  dataKey,
}: {
  geom: any;
  dataKey: string;
}) {
  const map = useMap();

  useEffect(() => {
    if (!geom) return;

    const bounds = L.geoJSON(geom).getBounds();

    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [30, 30] });
    }
  }, [geom, dataKey, map]);

  return null;
}

export default function MapView(p: Props) {
  const selRef = useRef(p.onSelect);
  selRef.current = p.onSelect;

  const cropStyle = (f: any) => ({
    color: "#0f172a",
    weight: 0.6,
    fillColor:
      CROP_COLORS[
        f.properties.crop_type as keyof typeof CROP_COLORS
      ] || "#999",
    fillOpacity:
      0.62 + Math.min(0.3, (f.properties.confidence || 0) * 0.3),
  });

  const changeStyle = (f: any) => ({
    color: "#111827",
    weight: 1,
    fillColor:
      CHANGE_COLORS[f.properties.category] || "#64748b",
    fillOpacity: 0.8,
  });

  const onEach = (f: any, layer: any) => {
    layer.on("click", () =>
      selRef.current(f.properties.parcel_id)
    );

    const pr = f.properties;

    layer.bindTooltip(
      pr.crop_type
        ? `${pr.parcel_id} · ${pr.crop_type} · ${(
            pr.confidence * 100
          ).toFixed(0)}%`
        : `${pr.parcel_id} · ${pr.category}`,
      { sticky: true }
    );
  };

  const sub = (ids: string[]) =>
    p.parcels && {
      type: "FeatureCollection",
      features: p.parcels.features.filter((f: any) =>
        ids.includes(f.properties.parcel_id)
      ),
    };

  const hl = p.highlightIds.length
    ? sub(p.highlightIds)
    : null;

  const sel = p.selectedId ? sub([p.selectedId]) : null;

  // Bounds from the backend: [[south, west], [north, east]]
  const ndviLeafletBounds =
    p.ndviBounds &&
    p.ndviBounds.length === 2 &&
    p.ndviBounds.every(
      (point) =>
        Array.isArray(point) &&
        point.length === 2 &&
        point.every(
          (coordinate) =>
            typeof coordinate === "number" &&
            Number.isFinite(coordinate)
        )
    )
      ? L.latLngBounds(
          L.latLng(
            p.ndviBounds[0][0],
            p.ndviBounds[0][1]
          ),
          L.latLng(
            p.ndviBounds[1][0],
            p.ndviBounds[1][1]
          )
        )
      : null;

  return (
    <MapContainer
      center={[8.7, 77.5]}
      zoom={11}
      preferCanvas
      className="h-full w-full"
      zoomControl
    >
      {p.satellite ? (
        <TileLayer
          attribution="Tiles © Esri"
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        />
      ) : (
        <TileLayer
          attribution="© OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
      )}

      {p.aoi && (
        <GeoJSON
          key={"aoi" + JSON.stringify(p.aoi.coordinates)}
          data={p.aoi}
          style={{
            color: "#2563eb",
            weight: 2,
            dashArray: "6 4",
            fillOpacity: 0.04,
          }}
          interactive={false}
        />
      )}

      {p.mode === "crops" &&
        p.showParcels &&
        p.parcels && (
          <GeoJSON
            key={"p" + p.dataKey}
            data={p.parcels}
            style={cropStyle}
            onEachFeature={onEach}
          />
        )}

      {p.mode === "changes" && p.changes && (
        <GeoJSON
          key={"c" + p.dataKey}
          data={p.changes}
          style={changeStyle}
          onEachFeature={onEach}
        />
      )}

      {hl && (
        <GeoJSON
          key={"h" + p.highlightIds.join(",")}
          data={hl as any}
          style={{
            color: "#d946ef",
            weight: 3,
            fillOpacity: 0.15,
          }}
          interactive={false}
        />
      )}

      {sel && (
        <GeoJSON
          key={"s" + p.selectedId}
          data={sel as any}
          style={{
            color: "#ffffff",
            weight: 4,
            fillOpacity: 0,
          }}
          interactive={false}
        />
      )}

      <Draw
        onAoi={p.onAoi}
        clearSignal={p.clearSignal}
      />

      <Fit
        geom={p.aoi}
        dataKey={p.dataKey.split("|")[0]}
      />

      {/* Real Sentinel-2 NDVI image overlay */}
      {p.showNdvi &&
        p.ndviOverlay &&
        ndviLeafletBounds?.isValid() && (
          <ImageOverlay
            key={`ndvi-${p.dataKey}`}
            url={`data:image/png;base64,${p.ndviOverlay}`}
            bounds={ndviLeafletBounds}
            opacity={0.85}
            interactive={false}
          />
        )}
    </MapContainer>
  );
}