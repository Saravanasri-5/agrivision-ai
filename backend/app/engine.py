"""AI + simulation layer.

`observe()` is the ONLY place that fabricates satellite-derived features. To go live with
Sentinel-2, replace it with zonal statistics of NDVI/EVI/NDWI/SWIR composites over each
parcel polygon (same 6 feature names) - classifier, API and UI stay unchanged.
"""
import hashlib
import json
import math
from typing import Any, Dict, List

import numpy as np
from shapely.affinity import scale as shp_scale
from shapely.geometry import Polygon, shape

CLASSES = ["Paddy", "Banana", "Other Vegetation", "Non-Agricultural"]
YEARS = [2024, 2025, 2026]
FEATURES = ["ndvi_peak", "ndvi_mean", "ndvi_std", "evi", "ndwi", "swir"]
MODEL_VERSION = "rf-baseline-1.0"
MIN_AREA_KM2 = 20.0
MAX_AREA_KM2 = 2000.0

MEANS = {
    "Paddy": np.array([0.82, 0.58, 0.22, 0.55, 0.25, 0.18]),
    "Banana": np.array([0.78, 0.72, 0.07, 0.60, 0.05, 0.22]),
    "Other Vegetation": np.array([0.62, 0.50, 0.12, 0.40, 0.02, 0.25]),
    "Non-Agricultural": np.array([0.25, 0.20, 0.06, 0.15, -0.10, 0.40]),
}
SIGMA = np.array([0.09, 0.08, 0.035, 0.08, 0.07, 0.07])
TRANS = {
    "Paddy": [0.89, 0.07, 0.03, 0.01],
    "Banana": [0.05, 0.92, 0.02, 0.01],
    "Other Vegetation": [0.08, 0.06, 0.84, 0.02],
    "Non-Agricultural": [0.0, 0.0, 0.03, 0.97],
}

_model = None
_cache: Dict[str, Any] = {}


# ---------------------------------------------------------------- geometry helpers
def make_proj(lat0: float, lon0: float):
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110574.0
    fwd = lambda lon, lat: ((lon - lon0) * kx, (lat - lat0) * ky)
    inv = lambda x, y: (x / kx + lon0, y / ky + lat0)
    return fwd, inv


def aoi_area_km2(geom: dict) -> float:
    poly = shape(geom)
    c = poly.centroid
    fwd, _ = make_proj(c.y, c.x)
    return Polygon([fwd(*p) for p in poly.exterior.coords]).area / 1e6


def aoi_hash(geom: dict) -> str:
    rounded = [[round(x, 5), round(y, 5)] for x, y in geom["coordinates"][0]]
    return hashlib.sha1(json.dumps(rounded).encode()).hexdigest()


# ---------------------------------------------------------------- model
def get_model():
    global _model
    if _model is None:
        from sklearn.ensemble import RandomForestClassifier
        rng = np.random.default_rng(42)
        X, y = [], []
        for ci, c in enumerate(CLASSES):
            X.append(MEANS[c] + rng.normal(0, 1, (1500, 6)) * SIGMA * 1.15)
            y += [ci] * 1500
        _model = RandomForestClassifier(n_estimators=150, min_samples_leaf=3, random_state=42, n_jobs=1)
        _model.fit(np.vstack(X), np.array(y))
    return _model


def level(conf: float) -> str:
    return "High" if conf >= 0.80 else "Medium" if conf >= 0.60 else "Low"


def explain(x: np.ndarray, crop: str, probs: Dict[str, float]) -> List[str]:
    f = dict(zip(FEATURES, [float(v) for v in x]))
    out: List[str] = []
    if crop == "Paddy":
        if f["ndvi_peak"] >= 0.70:
            out.append(f"High peak NDVI ({f['ndvi_peak']:.2f}) during the growing season")
        if f["ndwi"] >= 0.12:
            out.append(f"Elevated water index (NDWI {f['ndwi']:.2f}) typical of flooded paddy fields")
        if f["ndvi_std"] >= 0.15:
            out.append(f"Strong seasonal NDVI swing (sd {f['ndvi_std']:.2f}) from transplanting to harvest")
    elif crop == "Banana":
        if f["ndvi_mean"] >= 0.62:
            out.append(f"High mean NDVI ({f['ndvi_mean']:.2f}) - dense perennial canopy")
        if f["ndvi_std"] <= 0.12:
            out.append(f"Stable year-round vegetation signal (NDVI sd {f['ndvi_std']:.2f})")
        if f["evi"] >= 0.50:
            out.append(f"Strong enhanced vegetation index (EVI {f['evi']:.2f})")
    elif crop == "Other Vegetation":
        out.append(f"Moderate vegetation signal (mean NDVI {f['ndvi_mean']:.2f}) without a paddy or banana pattern")
    else:
        out.append(f"Low peak NDVI ({f['ndvi_peak']:.2f}) - little or no active vegetation")
        if f["swir"] >= 0.32:
            out.append(f"High SWIR reflectance ({f['swir']:.2f}) indicating bare soil or built-up surface")
    if len(out) < 2 and crop != "Non-Agricultural":
        out.append(f"Spectral profile (NDVI mean {f['ndvi_mean']:.2f}, NDWI {f['ndwi']:.2f}) is closest to {crop} samples")
    out.append(f"Similarity to known {crop} training samples: model probability {probs[crop] * 100:.0f}%")
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    if ranked[1][1] >= 0.15:
        out.append(f"Ambiguity: {ranked[1][0]} also plausible ({ranked[1][1] * 100:.0f}%)")
    return out


def classify_features(X: np.ndarray) -> List[Dict[str, Any]]:
    X = np.atleast_2d(X)
    proba = get_model().predict_proba(X)
    res = []
    for x, p in zip(X, proba):
        k = int(np.argmax(p))
        crop = CLASSES[k]
        conf = float(min(p[k], 0.97))  # never claim certainty
        probs = {c: round(float(p[i]), 3) for i, c in enumerate(CLASSES)}
        res.append({
            "crop_type": crop, "confidence": round(conf, 3), "confidence_level": level(conf),
            "probabilities": probs, "features": {n: round(float(v), 3) for n, v in zip(FEATURES, x)},
            "explanation": explain(x, crop, probs),
        })
    return res


# ---------------------------------------------------------------- simulation layer
def generate_parcels(geom: dict):
    poly = shape(geom)
    c = poly.centroid
    fwd, inv = make_proj(c.y, c.x)
    P = Polygon([fwd(*p) for p in poly.exterior.coords])
    s = 180.0
    if P.area / (s * s) > 1500:
        s = math.sqrt(P.area / 1500)
    minx, miny, maxx, maxy = P.bounds
    nx, ny = int((maxx - minx) / s) + 2, int((maxy - miny) / s) + 2
    seed0 = int(aoi_hash(geom)[:8], 16)
    nodes: Dict[Any, Any] = {}

    def node(i, j):
        if (i, j) not in nodes:
            r = np.random.default_rng([seed0, i, j, 1])
            nodes[(i, j)] = (minx + (i + r.uniform(-0.28, 0.28)) * s, miny + (j + r.uniform(-0.28, 0.28)) * s)
        return nodes[(i, j)]

    parcels = []
    n = 0
    for i in range(nx):
        for j in range(ny):
            q = Polygon([node(i, j), node(i + 1, j), node(i + 1, j + 1), node(i, j + 1)])
            if not q.is_valid or not P.contains(q.centroid):
                continue
            q = shp_scale(q, 0.9, 0.9, origin="centroid")
            if not P.contains(q):
                q = q.intersection(P)
                if q.geom_type == "MultiPolygon":
                    q = max(q.geoms, key=lambda g: g.area)
                if q.geom_type != "Polygon":
                    continue
            if q.area < 2000:
                continue
            n += 1
            ring = [[round(a, 6), round(b, 6)] for a, b in (inv(x, y) for x, y in q.exterior.coords)]
            cen = inv(*q.centroid.coords[0])
            parcels.append({
                "parcel_id": f"AV-{n:04d}", "ij": (i, j),
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "area_ha": round(q.area / 1e4, 3),
                "centroid_lon": round(cen[0], 6), "centroid_lat": round(cen[1], 6),
            })
    return parcels, seed0


def _crop_sequence(seed0: int, i: int, j: int) -> List[str]:
    r = np.random.default_rng([seed0, i, j, 2])
    z = math.sin(i * 0.13) + math.cos(j * 0.11)
    p = np.array([0.42, 0.28, 0.18, 0.12])
    if z > 0.6:
        p += np.array([-0.2, 0.2, 0, 0])
    elif z < -0.6:
        p += np.array([0.15, -0.15, 0, 0])
    p = np.clip(p, 0.02, None)
    p /= p.sum()
    seq = [CLASSES[int(r.choice(4, p=p))]]
    for _ in YEARS[1:]:
        seq.append(CLASSES[int(r.choice(4, p=TRANS[seq[-1]]))])
    return seq


def observe(seed0: int, i: int, j: int, year: int, crop: str) -> np.ndarray:
    """SIMULATED per-parcel spectral index features (replace with Sentinel-2 zonal stats)."""
    r = np.random.default_rng([seed0, i, j, year])
    q = r.uniform(0.7, 1.6)  # per-parcel noise: some parcels end up ambiguous
    x = np.clip(MEANS[crop] + r.normal(0, 1, 6) * SIGMA * q, -1, 1)
    x[2] = max(x[2], 0.0)
    return x


def run_analysis(geom: dict):
    key = aoi_hash(geom)
    if key in _cache:
        return _cache[key]
    parcels, seed0 = generate_parcels(geom)
    preds: Dict[int, List[Dict[str, Any]]] = {y: [] for y in YEARS}
    seqs = [_crop_sequence(seed0, *p["ij"]) for p in parcels]
    for yi, y in enumerate(YEARS):
        X = np.vstack([observe(seed0, *p["ij"], y, seqs[k][yi]) for k, p in enumerate(parcels)])
        preds[y] = classify_features(X)
    if len(_cache) > 8:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (parcels, preds)
    return parcels, preds


# ---------------------------------------------------------------- statistics
def compute_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = sum(r["area_ha"] for r in rows)
    area = {c: 0.0 for c in CLASSES}
    cnt = {c: 0 for c in CLASSES}
    lv = {"High": 0, "Medium": 0, "Low": 0}
    for r in rows:
        area[r["crop_type"]] += r["area_ha"]
        cnt[r["crop_type"]] += 1
        lv[r["confidence_level"]] += 1
    bins = [("<1 ha", 0, 1), ("1-2 ha", 1, 2), ("2-3 ha", 2, 3), ("3-4 ha", 3, 4), (">4 ha", 4, 1e9)]
    return {
        "total_parcels": len(rows),
        "total_area_ha": round(total, 2),
        "agricultural_area_ha": round(area["Paddy"] + area["Banana"], 2),
        "avg_confidence": round(sum(r["confidence"] for r in rows) / len(rows), 3) if rows else 0.0,
        "crop_area_ha": {c: round(v, 2) for c, v in area.items()},
        "crop_count": cnt,
        "crop_pct": {c: round(100 * v / total, 1) if total else 0.0 for c, v in area.items()},
        "confidence_levels": lv,
        "size_distribution": [{"bucket": b, "count": sum(1 for r in rows if lo <= r["area_ha"] < hi)} for b, lo, hi in bins],
    }
