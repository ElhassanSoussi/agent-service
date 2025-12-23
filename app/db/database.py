"""
SQLite database engine and session management.
Database path: data/jobs.db (relative to project root).
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database path - relative to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "jobs.db"

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite connection string
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create engine with check_same_thread=False for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # No SQL logging (security)
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Get a database session. Use as context manager."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from app.db.models import (
        Job, AgentStep, Tenant, ApiKey, UsageDaily, Memory, Feedback,
        ActionBatch, BatchAction, AuditLog  # Phase A1
    )  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Run migrations to add any missing columns
    run_migrations()


def run_migrations():
    """
    Run simple migrations for schema changes.
    Adds missing columns to existing tables.
    """
    import sqlite3
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    
    # Add tenant_id to jobs if missing
    cursor.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in cursor.fetchall()]
    if "tenant_id" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN tenant_id TEXT")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_jobs_tenant_created ON jobs(tenant_id, created_at)")
    
    # Add artifact columns to jobs if missing (Phase 14)
    if "artifact_path" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN artifact_path TEXT")
    if "artifact_name" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN artifact_name TEXT")
    if "artifact_size_bytes" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN artifact_size_bytes INTEGER")
    if "artifact_sha256" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN artifact_sha256 TEXT")
    if "builder_template" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN builder_template TEXT")
    if "builder_project_name" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN builder_project_name TEXT")
    
    # Add repo builder columns (Phase 15)
    if "repo_url" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN repo_url TEXT")
    if "repo_ref" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN repo_ref TEXT")
    if "patch_artifact_path" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN patch_artifact_path TEXT")
    if "patch_sha256" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN patch_sha256 TEXT")
    if "patch_size_bytes" not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN patch_size_bytes INTEGER")
    
    conn.commit()
    conn.close()
