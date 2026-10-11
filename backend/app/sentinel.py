"""Real (observed) Sentinel-2 NDVI service.

This module is completely separate from engine.py. engine.py produces SIMULATED parcels and
SIMULATED crop predictions; everything returned from here comes from real Sentinel-2 L2A pixels
read through the Earth Search STAC API.

What it does, in order:
  1. Validates the requested polygon (size limits, valid GeoJSON).
  2. Searches Sentinel-2 L2A scenes that intersect the polygon in the last N days.
  3. Keeps only scenes whose footprint fully covers the polygon (single-scene mode).
  4. For the best few scenes (lowest scene-wide cloud), reads ONLY the 20 m scene-classification
     (SCL) band inside the polygon and measures how many polygon pixels are clear.
  5. Picks the scene with the most clear polygon pixels (ties within 2 points -> most recent).
  6. Reads red + NIR for that scene, applies the STAC scale/offset, masks with the polygon and
     the SCL classes, and computes NDVI statistics + a map overlay PNG.

No secrets or credentials are used: the data is public.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from PIL import Image
from rasterio import features
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject, transform_geom
from rasterio.windows import Window, from_bounds as window_from_bounds
from shapely.geometry import mapping, shape

from .engine import aoi_area_km2

log = logging.getLogger("agrivision.sentinel")

# ------------------------------------------------------------------ settings
STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

MIN_AREA_KM2 = 0.25          # smaller than this has too few 10 m pixels to be meaningful
MAX_AREA_KM2 = 150.0         # safety limit (about 1.5 million 10 m pixels)
MAX_PIXELS_10M = 1_800_000   # hard pixel limit checked again on the real raster window
MAX_STAC_ITEMS = 40          # how many scenes to pull from the catalog
MAX_CANDIDATES = 8           # how many scenes to measure with the cheap SCL read
MIN_USABLE_PCT = 10.0        # below this we refuse to report NDVI for the polygon
TIME_BUDGET_S = 120          # whole request budget
CACHE_TTL_S = 30 * 60
CACHE_MAX = 8

# Network timeouts / retries for reading the cloud-optimised GeoTIFFs.
GDAL_OPTS = {
    "GDAL_HTTP_TIMEOUT": "25",
    "GDAL_HTTP_CONNECTTIMEOUT": "10",
    "GDAL_HTTP_MAX_RETRY": "2",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "AWS_NO_SIGN_REQUEST": "YES",
}

# Sentinel-2 L2A scene classification (SCL) classes.
SCL_NAMES = {
    0: "no_data", 1: "saturated_or_defective", 2: "dark_area_or_topographic_shadow", 3: "cloud_shadow",
    4: "vegetation", 5: "not_vegetated", 6: "water", 7: "unclassified",
    8: "cloud_medium_probability", 9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_or_ice",
}
# Pixels in these classes are NOT used. (Your original test also excluded 0,1,3,8,9,10,11;
# class 2 = dark/topographic shadow is added here because reflectance in shadow is unreliable.)
INVALID_SCL = (0, 1, 2, 3, 8, 9, 10, 11)
WATER_SCL = 6

LIMITATIONS = [
    "Observed NDVI from one Sentinel-2 L2A acquisition; it is not a crop classification and not a crop-health verdict.",
    "Statistics cover every usable land pixel inside the polygon (fields, trees, built-up, bare ground). "
    "No crop-only mask was applied and no parcel-level NDVI is computed.",
    "Cloud/shadow masking uses Sentinel-2's own scene classification (SCL), which is imperfect; thin cloud or haze can remain.",
    "Scene-wide cloud cover describes the whole ~110 km tile, not this polygon. Use the polygon clear-pixel percentage.",
    "Single-scene mode: polygons that are not fully inside one scene footprint are not supported.",
    "Water pixels (SCL class 6) are excluded from the NDVI statistics but counted in the coverage breakdown.",
]

PROVENANCE = {
    "note": "Which parts of AgriVision AI use real satellite data and which are simulated demo data.",
    "features": [
        {"name": "Observed Sentinel-2 NDVI (this feature)", "status": "real",
         "detail": "Real Sentinel-2 L2A red/NIR pixels from Earth Search, masked to the requested polygon. "
                   "Statistics, not a crop classification."},
        {"name": "Parcel polygons", "status": "simulated",
         "detail": "Synthetic jittered grid inside the study area. Not real field boundaries."},
        {"name": "Crop classification (Paddy/Banana/Other/Non-Agricultural)", "status": "simulated",
         "detail": "Random Forest trained on synthetic samples, applied to simulated features. No real accuracy figures exist."},
        {"name": "Per-parcel NDVI/EVI/NDWI/SWIR values and 'Why classified?' text", "status": "simulated",
         "detail": "Generated by engine.observe(); not measured from imagery."},
        {"name": "2024/2025/2026 history, change detection, statistics, charts", "status": "simulated",
         "detail": "Derived from the simulated predictions."},
        {"name": "Assistant answers, PDF/CSV/GeoJSON exports", "status": "simulated",
         "detail": "Built from the simulated analysis database."},
    ],
}

# NDVI colour ramp used for the map overlay (NDVI value -> RGB).
_STOPS = [(-0.2, (140, 81, 10)), (0.1, (216, 179, 101)), (0.3, (217, 240, 163)),
          (0.5, (120, 198, 121)), (0.7, (35, 132, 67)), (0.9, (0, 68, 27))]
LEGEND = [{"ndvi": v, "color": "#%02x%02x%02x" % rgb} for v, rgb in _STOPS]


class SentinelError(Exception):
    """Expected problem with a clear message; main.py turns it into an HTTP error."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class _OutsideScene(Exception):
    pass


# ------------------------------------------------------------------ small cache
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL_S:
            return hit[1]
        _cache.pop(key, None)
    return None


def _cache_put(key: str, value: Dict[str, Any]) -> None:
    with _cache_lock:
        if len(_cache) >= CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)
        _cache[key] = (time.time(), value)


# ------------------------------------------------------------------ validation
def _validate_polygon(aoi: Any):
    if not isinstance(aoi, dict) or aoi.get("type") != "Polygon" or not aoi.get("coordinates"):
        raise SentinelError(422, "Area must be a GeoJSON Polygon.")
    ring = aoi["coordinates"][0]
    if len(ring) < 4 or len(ring) > 500:
        raise SentinelError(422, "Polygon must have between 3 and 500 vertices.")
    try:
        poly = shape(aoi)
    except Exception:
        raise SentinelError(422, "Invalid polygon geometry.")
    if poly.is_empty or not poly.is_valid:
        raise SentinelError(422, "Invalid polygon (self-intersecting?).")
    minx, miny, maxx, maxy = poly.bounds
    if minx < -180 or maxx > 180 or miny < -80 or maxy > 80:
        raise SentinelError(422, "Coordinates out of range (expected lon/lat WGS84).")
    area = aoi_area_km2(aoi)
    if area < MIN_AREA_KM2:
        raise SentinelError(422, f"Area too small for NDVI statistics (min {MIN_AREA_KM2} km2, selected {area:.2f} km2).")
    if area > MAX_AREA_KM2:
        raise SentinelError(422, f"Area too large for a live satellite request (max {MAX_AREA_KM2:.0f} km2, selected {area:.1f} km2).")
    return poly, area


# ------------------------------------------------------------------ raster helpers
def _native_geom(poly, crs) -> Dict[str, Any]:
    """Polygon (lon/lat) -> the raster's own CRS (UTM)."""
    return transform_geom("EPSG:4326", crs, mapping(poly))


def _window(src, g_native: Dict[str, Any]) -> Window:
    """Whole-pixel window covering the polygon's bounding box, clipped to the raster."""
    minx, miny, maxx, maxy = shape(g_native).bounds
    w = window_from_bounds(minx, miny, maxx, maxy, transform=src.transform)
    col0 = max(int(math.floor(w.col_off)), 0)
    row0 = max(int(math.floor(w.row_off)), 0)
    col1 = min(int(math.ceil(w.col_off + w.width)), src.width)
    row1 = min(int(math.ceil(w.row_off + w.height)), src.height)
    if col1 <= col0 or row1 <= row0:
        raise _OutsideScene("Polygon is outside this scene.")
    return Window(col0, row0, col1 - col0, row1 - row0)


def _scale_offset(item, name: str) -> Tuple[float, float]:
    bands = item.assets[name].extra_fields.get("raster:bands")
    if not bands or "scale" not in bands[0]:
        raise SentinelError(502, f"Scene {item.id} has no reflectance scale/offset metadata for '{name}'. "
                                 "Refusing to guess, because that would give wrong NDVI.")
    return float(bands[0]["scale"]), float(bands[0].get("offset", 0.0))


def _r(x: float, n: int = 4) -> float:
    return round(float(x), n)


# ------------------------------------------------------------------ STAC search + scene ranking
def _search_items(poly, days_back: int) -> list:
    from pystac_client import Client

    end = dt.datetime.now(dt.timezone.utc).date()
    start = end - dt.timedelta(days=days_back)
    try:
        client = Client.open(STAC_URL, timeout=30)
    except TypeError:  # older pystac-client without a timeout argument
        client = Client.open(STAC_URL)
    search = client.search(collections=[COLLECTION], intersects=mapping(poly),
                           datetime=f"{start.isoformat()}/{end.isoformat()}", max_items=MAX_STAC_ITEMS)
    return list(search.items())


def _covers(item, poly) -> bool:
    try:
        footprint = shape(item.geometry).buffer(0)
        return footprint.intersection(poly).area >= 0.999 * poly.area
    except Exception:
        return False


def _scl_clear_pct(item, poly) -> Optional[float]:
    """Cheap estimate: percentage of polygon pixels that are clear, from the 20 m SCL band only."""
    with rasterio.open(item.assets["scl"].href) as src:
        g_native = _native_geom(poly, src.crs)
        win = _window(src, g_native)
        scl = src.read(1, window=win)
        tf = src.window_transform(win)
    inside = features.geometry_mask([g_native], out_shape=scl.shape, transform=tf, invert=True)
    n = int(inside.sum())
    if n == 0:
        return None
    clear = inside & ~np.isin(scl, INVALID_SCL)
    return 100.0 * int(clear.sum()) / n


# ------------------------------------------------------------------ NDVI for the chosen scene
def _colorize(ndvi: np.ndarray) -> np.ndarray:
    xs = [s[0] for s in _STOPS]
    ok = np.isfinite(ndvi)
    v = np.where(ok, ndvi, 0.0)
    rgba = np.zeros(ndvi.shape + (4,), dtype=np.uint8)
    for c in range(3):
        rgba[..., c] = np.interp(v, xs, [s[1][c] for s in _STOPS]).astype(np.uint8)
    rgba[..., 3] = np.where(ok, 200, 0).astype(np.uint8)
    return rgba


def _overlay(ndvi: np.ndarray, tf, crs, poly) -> Dict[str, Any]:
    """Reproject NDVI to a north-up lon/lat grid so Leaflet can place it exactly."""
    minx, miny, maxx, maxy = poly.bounds
    lat0 = (miny + maxy) / 2.0
    dx = 10.0 / (111320.0 * math.cos(math.radians(lat0)))
    dy = 10.0 / 110574.0
    W = int(min(max(round((maxx - minx) / dx), 1), 1600))
    H = int(min(max(round((maxy - miny) / dy), 1), 1600))
    dst_tf = transform_from_bounds(minx, miny, maxx, maxy, W, H)
    dst = np.full((H, W), np.nan, dtype="float32")
    reproject(source=ndvi, destination=dst, src_transform=tf, src_crs=crs, dst_transform=dst_tf,
              dst_crs="EPSG:4326", src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.nearest)
    inside = features.geometry_mask([mapping(poly)], out_shape=(H, W), transform=dst_tf, invert=True)
    dst[~inside] = np.nan
    buf = io.BytesIO()
    Image.fromarray(_colorize(dst)).save(buf, format="PNG", optimize=True)
    return {
        "png_data_url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
        "bounds": [[miny, minx], [maxy, maxx]],  # Leaflet order: [[south, west], [north, east]]
        "width": W, "height": H, "legend": LEGEND,
    }


def _ndvi_stats(vals: np.ndarray) -> Dict[str, Any]:
    p10, p50, p90 = np.percentile(vals, [10, 50, 90])
    shares = {
        "below_0.2": vals < 0.2,
        "0.2_to_0.4": (vals >= 0.2) & (vals < 0.4),
        "0.4_to_0.6": (vals >= 0.4) & (vals < 0.6),
        "0.6_and_above": vals >= 0.6,
    }
    return {
        "mean": _r(vals.mean()), "median": _r(p50), "p10": _r(p10), "p90": _r(p90),
        "min": _r(vals.min()), "max": _r(vals.max()), "std": _r(vals.std()),
        "class_share_pct": {k: _r(100.0 * m.mean(), 2) for k, m in shares.items()},
    }


def _compute_item(item, poly, area_km2: float) -> Dict[str, Any]:
    sr, orr = _scale_offset(item, "red")
    sn, on = _scale_offset(item, "nir")

    with rasterio.open(item.assets["red"].href) as rsrc, rasterio.open(item.assets["nir"].href) as nsrc:
        if (rsrc.crs != nsrc.crs or rsrc.transform != nsrc.transform
                or (rsrc.width, rsrc.height) != (nsrc.width, nsrc.height)):
            raise SentinelError(502, "Red and NIR rasters are not on the same grid; refusing to combine them.")
        crs = rsrc.crs
        g_native = _native_geom(poly, crs)
        win = _window(rsrc, g_native)
        if win.width * win.height > MAX_PIXELS_10M:
            raise SentinelError(422, "Selected area has too many pixels for a live request. Draw a smaller area.")
        red_raw = rsrc.read(1, window=win)
        nir_raw = nsrc.read(1, window=win)
        tf = rsrc.window_transform(win)

    h, w = red_raw.shape
    # Bring the 20 m SCL band onto the 10 m red grid (nearest neighbour keeps class codes intact).
    with rasterio.open(item.assets["scl"].href) as ssrc:
        with WarpedVRT(ssrc, crs=crs, transform=tf, width=w, height=h, resampling=Resampling.nearest) as vrt:
            scl = vrt.read(1)
    if red_raw.shape != nir_raw.shape or red_raw.shape != scl.shape:
        raise SentinelError(502, f"Band alignment failed: red={red_raw.shape}, nir={nir_raw.shape}, scl={scl.shape}.")

    inside = features.geometry_mask([g_native], out_shape=(h, w), transform=tf, invert=True)
    n_poly = int(inside.sum())
    if n_poly == 0:
        raise SentinelError(422, "Polygon contains no 10 m pixels.")

    red = red_raw.astype("float32") * sr + orr
    nir = nir_raw.astype("float32") * sn + on
    nodata = (red_raw == 0) | (nir_raw == 0)  # 0 is the Sentinel-2 nodata value
    scl_ok = ~np.isin(scl, INVALID_SCL)
    clear = inside & ~nodata & scl_ok

    denom = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / denom
    good = clear & np.isfinite(ndvi) & (denom > 0) & (ndvi >= -1) & (ndvi <= 1)
    usable = int(good.sum())
    land = good & (scl != WATER_SCL)
    vals = ndvi[land]
    if vals.size == 0:
        raise SentinelError(404, "No usable land pixels inside the polygon for the best scene.")

    counts = np.bincount(scl[inside].astype(np.int64), minlength=12)
    breakdown = {SCL_NAMES[k]: _r(100.0 * counts[k] / n_poly, 2) for k in range(12) if counts[k] > 0}

    ndvi_map = np.full((h, w), np.nan, dtype="float32")
    ndvi_map[land] = ndvi[land]

    return {
        "area_km2": _r(area_km2, 3),
        "polygon_pixels_10m": n_poly,
        "usable_pixels": usable,
        "usable_pct_of_polygon": _r(100.0 * usable / n_poly, 2),
        "cloud_or_invalid_pct_of_polygon": _r(100.0 * (n_poly - int((inside & ~nodata & scl_ok).sum())) / n_poly, 2),
        "dropped_bad_ndvi_pixels": int((clear & ~good).sum()),
        "water_pct_of_polygon": _r(100.0 * int((inside & (scl == WATER_SCL)).sum()) / n_poly, 2),
        "ndvi_pixels": int(vals.size),
        "scl_breakdown_pct": breakdown,
        "ndvi": _ndvi_stats(vals),
        "scale_offset": {"red": [sr, orr], "nir": [sn, on]},
        "overlay": _overlay(ndvi_map, tf, crs, poly),
    }


# ------------------------------------------------------------------ public entry point
def _run(poly, area_km2: float, days_back: int, max_scene_cloud: float, deadline: float) -> Dict[str, Any]:
    items = _search_items(poly, days_back)
    if not items:
        raise SentinelError(404, f"No Sentinel-2 L2A scenes found for this area in the last {days_back} days.")

    cands = [it for it in items
             if it.datetime is not None
             and it.properties.get("eo:cloud_cover", 100.0) <= max_scene_cloud
             and all(k in it.assets for k in ("red", "nir", "scl"))
             and _covers(it, poly)]
    if not cands:
        raise SentinelError(404, "No scene both fully covers this polygon and passes the scene cloud limit. "
                                 "Try more days back, a higher cloud limit, or a polygon inside one scene.")
    cands.sort(key=lambda it: (it.properties.get("eo:cloud_cover", 100.0), -it.datetime.timestamp()))
    cands = cands[:MAX_CANDIDATES]

    evaluated: List[Dict[str, Any]] = []
    errors = 0
    for it in cands:
        if time.monotonic() > deadline:
            break
        try:
            pct = _scl_clear_pct(it, poly)
        except Exception as e:  # one bad scene must not kill the request
            errors += 1
            log.warning("SCL read failed for %s: %s", it.id, type(e).__name__)
            continue
        if pct is None:
            continue
        evaluated.append({"id": it.id, "datetime": it.datetime.isoformat(),
                          "scene_cloud_cover_pct": _r(it.properties.get("eo:cloud_cover", float("nan")), 2),
                          "polygon_clear_pct_scl_estimate": _r(pct, 2), "_item": it})
    if not evaluated:
        if errors:
            raise SentinelError(502, "Could not read satellite data (network problem?). Check your connection and try again.")
        if time.monotonic() > deadline:
            raise SentinelError(504, "The satellite request took too long. Try a smaller area.")
        raise SentinelError(404, "No candidate scene had pixels inside the polygon.")

    top = max(e["polygon_clear_pct_scl_estimate"] for e in evaluated)
    pool = [e for e in evaluated if e["polygon_clear_pct_scl_estimate"] >= top - 2.0]
    best = max(pool, key=lambda e: e["_item"].datetime.timestamp())
    if best["polygon_clear_pct_scl_estimate"] < MIN_USABLE_PCT:
        raise SentinelError(404, f"Best scene has only {best['polygon_clear_pct_scl_estimate']:.1f}% clear pixels "
                                 f"inside the polygon. Try more days back.")
    if time.monotonic() > deadline:
        raise SentinelError(504, "The satellite request took too long. Try a smaller area.")

    item = best["_item"]
    core = _compute_item(item, poly, area_km2)
    overlay = core.pop("overlay")
    cands_public = [{k: v for k, v in e.items() if k != "_item"} for e in evaluated]
    return {
        "provenance": "observed_satellite",
        "label": "Observed Sentinel-2 NDVI",
        "source": "Sentinel-2 L2A via Earth Search STAC (earth-search.aws.element84.com)",
        "scene": {
            "id": item.id,
            "datetime": item.datetime.isoformat(),
            "scene_cloud_cover_pct": _r(item.properties.get("eo:cloud_cover", float("nan")), 2),
            "mgrs_tile": item.properties.get("s2:mgrs_tile"),
            "platform": item.properties.get("platform"),
        },
        "coverage": {k: core[k] for k in (
            "area_km2", "polygon_pixels_10m", "usable_pixels", "usable_pct_of_polygon",
            "cloud_or_invalid_pct_of_polygon", "water_pct_of_polygon", "ndvi_pixels",
            "dropped_bad_ndvi_pixels", "scl_breakdown_pct")},
        "ndvi": core["ndvi"],
        "processing": {
            "pixel_size_m": 10,
            "reflectance_scale_offset": core["scale_offset"],
            "scl_excluded_classes": {str(k): SCL_NAMES[k] for k in INVALID_SCL},
            "water_excluded_from_ndvi_stats": True,
            "scene_ranking": "polygon clear-pixel % from the 20 m SCL band (ties within 2 points -> most recent)",
            "search_days_back": days_back,
            "max_scene_cloud_pct": max_scene_cloud,
            "candidates_evaluated": cands_public,
        },
        "overlay": overlay,
        "limitations": LIMITATIONS,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def compute_ndvi(aoi: Dict[str, Any], days_back: int = 90, max_scene_cloud: float = 80.0) -> Dict[str, Any]:
    poly, area_km2 = _validate_polygon(aoi)
    rounded = [[round(x, 5), round(y, 5)] for x, y in aoi["coordinates"][0]]
    key = hashlib.sha1(json.dumps([rounded, days_back, max_scene_cloud]).encode()).hexdigest()
    hit = _cache_get(key)
    if hit is not None:
        return {**hit, "cached": True}

    deadline = time.monotonic() + TIME_BUDGET_S
    try:
        with rasterio.Env(**GDAL_OPTS):
            result = _run(poly, area_km2, days_back, max_scene_cloud, deadline)
    except SentinelError:
        raise
    except Exception as e:
        log.exception("Unexpected Sentinel-2 error")
        raise SentinelError(502, f"Could not read satellite data ({type(e).__name__}). "
                                 "Check your internet connection and try again.")
    _cache_put(key, result)
    return {**result, "cached": False}
