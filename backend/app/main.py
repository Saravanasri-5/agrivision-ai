import csv
import io
import os
import time
import datetime as dt
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator
from shapely.geometry import shape
from sqlalchemy.orm import Session

from . import services as S
from .db import AnalysisJob, HistoricalResult, Report, StudyArea, get_db, init_db
from .engine import (CLASSES, FEATURES, MAX_AREA_KM2, MIN_AREA_KM2, MODEL_VERSION, YEARS,
                     aoi_area_km2, classify_features, compute_stats)
from .reports import build_pdf
from . import sentinel as SEN

import numpy as np

REPORT_DIR = os.getenv("REPORT_DIR", "./reports")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "300"))
ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")]

app = FastAPI(title="AgriVision AI API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])
HITS: Dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    now, dq = time.time(), HITS[ip]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= RATE_LIMIT:
        return JSONResponse({"detail": "Rate limit exceeded. Try again shortly."}, status_code=429)
    dq.append(now)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


@app.on_event("startup")
def startup():
    os.makedirs(REPORT_DIR, exist_ok=True)
    init_db()


# ------------------------------------------------------------------ models
class AnalysisRequest(BaseModel):
    name: str = Field("Custom study area", max_length=120)
    aoi: Dict[str, Any]
    min_confidence: float = Field(0.0, ge=0.0, le=0.99)

    @field_validator("aoi")
    @classmethod
    def valid_aoi(cls, v):
        if v.get("type") != "Polygon" or not v.get("coordinates"):
            raise ValueError("AOI must be a GeoJSON Polygon")
        ring = v["coordinates"][0]
        if len(ring) < 4 or len(ring) > 500:
            raise ValueError("Polygon must have between 3 and 500 vertices")
        try:
            g = shape(v)
        except Exception:
            raise ValueError("Invalid geometry")
        if not g.is_valid:
            raise ValueError("Invalid polygon (self-intersecting?)")
        minx, miny, maxx, maxy = g.bounds
        if minx < -180 or maxx > 180 or miny < -80 or maxy > 80:
            raise ValueError("Coordinates out of range (expected lon/lat WGS84)")
        return v


class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    area_km2: float
    message: str


class ClassifyRequest(BaseModel):
    ndvi_peak: float = Field(..., ge=-1, le=1)
    ndvi_mean: float = Field(..., ge=-1, le=1)
    ndvi_std: float = Field(..., ge=0, le=1)
    evi: float = Field(..., ge=-1, le=1)
    ndwi: float = Field(..., ge=-1, le=1)
    swir: float = Field(..., ge=-1, le=1)


class ReportRequest(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=32)
    year: int = 2026
    period_a: int = 2025
    period_b: int = 2026


class ChatRequest(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=32)
    message: str = Field(..., min_length=1, max_length=300)
    period_a: int = 2025
    period_b: int = 2026


def year_ok(y: int) -> int:
    if y not in YEARS:
        raise HTTPException(422, f"Year must be one of {YEARS}")
    return y


def job_ok(db: Session, job_id: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Analysis job not found")
    if job.status != "done":
        raise HTTPException(409, f"Analysis job is {job.status}")
    return job


# ------------------------------------------------------------------ endpoints
@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_VERSION, "years": YEARS}


@app.post("/analysis", response_model=AnalysisResponse)
def start_analysis(req: AnalysisRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    area = aoi_area_km2(req.aoi)
    if area < MIN_AREA_KM2:
        raise HTTPException(422, f"Please select an area of at least {MIN_AREA_KM2:.0f} km² (selected {area:.1f} km²)")
    if area > MAX_AREA_KM2:
        raise HTTPException(422, f"Selected area too large (max {MAX_AREA_KM2:.0f} km²)")
    job = S.create_job(db, req.aoi, req.name, {"min_confidence": req.min_confidence})
    bg.add_task(S.execute_job, job.id)
    return AnalysisResponse(job_id=job.id, status="queued", area_km2=round(area, 2), message="Analysis started")


@app.get("/analysis/{job_id}")
def analysis_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Analysis job not found")
    sa = db.get(StudyArea, job.study_area_id)
    return {"job_id": job.id, "status": job.status, "progress": job.progress, "error": job.error,
            "study_area": {"name": sa.name, "area_km2": round(sa.area_km2, 2), "geometry": sa.geometry}}


@app.get("/parcels")
def parcels(job_id: str, year: int = 2026, min_confidence: float = Query(0.0, ge=0, le=0.99), db: Session = Depends(get_db)):
    job_ok(db, job_id)
    return S.feature_collection(S.load(db, job_id, year_ok(year), min_confidence))


@app.get("/parcels/{job_id}/{parcel_id}")
def parcel_detail(job_id: str, parcel_id: str, year: int = 2026, db: Session = Depends(get_db)):
    job_ok(db, job_id)
    cur = [r for r in S.load(db, job_id, year_ok(year)) if r["parcel_id"] == parcel_id]
    if not cur:
        raise HTTPException(404, "Parcel not found")
    hist = []
    for y in YEARS:
        r = next((x for x in S.load(db, job_id, y) if x["parcel_id"] == parcel_id), None)
        if r:
            hist.append({"year": y, "crop_type": r["crop_type"], "confidence": r["confidence"]})
    return {**S.to_feature(cur[0], extra=True)["properties"], "history": hist,
            "centroid": [cur[0]["centroid_lon"], cur[0]["centroid_lat"]]}


@app.post("/classify")
def classify(req: ClassifyRequest):
    x = np.array([[getattr(req, f) for f in FEATURES]])
    return classify_features(x)[0]


@app.get("/statistics")
def statistics(job_id: str, year: int = 2026, min_confidence: float = Query(0.0, ge=0, le=0.99), db: Session = Depends(get_db)):
    job_ok(db, job_id)
    return {"job_id": job_id, "year": year, "stats": compute_stats(S.load(db, job_id, year_ok(year), min_confidence))}


@app.get("/history")
def history(job_id: str, period_a: int = 2025, period_b: int = 2026, db: Session = Depends(get_db)):
    job_ok(db, job_id)
    year_ok(period_a), year_ok(period_b)
    hist = {h.year: h.stats for h in db.query(HistoricalResult).filter_by(job_id=job_id).all()}
    sa, sb = hist[period_a], hist[period_b]
    delta = {c: {"area_ha": round(sb["crop_area_ha"][c] - sa["crop_area_ha"][c], 2),
                 "pct_points": round(sb["crop_pct"][c] - sa["crop_pct"][c], 1),
                 "parcels": sb["crop_count"][c] - sa["crop_count"][c]} for c in CLASSES}
    return {"period_a": {"year": period_a, "stats": sa}, "period_b": {"year": period_b, "stats": sb}, "delta": delta,
            "timeline": [{"year": y, **hist[y]["crop_area_ha"]} for y in sorted(hist)]}


@app.get("/change-detection")
def change_detection(job_id: str, period_a: int = 2025, period_b: int = 2026, db: Session = Depends(get_db)):
    job_ok(db, job_id)
    return S.detect_changes(db, job_id, year_ok(period_a), year_ok(period_b))


@app.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    job_ok(db, req.job_id)
    return S.answer_chat(db, req.job_id, req.message, year_ok(req.period_a), year_ok(req.period_b))


def _make_pdf(db: Session, job_id: str, year: int, a: int, b: int) -> str:
    job = job_ok(db, job_id)
    sa = db.get(StudyArea, job.study_area_id)
    rows = S.load(db, job_id, year_ok(year))
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f"agrivision_{job_id[:8]}_{year}_{dt.datetime.utcnow():%H%M%S}.pdf")
    build_pdf(path, {"name": sa.name, "area_km2": sa.area_km2}, compute_stats(rows),
              S.detect_changes(db, job_id, year_ok(a), year_ok(b)), rows, year, a, b)
    return path


@app.post("/reports")
def create_report(req: ReportRequest, db: Session = Depends(get_db)):
    path = _make_pdf(db, req.job_id, req.year, req.period_a, req.period_b)
    rep = Report(job_id=req.job_id, file_path=path, format="pdf", period_a=req.period_a, period_b=req.period_b)
    db.add(rep)
    db.commit()
    return {"report_id": rep.id, "download_url": f"/reports/{rep.id}/download"}


@app.get("/reports/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db)):
    rep = db.get(Report, report_id)
    if not rep or not os.path.exists(rep.file_path):
        raise HTTPException(404, "Report not found")
    return FileResponse(rep.file_path, media_type="application/pdf", filename=os.path.basename(rep.file_path))


@app.get("/export")
def export(job_id: str, format: str = Query("geojson", pattern="^(csv|geojson|pdf)$"), year: int = 2026,
           period_a: int = 2025, period_b: int = 2026, min_confidence: float = Query(0.0, ge=0, le=0.99),
           db: Session = Depends(get_db)):
    job_ok(db, job_id)
    rows = S.load(db, job_id, year_ok(year), min_confidence)
    name = f"agrivision_{job_id[:8]}_{year}"
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["parcel_id", "year", "crop_type", "confidence", "confidence_level", "area_ha",
                    "centroid_lon", "centroid_lat", "model_version"])
        for r in rows:
            w.writerow([r["parcel_id"], r["year"], r["crop_type"], r["confidence"], r["confidence_level"],
                        r["area_ha"], r["centroid_lon"], r["centroid_lat"], r["model_version"]])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    if format == "geojson":
        fc = {"type": "FeatureCollection", "features": [S.to_feature(r, extra=True) for r in rows]}
        import json
        return Response(json.dumps(fc), media_type="application/geo+json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.geojson"'})
    path = _make_pdf(db, job_id, year, period_a, period_b)
    return FileResponse(path, media_type="application/pdf", filename=f"{name}.pdf")
# ------------------------------------------------------------------ real satellite data (Sentinel-2 NDVI)
# Everything below returns OBSERVED satellite data. It is independent of the simulated crop analysis above.
class NdviRequest(BaseModel):
    aoi: Dict[str, Any]
    days_back: int = Field(90, ge=7, le=365)
    max_scene_cloud: float = Field(80.0, ge=0, le=100)


@app.post("/satellite/ndvi")
def satellite_ndvi(req: NdviRequest):
    try:
        return SEN.compute_ndvi(req.aoi, req.days_back, req.max_scene_cloud)
    except SEN.SentinelError as e:
        raise HTTPException(e.status, e.message)


@app.get("/provenance")
def provenance():
    return SEN.PROVENANCE