# AGRIVISION AI — Satellite-Powered Agricultural Intelligence

Paddy vs Banana parcel classification for Ambasamudram & Cheranmahadevi taluks (Tirunelveli). Runs fully locally with a **simulated Sentinel-2 feature layer** — no paid APIs, no cloud.

## Structure
```
backend/   FastAPI app (app/main.py API, engine.py AI + simulation, services.py, reports.py, db.py), seed.py, tests/
frontend/  Next.js 14 + TypeScript + Tailwind + Leaflet + Recharts
database/  schema.sql (PostgreSQL + PostGIS)
data/      sample_aoi.geojson
docker-compose.yml
```

## Option A — Docker (PostGIS + API + UI)
```bash
docker compose up --build
docker compose exec backend python seed.py      # optional demo data
```
UI: http://localhost:3000 · API docs: http://localhost:8000/docs

## Option B — Local (SQLite, no Docker)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # optional
uvicorn app.main:app --reload --port 8000
# in a second terminal
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                                           # http://localhost:3000
```
Local PostgreSQL instead of SQLite: create a PostGIS database, run `database/schema.sql`, set `DATABASE_URL=postgresql://user:pass@localhost:5432/agrivision`.

## Using the app
1. Open the site → **Launch Analysis**.
2. Choose a taluk preset or draw a polygon/rectangle (top-right map tools). Areas under 20 km² are rejected (UI and API).
3. **Analyze** → parcels appear coloured by crop (Paddy green, Banana yellow, Other light green, Non-Agri gray). Click a parcel for class, confidence and "Why classified?".
4. **Compare** tab: pick Period A/B → area deltas, change categories, map visualization. **Assistant** tab: ask questions answered from the database.
5. Export PDF / CSV / GeoJSON from the left panel.

## Tests
```bash
cd backend && pytest -q
```

## Moving to real Sentinel-2
Only `observe()` in `backend/app/engine.py` fabricates data. Replace it with zonal statistics (NDVI peak/mean/std, EVI, NDWI, SWIR) per parcel from real composites, and retrain `get_model()` on labelled field samples. Parcel generation can be replaced with a segmentation model or cadastral polygons. The API, DB and UI are unchanged.

## Notes
- Map tiles (OpenStreetMap / Esri imagery) need internet; everything else is offline.
- Confidence is capped at 97%; Low (<60%) parcels should be field-verified.
- Rate limiting is in-process (`RATE_LIMIT_PER_MIN`); background jobs use FastAPI BackgroundTasks (swap for Celery/RQ at scale). Add authentication before any public deployment.
