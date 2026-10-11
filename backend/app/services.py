import datetime as dt
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .db import (AnalysisJob, CropPrediction, HistoricalResult, Parcel, Project,
                 SessionLocal, StudyArea, User)
from .engine import (CLASSES, MODEL_VERSION, YEARS, aoi_area_km2, aoi_hash,
                     compute_stats, run_analysis)

CHANGE_CATEGORIES = ["Paddy → Banana", "Banana → Paddy", "New Cultivation", "Non-Crop Conversion", "Other Vegetation Shift"]
CROPS = ("Paddy", "Banana")


def ensure_defaults(db: Session) -> Project:
    if not db.query(User).first():
        u = User(email="demo@agrivision.ai", name="Demo Officer")
        db.add(u)
        db.flush()
        db.add(Project(user_id=u.id, name="Tirunelveli Crop Survey"))
        db.commit()
    return db.query(Project).first()


def create_job(db: Session, geom: dict, name: str, params: dict) -> AnalysisJob:
    proj = ensure_defaults(db)
    sa = StudyArea(project_id=proj.id, name=name, geometry=geom, area_km2=aoi_area_km2(geom))
    db.add(sa)
    db.flush()
    job = AnalysisJob(id=uuid.uuid4().hex, study_area_id=sa.id, status="queued", progress=0,
                      params=params, aoi_hash=aoi_hash(geom))
    db.add(job)
    db.commit()
    return job


def execute_job(job_id: str) -> None:
    """Runs in a FastAPI background task (swap for Celery/RQ in production)."""
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        job.status, job.progress = "running", 10
        db.commit()
        sa = db.get(StudyArea, job.study_area_id)
        parcels, preds = run_analysis(sa.geometry)
        job.progress = 60
        db.commit()
        for p in parcels:
            db.add(Parcel(job_id=job_id, parcel_id=p["parcel_id"], geometry=p["geometry"], area_ha=p["area_ha"],
                          centroid_lon=p["centroid_lon"], centroid_lat=p["centroid_lat"]))
        for y, res in preds.items():
            rows = []
            for p, r in zip(parcels, res):
                db.add(CropPrediction(job_id=job_id, parcel_id=p["parcel_id"], year=y, crop_type=r["crop_type"],
                                      confidence=r["confidence"], confidence_level=r["confidence_level"],
                                      probabilities=r["probabilities"], features=r["features"],
                                      explanation=r["explanation"], model_version=MODEL_VERSION,
                                      date=dt.date(y, 9, 30)))
                rows.append({**r, "area_ha": p["area_ha"]})
            db.add(HistoricalResult(job_id=job_id, year=y, stats=compute_stats(rows)))
        job.status, job.progress, job.finished_at = "done", 100, dt.datetime.utcnow()
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status, job.error = "failed", str(e)[:500]
        db.commit()
    finally:
        db.close()


def load(db: Session, job_id: str, year: int, min_conf: float = 0.0) -> List[Dict[str, Any]]:
    q = (db.query(Parcel, CropPrediction)
         .join(CropPrediction, (CropPrediction.job_id == Parcel.job_id) & (CropPrediction.parcel_id == Parcel.parcel_id))
         .filter(Parcel.job_id == job_id, CropPrediction.year == year, CropPrediction.confidence >= min_conf)
         .order_by(Parcel.id))
    return [{
        "parcel_id": p.parcel_id, "geometry": p.geometry, "area_ha": p.area_ha,
        "centroid_lon": p.centroid_lon, "centroid_lat": p.centroid_lat, "year": c.year,
        "crop_type": c.crop_type, "confidence": c.confidence, "confidence_level": c.confidence_level,
        "probabilities": c.probabilities, "features": c.features, "explanation": c.explanation,
        "model_version": c.model_version,
    } for p, c in q.all()]


def to_feature(r: Dict[str, Any], extra: bool = False) -> dict:
    keys = ["parcel_id", "area_ha", "crop_type", "confidence", "confidence_level", "year"]
    props = {k: r[k] for k in keys}
    if extra:
        props.update({k: r[k] for k in ("explanation", "probabilities", "features", "model_version")})
    return {"type": "Feature", "geometry": r["geometry"], "properties": props}


def feature_collection(rows: List[Dict[str, Any]]) -> dict:
    return {"type": "FeatureCollection", "features": [to_feature(r) for r in rows]}


def categorize(a: str, b: str) -> Optional[str]:
    if a == b:
        return None
    if a == "Paddy" and b == "Banana":
        return "Paddy → Banana"
    if a == "Banana" and b == "Paddy":
        return "Banana → Paddy"
    if a not in CROPS and b in CROPS:
        return "New Cultivation"
    if a in CROPS and b not in CROPS:
        return "Non-Crop Conversion"
    return "Other Vegetation Shift"


def detect_changes(db: Session, job_id: str, a: int, b: int, min_conf: float = 0.0) -> Dict[str, Any]:
    ra = {r["parcel_id"]: r for r in load(db, job_id, a, min_conf)}
    rb = {r["parcel_id"]: r for r in load(db, job_id, b, min_conf)}
    changes = []
    for pid, y in rb.items():
        x = ra.get(pid)
        if not x:
            continue
        cat = categorize(x["crop_type"], y["crop_type"])
        if cat:
            changes.append({"parcel_id": pid, "from_crop": x["crop_type"], "to_crop": y["crop_type"], "category": cat,
                            "area_ha": y["area_ha"], "confidence": round(min(x["confidence"], y["confidence"]), 3),
                            "message": f"Crop Change Detected: {x['crop_type']} → {y['crop_type']}",
                            "geometry": y["geometry"]})
    summary = {c: {"count": 0, "area_ha": 0.0} for c in CHANGE_CATEGORIES}
    for c in changes:
        summary[c["category"]]["count"] += 1
        summary[c["category"]]["area_ha"] = round(summary[c["category"]]["area_ha"] + c["area_ha"], 2)
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": c["geometry"], "properties": {k: v for k, v in c.items() if k != "geometry"}}
        for c in changes]}
    return {"period_a": a, "period_b": b, "total_changed": len(changes), "total_parcels": len(rb),
            "summary": summary, "changes": [{k: v for k, v in c.items() if k != "geometry"} for c in changes],
            "geojson": fc}


def answer_chat(db: Session, job_id: str, msg: str, a: int, b: int) -> Dict[str, Any]:
    """Local retrieval assistant: intent matching + database queries. No external LLM."""
    m = msg.lower()
    rows = load(db, job_id, b)
    st = compute_stats(rows)
    area = st["crop_area_ha"]
    hl: List[str] = []
    if not rows:
        return {"answer": "No analysis data found for this job yet.", "highlight_parcels": []}
    if "paddy" in m and "banana" in m and any(w in m for w in ("chang", "convert", "switch", "shift", " to ")):
        want = "Paddy → Banana" if m.index("paddy") < m.index("banana") else "Banana → Paddy"
        ch = detect_changes(db, job_id, a, b)
        hit = [c for c in ch["changes"] if c["category"] == want]
        hl = [c["parcel_id"] for c in hit]
        ids = ", ".join(hl[:12]) + (" ..." if len(hl) > 12 else "")
        ans = (f"{len(hit)} parcels changed {want} between {a} and {b} "
               f"({sum(c['area_ha'] for c in hit):.1f} ha). " + (f"Parcels: {ids}. Highlighted on the map." if hit else ""))
    elif any(w in m for w in ("chang", "transition", "converted")):
        ch = detect_changes(db, job_id, a, b)
        parts = [f"{k}: {v['count']} parcels ({v['area_ha']} ha)" for k, v in ch["summary"].items() if v["count"]]
        ans = f"Between {a} and {b}, {ch['total_changed']} of {ch['total_parcels']} parcels changed. " + "; ".join(parts) + "."
    elif any(w in m for w in ("largest", "most", "dominant", "biggest", "occupies", "major")):
        top = max(area, key=area.get)
        ans = f"{top} occupies the largest area in {b}: {area[top]:.1f} ha ({st['crop_pct'][top]}% of mapped land)."
    elif "confidence" in m:
        lv = st["confidence_levels"]
        if "low" in m:
            hl = [r["parcel_id"] for r in rows if r["confidence_level"] == "Low"][:200]
            ans = f"{lv['Low']} parcels have Low confidence (below 60%). They are highlighted on the map for field verification."
        else:
            ans = (f"Average confidence in {b} is {st['avg_confidence'] * 100:.1f}%. High: {lv['High']}, "
                   f"Medium: {lv['Medium']}, Low: {lv['Low']} parcels.")
    elif "parcel" in m and any(w in m for w in ("how many", "total", "count", "number")):
        ans = f"There are {st['total_parcels']} parcels covering {st['total_area_ha']:.1f} ha. " + \
              ", ".join(f"{c}: {n}" for c, n in st["crop_count"].items()) + "."
    elif "paddy" in m or "banana" in m or "other" in m or "non" in m:
        c = "Paddy" if "paddy" in m else "Banana" if "banana" in m else "Other Vegetation" if "other" in m else "Non-Agricultural"
        hl = [r["parcel_id"] for r in rows if r["crop_type"] == c][:300]
        ans = f"{c} covers {area[c]:.1f} ha ({st['crop_pct'][c]}%) across {st['crop_count'][c]} parcels in {b}."
    elif "area" in m or "hectare" in m:
        ans = (f"Total mapped area is {st['total_area_ha']:.1f} ha; agricultural area (Paddy + Banana) is "
               f"{st['agricultural_area_ha']:.1f} ha.")
    else:
        ans = ("I can answer from the analysis database. Try: 'Which crop occupies the largest area?', "
               "'Show parcels where Paddy changed to Banana', 'What is the average confidence score?', "
               "'How many parcels are there?' or 'Show low confidence parcels'.")
    return {"answer": ans, "highlight_parcels": hl}
