"""Database models. Geometry is stored as GeoJSON (JSON) so the app runs on SQLite
and PostgreSQL alike; database/schema.sql adds real PostGIS geometry columns via triggers."""
import datetime as dt
import os

from sqlalchemy import (JSON, Column, Date, DateTime, Float, ForeignKey, Index,
                        Integer, String, Text, create_engine)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agrivision.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def now():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=now)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(160), nullable=False)
    created_at = Column(DateTime, default=now)


class StudyArea(Base):
    __tablename__ = "study_areas"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(160), nullable=False)
    geometry = Column(JSON, nullable=False)
    area_km2 = Column(Float, nullable=False)
    created_at = Column(DateTime, default=now)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id = Column(String(32), primary_key=True)
    study_area_id = Column(Integer, ForeignKey("study_areas.id"), nullable=False)
    status = Column(String(20), default="queued")
    progress = Column(Integer, default=0)
    params = Column(JSON)
    error = Column(Text)
    aoi_hash = Column(String(40))
    created_at = Column(DateTime, default=now)
    finished_at = Column(DateTime)


class Parcel(Base):
    __tablename__ = "parcels"
    id = Column(Integer, primary_key=True)
    job_id = Column(String(32), ForeignKey("analysis_jobs.id"), nullable=False)
    parcel_id = Column(String(20), nullable=False)
    geometry = Column(JSON, nullable=False)
    area_ha = Column(Float, nullable=False)
    centroid_lon = Column(Float)
    centroid_lat = Column(Float)
    __table_args__ = (Index("ix_parcels_job_parcel", "job_id", "parcel_id"),)


class CropPrediction(Base):
    __tablename__ = "crop_predictions"
    id = Column(Integer, primary_key=True)
    job_id = Column(String(32), ForeignKey("analysis_jobs.id"), nullable=False)
    parcel_id = Column(String(20), nullable=False)
    year = Column(Integer, nullable=False)
    crop_type = Column(String(40), nullable=False)
    confidence = Column(Float, nullable=False)
    confidence_level = Column(String(10), nullable=False)
    probabilities = Column(JSON)
    features = Column(JSON)
    explanation = Column(JSON)
    model_version = Column(String(40))
    date = Column(Date)
    __table_args__ = (Index("ix_pred_job_year", "job_id", "year"),)


class HistoricalResult(Base):
    __tablename__ = "historical_results"
    id = Column(Integer, primary_key=True)
    job_id = Column(String(32), ForeignKey("analysis_jobs.id"), nullable=False)
    year = Column(Integer, nullable=False)
    stats = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=now)


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    job_id = Column(String(32), ForeignKey("analysis_jobs.id"), nullable=False)
    file_path = Column(Text, nullable=False)
    format = Column(String(10), default="pdf")
    period_a = Column(Integer)
    period_b = Column(Integer)
    created_at = Column(DateTime, default=now)


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
