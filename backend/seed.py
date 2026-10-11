"""Seed demo user/project and two pre-computed study areas (Ambasamudram, Cheranmahadevi)."""
import json
from app import services as S
from app.db import SessionLocal, init_db

AREAS = {
    "Ambasamudram Taluk (demo)": [[77.45, 8.68], [77.52, 8.68], [77.52, 8.73], [77.45, 8.73], [77.45, 8.68]],
    "Cheranmahadevi Taluk (demo)": [[77.50, 8.66], [77.58, 8.66], [77.58, 8.72], [77.50, 8.72], [77.50, 8.66]],
}

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    S.ensure_defaults(db)
    for name, ring in AREAS.items():
        job = S.create_job(db, {"type": "Polygon", "coordinates": [ring]}, name, {"min_confidence": 0})
        S.execute_job(job.id)
        print(f"Seeded {name}: job_id={job.id}")
    db.close()
