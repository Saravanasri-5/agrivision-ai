-- AgriVision AI - PostgreSQL + PostGIS schema (auto-loaded by docker-compose).
-- Column names match backend/app/db.py. GeoJSON is the source of truth (jsonb);
-- triggers maintain a native PostGIS `geom` column for spatial SQL and GiST indexes.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL, name VARCHAR(120) NOT NULL,
  created_at TIMESTAMP DEFAULT now());

CREATE TABLE IF NOT EXISTS projects (
  id SERIAL PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id), name VARCHAR(160) NOT NULL,
  created_at TIMESTAMP DEFAULT now());

CREATE TABLE IF NOT EXISTS study_areas (
  id SERIAL PRIMARY KEY, project_id INT NOT NULL REFERENCES projects(id), name VARCHAR(160) NOT NULL,
  geometry JSONB NOT NULL, area_km2 DOUBLE PRECISION NOT NULL, created_at TIMESTAMP DEFAULT now(),
  geom geometry(Polygon, 4326));

CREATE TABLE IF NOT EXISTS analysis_jobs (
  id VARCHAR(32) PRIMARY KEY, study_area_id INT NOT NULL REFERENCES study_areas(id),
  status VARCHAR(20) DEFAULT 'queued', progress INT DEFAULT 0, params JSONB, error TEXT,
  aoi_hash VARCHAR(40), created_at TIMESTAMP DEFAULT now(), finished_at TIMESTAMP);

CREATE TABLE IF NOT EXISTS parcels (
  id SERIAL PRIMARY KEY, job_id VARCHAR(32) NOT NULL REFERENCES analysis_jobs(id), parcel_id VARCHAR(20) NOT NULL,
  geometry JSONB NOT NULL, area_ha DOUBLE PRECISION NOT NULL, centroid_lon DOUBLE PRECISION,
  centroid_lat DOUBLE PRECISION, geom geometry(Polygon, 4326));
CREATE INDEX IF NOT EXISTS ix_parcels_job_parcel ON parcels(job_id, parcel_id);
CREATE INDEX IF NOT EXISTS ix_parcels_geom ON parcels USING GIST(geom);

CREATE TABLE IF NOT EXISTS crop_predictions (
  id SERIAL PRIMARY KEY, job_id VARCHAR(32) NOT NULL REFERENCES analysis_jobs(id), parcel_id VARCHAR(20) NOT NULL,
  year INT NOT NULL, crop_type VARCHAR(40) NOT NULL, confidence DOUBLE PRECISION NOT NULL,
  confidence_level VARCHAR(10) NOT NULL, probabilities JSONB, features JSONB, explanation JSONB,
  model_version VARCHAR(40), date DATE);
CREATE INDEX IF NOT EXISTS ix_pred_job_year ON crop_predictions(job_id, year);

CREATE TABLE IF NOT EXISTS historical_results (
  id SERIAL PRIMARY KEY, job_id VARCHAR(32) NOT NULL REFERENCES analysis_jobs(id), year INT NOT NULL,
  stats JSONB NOT NULL, created_at TIMESTAMP DEFAULT now());

CREATE TABLE IF NOT EXISTS reports (
  id SERIAL PRIMARY KEY, job_id VARCHAR(32) NOT NULL REFERENCES analysis_jobs(id), file_path TEXT NOT NULL,
  format VARCHAR(10) DEFAULT 'pdf', period_a INT, period_b INT, created_at TIMESTAMP DEFAULT now());

CREATE OR REPLACE FUNCTION sync_geom() RETURNS trigger AS $$
BEGIN
  NEW.geom := ST_SetSRID(ST_GeomFromGeoJSON(NEW.geometry::text), 4326);
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_parcels_geom ON parcels;
CREATE TRIGGER trg_parcels_geom BEFORE INSERT OR UPDATE ON parcels FOR EACH ROW EXECUTE FUNCTION sync_geom();
DROP TRIGGER IF EXISTS trg_study_geom ON study_areas;
CREATE TRIGGER trg_study_geom BEFORE INSERT OR UPDATE ON study_areas FOR EACH ROW EXECUTE FUNCTION sync_geom();
