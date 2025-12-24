"""
Memory management for Xone.

Long-term memory storage and retrieval for the AI agent.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import XoneMemory

logger = logging.getLogger(__name__)


def store_memory(content: str, category: str = "other") -> str:
    """
    Store a new memory.

    Args:
        content: What to remember
        category: Category (insight, preference, decision, fact, other)

    Returns:
        Memory ID
    """
    db = SessionLocal()
    try:
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        memory = XoneMemory(
            id=memory_id,
            content=content,
            category=category,
            created_at=now,
            accessed_count=0,
        )

        db.add(memory)
        db.commit()

        logger.info(f"memory_stored id={memory_id} category={category} length={len(content)}")
        return memory_id

    finally:
        db.close()


def retrieve_memories(
    category: Optional[str] = None,
    limit: int = 10,
    search_term: Optional[str] = None
) -> List[dict]:
    """
    Retrieve memories.

    Args:
        category: Filter by category (optional)
        limit: Max number of memories to return
        search_term: Search for term in content (optional)

    Returns:
        List of memory dicts
    """
    db = SessionLocal()
    try:
        query = db.query(XoneMemory)

        if category:
            query = query.filter(XoneMemory.category == category)

        if search_term:
            query = query.filter(XoneMemory.content.like(f"%{search_term}%"))

        # Order by most recently created
        query = query.order_by(XoneMemory.created_at.desc())
        query = query.limit(limit)

        memories = query.all()

        # Update access count
        now = datetime.now(timezone.utc).isoformat()
        for mem in memories:
            mem.accessed_count += 1
            mem.last_accessed_at = now

        db.commit()

        result = [
            {
                "id": mem.id,
                "content": mem.content,
                "category": mem.category,
                "created_at": mem.created_at,
                "accessed_count": mem.accessed_count,
            }
            for mem in memories
        ]

        logger.info(f"memories_retrieved count={len(result)} category={category}")
        return result

    finally:
        db.close()


def get_relevant_memories(context: str, limit: int = 5) -> str:
    """
    Get memories relevant to current context.

    For now, this is a simple keyword-based search.
    In future, could use embeddings for semantic search.

    Args:
        context: Current conversation context
        limit: Max memories to retrieve

    Returns:
        Formatted string of relevant memories
    """
    # Simple keyword extraction (first 5 words)
    keywords = context.lower().split()[:10]

    all_memories = []

    # Search for each keyword
    db = SessionLocal()
    try:
        for keyword in keywords:
            if len(keyword) < 3:  # Skip short words
                continue

            memories = db.query(XoneMemory).filter(
                XoneMemory.content.like(f"%{keyword}%")
            ).limit(2).all()

            all_memories.extend(memories)

        # Deduplicate and limit
        seen = set()
        unique_memories = []
        for mem in all_memories:
            if mem.id not in seen:
                seen.add(mem.id)
                unique_memories.append(mem)
                # Update access count
                mem.accessed_count += 1
                mem.last_accessed_at = datetime.now(timezone.utc).isoformat()

        unique_memories = unique_memories[:limit]
        db.commit()

        if not unique_memories:
            return ""

        # Format as context
        formatted = "Relevant memories:\n"
        for mem in unique_memories:
            formatted += f"- [{mem.category}] {mem.content}\n"

        logger.info(f"relevant_memories_retrieved count={len(unique_memories)}")
        return formatted

    finally:
        db.close()


def delete_memory(memory_id: str) -> bool:
    """
    Delete a memory by ID.

    Args:
        memory_id: Memory ID to delete

    Returns:
        True if deleted, False if not found
    """
    db = SessionLocal()
    try:
        memory = db.query(XoneMemory).filter(XoneMemory.id == memory_id).first()

        if not memory:
            return False

        db.delete(memory)
        db.commit()

        logger.info(f"memory_deleted id={memory_id}")
        return True

    finally:
        db.close()


def get_memory_stats() -> dict:
    """
    Get statistics about stored memories.

    Returns:
        Dict with memory stats
    """
    db = SessionLocal()
    try:
        total = db.query(XoneMemory).count()

        by_category = {}
        categories = ["insight", "preference", "decision", "fact", "other"]
        for cat in categories:
            count = db.query(XoneMemory).filter(XoneMemory.category == cat).count()
            by_category[cat] = count

        return {
            "total": total,
            "by_category": by_category,
        }

    finally:
        db.close()
