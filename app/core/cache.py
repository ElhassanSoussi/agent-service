"""
SQLite-backed cache for tool outputs.
Supports TTL, max entries, and automatic cleanup.
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.db.database import SessionLocal, engine, Base
from sqlalchemy import Column, Text, Integer, Index, text

logger = logging.getLogger(__name__)

# Cache configuration
DEFAULT_TTL_SECONDS = 3600  # 1 hour
MAX_CACHE_ENTRIES = 5000
CLEANUP_BATCH_SIZE = 500


class CacheEntry(Base):
    """SQLite model for cache entries."""
    __tablename__ = "cache_entries"

    cache_key = Column(Text, primary_key=True, index=True)
    tool_name = Column(Text, nullable=False, index=True)
    output_json = Column(Text, nullable=False)
    created_at = Column(Integer, nullable=False, index=True)  # Unix timestamp
    ttl_seconds = Column(Integer, nullable=False, default=DEFAULT_TTL_SECONDS)
    expires_at = Column(Integer, nullable=False, index=True)  # Unix timestamp

    __table_args__ = (
        Index("ix_cache_expires", "expires_at"),
    )


def _create_cache_table():
    """Create cache table if it doesn't exist."""
    CacheEntry.__table__.create(bind=engine, checkfirst=True)


def _compute_cache_key(tool_name: str, input_data: dict[str, Any]) -> str:
    """Compute SHA256 cache key from tool name and normalized input."""
    # Sort keys for consistent hashing
    normalized = json.dumps({"tool": tool_name, "input": input_data}, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


def _sanitize_output(output: dict[str, Any]) -> dict[str, Any]:
    """Remove any sensitive data from output before caching."""
    # Create a copy to avoid modifying original
    sanitized = output.copy()
    
    # Remove any keys that might contain secrets
    sensitive_keys = ["headers", "api_key", "authorization", "token", "secret", "password"]
    for key in list(sanitized.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            del sanitized[key]
    
    return sanitized


class ToolCache:
    """Cache manager for tool outputs."""
    
    def __init__(self):
        _create_cache_table()
    
    def get(self, tool_name: str, input_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Get cached output for a tool call.
        Returns None if not found or expired.
        """
        cache_key = _compute_cache_key(tool_name, input_data)
        now = int(time.time())
        
        db = SessionLocal()
        try:
            entry = db.query(CacheEntry).filter(
                CacheEntry.cache_key == cache_key,
                CacheEntry.expires_at > now
            ).first()
            
            if entry:
                logger.debug(f"cache_hit tool={tool_name} key={cache_key[:16]}")
                return json.loads(entry.output_json)
            
            logger.debug(f"cache_miss tool={tool_name} key={cache_key[:16]}")
            return None
        finally:
            db.close()
    
    def set(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        output: dict[str, Any],
        ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> None:
        """
        Store tool output in cache.
        Sanitizes output before storing.
        """
        cache_key = _compute_cache_key(tool_name, input_data)
        now = int(time.time())
        expires_at = now + ttl_seconds
        
        # Sanitize output
        sanitized = _sanitize_output(output)
        output_json = json.dumps(sanitized)
        
        db = SessionLocal()
        try:
            # Upsert (SQLite doesn't have native upsert, so delete + insert)
            db.query(CacheEntry).filter(CacheEntry.cache_key == cache_key).delete()
            
            entry = CacheEntry(
                cache_key=cache_key,
                tool_name=tool_name,
                output_json=output_json,
                created_at=now,
                ttl_seconds=ttl_seconds,
                expires_at=expires_at,
            )
            db.add(entry)
            db.commit()
            
            logger.debug(f"cache_set tool={tool_name} key={cache_key[:16]} ttl={ttl_seconds}")
            
            # Opportunistic cleanup
            self._cleanup_if_needed(db)
        finally:
            db.close()
    
    def _cleanup_if_needed(self, db) -> int:
        """Remove expired entries and enforce max entries limit."""
        try:
            now = int(time.time())
            
            # Delete expired entries
            expired_count = db.query(CacheEntry).filter(
                CacheEntry.expires_at <= now
            ).delete()
            
            if expired_count > 0:
                logger.info(f"cache_cleanup expired={expired_count}")
            
            # Check total count
            total = db.query(CacheEntry).count()
            
            if total > MAX_CACHE_ENTRIES:
                # Delete oldest entries
                to_delete = total - MAX_CACHE_ENTRIES + CLEANUP_BATCH_SIZE
                oldest = db.query(CacheEntry.cache_key).order_by(
                    CacheEntry.created_at
                ).limit(to_delete).subquery()
                
                deleted = db.query(CacheEntry).filter(
                    CacheEntry.cache_key.in_(oldest)
                ).delete(synchronize_session=False)
                
                logger.info(f"cache_cleanup_overflow deleted={deleted}")
            
            db.commit()
            return expired_count
        except Exception as e:
            logger.warning(f"cache_cleanup_error error_type={type(e).__name__}")
            db.rollback()
            return 0
    
    def invalidate(self, tool_name: str, input_data: dict[str, Any]) -> bool:
        """Invalidate a specific cache entry."""
        cache_key = _compute_cache_key(tool_name, input_data)
        
        db = SessionLocal()
        try:
            deleted = db.query(CacheEntry).filter(
                CacheEntry.cache_key == cache_key
            ).delete()
            db.commit()
            return deleted > 0
        finally:
            db.close()
    
    def clear_tool(self, tool_name: str) -> int:
        """Clear all cache entries for a tool."""
        db = SessionLocal()
        try:
            deleted = db.query(CacheEntry).filter(
                CacheEntry.tool_name == tool_name
            ).delete()
            db.commit()
            logger.info(f"cache_clear tool={tool_name} deleted={deleted}")
            return deleted
        finally:
            db.close()
    
    def clear_all(self) -> int:
        """Clear entire cache."""
        db = SessionLocal()
        try:
            deleted = db.query(CacheEntry).delete()
            db.commit()
            logger.info(f"cache_clear_all deleted={deleted}")
            return deleted
        finally:
            db.close()


# Global cache instance
tool_cache = ToolCache()
